# Gym Buddy: rep-detection findings (charts for the presentation)

All charts come from real recordings on the M5StickS3 at ~100 Hz, analyzed with
`server/app/analysis.py`. Set numbers match `recordings/labels.csv`.
Dates are when the finding was made.

---

## 01_dumbbell_sets_9-16_all_counted.png  (2026-10-30)

**What it shows:** the eight dumbbell sets (shoulder press, chest press, underhand and
overhand row). Black line is the smoothed accelerometer axis that moves the most, faint
red is the raw signal, green dots are the reps the analyzer counted, grey is the start
and end it ignores (the watch turned to face you to press the button).

**Finding:** the analyzer counts 6 of 6 on every dumbbell set. Presses show up as dips
(the weight slowing and turning at the top), rows as peaks. Each rep moves the watch by
about 0.6–1.8 g.

---

## 02_accel_vs_gyro_row_vs_pullup.png  (2026-10-31)

**What it shows:** the same two sensors on two exercises. Left: a row (set 15).
Right: a pull-up (set 17). Top row is the accelerometer, bottom row is the gyro.

**Finding:** the accelerometer answers "is the watch being shoved or tilted?", the gyro
answers "is the watch being turned?". In a row the hand carries the weight, so the
accelerometer swings about 1.5 g per rep. In a pull-up the hands are anchored on the
bar: accel x stays pinned at 1 g all set and the reps are only ~0.3 g ripples. But the
wrist rolls a little on the bar with every rep, and the gyro shows six clear bumps.
**When the hand travels, count on the accelerometer; when the hand is anchored, count
on the gyro.**

---

## 03_pullups_accel_and_gyro.png  (2026-10-31)

**What it shows:** both pull-up sets (17 and 18), accelerometer on top, gyro below,
with the reps the analyzer counted marked in red.

**Finding:** the analyzer found 1 of 6 and 2 of 6. The pull-up ripple (~0.3 g) sits
right at the analyzer's minimum rep size (`min_prominence=0.3`), so most reps are
thrown away. The gyro shows all six in both sets. This is the false-negative case.

---

## 04_wobble_vs_gyro_12_sets.png  (2026-10-31, superseded by 06)

**What it shows:** every set as one dot. Left–right: how fast the wrist turns (gyro
median, deg/s). Up–down: "total-g wobble", the standard deviation of the length of the
acceleration vector sqrt(x²+y²+z²). Tilting the watch just moves gravity between the
axes and cancels out of the total; only a real push changes it.

**Finding at 12 sets:** three clean bands. Dumbbell reps 0.29–0.49 (the watch is really
pushed), walking 0.11–0.18 (the arm swings but mostly tilts), pull-ups 0.03 (the watch
is anchored). It looked like total-g wobble alone was the differentiator.

---

## 05_stairs_jog_fastwalk_raw.png  (2026-10-31)

**What it shows:** the four boundary recordings made to test that idea: stairs up and
down (22), light jog (23), fast walk (24), stairs up (25). Left column accelerometer
with the total |a| in black and the analyzer's false "reps" as red dots; right column
gyro.

**Finding:** the analyzer counted 49, 41, 35 and 8 "reps" on sets where the right
answer is 0. Every footstep is a clean rhythmic bump, which is exactly what the
rep counter looks for. This is the false-positive case, and it is worse than plain
walking.

---

## 06_wobble_vs_gyro_16_sets.png  (2026-10-31)

**What it shows:** chart 04 redrawn with the four new sets added.

**Finding:** total-g wobble alone does not survive. The fast walk lands at 0.28, right
at the bottom of the rep band (0.29), and the jog lands at 0.70, above every rep,
because each stride is a real impact. One recording broke a rule that looked clean on
12 sets. The two features together still separate everything: the brisk movements have
gyro medians of 146–153 deg/s, nearly double the busiest row (86). Lesson for the
project: collect negative cases before trusting a rule.

---

## 07_cadence_reps_vs_footsteps.png  (2026-10-31)

**What it shows:** top: ten seconds of a row next to ten seconds of a fast walk, on
the busiest accelerometer axis, with the strongest repeating beat printed in the box.
Bottom: the frequency spectrum (which beat is loudest) of all 16 sets, each scaled so
its loudest beat is 1. The dot marks each set's dominant rhythm.

**Finding:** cadence is the strongest single separator so far. Every dumbbell set and
the pull-ups beat at 0.46–0.90 per second. Stairs, jog and fast walk beat at 1.8–2.6
per second, because a footstep comes about twice a second and a rep cannot. Only slow
walking (set 21, 0.70/s) lands in the rep band, and its low wobble (0.11) already
separates it. Important detail: this must be measured on the raw signal with a Fourier
transform, not on the peaks the analyzer keeps. The analyzer's own spacing rule drops
every other footstep and makes walking look rep-paced.

