# Gym Buddy API

What every address takes and returns. The code is `server/app/main.py`; the
tests in `server/tests/` are the proof. Last updated 2026-11-10.

## Who may call what

| Caller | Proves it with | May call |
|---|---|---|
| The watch | `X-Token` header = `GYM_BUDDY_TOKEN` | `POST /sets`, `POST /watch/health` |
| The dashboard | HTTP Basic password = `GYM_BUDDY_PASSWORD` (any user name) | `GET /`, every other `GET`, `PUT /sets/{id}/exercise` |
| Anyone | nothing | `GET /health` |

A wrong or missing token or password is 401. The token does not open the
dashboard and the password does not allow uploads. With `GYM_BUDDY_PASSWORD`
empty the dashboard is open (home network only). Secrets are compared with
`secrets.compare_digest`, which takes the same time for a near miss as for a
wild guess.

## GET /health

`{"status": "ok"}`. Says the server is up; Docker's health check and
`check_server.py` use it.

## POST /sets (the watch uploads one set)

- Body: the set's `.bin` bytes. Header `X-Set-Meta`: the set's `.json`. Header `X-Token`.
  Raw bytes plus a header, not multipart, because MicroPython has no multipart helper.
- 201 with the receipt: `{"set_id": "00004-a956cd", "stored": true, "reps": 6}`.
  The watch deletes its copy only when `stored` is true and `set_id` matches what it sent.
  `reps` is null if counting failed; the set is stored anyway and can be recounted.
- The same set again: the same receipt, nothing rewritten. Retrying is always safe.
- 422 when `X-Set-Meta` isn't a JSON object; when `set_id` doesn't match
  `^\d{5}-[0-9a-f]{6}$` (it becomes a file name, so this blocks path tricks);
  when the body isn't exactly `count` x 12 bytes (an upload cut off by a Wi-Fi drop).
- Storage: raw files in `GYM_BUDDY_DATA`, each written under a temporary name
  and renamed, `.bin` last. Then the reps are counted and a row is saved in SQLite.

The `.json` the watch sends:

| Field | Meaning |
|---|---|
| `set_id` | Five digits, a dash, six hex digits |
| `count`, `rate_hz`, `duration_ms` | Readings, readings per second (100), length |
| `late` | Readings taken more than a tick late |
| `exercise` | Picked on the watch: `curl`, `shoulder_press`, `chest_press`, `row`, `pullup`, `pushup` |
| `started_at` | Unix seconds when the set started, or null if the watch didn't know the time yet |
| `format`, `accel_unit`, `gyro_unit` | `<6h`: accel x y z in mg, gyro x y z in 0.1 deg/s |

## GET /sets, GET /sets/{id}

- `GET /sets`: every set, newest first. Each: `set_id`, `exercise`, `reps`,
  `rep_times` (seconds into the set of each rep), `duration_ms`, `rate_hz`,
  `late`, `analysis_version`, `received_at`, `started_at`.
- `GET /sets/{id}`: one set plus its pace: `gaps` (seconds from each rep to the
  next), `usual_s` (the middle gap) and `slowdown_pct` (how much longer the
  last gap is than the usual one; never below 0; null under three reps).
  404 if unknown or not shaped like a set ID.

## PUT /sets/{id}/exercise

Body `{"exercise": "pullup"}`. Corrects a wrong pick and recounts from the raw
file. Returns the set as `GET /sets/{id}` does. 404 unknown set, 422 unknown
exercise. The raw files are never changed.

## GET /exercises

`[{"name": "curl", "label": "Curl"}, ...]` in the watch's order. The watch
holds its own copy of this list; the two must match.

## GET /workouts (what the Today screen draws)

Sets less than 30 minutes apart are one workout. Newest first:

    [{"started_at": "2026-11-10T19:27:00Z", "minutes": 23, "timed": true,
      "sets": 16, "reps": 92,
      "exercises": [{"exercise": "curl", "label": "Curl",
                     "sets": [{"set_id": "...", "reps": 5, "slowdown_pct": 12}, ...],
                     "suggestion": {"kind": "stay", "text": "Good effort. Stay at this weight."}}]}]

- A set's time is `started_at`, or when it was received if the watch didn't
  know the time. `timed` is false when any set in the workout used the fallback.
- `suggestion` is null with too little to go on. The rules are in `coach.py`
  and in PLAN.md, "Suggestions". Nothing here is stored: it is worked out from
  the rows on every request, so the rules can change without touching data.

## POST /watch/health, GET /watch/health

- The watch posts a JSON object after each sync: `accel_g`, `gyro_dps` (at
  rest), `rssi`, `watch_time`, `battery_pct`, `battery_mv`, `free_pct`,
  `sets_waiting`. 201 `{"stored": true, "server_time": ...}`. Missing fields
  are allowed; that check then reads "No reading".
- `GET` returns the latest report, judged: `{"seen": true, "status": "ok",
  "summary": "...", "received_at": "...", "checks": [{"key": "sensor",
  "label": "Motion sensor", "status": "ok" | "warn" | "fail", "value":
  "1.00 g at rest", "help": ""}, ...]}`. Seven checks: last report, sensor,
  Wi-Fi, clock, battery, storage, sets waiting. The limits are `LIMITS` in
  `health.py`. Before any report: `{"seen": false, ...}`.

## GET / (the dashboard)

One page, `server/app/static/index.html`: plain HTML and JavaScript, no
framework, no build step. Three screens: Today (`/workouts`), one set
(`/sets/{id}`), Watch (`/watch/health`). It asks again every 4 seconds while
visible, so a sync shows up without a reload.
