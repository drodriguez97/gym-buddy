import csv
from pathlib import Path

import numpy as np
import pytest

from app.analysis import count_reps, describe_set, load_set

RATE = 100
FIXTURES = Path(__file__).parent / "fixtures"
LABELS = Path(__file__).parents[2] / "recordings" / "labels.csv"


def labeled_sets():
    """Every row of labels.csv whose .bin and .json are in fixtures/."""
    rows = []
    with open(LABELS, newline="") as f:
        for row in csv.DictReader(f):
            if (FIXTURES / f"{row['set_id']}.bin").exists():
                rows.append(pytest.param(row, id=f"{row['kind']}-{row['exercise']}-{row['set_id'][:5]}"))
    return rows


def fake_set(seconds, wave, axis=1, noise=0.05, seed=0):
    """accel array: one axis follows wave(t) plus noise, the others are noise.

    axis defaults to 1 (y), the axis that tilts during a curl on your wrist.
    """
    t = np.arange(0, seconds, 1 / RATE)
    rng = np.random.default_rng(seed)
    accel = rng.normal(0, noise, (len(t), 3))
    accel[:, axis] += wave(t)
    return accel


def curls(reps, period_s=2.0, axis=1, flip=False):
    """Arm hangs at -1 g for 1 s, does `reps` curls up to +1 g, then hangs again."""
    def wave(t):
        x = np.full_like(t, -1.0)
        active = (t >= 1) & (t < 1 + reps * period_s)
        x[active] = -np.cos(2 * np.pi * (t[active] - 1) / period_s)
        return -x if flip else x
    return fake_set(reps * period_s + 2, wave, axis=axis)


def test_five_curls_count_five():
    peaks, _, axis = count_reps(curls(5), RATE)
    assert len(peaks) == 5
    assert axis == 1


def test_fast_curls_still_count():
    peaks, _, _ = count_reps(curls(8, period_s=0.8), RATE)
    assert len(peaks) == 8


def test_picks_the_axis_that_moves():
    peaks, _, axis = count_reps(curls(5, axis=2), RATE)
    assert axis == 2
    assert len(peaks) == 5


def test_stick_worn_the_other_way_counts_the_same():
    # Flipped on the wrist, the tops become dips. The count must not change.
    peaks, _, _ = count_reps(curls(5, flip=True), RATE)
    assert len(peaks) == 5


def test_holding_still_counts_zero():
    peaks, _, _ = count_reps(fake_set(10, lambda t: -np.ones_like(t)), RATE)
    assert len(peaks) == 0


def test_small_fast_wobble_counts_zero():
    # Roughly what walking looks like: small, 2 per second.
    wobble = lambda t: -1 + 0.1 * np.sin(2 * np.pi * 2 * t)
    peaks, _, _ = count_reps(fake_set(10, wobble), RATE)
    assert len(peaks) == 0


def test_watch_facing_you_at_start_and_end_is_ignored():
    # 2 s with the watch facing up (z = +1) to press the button, then the arm
    # hangs (x = -1) for 5 curls on x, then the watch faces up again.
    t = np.arange(0, 16, 1 / RATE)
    rng = np.random.default_rng(1)
    accel = rng.normal(0, 0.05, (len(t), 3))
    facing = (t < 2) | (t >= 14)
    accel[facing, 2] += 1.0
    hanging = ~facing
    x = np.full_like(t, -1.0)
    active = (t >= 3) & (t < 13)
    x[active] = -np.cos(2 * np.pi * (t[active] - 3) / 2.0)
    accel[hanging, 0] += x[hanging]
    peaks, _, axis = count_reps(accel, RATE)
    assert axis == 0
    assert len(peaks) == 5


def test_every_fixture_is_labeled():
    # A fixture with no row in labels.csv is silently skipped by the test below.
    with open(LABELS, newline="") as f:
        labeled = {row["set_id"] for row in csv.DictReader(f)}
    missing = sorted(p.stem for p in FIXTURES.glob("*.bin") if p.stem not in labeled)
    assert not missing, f"add these to labels.csv: {missing}"


@pytest.mark.parametrize("row", labeled_sets())
def test_recorded_sets(row):
    # positive: the count must match. negative: must be 0. edge: must match, and
    # tells you which awkward situation broke it when it fails.
    # Too few on a positive set is a false negative, anything on a negative set
    # is a false positive; the message says which so the scorecard is readable.
    # Positive sets are counted the way the dashboard will use them: told the
    # exercise. Negatives are not, because nobody labels a walk.
    meta, _, accel, gyro = load_set(FIXTURES / f"{row['set_id']}.bin")
    exercise = row["exercise"] if row["kind"] != "negative" else None
    peaks, _, _ = count_reps(accel, meta["rate_hz"], gyro, exercise=exercise)
    info = describe_set(accel, meta["rate_hz"], gyro, exercise=exercise)
    want, got = int(row["true_reps"]), len(peaks)
    error = "false positive" if row["kind"] == "negative" else ("false negative" if got < want else "over-count")
    assert got == want, (f"{error}: {row['exercise']} {row['set_id'][:5]} counted {got}, expected {want} "
                         f"(looks like {info['kind']}: wobble {info['wobble']:.2f} swing {info['swing']:.2f} "
                         f"rhythm {info['rhythm_hz']:.2f}/s) {row['notes']}")


