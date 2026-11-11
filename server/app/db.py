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


def connect():
    # A short-lived connection per request: simple, and plenty for one watch.
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row            # rows read like dicts: row["reps"]
    db.execute(SCHEMA)
    return db


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
            "INSERT OR IGNORE INTO sets (set_id, exercise, reps, rep_times, duration_ms, rate_hz, late, analysis_version)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (meta["set_id"], meta.get("exercise"), reps, json.dumps(rep_times),
             int(meta.get("duration_ms", 0)), float(meta.get("rate_hz", 0)), int(meta.get("late", 0)),
             analysis_version))


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
