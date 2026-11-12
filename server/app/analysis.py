"""Rep detection for Gym Buddy sets. Runs on the laptop now, inside FastAPI later."""
import json
from pathlib import Path

import numpy as np
from scipy.ndimage import maximum_filter1d
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


def rep_period(signal, rate_hz, shortest_s=0.6, longest_s=6.0):
    """Seconds per rep, from how well the signal lines up with a shifted copy of itself.

    None if nothing repeats clearly (holding still, random movement).
    """
    period, strength = rep_rhythm(signal, rate_hz, shortest_s, longest_s)
    return period if strength >= 0.3 else None


def rep_rhythm(signal, rate_hz, shortest_s=0.6, longest_s=6.0):
    """(seconds per rep, how regular it is) from the signal's match with a
    shifted copy of itself. Regularity is 0 to 1: curls and swings score
    0.7-0.9, fidgeting between sets scores under 0.2, so it tells exercise
    from rest. Returns (None, 0) if nothing repeats at all.
    """
    x = signal - signal.mean()
    match = np.correlate(x, x, mode="full")[len(x) - 1:]
    if match[0] == 0:
        return None, 0.0
    match = match / match[0]                  # 1.0 = a perfect repeat
    lo, hi = int(shortest_s * rate_hz), int(longest_s * rate_hz)
    shifts, _ = find_peaks(match[lo:hi], height=0)
    if not len(shifts):
        return None, 0.0
    best = shifts[np.argmax(match[lo:hi][shifts])]
    return (best + lo) / rate_hz, float(match[lo:hi][best])


def is_linear(accel, axis_signal, rate_hz):
    """True if the reps push the watch in a line (press, row), False if they tilt it (curl).

    Tilting only moves gravity between the axes, so the total stays near 1 g.
    Pushing changes the total too, about as much as it changes the busy axis.
    """
    total = smooth(np.linalg.norm(accel, axis=1), rate_hz)
    return total.std() > 0.6 * axis_signal.std()


def total_wobble(accel, rate_hz):
    """How hard the watch is really pushed, in g (std of the smoothed |accel|).

    Tilting only moves gravity between the axes, so it cancels out of the
    total. Reps that carry a weight push the watch (0.3-0.5 g on Dan's sets);
    a walking arm swing mostly tilts (0.1-0.2 g); a hand on a bar barely
    moves at all (0.03 g).
    """
    return smooth(np.linalg.norm(accel, axis=1), rate_hz).std()


def swing_size(signal):
    """How far the signal travels, top to bottom, ignoring the outliers (g)."""
    return np.percentile(signal, 98) - np.percentile(signal, 2)


def dominant_hz(signal, rate_hz, min_hz=0.3):
    """The strongest repeating beat in the signal, in beats per second.

    Reps come at 0.5-0.9 per second. Footsteps come at about 2 per second,
    which a rep never does. Measured on the raw signal, not on counted peaks:
    the peak spacing rule drops every other footstep and makes walking look
    rep-paced.
    """
    x = signal - signal.mean()
    freqs = np.fft.rfftfreq(len(x), 1 / rate_hz)
    power = np.abs(np.fft.rfft(x)) ** 2
    power[freqs < min_hz] = 0                 # ignore slow drift
    return freqs[np.argmax(power)]


def roll_angle(gyro, rate_hz, axis=None, drift_s=3.0):
    """Wrist angle in degrees from the gyro, with the slow drift removed.

    A gyro reads turning speed. Adding it up over time gives the angle, which
    for a pull-up rises and falls once per rep, like a tilt would. The running
    sum also drifts, so a drift_s-second average is subtracted back out.
    Returns (angle, axis used). axis None picks the gyro axis that turns most.
    """
    if axis is None:
        axis = int(np.argmax(gyro.std(axis=0)))
    angle = np.cumsum(gyro[:, axis]) / rate_hz
    angle = angle - smooth(angle, rate_hz, drift_s)
    return smooth(angle, rate_hz, 0.2), axis


