# clock.py: what time is it, and does the watch actually know?
#
# The watch has no battery-backed clock. Its time is only right after it has
# asked the internet (during a sync), and it is lost when the power goes.
# So every time is "unix seconds, or None if the clock was never set".
import time

EPOCH_2000 = 946684800          # MicroPython on the ESP32 counts seconds from 2000, not 1970


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
    try:
        import ntptime
        ntptime.timeout = 3
        ntptime.settime()
        return unix_now() is not None
    except Exception:
        return False
