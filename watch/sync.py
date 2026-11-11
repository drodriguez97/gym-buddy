# sync.py: upload finished sets to the server. No receipt, no delete.
#
# For each set in /flash/sets: POST the .bin as the body with the .json in the
# X-Set-Meta header (docs/api.md), and delete the two files only when the
# server's receipt names the same set_id. Anything else leaves the set on the
# watch for the next sync. Sending a set twice is safe: the server stores it once.
# Needs config.py on the watch (see config.example.py).
import gc
import json
import os
import time
import network
import config

try:
    import requests             # UIFlow2 firmware
except ImportError:
    import urequests as requests

SET_DIR = "/flash/sets"
WIFI_TIMEOUT_MS = 15000
TRIES = 3                       # per set, when the server can't be reached
RETRY_WAIT_MS = 5000
POST_TIMEOUT_S = 15             # give up on one upload after this long; never hang with Wi-Fi on
last_reps = []                  # rep count of each set stored by the latest sync, when the server sends one


def pending_sets():
    # Set IDs ready to upload, oldest first. A set is ready once its .json exists:
    # the recorder writes that last, so a .bin on its own is still being recorded.
    try:
        names = os.listdir(SET_DIR)
    except OSError:
        return []
    ready = []
    for name in sorted(names):
        if not name.endswith(".json"):
            continue
        set_id = name[:-5]
        if set_id + ".bin" in names:
            ready.append(set_id)
        elif set_id + ".tmp" in names:
            pass                # a save cut short by power loss; the recorder finishes it at boot
        else:
            # Left over from a delete that was cut short after the receipt: the
            # server already has this set, so the stray .json can go.
            os.remove("%s/%s" % (SET_DIR, name))
    return ready


def join_wifi():
    # Returns the connected WLAN, or None after WIFI_TIMEOUT_MS.
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        start = time.ticks_ms()
        while not wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), start) > WIFI_TIMEOUT_MS:
                return None
            time.sleep_ms(100)
    return wlan


def wifi_off():
    # The radio costs tens of mA; it is only ever on during a sync.
    try:
        network.WLAN(network.STA_IF).active(False)
    except Exception:
        pass


def post(url, data, headers):
    try:
        return requests.post(url, data=data, headers=headers, timeout=POST_TIMEOUT_S)
    except TypeError:           # an older requests library without timeout
        return requests.post(url, data=data, headers=headers)


def upload_set(set_id):
    # Returns "stored" (and the set is deleted), "rejected" (server refused it; kept),
    # "bad token" or "no receipt". Raises OSError if the server can't be reached.
    with open("%s/%s.json" % (SET_DIR, set_id)) as f:
        meta = f.read().strip()
    with open("%s/%s.bin" % (SET_DIR, set_id), "rb") as f:
        data = f.read()
    r = post(config.SERVER + "/sets", data,
             {"X-Token": config.TOKEN, "X-Set-Meta": meta, "Content-Type": "application/octet-stream"})
    try:
        status = r.status_code
        try:
            receipt = r.json() if status == 201 else None
        except ValueError:
            receipt = None
    finally:
        r.close()               # each open response holds memory the watch is short on
    del data

    if status == 401:
        return "bad token"
    if status == 422:
        return "rejected"
    # A bare 2xx is not a receipt: it must name the set we sent.
    if (status != 201 or not isinstance(receipt, dict)
            or receipt.get("set_id") != set_id or receipt.get("stored") is not True):
        return "no receipt"
    if isinstance(receipt.get("reps"), int):
        last_reps.append(receipt["reps"])
    os.remove("%s/%s.bin" % (SET_DIR, set_id))      # .bin first: a stray .json is cleaned up later
    os.remove("%s/%s.json" % (SET_DIR, set_id))
    return "stored"


def sync(report=None):
    # Upload everything that is ready. report(text) is called with progress for the screen.
    # Returns (sets stored, sets still on the watch, problem or None).
    def say(text):
        if report:
            report(text)

    del last_reps[:]
    sets = pending_sets()
    if not sets:
        return 0, 0, None
    stored = 0
    problem = None
    try:
        say("joining Wi-Fi")
        if join_wifi() is None:
            return 0, len(sets), "no Wi-Fi"
        for i, set_id in enumerate(sets):
            say("set %d of %d" % (i + 1, len(sets)))
            gc.collect()
            result = None
            for attempt in range(TRIES):
                try:
                    result = upload_set(set_id)
                    break
                except OSError:
                    if attempt + 1 < TRIES:
                        say("retry %d of %d" % (attempt + 2, TRIES))
                        time.sleep_ms(RETRY_WAIT_MS)
            if result is None:
                problem = "no server"       # unreachable after every try: the rest would fail too
                break
            if result == "bad token":
                problem = "bad token"       # every set would get the same answer
                break
            if result == "stored":
                stored += 1
            else:
                problem = result            # "rejected" or "no receipt": keep it, try the next set
    finally:
        wifi_off()
    return stored, len(pending_sets()), problem
