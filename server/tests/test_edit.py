"""What the wearer can change from the dashboard: the count, the weight, and whether a set is shown."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import coach
from app.main import app

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures"
CURL_A, CURL_B = "00004-a956cd", "00007-130966"       # two real curl sets, 6 reps each
UNKNOWN = "99999-abcdef"
T0 = 1794300000


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.SET_DIR", tmp_path / "sets")
    monkeypatch.setattr("app.db.DB_PATH", tmp_path / "test.db")


def upload(set_id, **meta_changes):
    meta = {**json.loads((FIXTURES / f"{set_id}.json").read_text()), "exercise": "curl", **meta_changes}
    return client.post("/sets", content=(FIXTURES / f"{set_id}.bin").read_bytes(),
                       headers={"X-Token": "dev-token", "X-Set-Meta": json.dumps(meta)})


def one(set_id=CURL_A):
    return client.get(f"/sets/{set_id}").json()


# ---- correcting the count

def test_a_corrected_count_is_what_is_shown_and_the_counters_is_kept():
    assert upload(CURL_A).json()["reps"] == 6
    body = client.put(f"/sets/{CURL_A}/reps", json={"reps": 7}).json()
    assert (body["reps"], body["counted"], body["reps_fixed"]) == (7, 6, 7)
    assert client.get("/sets").json()[0]["reps"] == 7
    workout = client.get("/workouts").json()[0]
    assert workout["reps"] == 7 and workout["exercises"][0]["sets"][0]["reps"] == 7


def test_clearing_a_correction_goes_back_to_the_counter():
    upload(CURL_A)
    client.put(f"/sets/{CURL_A}/reps", json={"reps": 7})
    body = client.put(f"/sets/{CURL_A}/reps", json={"reps": None}).json()
    assert (body["reps"], body["counted"], body["reps_fixed"]) == (6, 6, None)


def test_a_correction_to_zero_is_a_real_answer_not_no_answer():
    upload(CURL_A)
    assert client.put(f"/sets/{CURL_A}/reps", json={"reps": 0}).json()["reps"] == 0


def test_a_correction_survives_changing_the_exercise():
    # The recount replaces the counter's number, not the wearer's.
    upload(CURL_A)
    client.put(f"/sets/{CURL_A}/reps", json={"reps": 7})
    body = client.put(f"/sets/{CURL_A}/exercise", json={"exercise": "row"}).json()
    assert body["reps"] == 7 and body["exercise"] == "row"


def test_the_pace_still_comes_from_what_the_counter_found():
    upload(CURL_A)
    before = one()["gaps"]
    client.put(f"/sets/{CURL_A}/reps", json={"reps": 9})
    assert one()["gaps"] == before and len(before) == 5


@pytest.mark.parametrize("reps", [-1, 201, 2.5, "six"])
def test_an_impossible_count_is_refused(reps):
    upload(CURL_A)
    assert client.put(f"/sets/{CURL_A}/reps", json={"reps": reps}).status_code == 422
    assert one()["reps_fixed"] is None


# ---- weight

def test_a_weight_is_saved_and_can_be_cleared():
    upload(CURL_A)
    assert client.put(f"/sets/{CURL_A}/weight", json={"weight": 27.5}).json()["weight"] == 27.5
    assert client.put(f"/sets/{CURL_A}/weight", json={"weight": None}).json()["weight"] is None


@pytest.mark.parametrize("weight", [0, -5, 1000.5, "heavy"])
def test_an_impossible_weight_is_refused(weight):
    upload(CURL_A)
    assert client.put(f"/sets/{CURL_A}/weight", json={"weight": weight}).status_code == 422
    assert one()["weight"] is None


def test_a_set_is_offered_the_weight_last_used_for_its_exercise():
    upload(CURL_A, started_at=T0)
    upload(CURL_B, started_at=T0 + 90)
    assert one(CURL_B)["last_weight"] is None
    client.put(f"/sets/{CURL_A}/weight", json={"weight": 25})
    assert one(CURL_B)["last_weight"] == 25
    assert one(CURL_A)["last_weight"] is None           # its own weight is not "the last one"


def test_the_offer_is_only_from_the_same_exercise():
    upload(CURL_A, started_at=T0)
    upload(CURL_B, started_at=T0 + 90, exercise="row")
    client.put(f"/sets/{CURL_A}/weight", json={"weight": 25})
    assert one(CURL_B)["last_weight"] is None


def test_with_a_weight_the_suggestion_names_a_number():
    upload(CURL_A, started_at=T0)
    upload(CURL_B, started_at=T0 + 90)
    plain = client.get("/workouts").json()[0]["exercises"][0]["suggestion"]
    client.put(f"/sets/{CURL_B}/weight", json={"weight": 25})
    with_weight = client.get("/workouts").json()[0]["exercises"][0]
    assert with_weight["suggestion"]["kind"] == plain["kind"]
    assert "25" in with_weight["suggestion"]["text"] or "27.5" in with_weight["suggestion"]["text"]
    assert with_weight["sets"][1]["weight"] == 25 and with_weight["sets"][0]["weight"] is None


@pytest.mark.parametrize("kind, weight, text", [
    ("more", 25, "That looked easy. Try 27.5 lb next time."),
    ("stay", 25, "Good effort. Stay at 25 lb."),
    ("less", 25, "Tough from the first set. Try 22.5 lb."),
    ("more", 47.5, "That looked easy. Try 50 lb next time."),
    ("more", 50, "That looked easy. Try 55 lb next time."),       # heavier loads move in 5s
    ("less", 135, "Tough from the first set. Try 130 lb."),
    ("more", None, coach.SUGGESTIONS["more"]),
    ("less", 2.5, coach.SUGGESTIONS["less"]),                       # never suggests 0 lb
])
def test_the_wording_of_a_suggestion(kind, weight, text):
    assert coach.sentence(kind, weight) == text


# ---- removing a set

def test_a_removed_set_leaves_the_dashboard_but_not_the_disk(tmp_path):
    upload(CURL_A, started_at=T0)
    upload(CURL_B, started_at=T0 + 90)
    body = client.delete(f"/sets/{CURL_A}").json()
    assert body["removed_at"] is not None
    assert [s["set_id"] for s in client.get("/sets").json()] == [CURL_B]
    workout = client.get("/workouts").json()[0]
    assert workout["sets"] == 1 and workout["reps"] == 6
    assert (tmp_path / "sets" / f"{CURL_A}.bin").exists() and (tmp_path / "sets" / f"{CURL_A}.json").exists()


def test_a_removed_set_can_be_put_back_with_everything_it_had():
    upload(CURL_A)
    client.put(f"/sets/{CURL_A}/reps", json={"reps": 7})
    client.put(f"/sets/{CURL_A}/weight", json={"weight": 25})
    client.delete(f"/sets/{CURL_A}")
    body = client.post(f"/sets/{CURL_A}/restore").json()
    assert (body["removed_at"], body["reps"], body["weight"]) == (None, 7, 25)
    assert len(client.get("/sets").json()) == 1


def test_the_watch_sending_a_removed_set_again_does_not_bring_it_back():
    # The receipt was lost, the wearer removed the set, the watch retries.
    upload(CURL_A)
    client.delete(f"/sets/{CURL_A}")
    again = upload(CURL_A)
    assert again.status_code == 201 and again.json()["stored"] is True      # so the watch can delete its copy
    assert client.get("/sets").json() == []


def test_a_removed_sets_weight_is_not_offered():
    upload(CURL_A, started_at=T0)
    upload(CURL_B, started_at=T0 + 90)
    client.put(f"/sets/{CURL_A}/weight", json={"weight": 25})
    client.delete(f"/sets/{CURL_A}")
    assert one(CURL_B)["last_weight"] is None


@pytest.mark.parametrize("call", [
    lambda: client.put(f"/sets/{UNKNOWN}/reps", json={"reps": 6}),
    lambda: client.put(f"/sets/{UNKNOWN}/weight", json={"weight": 25}),
    lambda: client.delete(f"/sets/{UNKNOWN}"),
    lambda: client.post(f"/sets/{UNKNOWN}/restore"),
    lambda: client.delete("/sets/..%2F..%2Fgymbuddy"),
], ids=["reps", "weight", "remove", "restore", "not an id"])
def test_an_unknown_set_is_404(call):
    assert call().status_code == 404


# ---- an older database

def test_a_database_from_before_these_columns_gets_them(tmp_path, monkeypatch):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE sets (set_id TEXT PRIMARY KEY, exercise TEXT, reps INTEGER, rep_times TEXT,"
                " duration_ms INTEGER NOT NULL, rate_hz REAL NOT NULL, late INTEGER NOT NULL,"
                " analysis_version INTEGER NOT NULL, received_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
    old.execute("INSERT INTO sets (set_id, exercise, reps, rep_times, duration_ms, rate_hz, late, analysis_version)"
                " VALUES ('00001-aaaaaa', 'curl', 5, '[1, 2, 3, 4, 5]', 9000, 100, 0, 1)")
    old.commit()
    old.close()
    monkeypatch.setattr("app.db.DB_PATH", path)
    row = client.get("/sets").json()[0]
    assert (row["reps"], row["counted"], row["weight"], row["removed_at"]) == (5, 5, None, None)
    assert client.put("/sets/00001-aaaaaa/weight", json={"weight": 20}).json()["weight"] == 20


# ---- progress

def row(set_id, exercise, reps, at, weight=None):
    return {"set_id": set_id, "exercise": exercise, "reps": reps, "rep_times": [], "duration_ms": 10000,
            "started_at": at, "received_at": "2026-11-10 00:00:00", "weight": weight}


LABELS = {"curl": "Curl", "row": "Row"}
DAY = 24 * 3600


def test_progress_follows_each_exercise_across_workouts_oldest_first():
    rows = [row("00001-aaaaaa", "curl", 6, T0), row("00002-aaaaaa", "curl", 5, T0 + 90, weight=20),
            row("00003-aaaaaa", "row", 8, T0 + 180),
            row("00004-aaaaaa", "curl", 7, T0 + DAY, weight=25), row("00005-aaaaaa", "curl", 7, T0 + DAY + 90, weight=22.5)]
    curl, rows_ = coach.progress(rows, LABELS)
    assert (curl["exercise"], curl["label"], curl["change"]) == ("curl", "Curl", 3)
    assert [(w["sets"], w["reps"], w["best"], w["weight"]) for w in curl["workouts"]] == [(2, 11, 6, 20), (2, 14, 7, 25)]
    assert curl["workouts"][0]["started_at"] == coach.iso(T0)
    assert (rows_["exercise"], rows_["change"], len(rows_["workouts"])) == ("row", None, 1)


def test_progress_leaves_out_sets_with_no_exercise_and_exercises_never_done():
    assert coach.progress([row("00001-aaaaaa", None, 6, T0)], LABELS) == []


def test_progress_over_the_api_uses_corrected_counts_and_skips_removed_sets():
    upload(CURL_A, started_at=T0)
    upload(CURL_B, started_at=T0 + DAY)
    client.put(f"/sets/{CURL_B}/reps", json={"reps": 9})
    curl = client.get("/progress").json()[0]
    assert [w["reps"] for w in curl["workouts"]] == [6, 9] and curl["change"] == 3
    client.delete(f"/sets/{CURL_B}")
    curl = client.get("/progress").json()[0]
    assert [w["reps"] for w in curl["workouts"]] == [6] and curl["change"] is None
