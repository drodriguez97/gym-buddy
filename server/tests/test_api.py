import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

FIXTURES = Path(__file__).parent / "fixtures"
SET_ID = "00004-a956cd"                          # a real set from the watch: 6 curls
SET_BIN = (FIXTURES / f"{SET_ID}.bin").read_bytes()
SET_META = json.loads((FIXTURES / f"{SET_ID}.json").read_text())
HEADERS = {"X-Token": "dev-token", "X-Set-Meta": json.dumps(SET_META)}


# Each rejection test also checks the error message, so it fails if the
# request was turned away for some other reason (a wrong token, say)
# instead of for the problem the test is about.


@pytest.fixture(autouse=True)
def folder(tmp_path, tmp_path_factory, monkeypatch):
    # Every test gets its own empty folder and its own empty database; the real
    # data/ is never touched.
    monkeypatch.setattr("app.main.SET_DIR", tmp_path)
    monkeypatch.setattr("app.db.DB_PATH", tmp_path_factory.mktemp("db") / "test.db")
    return tmp_path


def upload(body=SET_BIN, headers=HEADERS):
    return client.post("/sets", content=body, headers=headers)


def with_meta(**changes):
    # The good headers, with some fields of the set's .json replaced.
    return {**HEADERS, "X-Set-Meta": json.dumps({**SET_META, **changes})}


def test_get_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_upload_saves_both_files_and_returns_the_receipt(folder):
    response = upload(headers=with_meta(exercise="curl"))
    assert response.status_code == 201
    assert response.json() == {"set_id": SET_ID, "stored": True, "reps": 6}
    assert (folder / f"{SET_ID}.bin").read_bytes() == SET_BIN
    assert json.loads((folder / f"{SET_ID}.json").read_text()) == {**SET_META, "exercise": "curl"}


def test_same_upload_twice_gives_the_same_receipt(folder):
    # The watch retries when a receipt gets lost, so a repeat must be harmless.
    first, second = upload(), upload()
    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert sorted(p.name for p in folder.iterdir()) == [f"{SET_ID}.bin", f"{SET_ID}.json"]


@pytest.mark.parametrize("token", ["wrong-token", None])
def test_wrong_or_missing_token_is_401_and_saves_nothing(folder, token):
    headers = {"X-Set-Meta": HEADERS["X-Set-Meta"]}
    if token is not None:
        headers["X-Token"] = token
    response = upload(headers=headers)
    assert response.status_code == 401
    assert list(folder.iterdir()) == []


@pytest.mark.parametrize("meta", ["not json", "[1, 2, 3]", None])
def test_meta_that_is_not_a_json_object_is_422(folder, meta):
    headers = {"X-Token": "dev-token"}
    if meta is not None:
        headers["X-Set-Meta"] = meta
    response = upload(headers=headers)
    assert response.status_code == 422
    assert "X-Set-Meta" in response.json()["detail"]
    assert list(folder.iterdir()) == []


@pytest.mark.parametrize("set_id", ["../evil", "../../app/main", "00004", "00004-A956CD", 4])
def test_bad_set_id_is_422_and_saves_nothing(folder, set_id):
    # set_id becomes a file name, so anything but the watch's exact format is refused.
    response = upload(headers=with_meta(set_id=set_id))
    assert response.status_code == 422
    assert response.json()["detail"] == "bad set_id"
    assert list(folder.iterdir()) == []


def test_cut_off_upload_is_422_and_saves_nothing(folder):
    # A Wi-Fi drop mid-upload: the last reading never arrived.
    response = upload(body=SET_BIN[:-12])
    assert response.status_code == 422
    assert "readings" in response.json()["detail"]
    assert list(folder.iterdir()) == []


@pytest.mark.parametrize("count", [None, "1990", 0])
def test_missing_or_wrong_count_is_422(folder, count):
    response = upload(headers=with_meta(count=count))
    assert response.status_code == 422
    assert "readings" in response.json()["detail"]
    assert list(folder.iterdir()) == []


