"""From counted sets to something a person can use: pace, workouts, a suggestion.

Everything here is worked out from rows in the database (rep_times, reps,
times). Nothing is stored, so the rules can change without touching the data.
"""
import calendar
import time

WORKOUT_GAP_S = 30 * 60     # sets further apart than this belong to different workouts
STEADY_PCT = 10             # a set that slows less than this is "steady"
HARD_PCT = 25               # a first set that slows more than this was too heavy from the start
REPS_FELL = 0.6             # the last set has under 60% of the first set's reps: reps fell sharply

SUGGESTIONS = {
    "more": "That looked easy. Try a little more weight next time.",
    "stay": "Good effort. Stay at this weight.",
    "less": "Tough from the first set. Try a little less weight.",
}


def pace(rep_times):
    """Seconds from each rep to the next, and how much the last one slowed.

    slowdown_pct compares the last gap with the fastest gap of the set. It is
    None with fewer than three reps: one gap alone says nothing. A gap includes
    any pause between reps, so a rest before the last rep reads as slowing.
    """
    gaps = [round(b - a, 2) for a, b in zip(rep_times, rep_times[1:])]
    if len(gaps) < 2 or min(gaps) <= 0:
        return {"gaps": gaps, "fastest_s": None, "slowdown_pct": None}
    return {"gaps": gaps, "fastest_s": min(gaps), "slowdown_pct": round((gaps[-1] / min(gaps) - 1) * 100)}


def suggest(sets):
    """One of "more", "stay", "less", or None when there isn't enough to go on.

    sets: one exercise's sets from one workout, in the order they were done,
    each with "reps" and "slowdown_pct".
    Slowing at the end of a set is the point of training, so it is never
    flagged by itself. "more" comes from staying steady across sets.
    """
    counted = [s for s in sets if s["reps"]]
    if not counted:
        return None
    first, last = counted[0], counted[-1]
    slowdowns = [s["slowdown_pct"] for s in counted]
    if first["slowdown_pct"] is not None and first["slowdown_pct"] > HARD_PCT:
        return "less"
    if len(counted) >= 2 and last["reps"] < REPS_FELL * first["reps"]:
        return "less"
    if len(counted) < 2 or None in slowdowns:
        return None             # one set, or sets too short to measure: say nothing
    if len({s["reps"] for s in counted}) == 1 and max(slowdowns) <= STEADY_PCT:
        return "more"
    return "stay"


def when(row):
    """Unix seconds for a set: when the watch started it, or when it arrived if the watch didn't know the time."""
    if row.get("started_at"):
        return row["started_at"]
    return calendar.timegm(time.strptime(row["received_at"], "%Y-%m-%d %H:%M:%S"))


def iso(seconds):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))


def workouts(rows, labels):
    """Sets grouped into workouts, newest workout first.

    rows: sets from the database. labels: {exercise name: label for people}.
    A workout is a run of sets with less than WORKOUT_GAP_S between one and the next.
    """
    ordered = sorted(rows, key=lambda r: (when(r), r["set_id"]))
    groups = []
    for row in ordered:
        if groups and when(row) - when(groups[-1][-1]) < WORKOUT_GAP_S:
            groups[-1].append(row)
        else:
            groups.append([row])

    result = []
    for group in reversed(groups):
        exercises = []                  # in the order each was first done
        for row in group:
            entry = next((e for e in exercises if e["exercise"] == row["exercise"]), None)
            if entry is None:
                entry = {"exercise": row["exercise"],
                         "label": labels.get(row["exercise"], row["exercise"] or "No exercise picked"),
                         "sets": []}
                exercises.append(entry)
            entry["sets"].append({"set_id": row["set_id"], "reps": row["reps"],
                                  "slowdown_pct": pace(row["rep_times"])["slowdown_pct"]})
        for entry in exercises:
            kind = suggest(entry["sets"]) if entry["exercise"] else None
            entry["suggestion"] = {"kind": kind, "text": SUGGESTIONS[kind]} if kind else None
        start = when(group[0])
        end = when(group[-1]) + group[-1]["duration_ms"] // 1000
        result.append({
            "started_at": iso(start),
            "minutes": max(1, round((end - start) / 60)),
            "timed": all(row.get("started_at") for row in group),   # False: times are when the sets were synced
            "sets": len(group),
            "reps": sum(row["reps"] or 0 for row in group),
            "exercises": exercises,
        })
    return result
