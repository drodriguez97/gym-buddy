# Gym Buddy API (spec, written before the code)

Decided 2026-10-30. Fill in the blanks before Sunday.

## Roles
- Watch: records sets to flash, uploads when on home Wi-Fi, deletes only after a matching receipt.
- Server (FastAPI): stores sets, runs count_reps, groups sets into workouts, serves the dashboard.
- Dashboard: reads from the server. Labels the exercise per set.

## POST /sets (built 2026-11-08, server/app/main.py)
- One request per set. Decided: the .bin bytes are the request body, and the set's .json goes in the `X-Set-Meta` header. Chosen over multipart because MicroPython's urequests has no multipart helper; raw bytes plus a header is a few lines on the watch.
- Header: X-Token = shared token. Server reads it from the `GYM_BUDDY_TOKEN` environment variable (default `dev-token` for development only).
- Response 201: {"set_id": "...", "stored": true}
- Duplicate set_id: same 201 receipt, file not written twice. Retrying is always safe.
- Watch deletes the local files only when the receipt's set_id matches the one it sent. A bare 200 is not a receipt.
- Bad token: 401. Missing/short body: 422.
- 422 also for: X-Set-Meta that isn't a JSON object, a set_id not matching `^\d{5}-[0-9a-f]{6}$` (it becomes a file name, so this blocks path traversal), and a body that isn't exactly `count` × 12 bytes (catches uploads cut off by a Wi-Fi drop).
- Storage: `GYM_BUDDY_DATA` (default `data/sets`). Each file is written to a temp name and renamed, and the .bin is written last, so a crash never leaves a half set that counts as "already have it".
- Tested: server/tests/test_api.py (TestClient, fixture set 00004), and over real HTTP with server/scripts/try_upload.py (set 00007 stored, still counts 6 reps).

## GET /sets, GET /sets/{id} (built 2026-11-10)
- `GET /sets`: every set, newest first. `GET /sets/{id}`: one set, 404 if unknown or not shaped like a set ID.
- Each set: set_id, exercise, reps, rep_times (seconds into the set of each rep), duration_ms, rate_hz, late, analysis_version, received_at.
- Decided: analyze on upload and store the count. Why: counting takes milliseconds, so the upload stays fast, the dashboard reads a ready number instead of opening raw files, and the receipt can carry the count back to the watch. `analysis_version` marks which analyzer produced each count, so old sets can be found and recounted when the analyzer improves.
- The receipt is now {"set_id": "...", "stored": true, "reps": 6}. `reps` is null if the analyzer failed; the set is stored and receipted anyway, because the raw file is safe and can be recounted.
- Storage: SQLite, one file (`GYM_BUDDY_DB`, default `data/gymbuddy.db`), one row per set. The raw files stay the truth; `scripts/backfill.py` rebuilds rows from them.
- Still to do: exercise_source, and no password on the GET endpoints yet (needed before AWS).

## GET /workouts
- A workout = sets with less than N minutes between them (N = ______). Needs started_at from NTP.

## Exercise labeling (built 2026-11-10)
- The exercise is picked on the watch before the set and arrives in the set's .json (see PLAN.md, "Decided").
- `GET /exercises`: the list, in the watch's order, as [{"name": "curl", "label": "Curl"}, ...]. The dashboard's dropdown is filled from it.
- `PUT /sets/{id}/exercise` with {"exercise": "pullup"}: corrects a wrong pick and recounts from the raw file. Returns the updated set. 404 for an unknown set, 422 for an exercise not on the list. The raw files are never changed.
- Still to do: no password on this endpoint yet (needed before AWS). The watch and the server each hold a copy of the list; they must match.
- Later: the server fills a guess, the user confirms. Confirmed sets are training data.

## The dashboard (built 2026-11-10)
- `GET /`: one page, server/app/static/index.html. Plain HTML and JavaScript, no framework and no build step.
- Today: total reps, then one card per exercise with a rep count per set. One set: reps, the time from each rep to the next, and the exercise dropdown.
- It asks `GET /sets` every 4 seconds while visible, so a sync shows up without a reload.
- Days are grouped by when a set was received, because sets have no start time yet.

## Watch upload loop (after POST /sets exists)
- Join Wi-Fi, sync clock, for each set in /flash/sets: POST, check receipt, delete.
- Retries: ______ attempts, ______ s apart. Screen shows "Synced N sets" or "N left, retrying".

## Layout
server/app/main.py (routes), storage.py (save, exists), analysis.py, models.py (pydantic). tests/test_api.py with fastapi.testclient.
Build order: POST /sets -> GET /sets -> watch upload loop -> workouts -> exercise guess -> dashboard.
