"""Is the watch working? The watch reports numbers; the server judges them.

The watch sends one report at the end of each sync. Each check below compares
one number with a limit and gives a verdict in plain words. Limits live here,
on the server, so they can change without touching the watch.
"""
import time

LIMITS = {
    "accel_low_g": 0.9,         # at rest the sensor must read 1 g, give or take
    "accel_high_g": 1.1,
    "gyro_still_dps": 30,       # turning faster than this means the watch was moving, not that it is broken
    "rssi_weak_dbm": -75,       # weaker than this and uploads start to fail
    "clock_off_s": 5,           # watch time against server time
    "battery_low_pct": 20,
    "storage_low_pct": 10,
    "seen_stale_s": 24 * 3600,  # no report for this long
}


def check(key, label, status, value, help_text=""):
    return {"key": key, "label": label, "status": status, "value": value, "help": help_text}


def number(report, key):
    value = report.get(key)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def judge(report, received_at, now=None):
    """The checks for one report. status is "ok", "warn" or "fail".

    report: what the watch sent. received_at: unix seconds when it arrived.
    A number the watch didn't send is a warning, never a pass.
    """
    now = time.time() if now is None else now
    checks = []

    age = now - received_at
    stale = age > LIMITS["seen_stale_s"]
    checks.append(check("seen", "Last report", "warn" if stale else "ok", ago(age),
                        "Hold B on the watch near your Wi-Fi to send a new one." if stale else ""))

    accel, gyro = number(report, "accel_g"), number(report, "gyro_dps")
    if accel is None or gyro is None:
        checks.append(check("sensor", "Motion sensor", "warn", "No reading", "The watch didn't send one."))
    elif gyro > LIMITS["gyro_still_dps"]:
        checks.append(check("sensor", "Motion sensor", "warn", "Moving", "Hold the watch still while it syncs, then sync again."))
    elif not LIMITS["accel_low_g"] <= accel <= LIMITS["accel_high_g"]:
        checks.append(check("sensor", "Motion sensor", "fail", "%.2f g at rest" % accel,
                            "It should read 1.00 g when still. Sync again with the watch held still."))
    else:
        checks.append(check("sensor", "Motion sensor", "ok", "%.2f g at rest" % accel))

    rssi = number(report, "rssi")
    if rssi is None:
        checks.append(check("wifi", "Wi-Fi", "warn", "No reading"))
    elif rssi < LIMITS["rssi_weak_dbm"]:
        checks.append(check("wifi", "Wi-Fi", "warn", "Weak (%d dBm)" % rssi, "Move closer to the router or hotspot."))
    else:
        checks.append(check("wifi", "Wi-Fi", "ok", "Strong (%d dBm)" % rssi))

    watch_time = number(report, "watch_time")
    if watch_time is None:
        checks.append(check("clock", "Clock", "warn", "Not set", "The watch couldn't get the time. Sets are ordered by when they arrive."))
    else:
        off = abs(watch_time - received_at)
        if off > LIMITS["clock_off_s"]:
            checks.append(check("clock", "Clock", "fail", "%s off" % span(off), "Sync again so the watch can set its clock."))
        else:
            checks.append(check("clock", "Clock", "ok", "%.0f s off" % off))

    percent, millivolts = number(report, "battery_pct"), number(report, "battery_mv")
    if percent is None:
        checks.append(check("battery", "Battery", "warn", "No reading"))
    else:
        value = "%d%%" % percent + (" (%.2f V)" % (millivolts / 1000) if millivolts else "")
        low = percent < LIMITS["battery_low_pct"]
        checks.append(check("battery", "Battery", "warn" if low else "ok", value, "Charge the watch." if low else ""))

    free = number(report, "free_pct")
    if free is None:
        checks.append(check("storage", "Storage", "warn", "No reading"))
    else:
        low = free < LIMITS["storage_low_pct"]
        checks.append(check("storage", "Storage", "warn" if low else "ok", "%d%% free" % free,
                            "Sync to clear the saved sets." if low else ""))

    waiting = number(report, "sets_waiting")
    if waiting is None:
        checks.append(check("waiting", "Sets waiting", "warn", "No reading"))
    else:
        checks.append(check("waiting", "Sets waiting", "warn" if waiting else "ok", "%d" % waiting,
                            "Some sets didn't upload. Hold B to try again." if waiting else ""))
    return checks


def summary(checks):
    """One line for the top of the page, and the worst status among the checks."""
    problems = [c for c in checks if c["status"] != "ok"]
    worst = "fail" if any(c["status"] == "fail" for c in checks) else "warn" if problems else "ok"
    if not problems:
        return worst, "Everything is working"
    if len(problems) == 1:
        return worst, "One thing to check"
    return worst, "%d things to check" % len(problems)


def span(seconds):
    seconds = int(seconds)
    if seconds < 90:
        return "%d s" % seconds
    if seconds < 90 * 60:
        return "%d min" % round(seconds / 60)
    if seconds < 36 * 3600:
        return "%d hours" % round(seconds / 3600)
    return "%d days" % round(seconds / 86400)


def ago(seconds):
    return "Just now" if seconds < 60 else span(seconds) + " ago"