def anchored_angle(gyro, rate_hz, accel=None, max_push=0.3, push_ratio=6, settle_s=0.3):
    """The wrist angle count_anchored counts on, with the transitions at the ends
    taken out (see count_anchored). Returns (angle in degrees, the readings
    treated as a transition, or None when accel wasn't given)."""
    moving = None
    if accel is not None:
        push = np.abs(smooth(np.linalg.norm(accel, axis=1), rate_hz) - 1.0)
        limit = max(max_push, push_ratio * np.percentile(push, 75))
        width = max(1, int(2 * settle_s * rate_hz))
        moving = maximum_filter1d((push > limit).astype(int), size=width) > 0
        n = len(moving)
        moving[n // 4: n - n // 4] = False       # transitions happen at the ends
        gyro = gyro.copy()
        gyro[moving] = 0
    angle, _ = roll_angle(gyro, rate_hz)
    return angle, moving


def count_anchored(gyro, rate_hz, accel=None, min_prominence_deg=8, min_rep_s=0.6,
                   min_lift=0.5, max_push=0.3, push_ratio=6, settle_s=0.3):
    """Count reps for an anchored hand (pull-ups, push-ups): one top per wrist roll.

    Same peak logic as count_reps, run on the wrist angle instead of the
    accelerometer. Getting into and out of position (dropping to a knee,
    jumping off the bar) rolls the wrist far more than a rep does and shoves
    the watch, which a rep on an anchored hand barely does. So when accel is
    given, a shove in the first or last quarter of the set (|accel| more than
    max_push from 1 g and push_ratio times the set's own usual push, plus
    settle_s either side) is treated as a transition: its gyro is zeroed
    before integrating, so it can't fold into the last rep's hill, and no top
    is counted there. Only the edges are checked because on a forearm a
    push-up itself pushes harder than on the wrist, and masking mid-set
    cost 10 points on RecoFit's push-ups. Returns peak indexes into gyro.
    """
    angle, moving = anchored_angle(gyro, rate_hz, accel, max_push, push_ratio, settle_s)
    period = rep_period(angle, rate_hz)
    gap = max(min_rep_s, 0.7 * period if period else 0)
    peaks, _ = find_peaks(angle, prominence=min_prominence_deg, distance=max(1, int(gap * rate_hz)))
    if moving is not None and len(peaks):
        peaks = peaks[~moving[peaks]]
    if len(peaks) and min_lift:
        lift = angle[peaks] - np.median(angle)
        peaks = peaks[lift >= min_lift * np.median(lift)]
    peaks = edge_reps(angle, peaks, min_prominence_deg, min_lift)      # the first and last rep, as in count_reps
    if moving is not None and len(peaks):
        peaks = peaks[~moving[peaks]]
    return peaks


# Exercises where the hand holds something fixed (bar, floor) and the body
# moves. The watch barely travels, so reps are counted from the wrist roll.
ANCHORED_EXERCISES = {"pullup", "chinup", "dip", "pushup", "pushup_knee", "hang"}

THRESHOLDS = dict(
    max_rhythm_hz=1.5,       # faster beats than this are footsteps, not reps
    anchored_wobble=0.08,    # below this push the hand is holding something fixed
    anchored_swing=0.6,
    swing_wobble=0.2,        # below this push with a modest swing is an arm swinging
    swing_max=1.2,           # a curl is tilt too, but swings the full 2 g
    min_regularity=0.3,      # below this nothing repeats: rest, fidgeting
    locomotion_s=150,        # very regular for longer than this is a walk/jog/machine
    locomotion_regularity=0.7,
)


def describe_set(accel, rate_hz, gyro=None, trim=True, exercise=None, **kw):
    """The measurements and which rule they trigger. Used by count_reps, the
    plot script and the scorecard, so a wrong count comes with a reason.

    exercise: the name the user picked in the dashboard, if any. A known
    anchored exercise is counted on the gyro, any other named exercise on the
    accelerometer, and the guesses between arm swing / anchored / reps are
    skipped: the user's word beats the guess. The no-rhythm and footstep
    checks still apply either way, so a mislabeled rest or walk still counts 0.

    Returns a dict: wobble, swing, rhythm_hz, regularity, seconds, kind (one of
    'reps', 'anchored', 'footsteps', 'arm swing', 'no rhythm') and the thresholds.
    """
    th = dict(THRESHOLDS)
    th.update(kw)
    start, end = active_window(accel, rate_hz) if trim else (0, len(accel))
    axis = busiest_axis(accel[start:end], rate_hz)
    reps = smooth(accel[:, axis], rate_hz)[start:end]
    wobble = total_wobble(accel[start:end], rate_hz)
    swing = swing_size(reps)
    rhythm = dominant_hz(reps, rate_hz)
    seconds = (end - start) / rate_hz
    _, regularity = rep_rhythm(reps, rate_hz)
    if gyro is not None:
        # An anchored hand barely moves the accelerometer; its rhythm is in the wrist roll.
        angle, _ = roll_angle(gyro[start:end], rate_hz)
        regularity = max(regularity, rep_rhythm(angle, rate_hz)[1])
    anchored = wobble < th["anchored_wobble"] and swing < th["anchored_swing"]
    if exercise is not None:
        anchored = exercise in ANCHORED_EXERCISES
    if rhythm > th["max_rhythm_hz"]:
        kind = "footsteps"
    elif seconds > th["locomotion_s"] and regularity > th["locomotion_regularity"]:
        kind = "footsteps"                    # nobody does a 3-minute set; treadmills and ellipticals do
    elif anchored:
        kind = "anchored"
    elif regularity < th["min_regularity"]:
        kind = "no rhythm"
    elif exercise is None and wobble < th["swing_wobble"] and swing < th["swing_max"]:
        kind = "arm swing"
    else:
        kind = "reps"
    return dict(wobble=wobble, swing=swing, rhythm_hz=rhythm, regularity=regularity,
                seconds=seconds, kind=kind, start=start, end=end, axis=axis, **th)


def gap_reps(y, peaks, rate_hz, min_prominence, min_lift, wide=1.6, near=0.6, weaker=0.5):
    """Add a rep in the middle of a set that the usual test wrongly drops.

    Sometimes the dip between two reps is shallow (the weight isn't lowered
    all the way, or the wearer pauses), so a top that rises as high as the
    others doesn't stand min_prominence clear and is skipped. That leaves a
    hole about two reps long between its neighbours.

    So where two counted reps are more than `wide` rep-lengths apart, a top
    between them counts if it rises like the other reps (min_lift), stands
    at least `weaker` x min_prominence clear, and is at least `near`
    rep-lengths from every rep already counted. The timing is the evidence:
    a weak top is only believed where a rep is due.
    """
    if len(peaks) < 3:
        return peaks
    level = np.median(y)
    lift = np.median(y[peaks] - level)
    period = float(np.median(np.diff(peaks)))
    weak, _ = find_peaks(y, prominence=weaker * min_prominence, distance=max(1, int(near * period)))
    found = list(peaks)
    for i in weak:
        left = max((p for p in found if p < i), default=None)
        right = min((p for p in found if p > i), default=None)
        if left is None or right is None or i in found:
            continue                                  # the ends are edge_reps' job
        if right - left < wide * period or min(i - left, right - i) < near * period:
            continue
        if y[i] - level >= min_lift * lift:
            found.append(i)
            found.sort()
    return np.array(found)


def edge_reps(y, peaks, min_prominence, min_lift, tolerance=0.35):
    """Add the first and last rep when the usual test wrongly drops them.

    A rep counts when its top stands min_prominence clear of the dips on BOTH
    sides. The first rep starts from rest and the last one ends in rest, so
    each has a real dip on one side only and often fails that test, which
    left the count one short (157 of RecoFit's 562 exercise sets).

    So step outward from the first and last counted rep, one rep-length at a
    time. If the highest point about one rep-length away (within tolerance)
    is a real top, rises like the other reps (min_lift) and stands
    min_prominence clear of the dip on its inner side, it is a rep. Stops at
    the first step that finds none. Only looks inside y, which is the trimmed
    window: reaching past it counts picking the weights up as reps.
    """
    if len(peaks) < 2:
        return peaks
    level = np.median(y)
    lift = np.median(y[peaks] - level)
    period = float(np.median(np.diff(peaks)))        # readings per rep, from the reps already found
    reach = int(period)
    peaks = list(peaks)
    for sign in (-1, 1):                             # -1: before the first rep, +1: after the last
        while True:
            anchor = peaks[0] if sign < 0 else peaks[-1]
            lo, hi = sorted((anchor + sign * int((1 - tolerance) * period),
                             anchor + sign * int((1 + tolerance) * period)))
            lo, hi = max(lo, 0), min(hi, len(y) - 1)
            if hi - lo < 3:
                break
            i = lo + int(np.argmax(y[lo:hi + 1]))
            if i in (lo, hi):
                break                                # highest at the border of the search: a slope, not a top
            inner = y[i:i + reach + 1] if sign < 0 else y[max(0, i - reach):i + 1]
            if y[i] - level < min_lift * lift or y[i] - inner.min() < min_prominence:
                break
            if sign < 0:
                peaks.insert(0, i)
            else:
                peaks.append(i)
    return np.array(peaks)


def count_reps(accel, rate_hz, gyro=None, axis=None, invert=None, trim=True,
               exercise=None, min_prominence=0.3, min_rep_s=0.3, min_lift=0.6, **thresholds):
    """Find the top of each rep. Returns (peak indexes, smoothed signal, axis used).

    Checks run first, in this order (see describe_set and THRESHOLDS):
      beat faster than 1.5/s, or very regular for over 150 s -> footsteps, no reps
      wobble and swing both tiny (or a known anchored exercise) -> count wrist roll on the gyro
      nothing repeats (regularity under 0.3)                   -> rest or fidgeting, no reps
      wobble small and swing under 1.2 g                        -> arm swinging while walking, no reps
    Anything else is counted on the accelerometer as before. A curl is mostly
    tilt too, but it swings the full 2 g, which is what swing_max protects.

    exercise: what the user picked in the dashboard; skips the guesses (see describe_set).
    gyro: needed for the anchored case; without it that case counts 0.
    axis: None picks the axis that moves the most during the reps.
    invert: None works out whether the tops are peaks or dips (see below).
    trim: ignore the start and end where the watch faces you (see active_window).
    min_lift: drop a top that rises less than this share of a typical rep,
        e.g. the bump from getting into position before the first rep.
    Weak tops get a second look afterwards where a rep is due: in a hole
    between two reps (gap_reps) and before the first / after the last (edge_reps).
    Peak indexes count from the start of the whole set, so they line up with t.
    """
    info = describe_set(accel, rate_hz, gyro, trim, exercise, **thresholds)
    start, end = info["start"], info["end"]
    if axis is None:
        axis = info["axis"]
    sig = smooth(accel[:, axis], rate_hz)
    reps = sig[start:end]
    none = np.array([], dtype=int)
    if info["kind"] in ("footsteps", "arm swing", "no rhythm"):
        return none, sig, axis
    if info["kind"] == "anchored":
        if gyro is None:
            return none, sig, axis
        return count_anchored(gyro[start:end], rate_hz, accel[start:end]) + start, sig, axis
    if invert is None:
        if is_linear(accel[start:end], reps, rate_hz):
            # Press or row: the top of a rep is where the weight slows down
            # and turns back, a push downward. If the axis points up
            # (median > 0) that's a dip, if it points down it's a peak.
            invert = bool(np.median(reps) > 0)
        else:
            # Curl: the tops are the short trips away from the resting level.
            mid = np.median(reps)
            invert = (np.percentile(reps, 98) - mid) < (mid - np.percentile(reps, 2))
    y = -reps if invert else reps
    # One top per rep: two tops closer than 70% of a rep are the same rep.
    period = rep_period(y, rate_hz)
    gap = max(min_rep_s, 0.7 * period if period else 0)
    peaks, _ = find_peaks(y, prominence=min_prominence, distance=max(1, int(gap * rate_hz)))
    if len(peaks) and min_lift:
        lift = y[peaks] - np.median(y)
        peaks = peaks[lift >= min_lift * np.median(lift)]
    peaks = gap_reps(y, peaks, rate_hz, min_prominence, min_lift)
    peaks = edge_reps(y, peaks, min_prominence, min_lift)
    return peaks + start, sig, axis


if __name__ == "__main__":
    # python -m app.analysis ..\recordings\practice\00004-a956cd.bin
    import sys
    import matplotlib.pyplot as plt

    meta, t, accel, gyro = load_set(sys.argv[1])
    peaks, sig, axis = count_reps(accel, meta["rate_hz"], gyro)
    info = describe_set(accel, meta["rate_hz"], gyro)
    start, end = info["start"], info["end"]
    name = "xyz"[axis]
    print(f"{meta['set_id']}: {len(peaks)} reps on {name}, {meta['count']} readings at {meta['rate_hz']:.1f} Hz, late {meta['late']}")
    print(f"reps counted between {t[start]:.1f} s and {t[end - 1]:.1f} s")
    print(f"looks like {info['kind']}: wobble {info['wobble']:.2f} g, swing {info['swing']:.2f} g, "
          f"rhythm {info['rhythm_hz']:.2f}/s, regularity {info['regularity']:.2f}, {info['seconds']:.0f} s")
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


def trace_signal(accel, rate_hz, gyro=None, exercise=None):
    """The signal count_reps looked at for this set, for drawing. Returns (signal, unit).

    Most exercises are counted on the accelerometer axis that moves most ("g").
    An anchored hand (pull-ups, push-ups) is counted on the wrist angle
    ("degrees"); its accelerometer line is nearly flat and would show nothing.
    The angle only exists inside the counted window, so it is 0 outside it.
    """
    info = describe_set(accel, rate_hz, gyro, True, exercise)
    if info["kind"] == "anchored" and gyro is not None:
        start, end = info["start"], info["end"]
        angle, _ = anchored_angle(gyro[start:end], rate_hz, accel[start:end])
        full = np.zeros(len(accel))
        full[start:end] = angle
        return full, "degrees"
    return smooth(accel[:, info["axis"]], rate_hz), "g"
