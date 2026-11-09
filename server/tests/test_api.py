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
def folder(tmp_path, monkeypatch):
    # Every test gets its own empty folder; the real data/sets is never touched.
    monkeypatch.setattr("app.main.SET_DIR", tmp_path)
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
    response = upload()
    assert response.status_code == 201
    assert response.json() == {"set_id": SET_ID, "stored": True}
    assert (folder / f"{SET_ID}.bin").read_bytes() == SET_BIN
    assert json.loads((folder / f"{SET_ID}.json").read_text()) == SET_META


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
