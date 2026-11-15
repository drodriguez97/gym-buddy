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
| 2026-11-12 | server/app/analysis.py, main.py, tests | tail_rep: a last rep that goes straight into the stop button counts if it rises 1.0-2.0x a typical rep. ANALYSIS_VERSION 3. Two tests. 251 server tests pass; RecoFit and MM-Fit unchanged or slightly better | n/a, server side |
| 2026-11-12 | watch/clock.py, recorder.py, sync.py, tests | A set stamped before the clock was checked gets its start time moved by what the check found (set 00052 was 8 hours early). 206 watch tests pass | NOT yet flashed or checked on the watch |
| 2026-11-13 | server/app/analysis.py, main.py, tests | tail_rep: takes a real turning point nearest to where the rep was due (not the highest reading), accepts a rise of 0.8-2.0, rejects a ledge on the climb to the button. Sets 00063 and 00064 (4 of 5) come out 5 on their traces. ANALYSIS_VERSION 4. Four tests; 255 server tests pass; MM-Fit 15 better / 1 worse, RecoFit 3 better / 1 worse | n/a, server side; NOT yet confirmed by a recount on the live server |
| 2026-11-13 | server/app/static/index.html | Other workouts grouped by day with bolder headers; sets synced while the page was closed show as New (seen set IDs kept in localStorage) | n/a |
| 2026-11-15 | server/app/static/index.html, login.html | Today opens with the watch-face buddy as a coach: a mood, an animation and a speech bubble chosen from the pushed-hard counts and suggestions the server already sends. Calendar runs Sunday to Saturday and counts days trained. Light theme on every device. Checked by eye on a scratch server at phone size; the tests do not cover the page | n/a |
| 2026-11-15 | server/scripts/seed_history.py | Standalone script that replays 13 labelled recordings through POST /sets as 42 back-dated sets (Mon/Wed/Fri, four weeks, UTC). IDs are 9DDNN-5eedXX so one query removes them. Tested on a scratch server | NOT run against the live server |
