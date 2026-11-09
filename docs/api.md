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

## GET /sets, GET /sets/{id}
- Metadata + rep count + exercise + exercise_source (manual | guessed | confirmed).
- Decide: analyze on upload and store the count, or compute on every GET? Choice: ______ Why: ______

## GET /workouts
- A workout = sets with less than N minutes between them (N = ______). Needs started_at from NTP.

## Exercise labeling
- v1: dropdown in the dashboard, defaults to the previous set's exercise. Not on the watch.
- Exercise list comes from the server (GET /exercises), not hard-coded in the dashboard.
- Later: the server fills a guess, the user confirms. Confirmed sets are training data.

## Watch upload loop (after POST /sets exists)
- Join Wi-Fi, sync clock, for each set in /flash/sets: POST, check receipt, delete.
- Retries: ______ attempts, ______ s apart. Screen shows "Synced N sets" or "N left, retrying".

## Layout
server/app/main.py (routes), storage.py (save, exists), analysis.py, models.py (pydantic). tests/test_api.py with fastapi.testclient.
Build order: POST /sets -> GET /sets -> watch upload loop -> workouts -> exercise guess -> dashboard.