def test_empty_body_is_422(folder):
    response = upload(body=b"", headers=with_meta(count=0))
    assert response.status_code == 422
    assert "readings" in response.json()["detail"]
    assert list(folder.iterdir()) == []


# ---- counting on upload, and the database

from app import db  # noqa: E402

CURL = with_meta(exercise="curl")


def test_an_uploaded_set_gets_a_row_with_its_count_and_rep_times():
    upload(headers=CURL)
    row = db.get_set(SET_ID)
    assert row["reps"] == 6 and row["exercise"] == "curl"
    assert row["rep_times"] == [4.7, 7.32, 9.73, 12.07, 14.8, 17.61]
    assert row["duration_ms"] == SET_META["duration_ms"] and row["late"] == SET_META["late"]
    assert row["analysis_version"] == 1 and row["received_at"]


def test_uploading_twice_keeps_one_row_and_the_first_count():
    first = upload(headers=CURL)
    second = upload(headers=with_meta(exercise="pullup"))      # same set, sent again with a different label
    assert first.json() == second.json() == {"set_id": SET_ID, "stored": True, "reps": 6}
    assert len(db.list_sets()) == 1 and db.get_set(SET_ID)["exercise"] == "curl"


@pytest.mark.parametrize("headers, body", [
    ({"X-Set-Meta": HEADERS["X-Set-Meta"]}, SET_BIN),            # no token
    (HEADERS, SET_BIN[:-12]),                                     # cut off
    (with_meta(set_id="../evil"), SET_BIN),                       # bad ID
], ids=["no token", "cut off", "bad id"])
def test_a_rejected_upload_leaves_no_row(headers, body):
    assert upload(body=body, headers=headers).status_code in (401, 422)
    assert db.list_sets() == []


def test_a_set_the_analyzer_cannot_count_is_still_stored_and_receipted(monkeypatch):
    # An analysis bug must never leave the watch holding a set it can't hand over.
    def broken(*args, **kwargs):
        raise RuntimeError("analysis bug")
    monkeypatch.setattr("app.main.count_reps", broken)
    response = upload(headers=CURL)
    assert response.status_code == 201
    assert response.json() == {"set_id": SET_ID, "stored": True, "reps": None}
    assert db.get_set(SET_ID)["reps"] is None and db.get_set(SET_ID)["rep_times"] == []


def test_files_that_arrived_before_the_database_get_a_row_on_the_next_upload(folder):
    # The raw files are there but the row is not (an older server, or a crash in between).
    (folder / f"{SET_ID}.bin").write_bytes(SET_BIN)
    (folder / f"{SET_ID}.json").write_text(json.dumps({**SET_META, "exercise": "curl"}))
    assert db.get_set(SET_ID) is None
    assert upload(headers=CURL).json()["reps"] == 6
    assert db.get_set(SET_ID)["reps"] == 6


def test_a_value_that_looks_like_sql_is_stored_as_plain_text():
    # Placeholders, not string-joining: this is data, and the table survives it.
    nasty = "curl'); DROP TABLE sets; --"
    upload(headers=with_meta(exercise=nasty))
    assert db.get_set(SET_ID)["exercise"] == nasty
    assert len(db.list_sets()) == 1


# ---- reading sets back

def test_get_sets_is_empty_before_anything_is_uploaded():
    response = client.get("/sets")
    assert response.status_code == 200 and response.json() == []


def test_get_sets_lists_newest_first():
    other_id = "00007-130966"
    other_meta = json.loads((FIXTURES / f"{other_id}.json").read_text())
    upload(headers=CURL)
    client.post("/sets", content=(FIXTURES / f"{other_id}.bin").read_bytes(),
                headers={"X-Token": "dev-token", "X-Set-Meta": json.dumps({**other_meta, "exercise": "curl"})})
    listed = client.get("/sets").json()
    assert [row["set_id"] for row in listed] == [other_id, SET_ID]
    assert [row["reps"] for row in listed] == [6, 6]


def test_get_one_set():
    upload(headers=CURL)
    response = client.get(f"/sets/{SET_ID}")
    assert response.status_code == 200
    assert response.json()["reps"] == 6 and len(response.json()["rep_times"]) == 6


