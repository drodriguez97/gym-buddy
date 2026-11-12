r"""Convert the MM-Fit data set into Gym Buddy .bin/.json sets.

MM-Fit: 21 workouts, a smartwatch on EACH wrist (accelerometer and gyroscope,
about 100 Hz), ten exercises, with the true rep count labeled for every set.
Paper: Stromback, Huang, Radu, "MM-Fit: Multimodal Deep Learning for Automatic
Exercise Logging across Sensing Devices", IMWUT 2020. Data: https://mmfit.github.io/
(one 1.7 GB zip; only the *_sw_* and *_labels.csv files are needed, about 780 MB).

    python scripts/import_mmfit.py ..\recordings\mmfit\mm-fit ..\recordings\mmfit\sets

Each workout folder holds one long recording per wrist and a labels.csv of
`first frame, last frame, reps, exercise` (frames of the 30-per-second video,
which every sensor row is stamped with). Each labeled set is cut out, put on
an even 100 Hz clock (the watches' readings arrive unevenly), converted from
m/s2 and rad/s to the watch's units, and written once per wrist in the same
format the watch writes, plus labels.csv in the columns scorecard.py reads.

The bicep curls are done one arm at a time, alternating, and the label counts
both arms. Each wrist therefore did half of it, which is what is written; a
curl set with an odd label is skipped because the halves can't be told apart.

Unlike a set from our watch, these are cut exactly where the labeler said the
reps start and stop: no picking the weights up, no button press.
"""
import csv
import json
import sys
from pathlib import Path

import numpy as np

EXERCISES = {
    "dumbbell_shoulder_press": "shoulder_press",
    "bicep_curls": "curl",
    "dumbbell_rows": "row",
    "pushups": "pushup",
    "tricep_extensions": "triceps_overhead",
    "lateral_shoulder_raises": "lateral_raise",
    "jumping_jacks": "jumping_jacks",
    "squats": "squat",
    "lunges": "lunge",
    "situps": "situp",
}
ALTERNATING = {"bicep_curls"}      # one arm at a time; the label counts both arms
RATE = 100
G = 9.80665
MIN_SECONDS = 4


def cut(recording, first_frame, last_frame):
    """Rows of one sensor between two video frames, on an even 100 Hz clock. None if too little is there."""
    part = recording[(recording[:, 0] >= first_frame) & (recording[:, 0] <= last_frame)]
    if len(part) < MIN_SECONDS * RATE // 2:
        return None
    ms = part[:, 1] - part[0, 1]
    keep = np.concatenate([[True], np.diff(ms) > 0])          # two readings with one timestamp: keep the first
    ms, part = ms[keep], part[keep]
    clock = np.arange(0, ms[-1], 1000 / RATE)
    return np.column_stack([np.interp(clock, ms, part[:, i]) for i in (2, 3, 4)])


def write_set(out_dir, set_id, accel_g, gyro_dps, placement):
    """Same files the watch writes: see recorder.py on the watch."""
    n = min(len(accel_g), len(gyro_dps))
    mg = np.clip(np.round(accel_g[:n] * 1000), -32768, 32767).astype("<i2")
    ddps = np.clip(np.round(gyro_dps[:n] * 10), -32768, 32767).astype("<i2")
    rows = np.hstack([mg, ddps])
    (out_dir / f"{set_id}.bin").write_bytes(rows.tobytes())
    meta = {"set_id": set_id, "count": len(rows), "rate_hz": float(RATE),
            "duration_ms": int(1000 * len(rows) / RATE), "late": 0,
            "format": "<6h", "accel_unit": "mg", "gyro_unit": "0.1 dps",
            "source": "mm-fit", "placement": placement}
    (out_dir / f"{set_id}.json").write_text(json.dumps(meta))


def main(mmfit_dir, out_dir):
    mmfit_dir, out_dir = Path(mmfit_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows, seen = [], {}
    for workout in sorted(p for p in mmfit_dir.iterdir() if p.is_dir()):
        w = workout.name
        labels = list(csv.reader(open(workout / f"{w}_labels.csv", newline="")))
        for side, wrist in (("l", "left wrist"), ("r", "right wrist")):
            acc_path, gyr_path = workout / f"{w}_sw_{side}_acc.npy", workout / f"{w}_sw_{side}_gyr.npy"
            if not (acc_path.exists() and gyr_path.exists()):
                continue
            acc, gyr = np.load(acc_path), np.load(gyr_path)
            for number, (first, last, reps, name) in enumerate(labels, 1):
                accel, gyro = cut(acc, int(first), int(last)), cut(gyr, int(first), int(last))
                if name not in EXERCISES or accel is None or gyro is None or len(accel) < MIN_SECONDS * RATE:
                    continue
                exercise, reps = EXERCISES[name], int(reps)
                if name in ALTERNATING:
                    if reps % 2:
                        continue
                    reps //= 2
                set_id = f"mm{w[1:]}{side}-{exercise}-{number:02d}"
                write_set(out_dir, set_id, accel / G, np.degrees(gyro), wrist)
                seen[exercise] = seen.get(exercise, 0) + 1
                rows.append([set_id, "positive", exercise, int(reps), f"mm-fit workout {w}, {wrist}, {name}"])
    rows.sort()
    with open(out_dir / "labels.csv", "w", newline="") as f:
        out = csv.writer(f)
        out.writerow(["set_id", "kind", "exercise", "true_reps", "notes"])
        out.writerows(rows)
    print(f"wrote {len(rows)} sets to {out_dir}")
    for exercise, n in sorted(seen.items()):
        print(f"  {exercise}: {n}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
