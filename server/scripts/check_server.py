"""Is a Gym Buddy server set up correctly? Run this against it after every deploy.

    python scripts/check_server.py http://203.0.113.7:8000         (from server/)

Reads GYM_BUDDY_TOKEN and GYM_BUDDY_PASSWORD from the environment: the values
the server is supposed to have. It only reads; nothing on the server changes.
Exits with 0 when every check passes, so it can be used in a script.
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request


def ask(url, method="GET", headers=None, data=None):
    """(status, body) for one request; status 0 when the server can't be reached at all."""
    request = urllib.request.Request(url, method=method, headers=headers or {}, data=data)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()
    except (urllib.error.URLError, OSError) as error:
        return 0, str(error)


def run(server, token, password, ask=ask):
    """The checks, in the order you'd debug them. Returns a list of (passed, what, note)."""
    basic = {"Authorization": "Basic " + base64.b64encode(f":{password}".encode()).decode()}
    results = []

    def check(what, passed, if_not, note=""):
        results.append((bool(passed), what, note if passed else if_not))
        return passed

    status, body = ask(server + "/health")
    if not check("the server answers", status == 200, f"GET /health gave {status or body}"):
        return results              # nothing else can pass

    status, _ = ask(server + "/sets")
    check("the dashboard is closed without the password", status == 401,
          f"GET /sets without a password gave {status}; is GYM_BUDDY_PASSWORD set on the server?")

    status, body = ask(server + "/workouts", headers=basic)
    if check("the password opens the dashboard", status == 200, f"GET /workouts gave {status}"):
        workouts = json.loads(body)
        sets = sum(w["sets"] for w in workouts)
        check("there are sets to show", sets > 0, "none stored yet", f"{sets} sets in {len(workouts)} workouts")

    status, _ = ask(server + "/watch/health", "POST", {"X-Token": "not-the-token"}, b"{}")
    check("a wrong token is refused", status == 401, f"POST /watch/health with a wrong token gave {status}")

    # The right token, checked without storing anything: a body that isn't JSON
    # gets past the token check (so not 401) and is then turned away with 422.
    status, _ = ask(server + "/watch/health", "POST", {"X-Token": token}, b"not json")
    check("the watch's token is accepted", status == 422, f"POST /watch/health with the token gave {status}")
    check("the token is not the development one", token != "dev-token", "set GYM_BUDDY_TOKEN on the server and here")

    status, body = ask(server + "/watch/health", headers=basic)
    if status == 200:
        report = json.loads(body)
        if check("the watch has reported in", report["seen"], "hold B on the watch to sync"):
            check("the watch's last report has no failures", report["status"] != "fail", report["summary"], report["summary"])
    return results


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    results = run(sys.argv[1].rstrip("/"), os.environ.get("GYM_BUDDY_TOKEN", "dev-token"),
                  os.environ.get("GYM_BUDDY_PASSWORD", ""))
    for passed, what, note in results:
        print(("  ok    " if passed else "  FAIL  ") + what + (f"  ({note})" if note else ""))
    failed = sum(not passed for passed, _, _ in results)
    print("All good." if not failed else f"{failed} to fix.")
    sys.exit(1 if failed else 0)
