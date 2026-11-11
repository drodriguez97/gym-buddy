# Gym Buddy: the plan

The one reference for what we are building, for whom, and by when. If another
document disagrees with this one, this one wins and the other gets fixed.
Last updated 2026-11-10.

Other documents, and what each is for:
- `api.md`: the exact request and response of every endpoint
- `deploy.md`: putting it on AWS, step by step
- `demo.md`: the demo runbook, with the questions to expect
- `decisions.md`: why each choice was made, with numbers
- `pain-points.md`: what went wrong and what it taught us
- `presentation/`: charts for the slides

## What it is

A wrist-worn tracker for strength training. An M5StickS3 watch records the
motion of each set. A server counts the reps and shows the workout on a web
page. It counts reps, which mainstream watches mostly don't, and it keeps the
raw motion data so every count can be checked and recounted.

## The deadline

**Demo at the CHAOS onsite, Monday 2026-11-16.**
Goal: a demo that cannot fail. Structure and Dan's understanding matter more
than looks.

The demo, in one line: do 5 curls, press sync, and the phone shows 5 reps.

## How it fits together

    Watch (MicroPython)            Server (FastAPI, Docker, AWS)         Phone / laptop
    record a set to memory   -->   POST /sets: check, store raw file
    save to flash                  count reps, save a row (SQLite)
    button B: sync over Wi-Fi <--  receipt: set_id, stored
    delete after the receipt       GET /workouts, /sets/{id},
    then report its own health         /watch/health                -->  dashboard page

Rules that hold everywhere:
- **No receipt, no delete.** The watch keeps a set until the server confirms that exact set.
- **Uploads are idempotent.** The same set sent twice is stored once.
- **Raw data is the truth.** Counts are derived from it and can be recomputed.
- **The watch stays simple.** Counting and judging happen on the server.
- **Nothing draws or sleeps during a set.** Readings come first.

