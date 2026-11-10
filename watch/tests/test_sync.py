"""watch/sync.py against the real server code.

sync.py is loaded with fake network, config and time modules. Its HTTP calls go
straight into the FastAPI app from server/app/main.py (through TestClient), so
these tests fail if the watch and the server ever disagree about the upload
format. They can't check the watch's real Wi-Fi, memory or HTTP library.
"""
import importlib.util
import json
import shutil
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).parents[2]
FIXTURES = REPO / "server" / "tests" / "fixtures"
SETS = ["00004-a956cd", "00007-130966"]         # two real sets from the watch

sys.path.insert(0, str(REPO / "server"))
import app.main as server                       # noqa: E402


class Watch:
    """sync.py loaded on the laptop, with a folder standing in for /flash/sets."""

    def __init__(self, tmp_path, monkeypatch):
        self.flash = tmp_path / "flash_sets"
        self.flash.mkdir()
        self.server_dir = tmp_path / "server_sets"
        monkeypatch.setattr(server, "SET_DIR", self.server_dir)
        self.client = TestClient(server.app)
        self.wifi_available = True
        self.radio_on = False
        self.radio_was_on = False
        self.posts = []                         # set_id of every POST attempted
        self.waited_ms = 0
        self.token = "dev-token"
        self.post = self.post_to_server         # tests swap this to break the network
        self.sync = self._load()
        self.sync.SET_DIR = str(self.flash)

    def _load(self):
        watch = self

        class WLAN:
            def __init__(self, interface):
                pass

            def active(self, on):
                watch.radio_on = on
                watch.radio_was_on = watch.radio_was_on or on

            def isconnected(self):
                return watch.radio_on and watch.wifi_available

            def connect(self, ssid, password):
                pass

        clock = [0]

        def sleep_ms(ms):
            clock[0] += ms
            watch.waited_ms += ms

        fakes = {
            "network": types.SimpleNamespace(WLAN=WLAN, STA_IF=0),
            "config": types.SimpleNamespace(WIFI_SSID="home", WIFI_PASSWORD="pw",
                                            SERVER="http://server", TOKEN="dev-token"),
            "time": types.SimpleNamespace(ticks_ms=lambda: clock[0], sleep_ms=sleep_ms,
                                          ticks_diff=lambda a, b: a - b),
            "requests": types.SimpleNamespace(post=lambda url, data, headers: watch.post(url, data, headers)),
        }
        real = {name: sys.modules.get(name) for name in fakes}
        sys.modules.update(fakes)
        try:
            spec = importlib.util.spec_from_file_location("watch_sync", REPO / "watch" / "sync.py")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        finally:
            for name, old in real.items():
                if old is None:
                    del sys.modules[name]
                else:
                    sys.modules[name] = old
        return module

    def post_to_server(self, url, data, headers):
        self.posts.append(json.loads(headers["X-Set-Meta"])["set_id"])
        assert url == "http://server/sets"
        return self.client.post("/sets", content=data, headers={**headers, "X-Token": self.token})

    def record(self, set_id):
        # Put a real recorded set on the watch.
        for ext in (".bin", ".json"):
            shutil.copy(FIXTURES / (set_id + ext), self.flash / (set_id + ext))

    def on_watch(self):
        return sorted(p.name for p in self.flash.iterdir())

    def on_server(self):
        return sorted(p.name for p in self.server_dir.iterdir()) if self.server_dir.exists() else []


@pytest.fixture
def watch(tmp_path, monkeypatch):
    w = Watch(tmp_path, monkeypatch)
    for set_id in SETS:
        w.record(set_id)
    return w


class Reply:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body

    def json(self):
        if self.body is None:
            raise ValueError("not JSON")
        return self.body

    def close(self):
        pass


# ---- the normal case

def test_sync_uploads_every_set_and_deletes_them_from_the_watch(watch):
    assert watch.sync.sync() == (2, 0, None)
    assert watch.on_watch() == []
    assert watch.on_server() == sorted(s + ext for s in SETS for ext in (".bin", ".json"))
    for set_id in SETS:                         # the server's copy is byte-for-byte the recording
        assert (watch.server_dir / (set_id + ".bin")).read_bytes() == (FIXTURES / (set_id + ".bin")).read_bytes()
    assert watch.posts == SETS                  # oldest first


def test_wifi_is_off_again_after_a_sync(watch):
    watch.sync.sync()
    assert watch.radio_was_on and not watch.radio_on


