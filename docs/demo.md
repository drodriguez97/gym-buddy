# The demo: Monday 2026-11-16

An informal demo, not slides. One line: **do 5 curls, hold B, the phone shows 5.**
Everything else on this page is there so that line cannot fail, and so you can
explain every part of it.

## The night before

- [ ] Watch charged to full, then left on the charger.
- [ ] Phone charged. Hotspot name and password match `watch/config.py`.
- [ ] From the laptop: `check_server.py` against the AWS server says "All good."
- [ ] One full run on the hotspot, away from home Wi-Fi: 5 curls → hold B → phone shows 5.
- [ ] Screenshots of Today, one set, and the Watch tab saved on the phone (the fallback if there is no signal in the room).
- [ ] A screen recording of the full run saved on the phone.
- [ ] Dashboard open in the phone's browser, already signed in.

## In the room, before you start

1. Hotspot on. Watch on (press A): the ready face, your exercise on screen.
2. Hold B once. "SYNCED" and "NOTHING NEW" means watch → hotspot → AWS works right now.
3. Phone: reload the dashboard. The Watch tab says "seen just now" and all checks pass.

If step 2 fails, you know before anyone is watching. Go to "If something breaks".

## The run (about three minutes)

| Do | Say |
|---|---|
| Show the watch face | "It's an M5Stick: a small microcontroller with a motion sensor and a screen. I picked curls with this button." |
| Press A, do 5 curls, press A | "It's recording 100 readings a second into memory. Nothing else happens during a set: no drawing, no Wi-Fi. Readings come first." |
| Point at "SAVED" | "The set is on the watch's flash now. If the battery died here, I'd lose nothing." |
| Hold B | "Now it joins Wi-Fi and uploads. It only deletes its copy when the server sends back a receipt for that exact set. No receipt, no delete." |
| Point at "REPS 5" on the watch | "The server counted the reps and put the count in the receipt." |
| Show the phone, Today: the new set pulses and is marked "New" | "Same number here. The watch never counted anything: it's a recorder. All the thinking is on the server, so I can improve the counting without touching the watch." |
| Tap the set | "Time between each rep. The last rep took longer than my usual pace: that's fatigue, measured." |
| Back; point at the suggestion | "Across the sets of an exercise it turns that into one plain sentence." |
| Set screen: plus, minus, weight | "If the counter is wrong I correct it, and it keeps both numbers: mine, and what it found. That difference is training data. With a weight, the suggestion names a number." |
| Progress tab | "And across workouts: total reps per exercise, and the change from last time." |
| Watch tab | "The watch also reports its own health on every sync: sensor, Wi-Fi, clock, battery, storage. The server judges each against a limit." |

## How it fits together (draw this if asked)

    Watch                       Server (one container on AWS)          Phone
    record → save to flash
    hold B: POST /sets  ─────►  check token, check size
                                save raw file  (volume)
                                count reps → row in SQLite (volume)
            ◄─────  receipt: set_id, stored, reps
    delete its copy             GET /workouts, /sets/{id},      ◄────  dashboard
                                    /watch/health  (password)

## Questions you may get, and the short answers

**Why count on the server and not the watch?** The watch is slow and has a
250 mAh battery. Recording is cheap; analysis in Python on a server is easy to
change and test. The cost: no live count on the wrist.

**What if Wi-Fi drops mid-upload?** The server checks the body is exactly
`count × 12` bytes and rejects anything short. The watch keeps the set and
tries again next sync. Sending the same set twice is safe: the server answers
with the same receipt and stores nothing new (idempotent).

**What if the server crashes mid-save?** Files are written under a temporary
name and renamed, and the `.bin` is written last, so a half-written set never
looks finished. The count is saved after the raw file: if that step is lost,
the next upload of the set finds the file and counts it.

**Why keep the raw files if you have a database?** The raw recording is the
truth; the row is worked out from it. When the counter improves, every old set
can be recounted (`backfill.py`), and `analysis_version` says which counter
produced each number.

**Why SQLite and not Postgres?** One watch, one writer, one file. It needs no
second container and backs up by copying a file. With many users I'd move to
Postgres for concurrent writes and put the raw files in object storage (S3).

**What does Docker give you?** The same server on my laptop and on AWS, built
from one file. The container is disposable; the data sits on a volume outside
it. I delete the container, start a new one, and the sets are still there.

**How is it secured?** Two secrets, both environment variables, neither in
Git. The watch sends a token; the dashboard asks for a password over HTTPS.
The set ID becomes a file name, so it must match a strict pattern, which
blocks path tricks. Known gap: the watch uploads over plain HTTP, so the token
could be read on a hostile network. It only allows uploads, not reads. HTTPS
from the watch is next.

**How do you know the counts are right?** Every recorded set has a label (true
reps) and a test that runs the counter on it. The 13 labeled sets on the
server all count correctly. On a public dataset from other people's forearms
it scores 79% within one rep when told the exercise: it is tuned to my wrist,
and I say so.

**Why pick the exercise on the watch?** Counting blind is wrong for some
movements (6 real curls counted as 0). Guessing the exercise needs far more
labeled data than I can record alone. A two-second choice on the watch makes
the count right and makes every set a labeled example for later.

**How is it tested without the hardware?** A fake watch: stand-ins for the
screen, buttons, sensor and clock, with time under the test's control. The
real watch code runs against it, and the sync tests upload to the real server
code. About 180 watch tests and 160 server tests.

**What would you do next?** HTTPS from the watch and a token per device; use
the corrected counts to improve the counter; automatic exercise guess with
confirmation; a count on the wrist during the set.

## If something breaks

| What you see | Do |
|---|---|
| Watch shows OOPS after hold B | The set is safe on the watch. Check the hotspot is on and 2.4 GHz, hold B again. |
| Still OOPS | Say "the watch keeps the set until the server confirms it, so nothing is lost", and show the preloaded workout on the phone. |
| Phone can't load the dashboard | Show the screenshots, then the recording. |
| Count is off by one | Say so. Open the set and show the rep gaps: "this is why I keep the raw data: I can see what it saw and fix the counter." |
| Watch won't turn on | It is on the charger from the night before; if it still won't, the recording is the demo. |

## Not confirmed on the hardware yet (as of 2026-11-10)

Do these before the freeze, and cross them off:

- [ ] Flash the 11-10 watch files (`clock.py`, `recorder.py`, `sync.py`, `main.py`) and run the 5-curl check on home Wi-Fi.
- [ ] After a sync, a new set shows a real start time on the dashboard ("Today, 7:42 PM", not "synced").
- [ ] The Watch tab shows a report with all seven checks.
- [ ] The hotspot run (M4).
- [ ] The battery: does it reach 100% on a wall charger?
