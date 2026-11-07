# Gym Buddy API (spec, written before the code)

Decided 2026-10-30. Fill in the blanks before Sunday.

## Roles
- Watch: records sets to flash, uploads when on home Wi-Fi, deletes only after a matching receipt.
- Server (FastAPI): stores sets, runs count_reps, groups sets into workouts, serves the dashboard.
- Dashboard: reads from the server. Labels the exercise per set.

## POST /sets
- One request per set, .json metadata and .bin bytes together (multipart? or bin as body + metadata in headers? decide: ______).
- Header: X-Token = shared token.
- Response 201: {"set_id": "...", "stored": true}
- Duplicate set_id: same 201 receipt, file not written twice. Retrying is always safe.
- Watch deletes the local files only when the receipt's set_id matches the one it sent. A bare 200 is not a receipt.
- Bad token: 401. Missing/short body: 422.

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