def test_progress_is_reported_for_the_screen(watch):
    seen = []
    watch.sync.sync(seen.append)
    assert seen == ["joining Wi-Fi", "set 1 of 2", "set 2 of 2"]


def test_nothing_to_upload_never_turns_wifi_on(watch):
    for p in watch.flash.iterdir():
        p.unlink()
    assert watch.sync.sync() == (0, 0, None)
    assert not watch.radio_was_on


# ---- no receipt, no delete

def test_a_bare_200_is_not_a_receipt(watch):
    watch.post = lambda url, data, headers: Reply(200, {})
    assert watch.sync.sync() == (0, 2, "no receipt")
    assert len(watch.on_watch()) == 4


def test_a_receipt_for_another_set_is_not_a_receipt(watch):
    watch.post = lambda url, data, headers: Reply(201, {"set_id": "00099-ffffff", "stored": True})
    assert watch.sync.sync() == (0, 2, "no receipt")
    assert len(watch.on_watch()) == 4


def test_a_201_that_is_not_json_is_not_a_receipt(watch):
    watch.post = lambda url, data, headers: Reply(201, None)
    assert watch.sync.sync() == (0, 2, "no receipt")
    assert len(watch.on_watch()) == 4


def test_lost_receipt_then_retry_stores_the_set_once(watch):
    # First sync: the server stores the sets but the replies never arrive.
    def reply_lost(url, data, headers):
        watch.post_to_server(url, data, headers)
        raise OSError("connection dropped")
    watch.post = reply_lost
    assert watch.sync.sync() == (0, 2, "no server")
    assert len(watch.on_watch()) == 4 and len(watch.on_server()) == 2   # only the first set got through

    watch.post = watch.post_to_server
    assert watch.sync.sync() == (2, 0, None)
    assert watch.on_watch() == []
    assert len(watch.on_server()) == 4          # each set stored exactly once


# ---- things that go wrong

def test_no_wifi_keeps_everything_and_sends_nothing(watch):
    watch.wifi_available = False
    assert watch.sync.sync() == (0, 2, "no Wi-Fi")
    assert watch.posts == [] and len(watch.on_watch()) == 4
    assert not watch.radio_on


def test_unreachable_server_is_tried_three_times_then_gives_up(watch):
    attempts = []

    def down(url, data, headers):
        attempts.append(1)
        raise OSError("unreachable")
    watch.post = down
    assert watch.sync.sync() == (0, 2, "no server")
    assert len(attempts) == 3                   # the first set only; the rest would fail the same way
    assert watch.waited_ms == 2 * watch.sync.RETRY_WAIT_MS
    assert len(watch.on_watch()) == 4


def test_one_dropped_connection_is_retried(watch):
    calls = []

    def flaky(url, data, headers):
        calls.append(1)
        if len(calls) == 1:
            raise OSError("dropped")
        return watch.post_to_server(url, data, headers)
    watch.post = flaky
    assert watch.sync.sync() == (2, 0, None)
    assert watch.on_watch() == []


def test_wrong_token_stops_after_the_first_set(watch):
    watch.token = "wrong"
    assert watch.sync.sync() == (0, 2, "bad token")
    assert len(watch.posts) == 1
    assert len(watch.on_watch()) == 4 and watch.on_server() == []


def test_a_damaged_set_is_kept_and_the_others_still_upload(watch):
    damaged = watch.flash / (SETS[0] + ".bin")
    damaged.write_bytes(damaged.read_bytes()[:-12])     # lost its last reading
    assert watch.sync.sync() == (1, 1, "rejected")
    assert watch.on_watch() == [SETS[0] + ".bin", SETS[0] + ".json"]
    assert watch.on_server() == [SETS[1] + ".bin", SETS[1] + ".json"]


# ---- which files count as a set

def test_a_set_still_being_recorded_is_left_alone(watch):
    recording = watch.flash / "00031-abc123.bin"        # no .json yet: the recorder writes it last
    recording.write_bytes(b"\x00" * 120)
    assert watch.sync.sync() == (2, 0, None)
    assert watch.on_watch() == ["00031-abc123.bin"]
    assert "00031-abc123" not in watch.posts


def test_a_stray_json_from_a_cut_short_delete_is_cleaned_up(watch):
    (watch.flash / (SETS[0] + ".bin")).unlink()         # deleted after its receipt, then power was lost
    assert watch.sync.pending_sets() == [SETS[1]]
    assert watch.on_watch() == [SETS[1] + ".bin", SETS[1] + ".json"]
