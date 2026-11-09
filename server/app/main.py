import json
import os
import re
from pathlib import Path

from fastapi import FastAPI, Request, Header, HTTPException

app = FastAPI(title="gym-buddy")

TOKEN = os.environ.get("GYM_BUDDY_TOKEN", "dev-token")
SET_DIR = Path(os.environ.get("GYM_BUDDY_DATA", "data/sets"))
SET_ID = re.compile(r"^\d{5}-[0-9a-f]{6}$")     # e.g. 00004-a956cd, nothing else
BYTES_PER_READING = 12                          # 6 int16s: accel xyz, gyro xyz


def save_atomically(path, data):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/sets", status_code=201)
async def upload_sets(
    request: Request,
    x_token: str | None = Header(default=None),
    x_set_meta: str | None = Header(default=None),
):
    # Who is calling? Missing and wrong are both 401
    if x_token != TOKEN:
        raise HTTPException(status_code=401, detail="missing or wrong token")

    # What do they say they are sending?
    try:
        meta = json.loads(x_set_meta or "")
    except ValueError:
        raise HTTPException(status_code=422, detail="X-Set-Meta is not valid JSON")
    if not isinstance(meta, dict):
        raise HTTPException(status_code=422, detail="X-Set-Meta must be a JSON object")

    # Is the ID safe to use as a file name?
    set_id = meta.get("set_id")
    if not isinstance(set_id, str) or not SET_ID.match(set_id):
        raise HTTPException(status_code=422, detail="bad set_id")

    # Did all of it arrive? The watch's .json says how many readings it sent.
    data = await request.body()
    count = meta.get("count")
    if not isinstance(count, int) or not data or len(data) != count * BYTES_PER_READING:
        raise HTTPException(status_code=422,
                            detail=f"expected {count} readings x {BYTES_PER_READING} bytes, got {len(data)} bytes")

    # Already have it? Same receipt, nothing rewritten.
    path = SET_DIR / f"{set_id}.bin"
    if path.exists():
        return {"set_id": set_id, "stored": True}

    # The .bin is what the duplicate check looks at, so it is written last.
    SET_DIR.mkdir(parents=True, exist_ok=True)
    save_atomically(SET_DIR / f"{set_id}.json", json.dumps(meta).encode())
    save_atomically(path, data)

    return {"set_id": set_id, "stored": True}
