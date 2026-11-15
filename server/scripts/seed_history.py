"""Seed four weeks of back-dated workouts by replaying real recorded sets.

    python scripts/seed_history.py                                  (from server/) print the plan, send nothing
    python scripts/seed_history.py --send https://your-server       upload it

Standalone: it imports nothing from the app and touches no database. Each set
goes through POST /sets, the same door the watch uses, so the server validates,
stores and counts it exactly like a real upload. The token is read from the
GYM_BUDDY_TOKEN environment variable, so it never ends up in the shell history.

What is real and what is made up: the movement data is a real recording of
that exercise, byte for byte. The set ID and the start time are made up.

The plan: Monday, Wednesday and Friday of the 28 days before --today, each
workout starting near 15:00 UTC, 3 or 4 sets, rests of 60 to 120 seconds.
All times are UTC. The same --today always gives the same plan and the same
IDs, and the server answers a set it already has with the same receipt, so
running it twice adds nothing.

Every seeded set is marked two ways:
  - its ID is 9DDNN-5eedXX (the watch counts up from 00001 and is nowhere near 90000)
  - its stored .json has "seeded": true and "seeded_from": the recording it replays

To take them all out again (the row, then the files):

    DELETE FROM sets WHERE set_id LIKE '9____-5eed__';
    rm /data/sets/9????-5eed??.*
"""
import argparse
import datetime
import json
import os
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path

UTC = datetime.timezone.utc
HERE = Path(__file__).resolve().parent
FIXTURES = HERE.parent / "tests" / "fixtures"     # the labelled recordings kept in Git
BYTES_PER_READING = 12

# The labelled recordings to replay, by the exercise that was really done.
SOURCES = {
    "curl":           ["00004-a956cd", "00007-130966"],
    "shoulder_press": ["00009-8a9712", "00010-b7c065"],
    "chest_press":    ["00011-986608", "00012-38b5e5"],
    "row":            ["00013-db6df8", "00014-8c8699", "00015-8494c3", "00016-929d8f"],
    "pullup":         ["00017-2aa0e3", "00018-f6719e"],
    "pushup":         ["00026-2ffe6b", "00027-80659c"],
}

# Three workouts that take turns. Every other day drops its last set, so days have 4 or 3.
WORKOUTS = [
    ["curl", "curl", "shoulder_press", "shoulder_press"],
    ["chest_press", "chest_press", "row", "row"],
    ["pullup", "pullup", "pushup", "pushup"],        # the second pull-up set (00018) is one that was pushed hard
]
WEEKDAYS = (0, 2, 4)                    # Monday, Wednesday, Friday
DAYS_BACK = 28
START_HOUR_UTC = 15                     # 7 am Pacific in winter
START_JITTER_MIN = 20
REST_S = (60, 120)


def plan(today, sets_dir):
    """The sets to send: a list of (meta, path of the .bin to replay), oldest first."""
    rng = random.Random(5330)           # fixed, so the plan is the same every run
    turn = {exercise: 0 for exercise in SOURCES}
    days = [today - datetime.timedelta(days=back) for back in range(DAYS_BACK, 0, -1)]
    days = [day for day in days if day.weekday() in WEEKDAYS]
    planned = []
    for day_number, day in enumerate(days, start=1):
        exercises = WORKOUTS[(day_number - 1) % len(WORKOUTS)]
        exercises = exercises if day_number % 2 else exercises[:-1]
        start = datetime.datetime(day.year, day.month, day.day, START_HOUR_UTC, tzinfo=UTC)
        at = int(start.timestamp()) + 60 * rng.randint(-START_JITTER_MIN, START_JITTER_MIN)
        for set_number, exercise in enumerate(exercises, start=1):
            source = SOURCES[exercise][turn[exercise] % len(SOURCES[exercise])]
            turn[exercise] += 1
            path = next((folder / f"{source}.bin" for folder in (sets_dir, FIXTURES)
                         if (folder / f"{source}.bin").exists()), None)
            if path is None:
                sys.exit(f"no recording {source} in {sets_dir} or {FIXTURES}; not sending anything")
            meta = json.loads(path.with_suffix(".json").read_text())
            if path.stat().st_size != meta["count"] * BYTES_PER_READING:
                sys.exit(f"{path} does not match its .json; not sending anything")
            meta.update(set_id=f"9{day_number:02d}{set_number:02d}-5eed{len(planned):02x}",
                        exercise=exercise, started_at=at, seeded=True, seeded_from=source)
            planned.append((meta, path))
            at += round(meta["duration_ms"] / 1000) + rng.randint(*REST_S)
    return planned


def utc(seconds):
    return datetime.datetime.fromtimestamp(seconds, UTC).strftime("%a %Y-%m-%d %H:%M:%SZ")


def send(server, token, meta, data):
    request = urllib.request.Request(server + "/sets", data=data, method="POST",
                                     headers={"X-Token": token, "X-Set-Meta": json.dumps(meta)})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:             # 401, 422 and so on arrive here
        return error.code, error.read().decode()


def main():
    parser = argparse.ArgumentParser(description="Seed back-dated workouts through POST /sets.")
    parser.add_argument("--send", metavar="SERVER", help="upload to this server; without it, only the plan is printed")
    parser.add_argument("--today", help="YYYY-MM-DD (UTC) the four weeks end before; default: today")
    parser.add_argument("--sets", default=HERE.parent / "data" / "sets", type=Path,
                        help="folder holding the recordings to replay (default: server/data/sets, then tests/fixtures)")
    args = parser.parse_args()
    today = (datetime.date.fromisoformat(args.today) if args.today
             else datetime.datetime.now(UTC).date())
    planned = plan(today, args.sets)

    token = os.environ.get("GYM_BUDDY_TOKEN")
    if args.send and not token:
        sys.exit("Set GYM_BUDDY_TOKEN to the server's token first.")
    server = (args.send or "").rstrip("/")

    stored, last_day = 0, None
    for meta, path in planned:
        day = utc(meta["started_at"])[:14]
        if day != last_day:
            print(day)
            last_day = day
        line = (f"  {utc(meta['started_at'])[15:]}  {meta['set_id']}  {meta['exercise']:15s}"
                f" {meta['duration_ms'] / 1000:5.1f} s  replays {meta['seeded_from']}")
        if server:
            status, answer = send(server, token, meta, path.read_bytes())
            ok = status in (200, 201) and isinstance(answer, dict) and answer.get("stored") is True
            stored += ok
            line += f"  -> stored, reps {answer['reps']}" if ok else f"  -> NOT stored: {status} {answer}"
        print(line)

    days = len({utc(meta["started_at"])[:14] for meta, _ in planned})
    if server:
        print(f"{stored} of {len(planned)} sets are on {server}")
        return stored == len(planned)
    print(f"Plan only: {len(planned)} sets on {days} days, nothing sent. Add --send SERVER to upload.")
    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
