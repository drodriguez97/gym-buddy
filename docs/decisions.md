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

## 2026-11-09 and 11-10: the watch, the server, the dashboard

- **The exercise is picked on the watch.** Replaces "picked in the dashboard".
  Counting blind got real sets wrong (6 curls counted 0, 7 push-ups counted 0),
  and labeling afterwards from memory defeats a counter. B cycles six
  exercises and the choice sticks for the next set. Cost: sync moved to a long
  hold of B, and the watch and server each hold a copy of the list.
- **Record to memory, write once at the end.** Writing to flash during a set
  stalled the loop for up to 491 ms, and asking the flash how full it is took
  483 ms. A set now goes into a 145 KB buffer set aside at boot and is written
  when it stops. Cost: sets are capped at two minutes, and a set is lost if
  the watch dies mid-set (not after: the save is finished or redone at boot).
- **Count on upload, store the count.** Counting takes milliseconds, so the
  receipt can carry the reps back to the watch and the dashboard reads a ready
  number. `analysis_version` marks which counter produced each row.
- **SQLite, one file, next to the raw files.** One watch means one writer. No
  database server to run, and a backup is a file copy. The raw files stay the
  truth: `backfill.py` rebuilds every row from them. Move to Postgres when
  there is more than one writer.
- **Pace, workouts and suggestions are worked out on every request, never
  stored.** They are cheap, and the rules will change. Storing them would mean
  migrating data every time a threshold moves.
- **Fatigue is the last gap against the usual gap, not the fastest.** The
  first version compared with the fastest gap. On the real shoulder-press sets
  the first gap was short (1.25 s, then a steady 1.7 to 1.8 s), so a perfectly
  steady set read "38% slower" and the suggestion said to drop the weight.
  The middle gap ignores one odd rep. Set 9 went from 38% to 0%.
- **The watch measures, the server judges.** The health report is raw numbers
  (g at rest, signal strength, battery). Limits live in `health.py`, so
  changing "what counts as weak Wi-Fi" never needs a reflash.
- **Start time from the watch, with an honest fallback.** The watch sets its
  clock from the internet at each sync and stamps each set. A set recorded
  before the first sync has no time; the server then uses the upload time and
  the page says "synced" instead of pretending.
- **Two secrets, two callers.** The watch has a token that only uploads; the
  dashboard has a password that only reads and relabels. Leaking one does not
  give the other. Both are environment variables, compared in constant time.
  HTTP Basic was chosen for the password because the browser provides the
  sign-in box: no login page, no sessions to get wrong. It is only safe over
  HTTPS, which is why Caddy sits in front.
- **The app in a container, the data on a volume, no database container.**
  SQLite is a file, so the volume holds everything worth keeping and the
  container can be thrown away and rebuilt.
- **The watch uploads over HTTP for the demo.** HTTPS from MicroPython on this
  firmware is untested and the demo cannot fail. The risk is a readable upload
  token on the hotspot, which allows fake uploads and nothing else.
- **Tests run the real code against stand-ins.** The watch code runs against
  a fake screen, buttons, sensor and clock; the sync tests upload to the real
  server app; the deploy test starts the server as a real process, fills it,
  restarts it and checks the data. Each important test was checked by breaking
  the code on purpose and seeing the test fail.
- **The wearer has the last word on the count.** A corrected count is stored
  next to the counter's, never over it. The page shows the wearer's; the
  difference between the two is a free labeled example of where the counter
  is wrong.
- **Removing a set marks it; nothing is deleted.** Sets recorded after the
  first sync exist only on the server, so a slip of the thumb must not destroy
  one. Because it can be undone, the page asks no "are you sure?".
- **A sign-in page instead of the browser's password box.** The box worked but
  was the one screen nobody designed, and it can't be signed out of. The
  session cookie holds an HMAC of the password, so there is no session table
  to store and changing the password signs everyone out. Scripts still send
  the password as HTTP Basic, which keeps `check_server.py` simple.
- **The watch syncs by itself once, when the workout ends.** Not after every
  set: joining Wi-Fi takes seconds, costs battery, and would block the button
  between sets. The end of the rest window (five quiet minutes) is the one
  moment nobody is waiting on the watch. One try only, and a failure is
  silent: no Wi-Fi at the gym is normal, and hold B still works at home.
- **Today leads with effort, not a total of reps (2026-11-11).** "46 reps"
  adds unlike things: six pull-ups and six curls are not the same work, and
  any counter can give a total. What this watch measures that a counter can't
  is how much each set slowed by its last rep. So the headline is "3 of 8 sets
  pushed hard" with one sentence of advice; reps, sets, exercises and minutes
  are the small numbers under it. Three things were looked at first. Fitbit's
  2025 redesign and others put one focal number on top with three beside it,
  and are moving from numbers to guidance. WHOOP rolls everything into one
  score (Strain), which nobody can check by hand; "3 of 8 sets" can be
  explained in a sentence, so no invented score. Strength logs (Hevy, Strong)
  lead with volume, sets and duration; volume needs a weight on every set, so
  it waits. The 25% line is not arbitrary: in velocity-based training a set is
  ended at a chosen loss of speed, and studies split thresholds at about 25%
  (lower favours strength, higher favours muscle growth). Ours is a rougher
  cousin: rep time on the wrist, not bar speed, and how many reps were left
  at a given loss differs from person to person.
