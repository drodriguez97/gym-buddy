# gym-buddy-weekend

Scratch copy for the weekend. Everything here drops into the real repo on Sunday.

## Run the tests here
    cd server
    python -m venv ..\.venv
    ..\.venv\Scripts\python.exe -m pip install -r requirements.txt
    ..\.venv\Scripts\python.exe -m pytest

## Adding a set
1. Copy the .bin and .json from the watch into server\tests\fixtures\
2. Add a row to recordings\labels.csv (kind = positive | negative | edge)
3. Run pytest. The new set is tested automatically.

## Sunday port
- server/app/analysis.py       -> replace the repo's copy
- server/tests/test_analysis.py -> replace
- server/tests/fixtures/*       -> copy in (new fixtures only; sets 3, 4, 7 stay in the repo)
- recordings/labels.csv         -> merge with the repo's (keep rows for 1 to 7, add the kind column)
- docs/*                        -> copy in; CHANGES.md rows become commit messages
- watch/*                       -> whatever you changed this weekend
