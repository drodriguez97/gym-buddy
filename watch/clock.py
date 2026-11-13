# clock.py: what time is it, and does the watch actually know?
#
# The watch has no battery-backed clock. Its time is only right after it has
# asked the internet (during a sync), and it is lost when the power goes.
# So every time is "unix seconds, or None if the clock was never set".
import time

EPOCH_2000 = 946684800          # MicroPython on the ESP32 counts seconds from 2000, not 1970

# The clock can hold a time we never checked: the firmware may set it at
# power-on, and it may set LOCAL time (seen 2026-11-12: a set stamped exactly
# 8 hours early, the offset of US Pacific time). So until set_from_internet
# has run since power-on, a time is "unchecked", and when it does run it
# records how far it moved the clock. sync.py uses that to put right the sets
# stamped before the check.
checked = False                 # has set_from_internet worked since power-on?
step = None                     # seconds the first check moved the clock; None if the clock had no time before


def unix_now():
    # Unix seconds (UTC), or None if the clock has not been set since power-on.
    try:
        if time.gmtime()[0] < 2026:
            return None
        return int(time.time()) + (EPOCH_2000 if time.gmtime(0)[0] == 2000 else 0)
    except Exception:
        return None


def set_from_internet():
    # Ask an internet time server (NTP). Needs Wi-Fi. True if the clock is now set.
    global checked, step
    try:
        import ntptime
        before = unix_now()
        ntptime.timeout = 3
        ntptime.settime()
        after = unix_now()
        if after is None:
            return False
        if not checked:             # only the first check says how wrong the power-on clock was
            step = after - before if before is not None else None
            checked = True
        return True
    except Exception:
        return False
