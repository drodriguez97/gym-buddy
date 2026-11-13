import hashlib
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Request, Header, HTTPException, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from app import coach, db, health
from app.analysis import count_reps, load_set, trace_signal

app = FastAPI(title="gym-buddy")

# Two secrets, for two kinds of caller. Both come from the environment, never from the code.
TOKEN = os.environ.get("GYM_BUDDY_TOKEN", "dev-token")      # the watch sends this with every upload
PASSWORD = os.environ.get("GYM_BUDDY_PASSWORD", "")         # the dashboard asks for this; empty = no password (home network only)
SET_DIR = Path(os.environ.get("GYM_BUDDY_DATA", "data/sets"))
SET_ID = re.compile(r"^\d{5}-[0-9a-f]{6}$")     # e.g. 00004-a956cd, nothing else
BYTES_PER_READING = 12                          # 6 int16s: accel xyz, gyro xyz
ANALYSIS_VERSION = 3                            # raise when count_reps changes, so old rows can be found and recounted
PAGES = Path(__file__).parent / "static"
# Sent with both pages: "ask me before reusing your saved copy". Without it a
# phone can keep showing the old page after an update (seen 2026-11-11).
FRESH = {"Cache-Control": "no-cache"}
# The exercises the watch offers, in its order: (name stored with the set, label shown to people).
EXERCISES = [
    ("curl", "Curl"),
    ("shoulder_press", "Shoulder press"),
    ("chest_press", "Chest press"),
    ("row", "Row"),
    ("pullup", "Pull-up"),
    ("pushup", "Push-up"),
]


def same(given, expected):
    # Compares secrets in a way that takes the same time whether or not they match,
    # so the time a wrong guess takes tells an attacker nothing.
    return secrets.compare_digest((given or "").encode(), expected.encode())


SESSION_COOKIE = "gym_buddy_session"
SESSION_DAYS = 30
WRONG_PASSWORD_WAIT_S = 1       # every wrong guess costs this long, which makes guessing thousands impractical


def session_value():
    # What the sign-in cookie holds: a fingerprint of the password, not the
    # password. It can't be turned back into the password, it can't be made
    # without knowing the password, and changing the password signs everyone out.
    return hmac.new(PASSWORD.encode(), b"gym-buddy session v1", hashlib.sha256).hexdigest()


def signed_in(request, credentials=None):
    # Two ways in: the cookie the sign-in page sets (people, in a browser), or
    # the password sent with the request as HTTP Basic (scripts such as check_server.py).
    if not PASSWORD:
        return True
    if same(request.cookies.get(SESSION_COOKIE), session_value()):
        return True
    return bool(credentials and same(credentials.password, PASSWORD))


def viewer(request: Request, credentials: HTTPBasicCredentials | None = Depends(HTTPBasic(auto_error=False))):
    # Guards everything the dashboard uses. The page sends people to /login when it gets this 401.
    if not signed_in(request, credentials):
        raise HTTPException(status_code=401, detail="sign in first")


