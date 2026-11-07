# Decisions

One entry per decision that shaped the analyzer or the project. Each says what
was decided, why, what it cost or what limitation forced it, and what it did to
the numbers. Newest at the bottom. Earlier design decisions (watch stores sets
on flash and deletes only after an upload receipt, NTP clock, user picks the
exercise in the dashboard) predate this log and are summarised first.

## Before this weekend

- **Count on the server, not the watch.** The M5StickS3 has a slow CPU and a
  small battery. Recording raw 100 Hz accel + gyro to flash and counting in
  Python on the laptop keeps the watch simple and lets the algorithm change
  without reflashing. Cost: no live rep count on the wrist.
- **The user picks the exercise in the dashboard.** Guessing the exercise from
  the signal is a harder problem than counting reps, and the first attempt
  showed shoulder press and chest press are indistinguishable on one axis.
  Deferred until there is enough data to guess well. This decision paid off on
  2026-10-31 (see "Use the exercise name").
- **Every set gets a label row.** `labels.csv` with kind = positive / negative /
  edge, true reps, and notes, and a parametrized pytest that runs every labeled
  set. The analyzer is only trusted on what it has been tested on.

## 2026-10-30

- **Tilt vs line to tell curls from presses.** A curl tilts the watch (total
  |accel| stays near 1 g); a press pushes it (total changes). `is_linear` picks
  the right peak-finding logic. Result: presses and rows went from 7–13 counted
  for 6 to 6/6 on all eight dumbbell sets.

## 2026-10-31, morning

- **Cadence, measured on the raw signal, to reject footsteps.** Walking, stairs,
  fast walk and jog were counting 8–49 "reps". Reps beat at 0.46–0.90/s on every
  recorded set; footsteps at 1.8–2.6/s. Chose a Fourier dominant frequency over
  counted-peak spacing because the peak finder's spacing rule drops every other
  footstep and makes walking look rep-paced. Threshold 1.5/s: halfway between
  the fastest rep set (0.90) and the fastest fake-curl test (1.25) on one side and
  the slowest footsteps (1.82) on the other. Result: stairs, jog, fast walk → 0.
- **Total-g wobble plus swing size to reject slow arm swings.** Slow walking
  beats at rep speed (0.70/s), so cadence can't catch it. It mostly tilts the
  watch (wobble 0.11–0.18) where a press really pushes it (0.29–0.49). Wobble
  alone would also reject curls (pure tilt), so the rule needs a small swing too:
  a curl swings the full 2 g, an arm swing under 1 g. Limitation accepted: the
  0.2 g line sits between walking at 0.18 and a press at 0.29 on 16 sets from
  one wrist. Result: both walking sets → 0, all fake-curl tests still pass.
- **Rejected: total-g wobble as the only differentiator.** It separated 12 sets
  into three clean bands and was the plan for an hour. The 13th recording (a
  jog, wobble 0.70, above every rep) broke it. Kept charts 04 and 06 side by
  side in the presentation as the reason negative data is collected first.
- **Gyro wrist-roll angle for anchored hands.** Pull-ups counted 1–2 of 6: the
  hand is fixed on the bar, the accelerometer sees 0.3 g ripples. The gyro shows
  the wrist rolling 25–35° per rep. Chose to integrate the gyro to an angle
  (then detrend) rather than count gyro-speed bumps, because speed gives two
  bumps per rep (roll up, roll back) at uneven heights; the angle gives one
  clean hill per rep. Trigger: wobble under 0.08 g and swing under 0.6 g.
  Limitation: depends on the user's wrist rolling on the bar; a rigid grip
  would shrink the signal. Result: 6/6 and 5/5 (the sixth rep in set 17 was a
  half rep; label corrected rather than the threshold).
- **Order of the checks: footsteps → anchored → arm swing → count.** Anchored
  must come before arm swing or pull-ups (wobble 0.03) are thrown out as a swing.
- **Lock the measurements in named tests.** Beyond "set 17 counts 5", tests
  assert the numbers the thresholds were chosen from (footsteps above 1.8/s,
  pull-ups under 0.05 wobble, dumbbells above 0.25). A change to `smooth()` that
  moves them fails by name instead of as a mystery pull-up regression.

## 2026-10-31, afternoon

