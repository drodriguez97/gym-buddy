"""Give every stored set a database row: python scripts/backfill.py   (from server/)

For sets whose files arrived before the database existed, or after the
database file was deleted. Counts each one from its raw file. Safe to run
again: sets that already have a row are left alone.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import db, main  # noqa: E402

before = len(db.list_sets())
for path in sorted(main.SET_DIR.glob("*.bin")):
    if path.with_suffix(".json").exists():
        main.record(path.stem)
rows = db.list_sets()
print(f"{len(rows) - before} rows added, {len(rows)} sets in {db.DB_PATH}")
for row in reversed(rows):
    print(f"  {row['set_id']}  {row['exercise'] or '(no exercise)':15s} reps {row['reps']}")