def save_atomically(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def analyze(set_id, exercise=None):
    # (reps, seconds of each rep's top) for a stored set, or (None, []) if the
    # analyzer fails. A set is never refused because it couldn't be counted:
    # the raw file is safe, and it can be recounted later.
    # exercise: count as this one; by default, the one the watch saved with the set.
    try:
        meta, _, accel, gyro = load_set(SET_DIR / f"{set_id}.bin")
        peaks, _, _ = count_reps(accel, meta["rate_hz"], gyro, exercise=exercise or meta.get("exercise"))
        return len(peaks), [round(float(p) / meta["rate_hz"], 2) for p in peaks]
    except Exception:
        return None, []


def record(set_id):
    # The set's row, counting it first if it has none yet. Also covers sets
    # whose files arrived before the database existed.
    row = db.get_set(set_id)
    if row is None:
        meta = json.loads((SET_DIR / f"{set_id}.json").read_text())
        reps, rep_times = analyze(set_id)
        db.add_set(meta, reps, rep_times, ANALYSIS_VERSION)
        row = db.get_set(set_id)
    return row


def receipt(set_id):
    # What the watch waits for before deleting its copy. reps is extra: the
    # watch shows it after a sync.
    return {"set_id": set_id, "stored": True, "reps": record(set_id)["reps"]}


@app.get("/health")
def ping():
    return {"status": "ok"}


@app.post("/sets", status_code=201)
async def upload_sets(
    request: Request,
    x_token: str | None = Header(default=None),
    x_set_meta: str | None = Header(default=None),
):
    # Who is calling? Missing and wrong are both 401
    if not same(x_token, TOKEN):
        raise HTTPException(status_code=401, detail="missing or wrong token")

    # What do they say they are sending?
    try:
        meta = json.loads(x_set_meta or "")
    except ValueError:
        raise HTTPException(status_code=422, detail="X-Set-Meta is not valid JSON")
    if not isinstance(meta, dict):
        raise HTTPException(status_code=422, detail="X-Set-Meta must be a JSON object")

    # Is the ID safe to use as a file name?
    set_id = meta.get("set_id")
    if not isinstance(set_id, str) or not SET_ID.match(set_id):
        raise HTTPException(status_code=422, detail="bad set_id")

    # Did all of it arrive? The watch's .json says how many readings it sent.
    data = await request.body()
    count = meta.get("count")
    if not isinstance(count, int) or not data or len(data) != count * BYTES_PER_READING:
        raise HTTPException(status_code=422,
                            detail=f"expected {count} readings x {BYTES_PER_READING} bytes, got {len(data)} bytes")

    # Already have it? Same receipt, nothing rewritten. This also covers a set
    # the wearer removed from the dashboard: its files are still here.
    path = SET_DIR / f"{set_id}.bin"
    if path.exists():
        return receipt(set_id)

    # The .bin is what the duplicate check looks at, so it is written last.
    SET_DIR.mkdir(parents=True, exist_ok=True)
    save_atomically(SET_DIR / f"{set_id}.json", json.dumps(meta).encode())
    save_atomically(path, data)

    # Raw files first, then the count: a crash in between loses nothing,
    # because the next upload of this set finds the files and counts them.
    return receipt(set_id)


@app.get("/sets", dependencies=[Depends(viewer)])
def list_sets():
    # Every set, newest first.
    return db.list_sets()


def known(set_id):
    # The set's row, or 404 for an unknown set and for anything that isn't shaped like a set ID.
    row = db.get_set(set_id) if SET_ID.match(set_id) else None
    if row is None:
        raise HTTPException(status_code=404, detail="no such set")
    return row


def last_weight(row):
    # The weight most recently used for this exercise in another set: the
    # dashboard offers it, because the next set usually uses the same.
    others = [r for r in db.list_sets()
              if r["exercise"] == row["exercise"] and r["weight"] and r["set_id"] != row["set_id"]]
    return max(others, key=lambda r: (coach.when(r), r["set_id"]))["weight"] if others and row["exercise"] else None


@app.get("/sets/{set_id}", dependencies=[Depends(viewer)])
def get_set(set_id: str):
    row = known(set_id)
    # plus gaps, usual_s and slowdown_pct, and the weight to offer
    return {**row, **coach.pace(row["rep_times"]), "last_weight": last_weight(row)}


TRACE_POINTS = 240          # enough for a smooth line on any screen; a 2-minute set has 12,000 readings


@app.get("/sets/{set_id}/trace", dependencies=[Depends(viewer)])
def get_trace(set_id: str):
    # What the watch felt during the set, for the dashboard to draw: the same
    # smoothed signal the counter looked at (movement in g, or for pull-ups and
    # push-ups the wrist angle in degrees), thinned out to TRACE_POINTS, and
    # the moment of each rep it found. Worked out from the raw file on request.
    row = known(set_id)
    try:
        meta, _, accel, gyro = load_set(SET_DIR / f"{set_id}.bin")
        rate = meta["rate_hz"]
        signal, unit = trace_signal(accel, rate, gyro, exercise=row["exercise"] or meta.get("exercise"))
    except Exception:
        raise HTTPException(status_code=404, detail="no recording to draw")
    step = max(1, len(signal) // TRACE_POINTS)
    points = [[round(i / rate, 2), round(float(signal[i:i + step].mean()), 3)] for i in range(0, len(signal), step)]
    return {"points": points, "reps": row["rep_times"], "unit": unit}


class RepsChange(BaseModel):
    reps: int | None            # None: go back to the counter's number


@app.put("/sets/{set_id}/reps", dependencies=[Depends(viewer)])
def correct_reps(set_id: str, change: RepsChange):
    # The wearer knows how many they did. Their number is shown; the counter's
    # is kept beside it, and each disagreement is a labeled example for improving the counter.
    known(set_id)
    if change.reps is not None and not 0 <= change.reps <= 200:
        raise HTTPException(status_code=422, detail="reps must be between 0 and 200")
    db.edit_set(set_id, "reps_fixed", change.reps)
    return get_set(set_id)


class WeightChange(BaseModel):
    weight: float | None        # pounds; None clears it


@app.put("/sets/{set_id}/weight", dependencies=[Depends(viewer)])
def set_weight(set_id: str, change: WeightChange):
    known(set_id)
    if change.weight is not None and not 0 < change.weight <= 1000:
        raise HTTPException(status_code=422, detail="weight must be above 0 and at most 1000 lb")
    db.edit_set(set_id, "weight", change.weight)
    return get_set(set_id)


@app.delete("/sets/{set_id}", dependencies=[Depends(viewer)])
def remove_set(set_id: str):
    # Takes a set off the dashboard (a recording started by accident, say).
    # Nothing is deleted: the row is marked and the raw files stay, so it can be put back.
    known(set_id)
    db.edit_set(set_id, "removed_at", int(time.time()))
    return get_set(set_id)


@app.post("/sets/{set_id}/restore", dependencies=[Depends(viewer)])
def restore_set(set_id: str):
    known(set_id)
    db.edit_set(set_id, "removed_at", None)
    return get_set(set_id)


@app.get("/progress", dependencies=[Depends(viewer)])
def list_progress():
    # Each exercise across workouts, oldest first.
    return coach.progress(db.list_sets(), dict(EXERCISES))


@app.get("/workouts", dependencies=[Depends(viewer)])
def list_workouts():
    # Sets grouped into workouts, newest first, each exercise with its sets and a suggestion.
    return coach.workouts(db.list_sets(), dict(EXERCISES))


@app.get("/exercises", dependencies=[Depends(viewer)])
def list_exercises():
    # The dashboard's dropdown is filled from this, so the list lives in one place.
    return [{"name": name, "label": label} for name, label in EXERCISES]


class ExerciseChange(BaseModel):
    exercise: str


@app.put("/sets/{set_id}/exercise", dependencies=[Depends(viewer)])
def change_exercise(set_id: str, change: ExerciseChange):
    # The watch had the wrong exercise picked: correct it and recount from the raw file.
    known(set_id)
    if change.exercise not in [name for name, _ in EXERCISES]:
        raise HTTPException(status_code=422, detail="unknown exercise")
    reps, rep_times = analyze(set_id, change.exercise)
    db.update_set(set_id, change.exercise, reps, rep_times, ANALYSIS_VERSION)
    return get_set(set_id)


@app.get("/", include_in_schema=False)
def dashboard(request: Request, credentials: HTTPBasicCredentials | None = Depends(HTTPBasic(auto_error=False))):
    # A person who isn't signed in is sent to the sign-in page, not shown an error.
    if not signed_in(request, credentials):
        return RedirectResponse("/login", status_code=303)
    return FileResponse(PAGES / "index.html", headers=FRESH)


ICON_SIZES = (180, 192, 512)


@app.get("/icon-{size}.png", include_in_schema=False)
def app_icon(size: int):
    # The home-screen icon. Open to everyone: a phone asks for it without the cookie.
    if size not in ICON_SIZES:
        raise HTTPException(status_code=404, detail="no such icon")
    return FileResponse(PAGES / ("icon-%d.png" % size), media_type="image/png")


@app.get("/manifest.webmanifest", include_in_schema=False)
def app_manifest():
    # Tells a phone how "Add to Home Screen" should behave: the name, the icon,
    # and "standalone" (full screen, without the browser's bars). No secrets in it.
    return Response(json.dumps({
        "name": "Gym Buddy", "short_name": "Gym Buddy", "start_url": "/", "display": "standalone",
        "background_color": "#0B0B0C", "theme_color": "#0B0B0C",
        "icons": [{"src": "/icon-%d.png" % size, "sizes": "%dx%d" % (size, size), "type": "image/png",
                   "purpose": "any maskable"} for size in ICON_SIZES if size != 180],
    }), media_type="application/manifest+json")


@app.get("/login", include_in_schema=False)
def login_page(request: Request):
    if signed_in(request):
        return RedirectResponse("/", status_code=303)
    return FileResponse(PAGES / "login.html", headers=FRESH)


class SignIn(BaseModel):
    password: str


@app.post("/login")
def sign_in(attempt: SignIn, request: Request, response: Response):
    if not same(attempt.password, PASSWORD):
        time.sleep(WRONG_PASSWORD_WAIT_S)
        raise HTTPException(status_code=401, detail="wrong password")
    # HttpOnly: scripts on the page can't read the cookie. SameSite=Lax: other
    # sites can't make the browser send it with a change. Secure: only over
    # HTTPS, when that is how the page was reached (Caddy says so in a header).
    https = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(SESSION_COOKIE, session_value(), max_age=SESSION_DAYS * 24 * 3600,
                        httponly=True, samesite="lax", secure=https)
    return {"signed_in": True}


@app.get("/session")
def session(_: None = Depends(viewer)):
    # Lets the page hide "Sign out" on a server that has no password to sign out of.
    return {"password": bool(PASSWORD)}


@app.post("/logout")
def sign_out(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"signed_in": False}


@app.post("/watch/health", status_code=201)
async def report_health(request: Request, x_token: str | None = Header(default=None)):
    # The watch's own numbers (sensor, Wi-Fi, clock, battery, storage), sent after each sync.
    if not same(x_token, TOKEN):
        raise HTTPException(status_code=401, detail="missing or wrong token")
    try:
        report = json.loads(await request.body())
    except ValueError:
        raise HTTPException(status_code=422, detail="the report is not valid JSON")
    if not isinstance(report, dict):
        raise HTTPException(status_code=422, detail="the report must be a JSON object")
    now = time.time()
    db.add_health(report, now)
    return {"stored": True, "server_time": int(now)}


@app.get("/watch/health", dependencies=[Depends(viewer)])
def watch_health():
    # The latest report, judged against the limits in health.py.
    latest = db.latest_health()
    if latest is None:
        return {"seen": False, "status": "warn", "summary": "No report from the watch yet", "checks": []}
    report, received_at = latest
    checks = health.judge(report, received_at)
    status, line = health.summary(checks)
    return {"seen": True, "status": status, "summary": line, "checks": checks,
            "received_at": coach.iso(received_at)}
