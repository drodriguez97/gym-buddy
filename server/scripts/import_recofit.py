r"""Convert the Microsoft RecoFit data set into Gym Buddy .bin/.json sets.

RecoFit: 94 people, 50 Hz, armband on the right forearm (not the wrist), with
the true rep count labeled per set. Paper: Morris, Saponas, Guillory, Kelner,
CHI 2014. Data: https://github.com/microsoft/Exercise-Recognition-from-Wearable-Sensors
(the .mat files are Git LFS, ~1.5 GB each; "single" = one exercise per recording).

    python scripts/import_recofit.py exercise_data.50.0000_singleonly.mat ..\recordings\recofit

Writes one <set_id>.bin + .json per recording in the same format the watch
writes (int16 mg and 0.1 dps, "<6h"), plus labels.csv with the same columns
as recordings\labels.csv, so scorecard.py and the tests can read them.
Only the master (right forearm) sensor is used.
"""
import csv
import json
import struct
import sys
from pathlib import Path

import numpy as np
import scipy.io

# RecoFit activity -> (our exercise name, kind). Reps come from the data set.
# Everything not listed is skipped. Non-Exercise is capped because there are 2000+.
ACTIVITIES = {
    "Shoulder Press (dumbbell)": ("shoulder_press", "positive"),
    "Squat Rack Shoulder Press": ("shoulder_press_rack", "positive"),
    "Chest Press (rack)": ("chest_press_rack", "positive"),
    "Bicep Curl": ("curl", "positive"),
    "Two-arm Dumbbell Curl (both arms, not alternating)": ("curl_two_arm", "positive"),
    "Biceps Curl (band)": ("curl_band", "positive"),
    "Dumbbell Deadlift Row": ("row_deadlift", "positive"),
    "Dumbbell Row (knee on bench) (right arm)": ("row_bench", "positive"),
    "Band Pull-Down Row": ("row_band", "positive"),
    "Lateral Raise": ("lateral_raise", "positive"),
    "Overhead Triceps Extension": ("triceps_overhead", "positive"),
    "Seated Back Fly": ("back_fly", "positive"),
    "Pushups": ("pushup", "positive"),
    "Pushup (knee or foot variation)": ("pushup_knee", "positive"),
    "Dip": ("dip", "positive"),
    "Jumping Jacks": ("jumping_jacks", "positive"),
    "Kettlebell Swing": ("kettlebell_swing", "positive"),
    "Walk": ("walking", "negative"),
    "Running (treadmill)": ("jog", "negative"),
    "Elliptical machine": ("elliptical", "negative"),
    "Plank": ("plank", "negative"),
    "Device on Table": ("device_on_table", "negative"),
    "Non-Exercise": ("non_exercise", "negative"),
}
MAX_PER_ACTIVITY = 60
MIN_SECONDS = 4


def recordings(mat_path):
    """Every labeled recording in the file, as the mat_struct RecoFit uses."""
    m = scipy.io.loadmat(mat_path, squeeze_me=True, struct_as_record=False)
    for cell in m["subject_data"].flat:
        if hasattr(cell, "_fieldnames"):
            yield cell
        elif isinstance(cell, np.ndarray):
            for e in cell.flat:
                if hasattr(e, "_fieldnames"):
                    yield e


def write_set(out_dir, set_id, accel_g, gyro_dps, rate_hz):
    """Same files the watch writes: see recorder.py on the watch."""
    mg = np.clip(np.round(accel_g * 1000), -32768, 32767).astype("<i2")
    ddps = np.clip(np.round(gyro_dps * 10), -32768, 32767).astype("<i2")
    rows = np.hstack([mg, ddps])
    (out_dir / f"{set_id}.bin").write_bytes(rows.tobytes())
    meta = {"set_id": set_id, "count": len(rows), "rate_hz": float(rate_hz),
            "duration_ms": int(1000 * len(rows) / rate_hz), "late": 0,
            "format": "<6h", "accel_unit": "mg", "gyro_unit": "0.1 dps",
            "source": "recofit", "placement": "right forearm"}
    (out_dir / f"{set_id}.json").write_text(json.dumps(meta))


def main(mat_path, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    seen = {}
    rows = []
    for e in recordings(mat_path):
        if e.activityName not in ACTIVITIES:
            continue
        exercise, kind = ACTIVITIES[e.activityName]
        if seen.get(exercise, 0) >= MAX_PER_ACTIVITY:
            continue
        accel = e.data.accelDataMatrix[:, 1:4]          # column 0 is the timestamp
        gyro = e.data.gyroDataMatrix[:, 1:4]
        if len(accel) < MIN_SECONDS * e.sampleRate:
            continue
        if kind == "positive" and e.activityReps <= 0:
            continue
        seen[exercise] = seen.get(exercise, 0) + 1
        set_id = f"rf{e.subjectID:03d}-{exercise}-{seen[exercise]:02d}"
        write_set(out_dir, set_id, accel, gyro, e.sampleRate)
        true_reps = int(e.activityReps) if kind == "positive" else 0
        rows.append([set_id, kind, exercise, true_reps, f"recofit subject {e.subjectID}, {e.activityName}"])
    rows.sort()
    with open(out_dir / "labels.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["set_id", "kind", "exercise", "true_reps", "notes"])
        w.writerows(rows)
    print(f"wrote {len(rows)} sets to {out_dir}")
    for exercise, n in sorted(seen.items()):
        print(f"  {exercise}: {n}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
