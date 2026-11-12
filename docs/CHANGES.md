# Watch changes (weekend log)

One line per flash. Becomes the commit messages on Sunday.
Rule: do not change the .bin format or the 100 Hz rate. Sets before and after must load the same way.

| Date | File | Change | Applies from set |
|---|---|---|---|
| 2026-10-30 | server/app/analysis.py | count_reps handles presses and rows (is_linear, rep_period, min_lift) | n/a, server side |
| 2026-10-31 | server/app/analysis.py | count_reps takes gyro; three checks before counting: dominant_hz > 1.5 -> footsteps (0), wobble < 0.08 & swing < 0.6 -> anchored (count wrist roll on gyro), wobble < 0.2 & swing < 1.2 -> arm swing (0). New: total_wobble, swing_size, dominant_hz, roll_angle, count_anchored, describe_set | n/a, server side |
| 2026-10-31 | server/tests/test_analysis.py | recorded-set test passes gyro and names false positive / false negative; threshold lock-in tests; every-fixture-is-labeled test. 28 pass | n/a |
| 2026-10-31 | recordings/labels.csv | sets 17-18 pull-ups, 20-25 walking / stairs / jog / fast walk; 17 relabeled edge, 5 reps (6th was a half rep) | n/a |
| 2026-10-31 | server/scripts/import_recofit.py, scorecard.py | RecoFit importer and per-exercise scorecard; recordings/recofit = 821 converted sets + labels.csv | n/a |
| 2026-10-31 | server/app/analysis.py | rep_rhythm returns (period, regularity); describe_set adds regularity + duration; new checks: no rhythm (< 0.3 -> 0), long locomotion (> 150 s and regularity > 0.7 -> 0); count_reps(exercise=) skips the guess (ANCHORED_EXERCISES -> gyro path); THRESHOLDS dict | n/a |
| 2026-10-31 | server/tests/test_analysis.py, pytest.ini | exercise-name tests; RecoFit benchmark with per-exercise floors behind `-m benchmark` (default run deselects it). 30 fast + 1 benchmark pass | n/a |
| 2026-10-31 | server/scripts/scorecard.py | blind vs told-the-exercise columns, regularity and seconds per set | n/a |
| 2026-10-31 | docs/decisions.md | new: why each rule and data choice was made, with before/after numbers | n/a |
| 2026-10-31 | server/app/analysis.py | count_anchored(accel=): a big push in the first/last quarter of a set is a transition; gyro zeroed there before integrating, no tops counted there (push-ups 26, 27 -> 7/7, 6/6) | n/a |
| 2026-10-31 | server/tests/test_analysis.py, recordings/labels.csv | sets 26, 27 push-ups (7, 6); recorded-set test passes the exercise name; transition test. 33 pass | n/a |
| 2026-11-12 | server/app/analysis.py, main.py | edge_reps and gap_reps: weak first/last/mid-set tops count where a rep is due; count_anchored uses edge_reps. ANALYSIS_VERSION 2. RecoFit 57% -> 65% exact, MM-Fit 42% -> 65% | n/a, server side (old rows keep their count until recounted) |
| 2026-11-12 | server/scripts/import_mmfit.py, server/tests/test_analysis.py, .gitignore | MM-Fit importer (1,224 wrist sets with rep counts), MM-Fit benchmark floors, six tests for the new rules. 249 fast tests and the MM-Fit benchmark pass; RecoFit floors checked with the scorecard (none dropped) | n/a |
