# Gym Buddy

A wrist-worn rep counter for strength training. An M5StickS3 watch records the
motion of each set, a server counts the reps, and a web page shows the workout:
reps per set, how much each set slowed down, and a suggestion for next time.

    Watch (MicroPython)          Server (FastAPI + SQLite, in Docker)       Phone
    record a set, save it
    hold B: upload       ───►    check, store the raw file, count reps
                         ◄───    receipt: set_id, stored, reps
    delete its copy              workouts, pace, suggestions, watch health  ◄───  dashboard

Three rules hold everywhere:

- **No receipt, no delete.** The watch keeps a set until the server confirms that exact set.
- **Uploads are idempotent.** The same set sent twice is stored once.
- **Raw data is the truth.** Counts are worked out from it and can be redone.

## Where things are

| Folder | What |
|---|---|
| `watch/` | The program on the watch: `main.py` (states and screens), `recorder.py`, `sync.py`, `clock.py`, `faces.py` |
| `watch/tests/` | A fake watch (screen, buttons, sensor, clock) that the real watch code runs against |
| `server/app/` | `main.py` (the API), `analysis.py` (rep counting), `coach.py` (pace, workouts, suggestions), `health.py` (watch checks), `db.py`, `static/index.html` (the dashboard) |
| `server/scripts/` | `push_sets.py`, `check_server.py`, `backfill.py`, `archive_sets.py` and analysis tools |
| `server/tests/` | API, auth, coach, health, analyzer and a deploy rehearsal |
| `docs/` | Start with `PLAN.md`. Then `api.md`, `deploy.md`, `demo.md`, `decisions.md`, `pain-points.md` |

## Run it on a laptop (Windows)

```powershell
cd server
python -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
..\.venv\Scripts\python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000. With no settings the token is `dev-token` and the
dashboard has no password: fine on a home network, never on the internet.

| Setting (environment variable) | Meaning | Default |
|---|---|---|
| `GYM_BUDDY_TOKEN` | The watch sends this with every upload | `dev-token` |
| `GYM_BUDDY_PASSWORD` | The dashboard asks for this; empty means open | empty |
| `GYM_BUDDY_DATA` | Folder for the raw sets | `data/sets` |
| `GYM_BUDDY_DB` | The SQLite file | `data/gymbuddy.db` |

## Run the tests

```powershell
cd server; ..\.venv\Scripts\python.exe -m pytest -q
cd ..;     .\.venv\Scripts\python.exe -m pytest watch\tests -q
```

## Put it on the watch

Copy `watch/config.example.py` to `watch/config.py`, fill in the Wi-Fi name,
password, server address and token, then save `config.py`, `main.py`,
`recorder.py`, `sync.py`, `clock.py` and `faces.py` to the watch with Thonny.
`config.py` is in `.gitignore`.

On the watch: **A** starts and stops a set. **B** changes the exercise. **Hold B** syncs.
Hold B while it boots for developer mode (timing numbers, errors shown in Thonny).

## Put it on a server

`docs/deploy.md` walks through AWS, Docker and HTTPS. `docs/demo.md` is the demo runbook.
