"""Power states of watch/main.py, run against fake hardware (fake_watch.py).

Run from the repo root:  python -m pytest watch/tests
These check the logic: when the watch sleeps and what a press does. They can't
check the hardware itself (real current, the backlight pin, the real button GPIO).
"""
from fake_watch import run

TAP = 0.15          # seconds a normal press lasts


def press(at, hold=TAP):
    return (at, at + hold)


def set_one_edit(name, value):
    # Flip one setting at the top of main.py, e.g. LIGHT_SLEEP = False.
    def edit(source):
        old = [line for line in source.splitlines() if line.startswith(name + " = ")]
        assert len(old) == 1, name
        return source.replace(old[0], "%s = %s" % (name, value))
    return edit


# ---- the button

def test_first_press_starts_a_set_and_second_stops_it():
    r = run(presses=[press(1), press(6)], run_for_s=10)
    assert len(r.times("recording start")) == 1
    assert len(r.times("recording stop")) == 1
    assert 1.0 <= r.times("recording start")[0] < 1.3
    assert "screen: REC" in r.between(1, 2)
    assert "screen: Saved #00030" in r.between(6, 7)


def test_first_press_learns_button_a_pin_and_arms_it():
    r = run(presses=[press(1)], run_for_s=3)
    assert r.has("pin saved 11")
    assert r.armed == [11]


def test_learns_g12_if_that_is_button_a():
    r = run(presses=[press(1)], run_for_s=3, a_gpio=12)
    assert r.has("pin saved 12")
    assert r.armed == [12]


def test_saved_pin_is_armed_at_boot_without_a_press():
    r = run(run_for_s=3, saved_pin=11)
    assert r.armed == [11]
    assert not r.has("pin saved 11")            # already known, not written again


# ---- awake -> dark -> off

def test_screen_goes_dark_20_s_after_the_last_press_then_light_sleeps():
    r = run(presses=[press(1), press(6)], run_for_s=40)
    off = r.times("backlight off")
    assert len(off) == 1 and 26.0 <= off[0] < 26.5
    assert r.times("light sleep")[0] >= off[0]
    assert not r.between(0, 26).count("light sleep")


def test_deep_sleep_10_minutes_after_going_dark():
    r = run(run_for_s=900, saved_pin=11)
    assert r.times("backlight off")[0] < 20.5
    deep = r.times("deep sleep")
    assert len(deep) == 1 and 620 <= deep[0] < 625


def test_nothing_is_drawn_while_dark():
    r = run(run_for_s=120, saved_pin=11)
    dark_from = r.times("backlight off")[0]
    assert set(r.between(dark_from + 0.1, 120)) == {"light sleep"}


# ---- waking up

def test_wake_press_only_wakes_the_screen():
    r = run(presses=[press(40)], run_for_s=45, saved_pin=11)
    assert r.has("woke by button")
    assert 40.0 <= r.times("backlight on")[-1] < 40.3
    assert not r.has("recording start")


def test_long_wake_press_does_not_start_a_set_when_the_debounce_catches_up():
    # Held 2 s: the debounced "pressed" arrives after the watch is already awake.
    r = run(presses=[press(40, hold=2.0)], run_for_s=50, saved_pin=11)
    assert r.has("woke by button")
    assert not r.has("recording start")


def test_press_after_waking_starts_a_set():
    r = run(presses=[press(40), press(42)], run_for_s=45, saved_pin=11)
    starts = r.times("recording start")
    assert len(starts) == 1 and 42.0 <= starts[0] < 42.3


def test_a_wake_press_restarts_the_10_minute_countdown():
    r = run(presses=[press(300)], run_for_s=1000, saved_pin=11)
    # Dark again 20 s after the wake press, deep sleep 10 minutes after that.
    assert 920 <= r.times("deep sleep")[0] < 925


# ---- recording comes first

def test_a_long_set_never_sleeps_or_draws():
    # 90 s set: longer than the screen timeout and the status refresh.
    r = run(presses=[press(1), press(91)], run_for_s=95, saved_pin=11)
    during = r.between(1.5, 91)
    assert during == [], during             # no status line, no backlight change, no sleep
    assert r.times("recording stop")[0] < 91.3


# ---- when it must stay awake

def test_no_sleep_until_the_pin_is_known():
    r = run(run_for_s=900)                  # never pressed, nothing saved
    assert r.has("backlight off")           # the screen still turns off
    assert not r.has("light sleep") and not r.has("deep sleep")


def test_no_sleep_if_button_a_is_on_neither_candidate_pin():
    r = run(presses=[press(1), press(6)], run_for_s=900, a_gpio=5)
    assert r.armed == []
    assert not r.has("light sleep") and not r.has("deep sleep")


def test_no_sleep_while_charging():
    r = run(run_for_s=900, saved_pin=11, charging=True)
    assert r.has("backlight off")
    assert not r.has("light sleep") and not r.has("deep sleep")


def test_no_sleep_in_dev_mode_and_the_screen_says_so():
    r = run(run_for_s=900, saved_pin=11, b_held=True)
    assert "screen: no sleep (B held)" in r.between(0, 1)
    assert r.has("backlight off")
    assert not r.has("light sleep") and not r.has("deep sleep")


def test_dev_mode_button_still_works_with_the_screen_off():
    r = run(presses=[press(40), press(42)], run_for_s=45, saved_pin=11, b_held=True)
    assert 40.0 <= r.times("backlight on")[-1] < 40.3   # first press wakes the screen
    assert len(r.times("recording start")) == 1         # second one starts a set


# ---- the two fallback switches

def test_light_sleep_switch_off_means_no_sleep_at_all():
    r = run(run_for_s=900, saved_pin=11, edit=set_one_edit("LIGHT_SLEEP", False))
    assert r.has("backlight off")
    assert not r.has("light sleep") and not r.has("deep sleep")


def test_deep_sleep_switch_off_keeps_light_sleeping():
    r = run(run_for_s=900, saved_pin=11, edit=set_one_edit("DEEP_SLEEP", False))
    assert r.has("light sleep")
    assert not r.has("deep sleep")
