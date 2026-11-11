import json
import os
import re
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, Request, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from app import coach, db, health
from app.analysis import count_reps, load_set

app = FastAPI(title="gym-buddy")

# Two secrets, for two kinds of caller. Both come from the environment, never from the code.
TOKEN = os.environ.get("GYM_BUDDY_TOKEN", "dev-token")      # the watch sends this with every upload
PASSWORD = os.environ.get("GYM_BUDDY_PASSWORD", "")         # the dashboard asks for this; empty = no password (home network only)
SET_DIR = Path(os.environ.get("GYM_BUDDY_DATA", "data/sets"))
SET_ID = re.compile(r"^\d{5}-[0-9a-f]{6}$")     # e.g. 00004-a956cd, nothing else
BYTES_PER_READING = 12                          # 6 int16s: accel xyz, gyro xyz
ANALYSIS_VERSION = 1                            # raise when count_reps changes, so old rows can be found and recounted
PAGES = Path(__file__).parent / "static"
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


def viewer(credentials: HTTPBasicCredentials | None = Depends(HTTPBasic(auto_error=False))):
    # Guards everything the dashboard uses. The browser shows its own sign-in
    # box when it gets the 401 below; any user name is accepted.
    if PASSWORD and not (credentials and same(credentials.password, PASSWORD)):
        raise HTTPException(status_code=401, detail="password needed",
                            headers={"WWW-Authenticate": 'Basic realm="Gym Buddy"'})


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

    # Already have it? Same receipt, nothing rewritten.
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


@app.get("/sets/{set_id}", dependencies=[Depends(viewer)])
def get_set(set_id: str):
    # 404 for an unknown set, and for anything that isn't shaped like a set ID.
    row = db.get_set(set_id) if SET_ID.match(set_id) else None
    if row is None:
        raise HTTPException(status_code=404, detail="no such set")
    return {**row, **coach.pace(row["rep_times"])}     # plus gaps, usual_s and slowdown_pct


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
    if not SET_ID.match(set_id) or db.get_set(set_id) is None:
        raise HTTPException(status_code=404, detail="no such set")
    if change.exercise not in [name for name, _ in EXERCISES]:
        raise HTTPException(status_code=422, detail="unknown exercise")
    reps, rep_times = analyze(set_id, change.exercise)
    db.update_set(set_id, change.exercise, reps, rep_times, ANALYSIS_VERSION)
    return get_set(set_id)


@app.get("/", include_in_schema=False, dependencies=[Depends(viewer)])
def dashboard():
    return FileResponse(PAGES / "index.html")


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
