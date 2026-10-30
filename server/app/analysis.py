"""Rep detection for Gym Buddy sets. Runs on the laptop now, inside FastAPI later."""
import json
from pathlib import Path

import numpy as np
from scipy.signal import find_peaks


def load_set(bin_path):
    """Read a .bin and its .json. Returns (meta, t, accel in g, gyro in deg/s)."""
    bin_path = Path(bin_path)
    meta = json.loads(bin_path.with_suffix(".json").read_text())
    raw = np.fromfile(bin_path, dtype="<i2").reshape(-1, 6)
    accel = raw[:, :3] / 1000.0
    gyro = raw[:, 3:] / 10.0
    t = np.arange(len(raw)) / meta["rate_hz"]
    return meta, t, accel, gyro


def smooth(signal, rate_hz, window_s=0.2):
    """Moving average. Repeats the edge values so the ends don't dip toward 0."""
    win = max(1, int(window_s * rate_hz))
    padded = np.pad(signal, (win // 2, win - 1 - win // 2), mode="edge")
    return np.convolve(padded, np.ones(win) / win, mode="valid")


def busiest_axis(accel, rate_hz):
    """The axis (0 = x, 1 = y, 2 = z) whose smoothed signal moves the most."""
    return int(np.argmax([smooth(accel[:, i], rate_hz).std() for i in range(3)]))


def tops_point_up(signal, rate_hz, rest_s=0.5):
    """True if the top of each rep is a peak, False if it's a dip.

    A set starts with your arm resting at the bottom, so the tops are on
    whichever side of that resting level the rest of the set sits.
    """
    rest = np.median(signal[: max(1, int(rest_s * rate_hz))])
    return signal.mean() >= rest


def active_window(accel, rate_hz, margin_s=0.5, near_g=0.3):
    """(start, end) indexes of the part of a set where the reps happen.

    A set often starts and ends with the watch turned to face you, to press
    the button. The reps never use that position, so the window starts once
    the watch reaches a position from the middle of the set (plus a margin),
    and ends the same way. Sets without that lead-in are left as they are.
    """
    n = len(accel)
    if n < 4 * rate_hz:
        return 0, n                     # too short to tell, use all of it
    pos = np.column_stack([smooth(accel[:, i], rate_hz, 0.3) for i in range(3)])
    middle = pos[n // 4: 3 * n // 4]

    def gap(v):
        """Distance in g from v to the nearest position in the middle of the set."""
        return np.linalg.norm(middle - v, axis=1).min()

    edge = max(1, int(0.3 * rate_hz))
    margin = int(margin_s * rate_hz)
    start, end = 0, n
    if gap(pos[:edge].mean(axis=0)) > 2 * near_g:
        first = next(i for i in range(n) if gap(pos[i]) < near_g)
        start = min(first + margin, n // 4)
    if gap(pos[-edge:].mean(axis=0)) > 2 * near_g:
        last = next(i for i in range(n - 1, -1, -1) if gap(pos[i]) < near_g)
        end = max(last - margin, 3 * n // 4)
    return start, end


def count_reps(accel, rate_hz, axis=None, invert=None, trim=True,
               min_prominence=0.3, min_rep_s=0.3):
    """Find the top of each rep. Returns (peak indexes, smoothed signal, axis used).

    axis: None picks the axis that moves the most during the reps.
    invert: None works out from the start of the reps whether tops are peaks or dips.
    trim: ignore the start and end where the watch faces you (see active_window).
    Peak indexes count from the start of the whole set, so they line up with t.
    """
    start, end = active_window(accel, rate_hz) if trim else (0, len(accel))
    if axis is None:
        axis = busiest_axis(accel[start:end], rate_hz)
    sig = smooth(accel[:, axis], rate_hz)
    reps = sig[start:end]
    if invert is None:
        invert = not tops_point_up(reps, rate_hz)
    peaks, _ = find_peaks(-reps if invert else reps, prominence=min_prominence,
                          distance=max(1, int(min_rep_s * rate_hz)))
    return peaks + start, sig, axis


if __name__ == "__main__":
    # python -m app.analysis ..\recordings\practice\00004-a956cd.bin
    import sys
    import matplotlib.pyplot as plt

    meta, t, accel, gyro = load_set(sys.argv[1])
    peaks, sig, axis = count_reps(accel, meta["rate_hz"])
    start, end = active_window(accel, meta["rate_hz"])
    name = "xyz"[axis]
    print(f"{meta['set_id']}: {len(peaks)} reps on {name}, {meta['count']} readings at {meta['rate_hz']:.1f} Hz, late {meta['late']}")
    print(f"reps counted between {t[start]:.1f} s and {t[end - 1]:.1f} s")
    plt.axvspan(t[0], t[start], color="0.85", label="ignored")
    plt.axvspan(t[end - 1], t[-1], color="0.85")
    for i, n in enumerate("xyz"):
        plt.plot(t, accel[:, i], linewidth=1, label=n)
    plt.plot(t, sig, "k", linewidth=2, label=f"{name} smoothed")
    plt.plot(t[peaks], sig[peaks], "o", color="C3", label="counted rep")
    plt.xlabel("seconds")
    plt.ylabel("g")
    plt.title(f"{meta['set_id']}: {len(peaks)} reps")
    plt.legend()
    plt.show()
