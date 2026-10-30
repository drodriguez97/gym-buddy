from pathlib import Path

import numpy as np
import pytest

from app.analysis import count_reps, load_set

RATE = 100
FIXTURES = Path(__file__).parent / "fixtures"


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


@pytest.mark.parametrize("set_id, true_reps", [
    ("00003-36d8f2", 6),   # rubber band on wrist
    ("00004-a956cd", 6),   # strap, light weight
    ("00007-130966", 6),   # strap, medium weight
])
def test_recorded_curls(set_id, true_reps):
    # Counts come from recordings/labels.csv.
    meta, _, accel, _ = load_set(FIXTURES / f"{set_id}.bin")
    peaks, _, _ = count_reps(accel, meta["rate_hz"])
    assert len(peaks) == true_reps
