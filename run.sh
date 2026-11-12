#!/usr/bin/env bash
# Start Gym Buddy: the API and the dashboard are one server.
#   ./run.sh            start it on port 8000
#   ./run.sh --reload   also restart whenever a Python file changes
# Ctrl+C stops it.
set -e

cd "$(dirname "$0")"                # the repo folder, wherever this is run from

if [ -f .env ]; then                # the token and password; without .env there is no password
    set -a; . ./.env; set +a
else
    echo "No .env here: starting with the development token and no password."
fi

cd server                           # the app looks for data/ relative to this folder
exec ../.venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 "$@"
