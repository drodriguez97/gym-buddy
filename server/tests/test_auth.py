"""Who may call what: the watch's token, and the dashboard's password."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app, SESSION_COOKIE

FIXTURES = Path(__file__).parent / "fixtures"
SET_ID = "00004-a956cd"
DATA = ["/sets", f"/sets/{SET_ID}", "/workouts", "/exercises", "/watch/health", "/progress"]
PASSWORD = "open-sesame"


@pytest.fixture
def client():
    return TestClient(app)          # a fresh one per test, so no test inherits another's cookie


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.SET_DIR", tmp_path / "sets")
    monkeypatch.setattr("app.db.DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr("app.main.WRONG_PASSWORD_WAIT_S", 0)


@pytest.fixture
def password(monkeypatch):
    monkeypatch.setattr("app.main.PASSWORD", PASSWORD)


def upload(client, **more):
    meta = json.loads((FIXTURES / f"{SET_ID}.json").read_text())
    return client.post("/sets", content=(FIXTURES / f"{SET_ID}.bin").read_bytes(),
                       headers={"X-Token": "dev-token", "X-Set-Meta": json.dumps(meta)}, **more)


# ---- no password set (home network)

@pytest.mark.parametrize("path", ["/"] + DATA)
def test_with_no_password_set_the_dashboard_is_open(client, path):
    upload(client)
    assert client.get(path).status_code == 200


def test_with_no_password_set_the_sign_in_page_sends_you_straight_in(client):
    response = client.get("/login", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/"


# ---- signed out

@pytest.mark.parametrize("path", DATA)
def test_signed_out_every_data_address_is_closed(client, password, path):
    response = client.get(path)
    assert response.status_code == 401
    # No WWW-Authenticate header: that header makes the browser pop up its own
    # password box over the page, and the page has a proper sign-in screen.
    assert "www-authenticate" not in response.headers


def test_signed_out_the_page_sends_you_to_sign_in(client, password):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"
    assert "Sign in" in client.get("/login").text


@pytest.mark.parametrize("call", [
    lambda c: c.put(f"/sets/{SET_ID}/exercise", json={"exercise": "curl"}),
    lambda c: c.put(f"/sets/{SET_ID}/reps", json={"reps": 6}),
    lambda c: c.put(f"/sets/{SET_ID}/weight", json={"weight": 25}),
    lambda c: c.delete(f"/sets/{SET_ID}"),
    lambda c: c.post(f"/sets/{SET_ID}/restore"),
], ids=["exercise", "reps", "weight", "remove", "restore"])
def test_signed_out_nothing_can_be_changed(client, password, call):
    upload(client)
    assert call(client).status_code == 401
    row = client.get(f"/sets/{SET_ID}", auth=("", PASSWORD)).json()
    assert row["exercise"] is None and row["reps_fixed"] is None and row["weight"] is None and row["removed_at"] is None


# ---- signing in

def test_the_right_password_signs_you_in_and_the_cookie_opens_everything(client, password):
    upload(client)
    response = client.post("/login", json={"password": PASSWORD})
    assert response.status_code == 200 and response.json() == {"signed_in": True}
    for path in ["/"] + DATA:
        assert client.get(path).status_code == 200, path
    assert client.put(f"/sets/{SET_ID}/exercise", json={"exercise": "curl"}).status_code == 200


def test_a_wrong_password_is_refused_and_sets_no_cookie(client, password):
    for wrong in ["open-sesam", "", "open-sesame "]:
        response = client.post("/login", json={"password": wrong})
        assert response.status_code == 401 and "set-cookie" not in response.headers
    assert client.get("/sets").status_code == 401


def test_a_wrong_password_costs_time(client, password, monkeypatch):
    waits = []
    monkeypatch.setattr("app.main.WRONG_PASSWORD_WAIT_S", 0.5)
    monkeypatch.setattr("app.main.time.sleep", waits.append)
    client.post("/login", json={"password": "guess"})
    client.post("/login", json={"password": PASSWORD})
    assert waits == [0.5]           # the wrong one waited, the right one didn't


def test_the_cookie_is_not_the_password_and_scripts_cannot_read_it(client, password):
    response = client.post("/login", json={"password": PASSWORD})
    cookie = response.headers["set-cookie"]
    assert PASSWORD not in cookie
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=2592000" in cookie
    assert "Secure" not in cookie               # reached over plain http here


def test_over_https_the_cookie_is_marked_secure(client, password):
    # Caddy tells the server the page was reached over https with this header.
    response = client.post("/login", json={"password": PASSWORD}, headers={"X-Forwarded-Proto": "https"})
    assert "Secure" in response.headers["set-cookie"]


def test_a_made_up_cookie_is_refused(client, password):
    client.cookies.set(SESSION_COOKIE, "0" * 64)
    assert client.get("/sets").status_code == 401


def test_changing_the_password_signs_everyone_out(client, password, monkeypatch):
    client.post("/login", json={"password": PASSWORD})
    assert client.get("/sets").status_code == 200
    monkeypatch.setattr("app.main.PASSWORD", "a-new-one")
    assert client.get("/sets").status_code == 401


def test_signing_out_closes_it_again(client, password):
    client.post("/login", json={"password": PASSWORD})
    assert client.post("/logout").json() == {"signed_in": False}
    assert client.get("/sets").status_code == 401


def test_signed_in_the_sign_in_page_sends_you_to_the_dashboard(client, password):
    client.post("/login", json={"password": PASSWORD})
    assert client.get("/login", follow_redirects=False).headers["location"] == "/"


# ---- scripts: the password sent with each request (HTTP Basic)

@pytest.mark.parametrize("path", ["/"] + DATA)
def test_a_script_can_send_the_password_with_any_user_name(client, password, path):
    upload(client)
    assert client.get(path, auth=("dan", PASSWORD)).status_code == 200
    assert client.get(path, auth=("", PASSWORD)).status_code == 200


def test_a_script_with_a_wrong_password_is_refused(client, password):
    assert client.get("/sets", auth=("dan", "open-sesam")).status_code == 401
    assert client.get("/sets", auth=(PASSWORD, "")).status_code == 401


# ---- the watch

def test_the_watch_uploads_with_its_token_not_the_password(client, password):
    assert upload(client).status_code == 201
    report = client.post("/watch/health", content="{}", headers={"X-Token": "dev-token"})
    assert report.status_code == 201


def test_the_password_does_not_work_as_the_watch_token(client, password):
    meta = json.loads((FIXTURES / f"{SET_ID}.json").read_text())
    body = (FIXTURES / f"{SET_ID}.bin").read_bytes()
    as_basic = client.post("/sets", content=body, headers={"X-Set-Meta": json.dumps(meta)}, auth=("", PASSWORD))
    as_token = client.post("/sets", content=body, headers={"X-Set-Meta": json.dumps(meta), "X-Token": PASSWORD})
    client.post("/login", json={"password": PASSWORD})              # nor does being signed in
    signed_in = client.post("/sets", content=body, headers={"X-Set-Meta": json.dumps(meta)})
    assert [as_basic.status_code, as_token.status_code, signed_in.status_code] == [401, 401, 401]


def test_the_ping_stays_open_so_the_watch_and_monitors_can_check_the_server_is_up(client, password):
    assert client.get("/health").status_code == 200


# ---- the page asks whether there is anything to sign out of

def test_the_page_can_tell_that_no_password_is_set(client):
    assert client.get("/session").json() == {"password": False}


def test_with_a_password_the_session_says_so_only_once_signed_in(client, password):
    assert client.get("/session").status_code == 401
    client.post("/login", json={"password": PASSWORD})
    assert client.get("/session").json() == {"password": True}


# ---- "Add to Home Screen": the icon and the manifest are open, because a phone asks for them without the cookie

@pytest.mark.parametrize("path", ["/icon-180.png", "/icon-192.png", "/icon-512.png"])
def test_the_app_icons_are_open_and_are_png_files(client, password, path):
    response = client.get(path)
    assert response.status_code == 200 and response.headers["content-type"] == "image/png"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_an_icon_size_that_does_not_exist_is_not_found(client, password):
    assert client.get("/icon-999.png").status_code == 404
    assert client.get("/icon-..%2Fmain.png").status_code in (404, 422)


def test_the_manifest_is_open_and_points_at_icons_that_exist(client, password):
    response = client.get("/manifest.webmanifest")
    assert response.status_code == 200
    manifest = response.json()
    assert manifest["display"] == "standalone" and manifest["start_url"] == "/"
    for icon in manifest["icons"]:
        assert client.get(icon["src"]).status_code == 200


@pytest.mark.parametrize("page", ["index.html", "login.html"])
def test_both_pages_offer_the_icon_and_the_manifest_and_load_nothing_from_elsewhere(page):
    html = (Path(__file__).parents[1] / "app" / "static" / page).read_text(encoding="utf-8")
    assert 'rel="apple-touch-icon" href="/icon-180.png"' in html
    assert 'rel="manifest" href="/manifest.webmanifest"' in html
    assert "https://" not in html and "http://www.w3.org" in html      # only the SVG namespace, which is a name, not a request


@pytest.mark.parametrize("path", ["/", "/login"])
def test_the_pages_tell_the_browser_to_check_for_a_newer_copy(client, path):
    # Otherwise a phone keeps showing the old dashboard after the server is updated.
    assert client.get(path).headers["cache-control"] == "no-cache"
