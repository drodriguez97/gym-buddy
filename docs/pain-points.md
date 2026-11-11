# Pain points

Each entry: the problem, what it cost, and where it stands. Resolved ones stay
here because they are the story of the project. Why each fix was chosen is in
decisions.md; the evidence is in presentation/README.md.

## Open

- **Not yet confirmed on the real watch (2026-11-10).** The clock sync, set
  start times, the health report, light and deep sleep and the fonts are
  tested against the fake watch only. The Docker image has never been built.
  Each is a line in demo.md's checklist.
- **The battery may not be charging fully.** Plugged in, it read 3.86 V (70%)
  with `isCharging()` false. To do: read it again after 30 minutes and try a
  wall charger.
- **Sets 30 and 44 have no known rep count.** 44 is a curl counted as 3 with
  an irregular recording; 30 has no exercise.
- **Presses on the forearm.** On RecoFit's forearm data, shoulder press (53%),
  chest press on the rack (39%) and dips (35%) are still far below the 93%
  benchmark even when told the exercise. The forearm travels less than the wrist,
  so the rep bumps are small and `min_prominence=0.3 g` throws them out. Not a
  problem on Dan's wrist (100% on his presses), so it is parked until there is a
  reason to support another placement. See decisions.md, "Wrist only".
- **Non-exercise is 67% correct.** A third of RecoFit's rest periods still count
  reps: people fidget rhythmically (adjusting the band, bouncing a knee). The
  regularity check caught the other two thirds. The next step is probably a
  minimum number of consistent reps (3 or more at the same spacing) before a set
  counts at all.
- **Dips have no wrist data.** Counted on the wrist roll like pull-ups (35% on
  RecoFit's forearm). Two sets on the watch would tell us if the rule holds.
- **Shoulder press and chest press look identical on x.** Exercise guessing has
  a known floor until gyro or z features are added. Less urgent now that the
  dashboard supplies the exercise name and the analyzer uses it.
- **No clock on the watch until it joins Wi-Fi.** Sets can't be ordered across
  power-ons until the first NTP sync. Plan: `ntptime.settime()` on sync,
  `started_at = null` before that.
- **Curls that hold at the top can count the gaps instead of the reps.** Set
  00003 (worn on a rubber band, the arm staying up longer than it rests) counted
  the 5 gaps between its 6 reps, because the tops are taken to be the short trips
  away from where the arm spends most of its time. A fix that used the resting
  position at the start of the set got 00003 right but moved 26 RecoFit sets,
  more for the worse than the better, so it was not kept. 00003 was removed from
  the fixtures (2026-11-07): one set from a mount no longer used should not
  shape the counter. 00004 and 00007 still count 6.

## Resolved

- **The UIFlow startup app blocked the REPL.** Every reboot opened UIFlow's
  launcher, and Thonny showed "Device is busy". `boot_option` lives in NVS, not
  in `boot.py`. Fixed 2026-10-25 by setting it to 0, so the stick boots straight
  into `main.py`.
- **Which axis shows a curl depends on how the watch is worn.** On a rubber band
  curls showed up on y; with the strap, on x. Fixed 2026-10-29: `busiest_axis`
  picks the axis that moves most instead of assuming one.
- **Turning the watch to press the button looked like reps.** Sets 00004 and
  00007 (6 curls each) counted 8 and 5. Fixed 2026-10-29: `active_window`
  ignores the start and end of a set until the watch reaches a position the
  reps use.

- **Watch died in a day.** Idle loop polled at full power with the backlight on.
  Fixed 2026-10-30/31: screen off after 20 s, light sleep while dark, deep sleep
  after 10 min, radios off at boot. First attempt bricked the wake path (wrong
  GPIO for the ESP32-S3); sleep now stays off until `BTN_A_PIN` is set to a
  verified pin in 0–21.
- **Fixtures were silently skipped.** Sets copied into `tests/fixtures` without a
  `labels.csv` row never ran. Fixed 2026-10-31: `test_every_fixture_is_labeled`
  fails with the missing ids.
- **Walking, stairs and jogging counted as reps** (20–49 "reps" per recording).
  Fixed 2026-10-31 with the cadence check (dominant rhythm above 1.5/s is
  footsteps) and the arm-swing check (small push, modest swing). All six
  movement sets count 0.
- **Pull-ups counted 1 and 2 of 6.** The watch barely moves on the bar. Fixed
  2026-10-31 by counting the wrist-roll angle from the gyro when the hand is
  anchored. 5/5 and 6/6 (set 17's sixth rep was a half rep; relabeled `edge`).
- **One person's data was not enough.** Rules that looked clean on 12 sets broke
  on the 13th (a jog). Recruiting people to wear the watch is impractical.
  Resolved 2026-10-31: the Microsoft RecoFit data set (94 people, 70+ exercises,
  true rep counts, accel + gyro at 50 Hz). `scripts/import_recofit.py` converts
  it to our format; `recordings/recofit` holds 821 sets; `scripts/scorecard.py`
  scores them; `pytest -m benchmark` enforces floors.
- **Push-ups counted the drop-down and the stand-up as reps.** First two
  wrist sets (26, 27) counted 8 and 6 for 7 and 6: getting onto a knee and
  standing up roll the wrist more than a rep and landed as reps 1 and 8 (set 27
  was right by luck: a missed last rep and a counted stand-up). Fixed
  2026-10-31: a big push in the first or last quarter of a set is a transition;
  its gyro is zeroed before the angle is built and nothing is counted there.
  7/7 and 6/6. Masking anywhere in the set, not just the ends, cost 10 points on
  RecoFit's forearm push-ups, so it stays at the ends.
- **Thresholds tuned on the wrist did not transfer to the forearm.** First
  RecoFit run: 58% within ±1. Treadmill jogging and the elliptical slipped under
  the 1.5 Hz footstep line (a forearm swings once per two steps) and counted
  hundreds of reps; presses fell into the arm-swing band. Resolved the same
  afternoon to 79% (64% blind) with three changes: a regularity check (nothing
  repeats → 0), a long-locomotion check (very regular for over 150 s → 0; no set
  lasts that long), and passing the dashboard's exercise name into `count_reps`
  so the guess is skipped. Presses remain open (above).
- **The first count_reps only knew curls.** Presses and rows overcounted (7 to
  13 for 6) until the tilt-vs-line check was added (2026-10-30). Lesson that has
  held all weekend: every new exercise and every new non-exercise needs labeled
  sets before the counter is trusted on it.
- **Stopping a set felt laggy (2026-11-09).** The stop press took half a
  second to register. Timing each line on the watch found two causes: asking
  the flash how full it is (483 ms) and flash writes that stall (up to 491 ms).
  Both moved out of the recording loop; a pass of the loop is now 1.1 ms.
  Lesson: measure on the device before guessing.
- **A steady set was told to drop weight (2026-11-10).** Fatigue compared the
  last rep with the fastest, and one quick first rep made steady shoulder
  presses read 38% slower. Found by looking at the page with real data, not
  by a test: every test passed. Now compared with the usual rep.
- **Tests that passed for the wrong reason.** Several rejection tests only
  checked for "422" and kept passing when the wrong check rejected the
  upload. They now check the message too, and new tests are tried against
  deliberately broken code.
- **A pile of test uploads in the real data (2026-11-10).** 23 practice sets
  sat next to the real ones. Moved to an archive folder, not deleted, because
  sets 28 and up exist nowhere else.

