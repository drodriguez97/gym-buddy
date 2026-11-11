"""Health checks: the judging rules, then the two endpoints."""
import json

import pytest
from fastapi.testclient import TestClient

from app import health
from app.main import app

client = TestClient(app)
NOW = 1794300000
GOOD = {"accel_g": 1.0, "gyro_dps": 2.1, "rssi": -48, "watch_time": NOW, "battery_pct": 70,
        "battery_mv": 3860, "free_pct": 88, "sets_waiting": 0}
TOKEN = {"X-Token": "dev-token"}


@pytest.fixture(autouse=True)
def database(tmp_path, monkeypatch):
    monkeypatch.setattr("app.db.DB_PATH", tmp_path / "test.db")


def verdicts(report, received_at=NOW, now=NOW + 30):
    return {c["key"]: c for c in health.judge(report, received_at, now)}


# ---- the rules

def test_a_healthy_watch_passes_every_check():
    v = verdicts(GOOD)
    assert list(v) == ["seen", "sensor", "wifi", "clock", "battery", "storage", "waiting"]
    assert {c["status"] for c in v.values()} == {"ok"}
    assert health.summary(list(v.values())) == ("ok", "Everything is working")


def test_values_are_written_for_people():
    v = verdicts(GOOD)
    assert v["sensor"]["value"] == "1.00 g at rest" and v["wifi"]["value"] == "Strong (-48 dBm)"
    assert v["battery"]["value"] == "70% (3.86 V)" and v["storage"]["value"] == "88% free"
    assert v["clock"]["value"] == "0 s off" and v["seen"]["value"] == "Just now"


@pytest.mark.parametrize("accel", [0.85, 1.2, 0.0])
def test_a_sensor_that_does_not_read_one_g_at_rest_fails(accel):
    v = verdicts({**GOOD, "accel_g": accel})
    assert v["sensor"]["status"] == "fail" and v["sensor"]["help"]


def test_a_moving_watch_is_a_warning_not_a_broken_sensor():
    # Shaking it changes the reading, but that is the user moving, so the advice is to hold still.
    v = verdicts({**GOOD, "accel_g": 1.6, "gyro_dps": 140})
    assert v["sensor"]["status"] == "warn" and v["sensor"]["value"] == "Moving"
    assert "still" in v["sensor"]["help"]


def test_weak_wifi_is_a_warning():
    v = verdicts({**GOOD, "rssi": -82})
    assert v["wifi"]["status"] == "warn" and v["wifi"]["value"] == "Weak (-82 dBm)"
    assert verdicts({**GOOD, "rssi": -75})["wifi"]["status"] == "ok"        # the limit itself is fine


def test_a_clock_more_than_five_seconds_off_fails():
    assert verdicts({**GOOD, "watch_time": NOW + 5})["clock"]["status"] == "ok"
    late = verdicts({**GOOD, "watch_time": NOW - 4000})["clock"]
    assert late["status"] == "fail" and late["value"] == "67 min off"


def test_a_clock_that_was_never_set_is_a_warning():
    v = verdicts({**GOOD, "watch_time": None})
    assert v["clock"]["status"] == "warn" and v["clock"]["value"] == "Not set"


def test_low_battery_and_low_storage_are_warnings():
    assert verdicts({**GOOD, "battery_pct": 19})["battery"]["status"] == "warn"
    assert verdicts({**GOOD, "battery_pct": 20})["battery"]["status"] == "ok"
    assert verdicts({**GOOD, "free_pct": 9})["storage"]["status"] == "warn"


def test_sets_left_on_the_watch_are_a_warning():
    v = verdicts({**GOOD, "sets_waiting": 3})
    assert v["waiting"]["status"] == "warn" and v["waiting"]["value"] == "3"


def test_an_old_report_is_a_warning():
    v = verdicts(GOOD, received_at=NOW, now=NOW + 2 * 86400)
    assert v["seen"]["status"] == "warn" and v["seen"]["value"] == "2 days ago"


def test_a_number_the_watch_did_not_send_is_never_a_pass():
    v = verdicts({})
    assert [c["status"] for c in v.values()][1:] == ["warn"] * 6
    v = verdicts({**GOOD, "battery_pct": "70", "rssi": True})              # the wrong type is no reading either
    assert v["battery"]["status"] == "warn" and v["wifi"]["status"] == "warn"


def test_the_summary_counts_what_needs_attention():
    one = list(verdicts({**GOOD, "battery_pct": 5}).values())
    assert health.summary(one) == ("warn", "One thing to check")
    two = list(verdicts({**GOOD, "battery_pct": 5, "accel_g": 0.5}).values())
    assert health.summary(two) == ("fail", "2 things to check")


# ---- the endpoints

def test_before_any_report_the_page_is_told_so():
    body = client.get("/watch/health").json()
    assert body == {"seen": False, "status": "warn", "summary": "No report from the watch yet", "checks": []}


def test_a_report_is_stored_and_comes_back_judged():
    import time
    report = {**GOOD, "watch_time": int(time.time())}
    posted = client.post("/watch/health", content=json.dumps(report), headers=TOKEN)
    assert posted.status_code == 201 and posted.json()["stored"] is True
    assert abs(posted.json()["server_time"] - time.time()) < 5
    body = client.get("/watch/health").json()
    assert body["seen"] is True and body["status"] == "ok" and body["summary"] == "Everything is working"
    assert [c["key"] for c in body["checks"]] == ["seen", "sensor", "wifi", "clock", "battery", "storage", "waiting"]


def test_the_newest_report_wins():
    import time
    client.post("/watch/health", content=json.dumps({**GOOD, "watch_time": int(time.time())}), headers=TOKEN)
    client.post("/watch/health", content=json.dumps({**GOOD, "watch_time": int(time.time()), "battery_pct": 4}),
                headers=TOKEN)
    body = client.get("/watch/health").json()
    assert body["summary"] == "One thing to check"
    assert [c["status"] for c in body["checks"] if c["key"] == "battery"] == ["warn"]


def test_a_report_needs_the_token():
    assert client.post("/watch/health", content=json.dumps(GOOD)).status_code == 401
    assert client.post("/watch/health", content=json.dumps(GOOD), headers={"X-Token": "wrong"}).status_code == 401
    assert client.get("/watch/health").json()["seen"] is False


@pytest.mark.parametrize("body", ["not json", "[1, 2]", ""])
def test_a_report_that_is_not_a_json_object_is_refused(body):
    assert client.post("/watch/health", content=body, headers=TOKEN).status_code == 422
    assert client.get("/watch/health").json()["seen"] is False
