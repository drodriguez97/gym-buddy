r"""Run count_reps over every labeled set and print how it did, by exercise.

    python scripts/scorecard.py ..\recordings\labels.csv tests\fixtures
    python scripts/scorecard.py ..\recordings\recofit\labels.csv ..\recordings\recofit

Per exercise: how many sets, the share counted within +-1 of the truth
(RecoFit's paper reports 93% on that measure) both "blind" (the analyzer
guesses what the set is) and "told" (it is given the exercise name, as the
dashboard will), the mean miss, and which rule describe_set fired. Then every set that missed, worst first. The per-set
results also go to <labels dir>\scorecard.csv so they can be charted.
"""
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1]))
from app.analysis import count_reps, describe_set, load_set  # noqa: E402


def main(labels_path, sets_dir):
    labels_path, sets_dir = Path(labels_path), Path(sets_dir)
    results = []
    with open(labels_path, newline="") as f:
        for row in csv.DictReader(f):
            bin_path = sets_dir / f"{row['set_id']}.bin"
            if not bin_path.exists():
                continue
            meta, _, accel, gyro = load_set(bin_path)
            # "blind": the analyzer guesses what the set is. "counted": it is told
            # the exercise, as the dashboard will. Negatives are never told.
            exercise = row["exercise"] if row["kind"] == "positive" else None
            blind, _, _ = count_reps(accel, meta["rate_hz"], gyro)
            peaks, _, _ = count_reps(accel, meta["rate_hz"], gyro, exercise=exercise)
            info = describe_set(accel, meta["rate_hz"], gyro, exercise=exercise)
            want, got = int(row["true_reps"]), len(peaks)
            results.append(dict(set_id=row["set_id"], kind=row["kind"], exercise=row["exercise"],
                                true_reps=want, counted=got, miss=got - want, counted_blind=len(blind),
                                looks_like=info["kind"], wobble=round(info["wobble"], 3),
                                swing=round(info["swing"], 3), rhythm_hz=round(info["rhythm_hz"], 2),
                                regularity=round(info["regularity"], 2), seconds=round(info["seconds"]),
                                notes=row["notes"]))

    by_exercise = defaultdict(list)
    for r in results:
        by_exercise[r["exercise"]].append(r)
    print(f"{'exercise':<22}{'sets':>5}{'blind':>8}{'told':>7}{'mean miss':>11}  rule fired (told)")
    for exercise, rs in sorted(by_exercise.items(), key=lambda kv: kv[0]):
        miss = np.array([abs(r["miss"]) for r in rs])
        blind = np.array([abs(r["counted_blind"] - r["true_reps"]) for r in rs])
        rules = Counter(r["looks_like"] for r in rs)
        print(f"{exercise:<22}{len(rs):>5}{100 * np.mean(blind <= 1):>7.0f}%{100 * np.mean(miss <= 1):>6.0f}%"
              f"{miss.mean():>11.1f}  {dict(rules)}")
    total = np.array([abs(r["miss"]) for r in results])
    total_blind = np.array([abs(r["counted_blind"] - r["true_reps"]) for r in results])
    print(f"\nall {len(results)} sets within 1 rep: blind {100 * np.mean(total_blind <= 1):.0f}%, "
          f"told the exercise {100 * np.mean(total <= 1):.0f}%, mean miss {total.mean():.1f}")

    bad = sorted((r for r in results if abs(r["miss"]) > 1), key=lambda r: -abs(r["miss"]))
    if bad:
        print("\nmissed by more than 1 (worst first):")
        for r in bad[:25]:
            print(f"  {r['set_id']:<28} {r['exercise']:<20} counted {r['counted']:>3} expected {r['true_reps']:>3}"
                  f"  looks like {r['looks_like']:<10} wobble {r['wobble']:.2f} swing {r['swing']:.2f} rhythm {r['rhythm_hz']:.2f}")
        if len(bad) > 25:
            print(f"  ... and {len(bad) - 25} more")

    out = labels_path.parent / "scorecard.csv"
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    print(f"\nper-set results: {out}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