@pytest.mark.parametrize("set_id", ["00099-ffffff", "nonsense", "..%2Fevil"])
def test_an_unknown_or_malformed_set_id_is_404(set_id):
    response = client.get(f"/sets/{set_id}")
    assert response.status_code == 404


# ---- correcting the exercise, and the page

PULLUPS = "00018-f6719e"                         # 6 pull-ups: only counts right when told it's a pull-up


def upload_fixture(set_id, **meta_changes):
    meta = {**json.loads((FIXTURES / f"{set_id}.json").read_text()), **meta_changes}
    return client.post("/sets", content=(FIXTURES / f"{set_id}.bin").read_bytes(),
                       headers={"X-Token": "dev-token", "X-Set-Meta": json.dumps(meta)})


def test_exercises_are_listed_in_the_watch_order():
    listed = client.get("/exercises").json()
    assert [e["name"] for e in listed] == ["curl", "shoulder_press", "chest_press", "row", "pullup", "pushup"]
    assert listed[0] == {"name": "curl", "label": "Curl"}


def test_changing_the_exercise_recounts_from_the_raw_file():
    upload_fixture(PULLUPS, exercise="curl")                     # the wrong exercise was picked on the watch
    response = client.put(f"/sets/{PULLUPS}/exercise", json={"exercise": "pullup"})
    assert response.status_code == 200
    assert response.json()["exercise"] == "pullup" and response.json()["reps"] == 6
    assert len(response.json()["rep_times"]) == 6
    assert db.get_set(PULLUPS)["reps"] == 6                      # saved, not just returned


def test_changing_the_exercise_leaves_the_raw_files_alone(folder):
    upload_fixture(PULLUPS, exercise="curl")
    before = (folder / f"{PULLUPS}.bin").read_bytes(), (folder / f"{PULLUPS}.json").read_text()
    client.put(f"/sets/{PULLUPS}/exercise", json={"exercise": "pullup"})
    assert ((folder / f"{PULLUPS}.bin").read_bytes(), (folder / f"{PULLUPS}.json").read_text()) == before


def test_an_exercise_that_is_not_on_the_list_is_refused():
    upload_fixture(PULLUPS, exercise="curl")
    response = client.put(f"/sets/{PULLUPS}/exercise", json={"exercise": "juggling"})
    assert response.status_code == 422 and response.json()["detail"] == "unknown exercise"
    assert db.get_set(PULLUPS)["exercise"] == "curl"


@pytest.mark.parametrize("set_id", ["00099-ffffff", "nonsense"])
def test_changing_the_exercise_of_an_unknown_set_is_404(set_id):
    assert client.put(f"/sets/{set_id}/exercise", json={"exercise": "curl"}).status_code == 404


def test_the_dashboard_page_is_served_at_the_root():
    response = client.get("/")
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/html")
    assert "<title>Gym Buddy</title>" in response.text


# ---- archiving: off the dashboard, never destroyed

def test_archiving_moves_the_files_and_removes_the_row_and_restoring_undoes_it(folder, monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location("archive_sets", Path(__file__).parents[1] / "scripts" / "archive_sets.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    monkeypatch.setattr(tool, "ARCHIVE", folder.parent / (folder.name + "_archive"))
    upload(headers=CURL)
    upload_fixture(PULLUPS, exercise="pullup")
    original = (folder / f"{SET_ID}.bin").read_bytes()

    assert tool.archive({4}) == [SET_ID]
    assert [row["set_id"] for row in client.get("/sets").json()] == [PULLUPS]
    assert not (folder / f"{SET_ID}.bin").exists()
    assert (tool.ARCHIVE / f"{SET_ID}.bin").read_bytes() == original       # moved, not deleted

    assert tool.restore({4}) == [SET_ID]
    assert (folder / f"{SET_ID}.bin").read_bytes() == original
    assert db.get_set(SET_ID)["reps"] == 6 and len(db.list_sets()) == 2
