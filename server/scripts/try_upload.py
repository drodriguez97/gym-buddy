"""Send one recorded set to the running server: python scripts/try_upload.py <path to .bin>"""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

bin_path = Path(sys.argv[1])
meta = json.loads(bin_path.with_suffix(".json").read_text())

request = urllib.request.Request(
    "http://127.0.0.1:8000/sets",
    data=bin_path.read_bytes(),
    method="POST",
    headers={"X-Token": "dev-token", "X-Set-Meta": json.dumps(meta)},
)
try:
    with urllib.request.urlopen(request) as response:
        print(response.status, response.read().decode())
except urllib.error.HTTPError as error:          # 401, 422 etc. arrive here
    print(error.code, error.read().decode())