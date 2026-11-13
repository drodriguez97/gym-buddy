"""watch/clock.py: unix time, or None when the watch doesn't know it."""
import contextlib
import importlib.util
import sys
import types
from pathlib import Path

REPO = Path(__file__).parents[2]
EPOCH_2000 = 946684800


@contextlib.contextmanager
def watch_clock(year, seconds, epoch_year=2000, ntp=None):
    """clock.py running against a fake time module.

    year, seconds: what the watch's clock says. epoch_year: the year its
    time.time() counts from. ntp: stands in for ntptime.settime (it gets the
    clock's state to change); None means the firmware has no ntptime.
    """
    state = {"year": year, "seconds": seconds}

    def gmtime(s=None):
        return ((epoch_year if s == 0 else state["year"]), 1, 1, 0, 0, 0, 0, 0)

    fakes = {"time": types.SimpleNamespace(gmtime=gmtime, time=lambda: state["seconds"]),
             "ntptime": types.SimpleNamespace(settime=lambda: ntp(state)) if ntp else None}
    real = {name: sys.modules.get(name) for name in fakes}
    sys.modules.update(fakes)               # None in sys.modules makes "import ntptime" fail, as on a firmware without it
    try:
        spec = importlib.util.spec_from_file_location("watch_clock", REPO / "watch" / "clock.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        for name, old in real.items():
            if old is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = old


def test_a_clock_that_was_never_set_reads_none():
    with watch_clock(year=2000, seconds=120) as clock:
        assert clock.unix_now() is None


def test_seconds_since_2000_become_unix_seconds():
    with watch_clock(year=2026, seconds=1794300000 - EPOCH_2000) as clock:
        assert clock.unix_now() == 1794300000


def test_a_firmware_that_already_counts_from_1970_is_left_alone():
    with watch_clock(year=2026, seconds=1794300000, epoch_year=1970) as clock:
        assert clock.unix_now() == 1794300000


def test_setting_from_the_internet_makes_the_clock_known():
    def ntp(state):
        state["year"], state["seconds"] = 2026, 1794300000 - EPOCH_2000
    with watch_clock(year=2000, seconds=5, ntp=ntp) as clock:
        assert clock.unix_now() is None
        assert clock.set_from_internet() is True
        assert clock.unix_now() == 1794300000


def test_no_answer_from_the_time_server_is_not_an_error():
    def ntp(state):
        raise OSError("timed out")
    with watch_clock(year=2000, seconds=5, ntp=ntp) as clock:
        assert clock.set_from_internet() is False


def test_a_firmware_without_ntptime_is_not_an_error():
    with watch_clock(year=2000, seconds=5) as clock:
        assert clock.set_from_internet() is False


def test_the_first_check_says_how_far_it_moved_the_clock():
    # The firmware set local time at power-on: 8 hours behind UTC.
    def ntp(state):
        state["seconds"] = 1794300000 - EPOCH_2000
    with watch_clock(year=2026, seconds=1794300000 - 8 * 3600 - EPOCH_2000, ntp=ntp) as clock:
        assert clock.checked is False and clock.step is None
        assert clock.set_from_internet() is True
        assert clock.checked is True and clock.step == 8 * 3600
        assert clock.set_from_internet() is True        # a later check finds nothing to move...
        assert clock.step == 8 * 3600                   # ...and must not forget what the first one found


def test_a_clock_with_no_time_before_the_check_has_no_step():
    def ntp(state):
        state["year"], state["seconds"] = 2026, 1794300000 - EPOCH_2000
    with watch_clock(year=2000, seconds=5, ntp=ntp) as clock:
        assert clock.set_from_internet() is True
        assert clock.checked is True and clock.step is None
