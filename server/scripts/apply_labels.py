"""Label the stored sets from recordings/labels.csv: python scripts/apply_labels.py   (from server/)

For sets recorded before the watch had an exercise picker. Each labeled
exercise set gets its exercise and is recounted, the same way the dashboard's
dropdown does it. Walking, stairs and other "should count 0" recordings are
listed but left alone: they are test data, not exercises. Safe to run again.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import db, main  # noqa: E402

LABELS = Path(__file__).parents[2] / "recordings" / "labels.csv"
KNOWN = [name for name, _ in main.EXERCISES]


def exercise_for(label):
    # labels.csv is more specific than the watch's list: row_underhand and row_overhand are both "row".
    return "row" if label.startswith("row") else label if label in KNOWN else None


with open(LABELS, newline="") as f:
    for row in csv.DictReader(f):
        stored = db.get_set(row["set_id"])
        if stored is None:
            continue
        exercise = exercise_for(row["exercise"])
        if row["kind"] == "negative" or exercise is None:
            print(f"  {row['set_id']}  {row['exercise']:15s} not an exercise, left alone (counts {stored['reps']})")
            continue
        reps, rep_times = main.analyze(row["set_id"], exercise)
        db.update_set(row["set_id"], exercise, reps, rep_times, main.ANALYSIS_VERSION)
        verdict = "ok" if reps == int(row["true_reps"]) else f"EXPECTED {row['true_reps']}"
        print(f"  {row['set_id']}  {exercise:15s} reps {reps}  {verdict}")
