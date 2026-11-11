"""SQLite storage: one row per set.

The raw .bin and .json files are the truth. A row here is what was worked out
from them (the rep count, when each rep happened), so it can always be rebuilt.
The whole database is one file, GYM_BUDDY_DB, which in Docker sits on a volume.
"""
import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path

DB_PATH = Path(os.environ.get("GYM_BUDDY_DB", "data/gymbuddy.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS sets (
    set_id           TEXT PRIMARY KEY,                           -- from the watch, e.g. 00004-a956cd
    exercise         TEXT,                                       -- picked on the watch; empty on older sets
    reps             INTEGER,                                    -- empty if the analysis failed
    rep_times        TEXT,                                       -- JSON list: seconds into the set of each rep's top
    duration_ms      INTEGER NOT NULL,
    rate_hz          REAL NOT NULL,
    late             INTEGER NOT NULL,
    analysis_version INTEGER NOT NULL,                           -- which version of the analyzer produced reps
    received_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP     -- UTC
)
"""


HEALTH_SCHEMA = """
CREATE TABLE IF NOT EXISTS health (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    received_at INTEGER NOT NULL,           -- unix seconds (UTC), by the server's clock
    report      TEXT NOT NULL               -- JSON, exactly what the watch sent
)
"""

# Columns added after the first version. A database made before them gets them
# added on its next open, so an old file keeps working (a tiny migration).
ADDED_COLUMNS = {
    "started_at": "INTEGER",                # unix seconds (UTC) when the watch started the set; empty if it didn't know the time
}


def connect():
    # A short-lived connection per request: simple, and plenty for one watch.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row            # rows read like dicts: row["reps"]
    db.execute(SCHEMA)
    db.execute(HEALTH_SCHEMA)
    have = {column[1] for column in db.execute("PRAGMA table_info(sets)")}
    for name, kind in ADDED_COLUMNS.items():
        if name not in have:
            db.execute(f"ALTER TABLE sets ADD COLUMN {name} {kind}")    # names come from the dict above, never from a request
    return db


def plausible_time(value):
    # The watch's clock is only right after it has synced with the internet.
    # Anything outside 2026-2100 means it wasn't set; store nothing.
    return int(value) if isinstance(value, (int, float)) and 1767225600 <= value < 4102444800 else None


def as_dict(row):
    if row is None:
        return None
    d = dict(row)
    d["rep_times"] = json.loads(d["rep_times"]) if d["rep_times"] else []
    return d


def add_set(meta, reps, rep_times, analysis_version):
    # INSERT OR IGNORE: a second upload of the same set changes nothing.
    # The ? placeholders keep the values as data; they can never run as SQL.
    with closing(connect()) as db, db:      # the inner "db" commits, or rolls back on an error
        db.execute(
            "INSERT OR IGNORE INTO sets (set_id, exercise, reps, rep_times, duration_ms, rate_hz, late,"
            " analysis_version, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (meta["set_id"], meta.get("exercise"), reps, json.dumps(rep_times),
             int(meta.get("duration_ms", 0)), float(meta.get("rate_hz", 0)), int(meta.get("late", 0)),
             analysis_version, plausible_time(meta.get("started_at"))))


def get_set(set_id):
    with closing(connect()) as db:
        return as_dict(db.execute("SELECT * FROM sets WHERE set_id = ?", (set_id,)).fetchone())


def list_sets():
    # Newest first. The set_id starts with the watch's sequence number, so it orders them.
    with closing(connect()) as db:
        return [as_dict(row) for row in db.execute("SELECT * FROM sets ORDER BY set_id DESC")]


def update_set(set_id, exercise, reps, rep_times, analysis_version):
    # A corrected exercise and the recount that goes with it. The raw files are not touched.
    with closing(connect()) as db, db:
        db.execute(
            "UPDATE sets SET exercise = ?, reps = ?, rep_times = ?, analysis_version = ? WHERE set_id = ?",
            (exercise, reps, json.dumps(rep_times), analysis_version, set_id))


def delete_set(set_id):
    # Removes the row only. What happens to the raw files is the caller's decision.
    with closing(connect()) as db, db:
        db.execute("DELETE FROM sets WHERE set_id = ?", (set_id,))


def add_health(report, received_at):
    # Every report is kept: a history of the watch's state costs almost nothing.
    with closing(connect()) as db, db:
        db.execute("INSERT INTO health (received_at, report) VALUES (?, ?)", (int(received_at), json.dumps(report)))


def latest_health():
    # (report, received_at) of the newest report, or None if the watch has never sent one.
    with closing(connect()) as db:
        row = db.execute("SELECT received_at, report FROM health ORDER BY id DESC LIMIT 1").fetchone()
    return (json.loads(row["report"]), row["received_at"]) if row else None