- **Use the RecoFit data set as outside test data.** Limitation: only one
  person wears the watch and recruiting others is impractical; one person's
  data had already fooled us once. RecoFit gives 94 people, 70+ exercises,
  labeled rep counts, accel + gyro. Chose it over WISDM (walking only, 20 Hz)
  and Kaggle sets (needs a login). Cost: their sensor is a forearm armband at
  50 Hz, not a wrist watch at 100 Hz, so it tests transfer, not our exact case.
  Converted to our own .bin/.json format rather than writing a second loader,
  so every tool and test works on both. First result: 58% within ±1 (RecoFit's
  own algorithm: 93%).
- **Wrist only.** Gym Buddy is for one user on one wrist. The forearm results
  are used to find weaknesses, not as a target to hit. Concretely: thresholds
  stay tuned for the wrist; a forearm failure is fixed only if the fix is also
  right for the wrist. Presses on the forearm (39–53%) are therefore parked.
- **Regularity check (nothing repeats → 0 reps).** 70% of RecoFit's rest
  periods counted reps. `rep_period` already measured how well the signal
  matches a shifted copy of itself; curls score 0.74+ at the 10th percentile,
  non-exercise 0.00 (median 0.18). Threshold 0.3; measured on the accel axis
  or the gyro angle, whichever is more regular, so pull-ups (irregular on
  accel, 0.5 on the angle) survive. Result: non-exercise 30% → 67%, no change
  to any exercise above 85%.
- **Long-locomotion check (very regular for over 150 s → 0 reps).** On the
  forearm, jogging and the elliptical beat at 1.1–1.5/s (one arm swing per
  two steps), under the footstep line. Rather than lower the line and risk
  fast reps, used duration: the longest exercise set in 837 is 147 s, the
  shortest jog 150+ s, the watch itself caps a set at 120 s. Result: elliptical
  15% → 96%, jog 70% → 96%.
- **Use the exercise name.** The dashboard already asks the user what they
  did. `count_reps(exercise=...)` now skips the arm-swing / anchored / reps
  guess: a named anchored exercise (pull-up, dip, push-up) goes to the gyro
  path, anything else to the accelerometer. The footstep and regularity checks
  still apply, so a mislabeled walk or rest still counts 0 (tested). Result on
  RecoFit: 64% → 79% overall; triceps 24% → 86%, back fly 56% → 89%, push-ups
  4% → 68%, rows 69–76% → 94–96%. Negatives are scored without a name, since
  nobody would label a walk.
- **Benchmark floors as a regression gate.** `pytest -m benchmark` runs the
  821 RecoFit sets (18 s) and asserts per-exercise floors set at today's
  numbers. Kept out of the default run so the fast suite stays fast. Any
  future threshold change must keep the floors or raise them deliberately.
- **Rejected for now: a learned model.** With five measurements per set
  (wobble, swing, rhythm, regularity, gyro median) and 837 labeled sets, a
  small decision tree would find today's thresholds automatically. Deferred
  until the hand rules stop improving, because the rules are what make the
  features explainable in the presentation.

## 2026-10-31, evening

- **Transitions are masked by push, at the ends only.** Push-up sets 26 and
  27 counted the drop to a knee and the stand-up as reps. A rep on an anchored
  hand barely pushes the watch (|accel| within ~0.1 g of 1 g); getting down or
  up shoves it to 0.5–1.3 g away. Chose "push above 0.3 g and above 6× the
  set's own usual push, in the first or last quarter, ±0.3 s" and zeroed the
  gyro there before integrating, rather than dropping tops after the fact,
  because the stand-up roll was merging with the last real rep's hill (set 27's
  6th rep). Tried masking anywhere in the set: correct on the wrist too, but
  RecoFit's forearm push-ups fell from 73% to 39% because a forearm pushes
  hard mid-rep. Ends-only keeps the wrist at 7/7, 6/6 and RecoFit push-ups at
  64%. Limitation: a set that starts mid-rep with no lead-in has no transition
  to mask, which is fine; one with a transition in the middle (re-gripping) is
  not handled.
- **Recorded sets are tested told-the-exercise.** `test_recorded_sets` now
  passes the exercise name for positive and edge rows, matching how the
  dashboard will call it. The blind guess is still reported by the scorecard
  as its own column, so the two numbers stay visible side by side (RecoFit:
  64% blind, 79% told).
