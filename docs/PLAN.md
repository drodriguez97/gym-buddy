# Gym Buddy: the plan

The one reference for what we are building, for whom, and by when. If another
document disagrees with this one, this one wins and the other gets fixed.
Last updated 2026-11-09.

Other documents, and what each is for:
- `api.md`: the exact request and response of every endpoint
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
    delete after the receipt       GET /sets, /workouts, /health    -->  dashboard pages

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
| Sets, newest first | Exercise, reps, duration, when | Not built (M1) |
| Rep count | From `count_reps` | Analyzer works; not yet run on upload |
| Rep timing | Seconds per rep, and the average for the set | Not built. The analyzer already returns each rep's time, so this is small |
| Fatigue | How much the last reps slow down against the fastest rep of the set | Not built. Needs rep timing first |
| Suggestion | One sentence per exercise, from the rules below | Not built. Needs fatigue first |
| Workouts | Sets grouped by time | Not built. Needs a start time on each set |
| Device health | Pass / fail per check (see M2) | Not built (M2) |

For the demo, the first two rows and device health are required. Rep timing
and fatigue are the next most valuable and are added only after M1 passes.

## Milestones

No milestone starts until the one before it passes.

| | Milestone | Done when | Status |
|---|---|---|---|
| M0 | Audit every hop | Each hop marked works / missing | Done 11-09 |
| M1 | Core loop on home Wi-Fi | 5 curls shows 5 on the phone | In progress |
| M2 | Health checks | All green; unplugging Wi-Fi or tilting the watch turns one red | Not started |
| M3 | Docker | One container, data on a volume, upload token + dashboard password; a restart keeps the data | Not started |
| M4 | AWS | Same container on a small AWS server; on the phone hotspot, away from home, 5 curls shows 5 | Not started |
| M5 | Freeze, Fri to Sun | Real sets preloaded, screenshots and a recording, two rehearsals on the hotspot | Not started |

M1, piece by piece:

| Piece | Status |
|---|---|
| Watch joins Wi-Fi and reaches the server | Done |
| Watch uploads, checks the receipt, deletes (button B) | Done; 26 real sets on the server |
| Server counts on upload and saves a row (SQLite) | Done 11-10 |
| `GET /sets`, `GET /sets/{id}` | Done 11-10 |
| Set a set's exercise and recount | Done 11-10 |
| Page listing sets and reps | Done 11-10; the M1 check on the watch is still to do |

M2 checks: sensor at rest reads about 1 g with the gyro near 0, Wi-Fi signal,
clock difference from the server, battery, free flash, sets waiting. The
server judges each against a limit.

Cut lines:
- If M4 isn't working by Friday night, demo preloaded data.
- If M2 runs long, ship the sensor, Wi-Fi and clock checks only.
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

1. **Which exercises are on the watch's list.** Proposed, from what the
   analyzer is tested on: curl, shoulder press, chest press, row, pull-up, push-up.
2. **HTTP or HTTPS on AWS.** Leaning: HTTPS for the dashboard through Caddy and a DuckDNS name; test the watch on HTTPS and fall back to HTTP with a throwaway token if it is unreliable.
3. **Time on each set.** The watch saves no start time yet. Needed for workouts and the clock check.
4. **Are rep timing and fatigue in the demo?** They were goals of the first design. Proposed: only after M1 passes.
5. **Watch face.** Today's screen is a diagnostics screen. Mood faces are wanted; proposed after M1, and never drawn during a set.

## Known limits

- One user, one wrist. Thresholds are tuned on Dan's recordings.
- Counting needs the exercise name for some movements.
- Loop hiccups of 10 to 20 ms during a set (about 14 late readings a second). Checked: the timing error is at most about 40 ms and no readings are missing.
- Light and deep sleep are tested on the laptop, not yet confirmed on the watch.
- The 250 mAh battery is small.

## Who does what

- Dan writes the API endpoints and the health checks. Claude guides and reviews.
- Claude writes the dashboard pages and, when asked, the watch code, with tests.
- Whoever writes it, Dan can explain every part before it counts as done.

## Suggestions (after M1, with rep timing and fatigue)

The dashboard says what to do next, not just what happened. Starting rules,
to be tuned on real sets:

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
- Per-exercise profiles, automatic exercise guess with confirmation, a start
  time and workouts, Postgres and object storage, a token per device, background
  analysis, more wearers.