def measurements(set_id):
    meta, _, accel, gyro = load_set(FIXTURES / f"{set_id}.bin")
    return describe_set(accel, meta["rate_hz"], gyro)


# These lock in the numbers the thresholds were chosen from, so a change to
# smooth() or active_window() that moves them shows up here by name, not as a
# pull-up set quietly failing again.

def test_footsteps_beat_faster_than_any_rep():
    for set_id in ("00022-6371dc", "00023-c9ccd7", "00024-c365e4", "00025-436afd"):
        assert measurements(set_id)["rhythm_hz"] > 1.8, set_id
    for set_id in ("00016-929d8f",):                       # the fastest rep set
        assert measurements(set_id)["rhythm_hz"] < 1.0, set_id


def test_pullups_barely_push_the_watch():
    for set_id in ("00017-2aa0e3", "00018-f6719e"):
        m = measurements(set_id)
        assert m["wobble"] < 0.05 and m["swing"] < 0.5, set_id
        assert m["kind"] == "anchored"


def test_pushup_transitions_are_not_reps():
    # Set 26: dropping to a knee before and standing up after rolled the wrist
    # more than any rep and counted as reps 1 and 8 until transitions were masked.
    meta, _, accel, gyro = load_set(FIXTURES / "00026-2ffe6b.bin")
    peaks, _, _ = count_reps(accel, meta["rate_hz"], gyro, exercise="pushup")
    assert len(peaks) == 7
    assert peaks[0] / meta["rate_hz"] > 3.0        # nothing counted in the drop-down at 1.5 s
    assert peaks[-1] / meta["rate_hz"] < 12.5      # nothing counted in the stand-up at 12.8 s


def test_dumbbell_reps_really_push_the_watch():
    for set_id in ("00009-8a9712", "00012-38b5e5", "00013-db6df8"):
        m = measurements(set_id)
        assert m["wobble"] > 0.25, set_id
        assert m["kind"] == "reps"


def test_walking_is_arm_swing_or_no_rhythm():
    # A slow walk is either a small arm swing or, when the pace wanders, no
    # clear rhythm at all. Both count 0; neither may look like reps.
    for set_id in ("00020-c98ef8", "00021-813c5a"):
        assert measurements(set_id)["kind"] in ("arm swing", "no rhythm"), set_id


def test_named_exercise_skips_the_guess():
    # The user picked "pullup" in the dashboard: count the wrist roll even if
    # the accelerometer guess would have said otherwise, and vice versa.
    meta, _, accel, gyro = load_set(FIXTURES / "00018-f6719e.bin")
    peaks, _, _ = count_reps(accel, meta["rate_hz"], gyro, exercise="pullup")
    assert len(peaks) == 6
    meta, _, accel, gyro = load_set(FIXTURES / "00013-db6df8.bin")
    peaks, _, _ = count_reps(accel, meta["rate_hz"], gyro, exercise="row_underhand")
    assert len(peaks) == 6


def test_named_exercise_still_rejects_rest_and_footsteps():
    # A mislabeled jog or a rest period must not become reps just because a
    # name was attached.
    meta, _, accel, gyro = load_set(FIXTURES / "00023-c9ccd7.bin")
    peaks, _, _ = count_reps(accel, meta["rate_hz"], gyro, exercise="shoulder_press")
    assert len(peaks) == 0
    peaks, _, _ = count_reps(fake_set(10, lambda t: -np.ones_like(t)), RATE, exercise="curl")
    assert len(peaks) == 0


# ---- RecoFit benchmark: 821 sets from 94 people (recordings/recofit). Slow,
# so it only runs with:  python -m pytest -m benchmark
# Floors are where the analyzer stood on 2026-10-31. A change that drops one
# is a regression, however much it helps something else.

RECOFIT = Path(__file__).parents[2] / "recordings" / "recofit"
FLOORS = {"curl": 0.90, "curl_two_arm": 0.90, "kettlebell_swing": 0.95, "lateral_raise": 0.80,
          "plank": 0.95, "device_on_table": 0.95, "non_exercise": 0.65, "elliptical": 0.90, "jog": 0.90,
          "triceps_overhead": 0.80, "back_fly": 0.85, "row_deadlift": 0.90, "walking": 0.85}


@pytest.mark.benchmark
@pytest.mark.skipif(not (RECOFIT / "labels.csv").exists(), reason="unzip recordings/recofit_sets.zip first")
def test_recofit_floors():
    within = {}
    with open(RECOFIT / "labels.csv", newline="") as f:
        for row in csv.DictReader(f):
            if row["exercise"] not in FLOORS:
                continue
            meta, _, accel, gyro = load_set(RECOFIT / f"{row['set_id']}.bin")
            exercise = row["exercise"] if row["kind"] == "positive" else None
            peaks, _, _ = count_reps(accel, meta["rate_hz"], gyro, exercise=exercise)
            within.setdefault(row["exercise"], []).append(abs(len(peaks) - int(row["true_reps"])) <= 1)
    below = {ex: f"{np.mean(v):.0%} < {FLOORS[ex]:.0%}" for ex, v in within.items() if np.mean(v) < FLOORS[ex]}
    assert not below, f"below the floor: {below}"
