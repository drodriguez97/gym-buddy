# Pain points

Problems we hit while building Gym Buddy: what happened, what we learned, and where each one stands.
These are raw material for the presentation's "a bug found and fixed" and "limitations" slides.
Newest last. Status is **Open** or **Solved**.

---

## 1. The UIFlow startup app blocked the REPL (Solved, 2026-10-25)

**What happened:** Every reboot started UIFlow's own launcher, which held on to the stick. Thonny kept showing "Device is busy" and the `>>>` prompt kept disappearing.

**Cause:** UIFlow's `boot.py` reads a saved setting, `boot_option`, from NVS. It was 1 ("show the startup menu"). Editing `boot.py` didn't help, because the setting lives in NVS, not in the file.

**Fix:** Set `boot_option` to 0 in NVS (`set_u8`, then `commit()`). Now the stick boots straight into our `main.py`.

**Lesson:** A setting stored on the device is not the same as the code that reads it.

---

## 2. Which axis shows a curl depends on how the watch is worn (Solved, 2026-10-29)

**What happened:** We first guessed that x would run along the forearm. With a rubber band, curls actually showed up on y. With the strap, they showed up on x, because the strap holds the stick turned 90°.

**Fix:** `count_reps` picks the axis that moves the most (`busiest_axis`) instead of assuming one.

**Lesson:** Measure instead of assuming, and don't hard-code anything that depends on how the device is mounted.

---

## 3. Turning the watch toward you to press the button looked like reps (Solved, 2026-10-29)

**What happened:** Sets 00004 (light) and 00007 (medium) were 6 curls each, but the counter said 8 and 5.

**Cause:** Each set starts and ends with the wrist turned so the watch faces you, to press the button. That turn was the biggest movement in the set, so it fooled the axis choice and added a fake peak.

**Fix:** `active_window` ignores the start and end of a set until the watch reaches a position the reps actually use. Both sets now count 6, and tests with those recordings keep it that way.

**Lesson:** Real use includes the moments around the exercise, not just the reps. Synthetic test data didn't have this, and only real recordings exposed it.

---

## 4. Random movement still counts as reps (Open)

**What happened:** Sets 00001 and 00002 were just the stick moved up and down by hand (0 reps), but the counter finds 8 and 11.

**Why it's hard:** Waving the stick produces waves big enough to pass the strength threshold, just like real reps.

**Plan:** The design doc's consistency filter: each rep must look like the previous one in size, timing and axis. Random movement is irregular, and real sets are not.

---

## 5. Choosing how to count each exercise (Open)

**The problem:** Different exercises move the forearm in very different ways, so one counting method can't handle all of them.

| Family | What the forearm does | Examples | Signal |
|---|---|---|---|
| Tilt | Rotates, changing its angle to gravity | Curls, tricep extensions, lateral raises | Big ±1 g swings. **The counter works** |
| Push / pull | Keeps its angle and moves in a straight line | Bench press, shoulder press, rows, pulldowns | Small bumps of about ±0.2–0.4 g, only while the weight speeds up or slows down. **Not handled yet** |

**What makes it hard:**
- Push/pull reps don't tilt the watch, so gravity barely changes and the signal is about 4× weaker than a curl.
- A press starts at the top (lockout) and a curl at the bottom. The current direction check assumes the set starts at the bottom.
- Pauses at the top or bottom of a rep produce no signal at all, because a bar that isn't speeding up or slowing down has no acceleration.
- The movement direction changes from exercise to exercise (vertical presses, horizontal rows), so the axis changes too.
- How the exercises group into families is still a working guess.

**How others handle it:** As far as we know, Fitbit and Apple Watch don't count lifting reps. Garmin counts reps and guesses the exercise, and users often correct both afterwards.

**Plan:**
1. Record 2 sets each of bench press, row and shoulder press, plus 20 s lying still on the bench. Label them all in `labels.csv`.
2. Plot them next to a curl to check whether the push/pull family really holds. Split it if the plots disagree.
3. Build and test a push/pull counter from those recordings.
4. Add the exercise → family table on the server and an exercise picker on the watch (`BtnB`).
5. Later (v2): use the gyro to check or guess the family. Tilts spin the gyro, and pushes and pulls barely move it.

**Decision so far:** The user picks the exercise, and the server maps it to a family (see decisions.md, 2026-10-29). Guessing the exercise automatically is out of scope for v1.

---

## 6. Collecting labeled recordings is slow and manual (Open)

**The problem:** Every improvement to the counter depends on real recordings with a known answer. Getting one set takes many manual steps:

1. Do the set at the gym, pressing the button to start and stop.
2. Remember what it was (exercise, weight, how many reps).
3. Stop the program in Thonny and copy the `.bin` and `.json` over USB.
4. Add a row to `recordings/labels.csv` by hand.
5. Copy the useful sets into `server/tests/fixtures/` and add them to the tests.

**Why it matters:** Each movement family needs several sets, plus sets that should count 0 (walking, arm swings, re-racking). That's dozens of sets, and every step is a chance to lose a set or mislabel one.

**Why it can't just be skipped:** Synthetic sets from the simulator are fast and keep tests running without hardware, but they missed pain point 3 entirely. Only real recordings showed it. Commercial trackers have the same problem: labeled data is the expensive part.

**Plan:**
- **Milestone 3 removes the USB step.** The watch uploads sets over Wi-Fi when you get home.
- **Confirm counts on the dashboard.** The server counts each set after upload, and the dashboard shows the count with a way to correct it. A confirmed or corrected count becomes the label, so `labels.csv` is generated instead of typed. (The watch doesn't count reps itself, so it can't do this step.)
- **Or enter the count on the watch.** After stopping a set, the buttons set the number of reps you actually did, and it's saved in the set's `.json`. Simpler to build, but more presses at the gym.
- **Pick the exercise before the set** (pain point 5), so the exercise is recorded with the set automatically.
- **Record in batches.** Plan a session of several labeled sets at once instead of one at a time.
- **Keep the simulator for the bulk of the tests,** and use real recordings for the cases it can't imitate.