- **A weak top counts where a rep is due (2026-11-12).** Dan noticed shoulder
  press was often one rep short. RecoFit agreed: exactly one short on 157 of
  its 562 exercise sets, almost never one over. Cause: a top only counted if
  it stood 0.3 g clear of the dips on both sides. The first rep starts from
  rest and the last ends in rest (a dip on one side only), and mid-set a
  shallow dip hides a full-height rep. Three changes, all using timing as the
  evidence: `edge_reps` steps one rep-length out from the first and last
  counted rep and accepts a top judged on its inner side; `gap_reps` accepts
  a half-prominence top inside a hole two reps long; `count_anchored` runs
  `edge_reps` on the wrist angle too. Tried first and rejected: reaching past
  the trimmed window. It helped RecoFit but turned six of Dan's correct 6s
  into 8s and 9s, because lifting the dumbbells into position looks like a
  rep. Results (exact / within one rep): Dan's 20 labeled sets 100% before
  and after; RecoFit 57% / 79% -> 65% / 83%, shoulder press 29% / 53% ->
  53% / 80%; MM-Fit 42% / 84% -> 65% / 90%, shoulder press 18% / 53% ->
  50% / 81%, push-ups 16% -> 47% exact. Cost: RecoFit kettlebell swings
  81% -> 75% exact (still 100% within one), and rest or walking sets that
  were already miscounted gain a rep or two. `ANALYSIS_VERSION` is now 2.
- **MM-Fit as a second outside data set (2026-11-12).** RecoFit is a forearm
  band at 50 Hz; MM-Fit is a smartwatch on each wrist at about 100 Hz, which
  is our placement and rate. 21 workouts, ten exercises, 1,224 sets after
  import (`scripts/import_mmfit.py`), each with a labeled rep count. Its
  bicep curls alternate arms and the label counts both, so each wrist gets
  half. Its sets are cut tight around the reps, with no lead-in, so it says
  nothing about the trim. No data license is stated on its page, so it is
  downloaded, not committed (`recordings/mmfit/` is ignored). Other sets
  looked at and not used: Soro et al. CrossFit (reps paced by a vibration
  cue), GYMU (login needed, no shoulder press), RecGym and WEAR (too slow or
  no rep counts). Benchmark floors: `python -m pytest -m benchmark`.
- **A last rep that runs into the stop button counts (2026-11-12).** Dan's
  curl sets tonight (00053, 00054, 00055) each counted 4 of 5. He finishes
  the last curl at the top and reaches for the button from there, so the arm
  never comes back down and the top of that rep lies in the stretch
  `active_window` trims as "watch turned to face you". `tail_rep` looks one
  rep-length past the trim for one more top. Lowering the arm and then
  reaching for the button makes a rise in the same place, and counting that
  would break sets that are right today (tried without a height test: 4 of
  13 labeled sets gained a false rep). What separates them is height: the
  reach stops at 0.64-0.73 of a rep's rise in the labeled sets, the real last
  rep reached 1.23-1.38 in tonight's three, and a press tilts the watch 5.8
  times further. So the top must rise 1.0 to 2.0 times a typical rep. Thin
  evidence (three sets for, three against), so the safer habit for the demo
  is still: lower the arm, wait a second, then press. Labeled sets 13 of 13
  unchanged; RecoFit 64.8% -> 65.0% exact; MM-Fit 65.0% -> 65.6%, nothing
  worse. Checked against tonight's sets from their dashboard traces only;
  the raw files are on the server. `ANALYSIS_VERSION` is now 3.
- **Start times stamped by an unchecked clock are put right at upload
  (2026-11-12).** Set 00052 was stamped exactly 8 hours early; the three sets
  after it were right. The watch's clock held local (Pacific) time at
  power-on, which our code never sets: `ntptime.settime()` sets UTC, and it
  runs at the start of a sync, after the first set is already recorded. Why
  the power-on clock was local is not confirmed (the firmware setting it
  from its own time zone setting is the likely cause). The fix doesn't need
  to know: `clock.py` records how far the first time check since power-on
  moved the clock (`step`), each set's .json says whether its clock had been
  checked (`clock_checked`), and `sync.py` moves an unchecked set's start by
  `step` when that is more than two minutes. Not covered: a set stamped by a
  wrong clock and uploaded only after a later power-on.
