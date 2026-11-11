"""Pace, suggestions and workouts: plain functions on made-up sets."""
import pytest

from app import coach


def set_(reps, slowdown=None, **more):
    return {"reps": reps, "slowdown_pct": slowdown, **more}


# ---- pace

def test_pace_is_the_time_from_each_rep_to_the_next():
    p = coach.pace([1.0, 2.0, 3.0, 4.2])
    assert p["gaps"] == [1.0, 1.0, 1.2] and p["usual_s"] == 1.0 and p["slowdown_pct"] == 20


def test_a_steady_set_has_no_slowdown():
    assert coach.pace([1.0, 2.5, 4.0, 5.5])["slowdown_pct"] == 0


@pytest.mark.parametrize("rep_times", [[], [1.0], [1.0, 2.0]])
def test_fewer_than_three_reps_is_too_few_to_judge(rep_times):
    assert coach.pace(rep_times)["slowdown_pct"] is None


def test_a_real_recorded_set():
    # Set 00004's rep times, as the analyzer found them.
    p = coach.pace([4.7, 7.32, 9.73, 12.07, 14.8, 17.61])
    assert p["gaps"] == [2.62, 2.41, 2.34, 2.73, 2.81] and p["usual_s"] == 2.62 and p["slowdown_pct"] == 7


def test_one_quick_rep_does_not_make_a_steady_set_look_slow():
    # Set 00009: a short first gap, then steady. Against the fastest gap this read as 38% slower.
    assert coach.pace([0, 1.25, 3.09, 4.85, 6.62, 8.34])["slowdown_pct"] == 0


def test_a_last_rep_faster_than_usual_is_not_a_negative_slowdown():
    assert coach.pace([0, 2.0, 4.0, 5.0])["slowdown_pct"] == 0


# ---- suggestions

def test_steady_sets_with_the_same_reps_suggest_more_weight():
    assert coach.suggest([set_(8, 4), set_(8, 7), set_(8, 9)]) == "more"


def test_a_last_set_that_slows_is_good_effort():
    assert coach.suggest([set_(8, 5), set_(8, 8), set_(8, 22)]) == "stay"


def test_slowing_at_the_end_is_never_a_reason_to_go_lighter():
    assert coach.suggest([set_(8, 5), set_(8, 12), set_(7, 60)]) == "stay"


def test_a_first_set_that_already_slows_a_lot_suggests_less():
    assert coach.suggest([set_(8, 40), set_(6, 30)]) == "less"
    assert coach.suggest([set_(8, 40)]) == "less"          # even with one set


def test_reps_falling_sharply_suggests_less():
    assert coach.suggest([set_(8, 5), set_(6, 10), set_(3, 12)]) == "less"


def test_fewer_reps_but_not_sharply_is_still_good_effort():
    assert coach.suggest([set_(8, 5), set_(8, 8), set_(6, 15)]) == "stay"


def test_different_rep_counts_are_never_called_easy():
    assert coach.suggest([set_(8, 2), set_(7, 3)]) == "stay"


@pytest.mark.parametrize("sets", [
    [],
    [set_(8, 5)],                           # one steady set: not enough to say anything
    [set_(0), set_(None)],                  # nothing counted
    [set_(2, None), set_(2, None)],         # too few reps to measure pace
])
def test_too_little_to_go_on_says_nothing(sets):
    assert coach.suggest(sets) is None


def test_the_edges_of_the_thresholds():
    assert coach.suggest([set_(8, 10), set_(8, 10)]) == "more"      # exactly 10% is still steady
    assert coach.suggest([set_(8, 11), set_(8, 5)]) == "stay"
    assert coach.suggest([set_(8, 25), set_(8, 5)]) == "stay"       # exactly 25% is not yet "too heavy"
    assert coach.suggest([set_(8, 26), set_(8, 5)]) == "less"
    assert coach.suggest([set_(10, 5), set_(6, 5)]) == "stay"       # exactly 60% is not yet "fell sharply"
    assert coach.suggest([set_(10, 5), set_(5, 5)]) == "less"


# ---- workouts

T0 = 1794300000                             # a time in November 2026
LABELS = {"curl": "Curl", "row": "Row"}


def row(n, exercise, reps, at, rep_times=(), started=True, duration_ms=20000):
    return {"set_id": "%05d-aaaaaa" % n, "exercise": exercise, "reps": reps, "rep_times": list(rep_times),
            "duration_ms": duration_ms, "started_at": at if started else None,
            "received_at": coach.iso(at).replace("T", " ").replace("Z", "")}


def test_sets_close_together_are_one_workout():
    rows = [row(1, "curl", 8, T0), row(2, "curl", 8, T0 + 120), row(3, "row", 6, T0 + 400)]
    (w,) = coach.workouts(rows, LABELS)
    assert w["sets"] == 3 and w["reps"] == 22 and w["started_at"] == coach.iso(T0)
    assert [e["label"] for e in w["exercises"]] == ["Curl", "Row"]
    assert [s["reps"] for s in w["exercises"][0]["sets"]] == [8, 8]


def test_a_gap_of_thirty_minutes_starts_a_new_workout_newest_first():
    rows = [row(1, "curl", 8, T0), row(2, "curl", 8, T0 + 29 * 60), row(3, "curl", 5, T0 + 59 * 60 + 1)]
    first, second = coach.workouts(rows, LABELS)
    assert first["sets"] == 1 and first["reps"] == 5            # the newest workout comes first
    assert second["sets"] == 2


def test_minutes_run_from_the_first_set_to_the_end_of_the_last():
    rows = [row(1, "curl", 8, T0), row(2, "curl", 8, T0 + 600, duration_ms=30000)]
    assert coach.workouts(rows, LABELS)[0]["minutes"] == 10      # 600 s + 30 s, rounded


def test_exercises_keep_the_order_they_were_first_done_and_sets_theirs():
    rows = [row(3, "curl", 6, T0 + 300), row(1, "curl", 8, T0), row(2, "row", 6, T0 + 100)]
    (w,) = coach.workouts(rows, LABELS)
    assert [e["exercise"] for e in w["exercises"]] == ["curl", "row"]
    assert [s["reps"] for s in w["exercises"][0]["sets"]] == [8, 6]


def test_each_exercise_gets_its_suggestion_with_the_sentence():
    steady = [1, 2, 3, 4, 5]
    rows = [row(1, "curl", 5, T0, steady), row(2, "curl", 5, T0 + 120, steady)]
    (w,) = coach.workouts(rows, LABELS)
    assert w["exercises"][0]["suggestion"] == {"kind": "more", "text": coach.SUGGESTIONS["more"]}


def test_sets_with_no_exercise_are_grouped_and_get_no_suggestion():
    steady = [1, 2, 3, 4, 5]
    rows = [row(1, None, 5, T0, steady), row(2, None, 5, T0 + 60, steady)]
    (w,) = coach.workouts(rows, LABELS)
    assert w["exercises"][0]["label"] == "No exercise picked" and w["exercises"][0]["suggestion"] is None


def test_a_set_without_a_start_time_uses_when_it_arrived_and_says_so():
    rows = [row(1, "curl", 8, T0, started=False), row(2, "curl", 8, T0 + 60, started=False)]
    (w,) = coach.workouts(rows, LABELS)
    assert w["timed"] is False and w["sets"] == 2
    assert coach.workouts([row(1, "curl", 8, T0)], LABELS)[0]["timed"] is True


def test_no_sets_no_workouts():
    assert coach.workouts([], LABELS) == []
