"""A deploy rehearsal: the server as a real process, set up the way the container sets it up.

The other tests call the app in memory. This one starts uvicorn for real, with
its secrets and its storage paths coming from environment variables (as in
docker-compose.yml), fills it with push_sets.py, checks it with
check_server.py, then stops it and starts it again to prove the data is still
there. It is the "restart keeps data" test, minus Docker itself.
"""
import importlib.util
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).parents[1]
FIXTURES = Path(__file__).parent / "fixtures"
TOKEN = "rehearsal-token"
PASSWORD = "rehearsal-password"
GOOD_REPORT = {"accel_g": 1.0, "gyro_dps": 2.1, "rssi": -48, "battery_pct": 70,
               "battery_mv": 3860, "free_pct": 88, "sets_waiting": 0}


def script(name):
    spec = importlib.util.spec_from_file_location(name, SERVER_DIR / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Server:
    """uvicorn in its own process, storing under `data`."""

    def __init__(self, data, token=TOKEN, password=PASSWORD):
        with socket.socket() as s:                  # ask the system for a free port
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        env = {**os.environ, "GYM_BUDDY_TOKEN": token, "GYM_BUDDY_PASSWORD": password,
               "GYM_BUDDY_DATA": str(data / "sets"), "GYM_BUDDY_DB": str(data / "gymbuddy.db")}
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
            cwd=SERVER_DIR, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):                        # up to 10 s for it to answer
            try:
                urllib.request.urlopen(self.url + "/health", timeout=1)
                return
            except OSError:
                time.sleep(0.1)
        self.stop()
        raise RuntimeError("the server did not start")

    def stop(self):
        self.process.terminate()
        self.process.wait(timeout=10)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.stop()


@pytest.fixture
def laptop(tmp_path, monkeypatch):
    # push_sets reads "this laptop's" sets: point it at the fixtures and an empty database.
    monkeypatch.setattr("app.main.SET_DIR", FIXTURES)
    monkeypatch.setattr("app.db.DB_PATH", tmp_path / "laptop.db")


def failed(results):
    return [what for passed, what, _ in results if not passed]


def test_fill_check_restart_and_the_data_is_still_there(tmp_path, laptop):
    push, check = script("push_sets"), script("check_server")
    data = tmp_path / "volume"
    count = len(list(FIXTURES.glob("*.bin")))

    with Server(data) as server:
        assert push.run(server.url, TOKEN, as_workout=True) is True
        # Before the watch has synced, that is the one thing left to do.
        assert failed(check.run(server.url, TOKEN, PASSWORD)) == ["the watch has reported in"]
        request = urllib.request.Request(server.url + "/watch/health", data=json.dumps(GOOD_REPORT).encode(),
                                         method="POST", headers={"X-Token": TOKEN})
        assert urllib.request.urlopen(request).status == 201
        assert failed(check.run(server.url, TOKEN, PASSWORD)) == []

    assert (data / "gymbuddy.db").exists() and len(list((data / "sets").glob("*.bin"))) == count

    with Server(data) as server:                    # a new process, the same storage
        results = check.run(server.url, TOKEN, PASSWORD)
        assert failed(results) == []
        assert (True, "there are sets to show", f"{count} sets in 1 workouts") in results


def test_pushing_twice_stores_nothing_twice(tmp_path, laptop):
    push = script("push_sets")
    with Server(tmp_path / "volume") as server:
        assert push.run(server.url, TOKEN) and push.run(server.url, TOKEN)
    assert len(list((tmp_path / "volume" / "sets").glob("*.bin"))) == len(list(FIXTURES.glob("*.bin")))


def test_pushing_with_the_wrong_token_stores_nothing_and_says_so(tmp_path, laptop, capsys):
    push = script("push_sets")
    with Server(tmp_path / "volume") as server:
        assert push.run(server.url, "wrong") is False
    assert "NOT stored: 401" in capsys.readouterr().out
    assert not (tmp_path / "volume" / "sets").exists()


def test_the_check_names_what_is_wrong(tmp_path, laptop):
    check = script("check_server")
    # A server left on its defaults: no password, the development token.
    with Server(tmp_path / "volume", token="dev-token", password="") as server:
        wrong = failed(check.run(server.url, "dev-token", ""))
    assert "the dashboard is closed without the password" in wrong
    assert "the token is not the development one" in wrong
    assert "there are sets to show" in wrong


def test_the_check_says_when_the_token_it_was_given_is_not_the_servers(tmp_path, laptop):
    check = script("check_server")
    with Server(tmp_path / "volume") as server:
        assert "the watch's token is accepted" in failed(check.run(server.url, "some-other-token", PASSWORD))


def test_a_server_that_is_not_there_fails_one_check_and_stops():
    check = script("check_server")
    results = check.run("http://127.0.0.1:9", TOKEN, PASSWORD)
    assert len(results) == 1 and results[0][0] is False and results[0][1] == "the server answers"