---

## Where this leaves the detection rule (2026-10-31)

Three readings, each catching what the others miss:

1. **Dominant rhythm above ~1.3 per second** → footsteps, count 0 (stairs, jog, fast walk).
2. **Total-g wobble near 0** → anchored hand, count on the gyro (pull-ups).
3. **Wobble below ~0.2 with a rep-like rhythm** → slow arm swing, count 0 (slow walking).

Test status before implementing any of this: 15 passed, 8 failed
(2 pull-ups under-counted, 6 movement sets over-counted). After (same day):
30 passed on the watch data; RecoFit 821 sets 58% → 79% within ±1 (charts 09, 10).
Two more checks were added in the afternoon: regularity (nothing repeats → 0) and
long locomotion (very regular for over 150 s → 0), plus the exercise name from the
dashboard. The full reasoning is in ../decisions.md.

Caveats: 16 sets from one person on two days. The gyro and cadence thresholds need a
second person's gait and a couple of fast, light sets (quick curls or presses) before
the lines are trusted.

---

## 08_pullups_counted_on_wrist_angle.png  (2026-10-31)

**What it shows:** both pull-up sets after the anchored-hand rule was added. Black is
the wrist roll angle, rebuilt by adding up the gyro; red dots are the counted reps;
orange is accel y for comparison.

**Finding:** set 18 counts 6 of 6. Set 17 counts 5, and both sensors show five
cycles: the sixth rep was a half rep, so the label was corrected to 5 and the set is
kept as an `edge` case. Test suite after the rules: 28 passed, 0 failed (was 15 / 8).

---

## 09_recofit_scorecard.png  (2026-10-31)

**What it shows:** the analyzer, with the three rules, run over 821 sets from the
Microsoft RecoFit data set (94 people, armband on the right forearm, 50 Hz, true rep
count labeled). Each bar is the share of sets counted within ±1 rep. Green bars are
exercises with reps, red bars are activities that should count 0. The dashed line is
the 93% RecoFit's own algorithm reports.

**Finding:** 58% within ±1 overall. Curls, kettlebell swings, lateral raises and
jumping jacks are at or near the benchmark on people the analyzer has never seen.
Presses, push-ups and dips are poor, and the "rule fired" column in the scorecard says
why: on the forearm those movements produce less push than on the wrist, so they fall
into the arm-swing and anchored bands that were tuned on Dan's wrist data. Treadmill
jogging and the elliptical beat at 1.1–1.5 per second on the forearm (one arm swing
per two steps), just under the 1.5 Hz footstep line, so they count as hundreds of
reps. Two lessons for the slide: (1) more people's data exposed problems one person's
never could; (2) thresholds tuned at one sensor position do not transfer to another.
Reproduce with `python scripts\scorecard.py ..\recordings\recofit\labels.csv ..\recordings\recofit`.

---

## 10_recofit_before_after.png  (2026-10-31, afternoon)

**What it shows:** chart 09 redrawn with a second bar per exercise after three
changes made the same afternoon: a regularity check (nothing repeats → 0 reps), a
long-locomotion check (very regular for over 150 s → 0 reps), and passing the
dashboard's exercise name into `count_reps` so it skips the guess. Grey is the
morning, colour is the afternoon.

**Finding:** 58% → 79% of 821 sets within ±1 rep (64% when the analyzer is not told
the exercise). The two negatives that were counting hundreds of reps are fixed:
elliptical 15% → 96%, jog 70% → 96%. Rest periods 30% → 67%. Among exercises, the
exercise name did the most: triceps extension 24% → 86%, back fly 56% → 89%, push-ups
4% → 68%, rows 69–76% → 94–96%. Nothing that was above 85% moved. Still open on the
forearm: presses (39–53%) and dips (35%), whose rep bumps are smaller than the 0.3 g
minimum tuned on the wrist. Those are parked on purpose; see decisions.md, "Wrist
only". The fast test suite is 30/30 on the watch data and the benchmark floors hold.

---

## 11_pushups_transitions_masked.png  (2026-10-31, evening)

**What it shows:** the first two push-up sets on the watch. Grey is the wrist
angle as first computed; black is the same angle after the transitions (orange
bands: a big push at the start or end of the set) are zeroed out of the gyro
before integrating. Red dots are counted reps.

**Finding:** without the mask, dropping to a knee and standing back up each
counted as a rep (set 26: 8 for 7). With it, 7/7 and 6/6. Set 27 shows why the
mask has to happen before integrating, not after: its last real rep sits right
against the stand-up, and in the grey line the two merge into one hill. The push
test is physical, not tuned: an anchored hand cannot shove the watch, so a shove
means the hand let go. Suite: 33/33 on watch data; RecoFit 79% told, 64% blind.
