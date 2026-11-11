"""Send this laptop's stored sets to another Gym Buddy server, the way the watch would.

    python scripts/push_sets.py http://203.0.113.7:8000            (from server/)
    python scripts/push_sets.py http://203.0.113.7:8000 --as-workout

The token is read from the GYM_BUDDY_TOKEN environment variable, so it never
ends up in the shell history. Each set goes through POST /sets, the same door
the watch uses, so this also proves the new server's upload path works.
Safe to run again: the server answers a set it already has with the same receipt.

Use it to put real recorded sets on the demo server before the demo.

--as-workout gives the sets start times: one every 90 seconds, the last one
ten minutes ago. Sets recorded before the watch knew the time have none, so
without this the dashboard dates them all by when they were uploaded. The
movement data is untouched; only the start time is made up, so use it for
demo data only.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from app import db, main  # noqa: E402

SPACING_S = 90
ENDED_AGO_S = 10 * 60


def send(server, token, meta, data):
    request = urllib.request.Request(server + "/sets", data=data, method="POST",
                                     headers={"X-Token": token, "X-Set-Meta": json.dumps(meta)})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:             # 401, 422 and so on arrive here
        return error.code, error.read().decode()


def run(server, token, as_workout=False, now=None):
    paths = [p for p in sorted(main.SET_DIR.glob("*.bin")) if p.with_suffix(".json").exists()]
    first_start = int(now or time.time()) - ENDED_AGO_S - SPACING_S * (len(paths) - 1)
    stored = 0
    for index, path in enumerate(paths):
        meta = json.loads(path.with_suffix(".json").read_text())
        row = db.get_set(path.stem)
        if row and row["exercise"]:
            meta["exercise"] = row["exercise"]          # a label corrected on the dashboard goes along
        if as_workout:
            meta["started_at"] = first_start + SPACING_S * index
        status, answer = send(server, token, meta, path.read_bytes())
        ok = status in (200, 201) and answer.get("stored") is True
        stored += ok
        print(f"  {path.stem}  {meta.get('exercise') or '(no exercise)':15s} "
              + (f"stored, reps {answer['reps']}" if ok else f"NOT stored: {status} {answer}"))
    print(f"{stored} of {len(paths)} sets are on {server}")
    return stored == len(paths)


if __name__ == "__main__":
    arguments = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(arguments) != 1:
        sys.exit(__doc__)
    token = os.environ.get("GYM_BUDDY_TOKEN")
    if not token:
        sys.exit("Set GYM_BUDDY_TOKEN to the server's token first.")
    sys.exit(0 if run(arguments[0].rstrip("/"), token, "--as-workout" in sys.argv) else 1)
