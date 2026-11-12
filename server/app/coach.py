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
PUSHED_PCT = 25             # a set whose last rep slowed this much was pushed hard (close to what you had in you)

SUGGESTIONS = {
    "more": "That looked easy. Try a little more weight next time.",
    "stay": "Good effort. Stay at this weight.",
    "less": "Tough from the first set. Try a little less weight.",
}
# The same advice when the weight is known: it can name a number.
SUGGESTIONS_WITH_WEIGHT = {
    "more": "That looked easy. Try {next} lb next time.",
    "stay": "Good effort. Stay at {now} lb.",
    "less": "Tough from the first set. Try {next} lb.",
}
SMALL_STEP_LB, BIG_STEP_LB, BIG_FROM_LB = 2.5, 5, 50     # dumbbells go up in 2.5s, heavier loads in 5s


def pounds(weight):
    """25.0 -> "25", 27.5 -> "27.5"."""
    return ("%g" % round(weight, 1))


def sentence(kind, weight=None):
    """The suggestion in words. weight: what the last set used, in pounds, if the wearer said."""
    if not weight:
        return SUGGESTIONS[kind]
    step = BIG_STEP_LB if weight >= BIG_FROM_LB else SMALL_STEP_LB
    change = {"more": step, "stay": 0, "less": -step}[kind]
    if weight + change <= 0:
        return SUGGESTIONS[kind]
    return SUGGESTIONS_WITH_WEIGHT[kind].format(now=pounds(weight), next=pounds(weight + change))


def pace(rep_times):
    """Seconds from each rep to the next, and how much the last one slowed.

    slowdown_pct compares the last gap with the usual gap of the set: the
    middle one when they are sorted. The middle, not the fastest, because one
    quick rep (often the first) would make every steady set look like it slowed.
    It is None with fewer than three reps: one gap alone says nothing. A gap
    includes any pause between reps, so a rest before the last rep reads as slowing.
    """
    gaps = [round(b - a, 2) for a, b in zip(rep_times, rep_times[1:])]
    if len(gaps) < 2 or min(gaps) <= 0:
        return {"gaps": gaps, "usual_s": None, "slowdown_pct": None}
    usual = sorted(gaps)[(len(gaps) - 1) // 2]
    return {"gaps": gaps, "usual_s": usual, "slowdown_pct": max(0, round((gaps[-1] / usual - 1) * 100))}


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
            slowdown = pace(row["rep_times"])["slowdown_pct"]
            entry["sets"].append({"set_id": row["set_id"], "reps": row["reps"],
                                  "slowdown_pct": slowdown, "pushed": slowdown is not None and slowdown >= PUSHED_PCT,
                                  "weight": row.get("weight"), "at": iso(when(row)),
                                  "seconds": round(row["duration_ms"] / 1000)})
        for entry in exercises:
            kind = suggest(entry["sets"]) if entry["exercise"] else None
            weights = [s["weight"] for s in entry["sets"] if s["weight"]]
            entry["suggestion"] = {"kind": kind, "text": sentence(kind, weights[-1] if weights else None)} if kind else None
        every = [s for entry in exercises for s in entry["sets"]]
        start = when(group[0])
        end = when(group[-1]) + group[-1]["duration_ms"] // 1000
        result.append({
            "started_at": iso(start),
            "minutes": max(1, round((end - start) / 60)),
            "timed": all(row.get("started_at") for row in group),   # False: times are when the sets were synced
            "sets": len(group),
            "reps": sum(row["reps"] or 0 for row in group),
            # The headline: how many sets were pushed hard, out of those long enough to judge (3 reps or more).
            "effort": {"pushed": sum(s["pushed"] for s in every),
                       "judged": sum(s["slowdown_pct"] is not None for s in every)},
            "advice": advice([entry["suggestion"]["kind"] for entry in exercises if entry["suggestion"]]),
            "exercises": exercises,
        })
    return result


def advice(kinds):
    """The exercises' suggestions rolled into one sentence for the top of the workout, or None with nothing to say.

    kinds: the "more" / "stay" / "less" of each exercise that has a suggestion.
    """
    def some(n):
        return "%d exercise%s" % (n, "" if n == 1 else "s")
    more, less = kinds.count("more"), kinds.count("less")
    if more and less:
        return "Go heavier on %s and ease off on %s." % (some(more), some(less))
    if more:
        return "Go heavier on %s next time." % some(more)
    if less:
        return "Ease off on %s next time." % some(less)
    return "Stay at these weights next time." if kinds else None


def progress(rows, labels):
    """Each exercise across workouts, oldest first: is it going up?

    Built from workouts(), so "a workout" means the same thing on every screen.
    One entry per named exercise that has sets, in the order of `labels`.
    change compares the newest workout's total reps with the one before it;
    None when there is nothing to compare with.
    """
    history = {name: [] for name in labels}
    for workout in reversed(workouts(rows, labels)):        # oldest first
        for entry in workout["exercises"]:
            if entry["exercise"] not in history:
                continue
            counts = [s["reps"] or 0 for s in entry["sets"]]
            weights = [s["weight"] for s in entry["sets"] if s["weight"]]
            history[entry["exercise"]].append({
                "started_at": workout["started_at"], "timed": workout["timed"],
                "sets": len(counts), "reps": sum(counts), "best": max(counts),
                "weight": max(weights) if weights else None})
    result = []
    for name, points in history.items():
        if points:
            change = points[-1]["reps"] - points[-2]["reps"] if len(points) > 1 else None
            result.append({"exercise": name, "label": labels[name], "workouts": points, "change": change})
    return result
