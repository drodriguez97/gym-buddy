"""Who may call what: the watch's token, and the dashboard's password."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
FIXTURES = Path(__file__).parent / "fixtures"
SET_ID = "00004-a956cd"
DASHBOARD = ["/", "/sets", f"/sets/{SET_ID}", "/workouts", "/exercises", "/watch/health"]


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.SET_DIR", tmp_path / "sets")
    monkeypatch.setattr("app.db.DB_PATH", tmp_path / "test.db")


@pytest.fixture
def password(monkeypatch):
    monkeypatch.setattr("app.main.PASSWORD", "open-sesame")


def upload():
    meta = json.loads((FIXTURES / f"{SET_ID}.json").read_text())
    return client.post("/sets", content=(FIXTURES / f"{SET_ID}.bin").read_bytes(),
                       headers={"X-Token": "dev-token", "X-Set-Meta": json.dumps(meta)})


@pytest.mark.parametrize("path", DASHBOARD)
def test_with_no_password_set_the_dashboard_is_open(path):
    upload()
    assert client.get(path).status_code == 200


@pytest.mark.parametrize("path", DASHBOARD)
def test_with_a_password_set_every_dashboard_address_asks_for_it(password, path):
    response = client.get(path)
    assert response.status_code == 401
    assert response.headers["www-authenticate"].startswith("Basic")     # this is what makes the browser ask


@pytest.mark.parametrize("path", DASHBOARD)
def test_the_right_password_opens_it_with_any_user_name(password, path):
    upload()
    assert client.get(path, auth=("dan", "open-sesame")).status_code == 200
    assert client.get(path, auth=("", "open-sesame")).status_code == 200


def test_a_wrong_password_is_refused(password):
    assert client.get("/sets", auth=("dan", "open-sesam")).status_code == 401
    assert client.get("/sets", auth=("open-sesame", "")).status_code == 401


def test_changing_an_exercise_needs_the_password_too(password):
    upload()
    assert client.put(f"/sets/{SET_ID}/exercise", json={"exercise": "curl"}).status_code == 401
    assert client.put(f"/sets/{SET_ID}/exercise", json={"exercise": "curl"}, auth=("", "open-sesame")).status_code == 200


def test_the_watch_uploads_with_its_token_not_the_password(password):
    assert upload().status_code == 201
    report = client.post("/watch/health", content="{}", headers={"X-Token": "dev-token"})
    assert report.status_code == 201


def test_the_password_does_not_work_as_the_watch_token(password):
    meta = json.loads((FIXTURES / f"{SET_ID}.json").read_text())
    response = client.post("/sets", content=(FIXTURES / f"{SET_ID}.bin").read_bytes(), auth=("", "open-sesame"),
                           headers={"X-Set-Meta": json.dumps(meta)})
    assert response.status_code == 401


def test_the_ping_stays_open_so_the_watch_and_monitors_can_check_the_server_is_up(password):
    assert client.get("/health").status_code == 200