## The data

    workout  (sets close together in time)
      set    (one recording: exercise, reps, duration, quality)
        rep  (the time of each rep's top)

Raw file per set: 100 readings a second, 12 bytes each (accel x y z in mg, gyro x y z in 0.1 deg/s).

## What the dashboard shows

| Item | Meaning | Status |
|---|---|---|
| Today | Total reps, then a card per exercise with the reps of each set | Built 11-10 |
| Rep count | From `count_reps`, run when the set is uploaded | Built 11-10 |
| Rep timing | Seconds from each rep to the next, as bars | Built 11-10 |
| Fatigue | How much longer the last rep took than the set's usual rep. Sets at 25% or more are tinted | Built 11-10 |
| Suggestion | One sentence per exercise, from the rules below | Built 11-10 |
| Workouts | Sets less than 30 minutes apart, by the start time the watch saves | Built 11-10; start times not yet seen from the real watch |
| Watch health | Pass / check / fail for seven checks (see M2) | Built 11-10; not yet seen from the real watch |

All of it is tested on the laptop with real recorded sets. "Not yet seen from
the real watch" means the 11-10 watch code has to be flashed first.

## Milestones

No milestone starts until the one before it passes.

| | Milestone | Done when | Status |
|---|---|---|---|
| M0 | Audit every hop | Each hop marked works / missing | Done 11-09 |
| M1 | Core loop on home Wi-Fi | 5 curls shows 5 on the phone | Built. **The check on the real watch is still to do** |
| M2 | Health checks | All green; unplugging Wi-Fi or tilting the watch turns one red | Built and tested on the laptop 11-10; to confirm on the watch |
| M3 | Docker | One container, data on a volume, upload token + dashboard password; a restart keeps the data | Files written 11-10. Token, password and "restart keeps data" are tested as a real process. **The image has never been built** (no Docker on the laptop) |
| M4 | AWS | Same container on a small AWS server; on the phone hotspot, away from home, 5 curls shows 5 | Guide written (`deploy.md`). Not started: needs Dan's AWS account |
| M5 | Freeze, Fri to Sun | Real sets preloaded, screenshots and a recording, two rehearsals on the hotspot | Runbook written (`demo.md`); `push_sets.py` preloads the sets |

What is left, in order:

1. Flash the 11-10 watch files and run the M1 check: 5 curls, hold B, the watch says REPS 5 and the phone shows 5.
2. Look at the Watch tab: seven checks, and a new set shows a real start time.
3. `deploy.md`, steps 1 to 8. Step 4 is the first Docker build.
4. The hotspot run (M4), then `demo.md`'s night-before list.

M2 checks: sensor at rest reads about 1 g with the gyro near 0, Wi-Fi signal,
clock difference from the server, battery, free flash, sets waiting, and how
long ago the watch last reported. The watch only measures; the server judges
each number against a limit in `health.py`.

Cut lines:
- If M4 isn't working by Friday night, demo preloaded data.
- If Docker won't build, run the server without it (`deploy.md`, last section).
- No new exercises, no automatic exercise detection, no polish before M4 passes.

## Decided

- **The exercise is picked on the watch before the set** (2026-11-09). Button B
  cycles a short list, the choice stays selected for the next set, and it is
  saved in the set's `.json`. The server counts with it on upload. The
  dashboard can still correct it and recount. Sync moves to a long hold of B.
  Why: counting without the exercise is wrong for some real sets (6 curls
  counted 0), guessing it well would need far more labeled data than one
  person can record, and labeling sets afterwards from memory defeats the
  point of a counter. Every set recorded this way is also a labeled example
  for a future automatic guess. This replaces "dashboard only" in `api.md`.

## Open decisions

None blocking. Settled on 11-09 and 11-10 (reasons in `decisions.md`):

- The watch's list: curl, shoulder press, chest press, row, pull-up, push-up.
- HTTPS for the dashboard through Caddy and a DuckDNS name; the watch uploads over HTTP for the demo.
- Each set carries a start time; the watch sets its clock from the internet at every sync.
- Rep timing, fatigue and suggestions are in the demo.
- Mood faces on the watch, never drawn during a set.

Still unknown:
- Set 44 (curl, counted 3) and set 30 (no exercise, counted 6): how many reps were they really?
- Does the battery charge to 100%? It read 3.86 V (70%) while plugged in.

## Known limits

- One user, one wrist. Thresholds are tuned on Dan's recordings.
- Counting needs the exercise name for some movements.
- Fatigue measures how long a rep takes, pauses included: a rest before the last rep reads as slowing.
- The watch uploads over plain HTTP: the upload token could be read on a hostile network. It allows uploads only.
- One upload token for all watches, one password for the dashboard, no accounts.
- Loop hiccups of 10 to 20 ms during a set (about 14 late readings a second). Checked: the timing error is at most about 40 ms and no readings are missing.
- Light and deep sleep are tested on the laptop, not yet confirmed on the watch.
- The 250 mAh battery is small.

## Who does what

- Since 11-10 Claude writes the code, with tests, and explains each piece.
- Dan does everything that needs his hands or his accounts: flashing the watch, the checks on the real hardware, AWS and DuckDNS.
- Whoever writes it, Dan can explain every part before it counts as done. `demo.md` has the questions to practise on.

## Suggestions

The dashboard says what to do next, not just what happened. The rules, in
`coach.py`, still to be tuned on more real sets:

| What the sets of an exercise show | Suggestion |
|---|---|
| Every set hits the same reps and none slows more than about 10% | "That looked easy. Try a little more weight next time." |
| The last set slows 10 to 25% | "Good effort. Stay at this weight." |
| The first set already slows more than 25%, or reps fall sharply (8, 6, 3) | "Tough from the first set. Try a little less weight." |

Slowing at the end of a set is the point of training, so it is never flagged
by itself. "More weight" comes from staying steady across sets, not from moving
fast. Wording is always a suggestion ("try", "next time"): the app can't see
form or pain. Limits: it measures how long a rep takes, not bar speed, and it
doesn't know the weight.

## After the demo

- **Weight per set.** A field on each set in the dashboard, pre-filled with the
  last weight used for that exercise. Makes suggestions specific ("try 27.5 lb").
  Not on the watch, and no workout planning on the phone: the watch's job is to
  measure what actually happened.
- HTTPS from the watch, and a token per device.
- Per-exercise profiles, automatic exercise guess with confirmation, Postgres
  and object storage, background analysis, more wearers.
