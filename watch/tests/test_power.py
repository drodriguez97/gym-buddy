"""Power states of watch/main.py, run against fake hardware (fake_watch.py).

Run from the repo root:  python -m pytest watch/tests
These check the logic: when the watch sleeps and what a press does. They can't
check the hardware itself (real current, the backlight pin, the real button GPIO).
"""
from fake_watch import MAIN as MAIN_PATH
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
    assert "screen: SAVED" in r.between(6, 7)


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

def test_with_no_set_the_screen_goes_dark_after_20_s_then_light_sleeps():
    r = run(b_presses=[press(1), press(6)], run_for_s=40, saved_pin=11)     # two taps, no set
    off = r.times("backlight off")
    assert len(off) == 1 and 26.0 <= off[0] < 26.5
    assert r.times("light sleep")[0] >= off[0]
    assert not r.has("backlight dim")


def test_deep_sleep_10_minutes_after_going_dark():
    r = run(run_for_s=900, saved_pin=11)
    assert r.times("backlight off")[0] < 20.5
    deep = r.times("deep sleep")
    assert len(deep) == 1 and 620 <= deep[0] < 625


def test_nothing_is_drawn_while_dark():
    r = run(run_for_s=120, saved_pin=11)
    dark_from = r.times("backlight off")[0]
    assert set(r.between(dark_from + 0.1, 120)) == {"light sleep"}


# ---- button B: a tap picks the exercise, a long hold syncs

HOLD = 1.2          # seconds; longer than HOLD_MS in main.py


def screens(r, start_s, end_s):
    return [e[8:] for e in r.between(start_s, end_s) if e.startswith("screen: ")]


def test_the_ready_screen_shows_the_exercise_starting_on_curl():
    r = run(run_for_s=2, saved_pin=11)
    assert screens(r, 0, 1) == ["CURL", "A START  B NEXT"]


def test_a_tap_on_b_picks_the_next_exercise_and_saves_it():
    r = run(b_presses=[press(3)], run_for_s=6, saved_pin=11)
    assert "SHOULDER" in screens(r, 3, 4)
    assert r.has("exercise saved 1")
    assert not r.has("sync")


def test_b_cycles_through_all_six_and_wraps_around():
    r = run(b_presses=[press(2 + i) for i in range(6)], run_for_s=10, saved_pin=11)
    shown = [s for s in screens(r, 2, 9) if s != "A START  B NEXT"]
    assert shown == ["SHOULDER", "CHEST", "ROW", "PULL-UP", "PUSH-UP", "CURL"]


def test_the_picked_exercise_survives_a_restart():
    r = run(run_for_s=2, saved_pin=11, saved_exercise=4)
    assert screens(r, 0, 1)[0] == "PULL-UP"


def test_a_set_is_recorded_with_the_picked_exercise():
    r = run(b_presses=[press(2), press(3), press(4)], presses=[press(6), press(9)], run_for_s=11, saved_pin=11)
    assert r.has("set exercise row")
    assert screens(r, 6, 7) == ["REC", "ROW  A STOP"]


def test_the_exercise_stays_picked_for_the_next_set():
    r = run(b_presses=[press(2)], presses=[press(4), press(6), press(8), press(10)], run_for_s=12, saved_pin=11)
    assert r.times("set exercise shoulder_press") and len(r.times("set exercise shoulder_press")) == 2


def test_holding_b_syncs_and_shows_the_result():
    r = run(b_presses=[press(5, hold=HOLD)], run_for_s=15, saved_pin=11)
    assert len(r.times("sync")) == 1 and 5.8 <= r.times("sync")[0] < 6.3     # the hold, then 0.3 s reading the sensor
    assert screens(r, 5.8, 6.5) == ["SYNC", "SYNC", "SET 1 OF 2"]
    assert screens(r, 9.5, 11)[:2] == ["SYNCED", "2 SENT"]


def test_a_long_hold_syncs_once_and_does_not_also_change_the_exercise():
    r = run(b_presses=[press(5, hold=8)], run_for_s=20, saved_pin=11)
    assert len(r.times("sync")) == 1
    assert not r.has("exercise saved 1")


def test_sync_turns_the_radios_off_afterwards():
    r = run(b_presses=[press(5, hold=HOLD)], run_for_s=15, saved_pin=11)
    assert "radios off" in r.between(9.5, 11)


def test_sets_left_behind_are_shown_with_the_reason():
    r = run(b_presses=[press(5, hold=HOLD)], run_for_s=15, saved_pin=11, sync_result=(1, 3, "no server"))
    assert screens(r, 9.5, 11)[:2] == ["OOPS", "NO SERVER  3 LEFT"]


def test_a_crashing_sync_shows_an_error_and_recording_still_works():
    # e.g. config.py missing on the watch
    r = run(b_presses=[press(5, hold=HOLD)], presses=[press(8), press(10)], run_for_s=15, saved_pin=11,
            sync_result=ImportError("no module named 'config'"))
    assert screens(r, 5.8, 6.5)[-2:] == ["OOPS", "IMPORTERROR"]
    assert len(r.times("recording start")) == 1 and len(r.times("recording stop")) == 1


def test_button_b_does_nothing_during_a_set():
    r = run(presses=[press(1), press(10)], b_presses=[press(3), press(5, hold=HOLD)], run_for_s=12, saved_pin=11)
    assert not r.has("sync") and not r.has("exercise saved 1")
    assert r.between(1.5, 10) == []


def test_button_b_does_nothing_while_the_screen_is_off():
    r = run(b_presses=[press(40), press(42, hold=HOLD)], run_for_s=45, saved_pin=11, b_held=True, b_held_s=1)
    assert not r.has("sync") and not r.has("exercise saved 1")


def test_sync_keeps_the_screen_on_for_another_20_s():
    r = run(b_presses=[press(15, hold=HOLD)], run_for_s=60, saved_pin=11)
    off = r.times("backlight off")
    assert len(off) == 1 and 39.5 <= off[0] < 41.0     # 15 s + hold + sensor reading + 4 s sync + 20 s


def test_a_tap_keeps_the_screen_on_for_another_20_s():
    r = run(b_presses=[press(15)], run_for_s=60, saved_pin=11)
    off = r.times("backlight off")
    assert len(off) == 1 and 35.0 <= off[0] < 35.6


def test_holding_b_at_boot_is_dev_mode_not_a_tap_or_a_sync():
    r = run(run_for_s=10, saved_pin=11, b_held=True, b_held_s=2)
    assert "DEV  NO SLEEP" in screens(r, 0, 1)
    assert not r.has("sync") and not r.has("exercise saved 1")


def test_b_works_normally_after_the_boot_hold_is_released():
    r = run(b_presses=[press(4), press(6, hold=HOLD)], run_for_s=13, saved_pin=11, b_held=True, b_held_s=2)
    assert r.has("exercise saved 1") and len(r.times("sync")) == 1


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


# ---- nothing slow where a press is waiting

def test_flash_is_measured_at_boot_and_after_a_sync_only():
    # Measuring free space takes half a second. Never on a button press, a set
    # stopping, or the 30 s status refresh.
    r = run(presses=[press(2), press(8), press(12), press(16)], b_presses=[press(20), press(25, hold=HOLD)],
            run_for_s=60, saved_pin=11, b_held=True, b_held_s=0.2)
    measured = r.times("flash measured")
    assert len(measured) == 2
    assert measured[0] < 1 and 29.5 <= measured[1] < 31     # boot, and the end of the sync


def test_stopping_a_set_halts_readings_before_drawing():
    r = run(presses=[press(1), press(6)], run_for_s=10, saved_pin=11)
    # Order, not time: these can land on the same millisecond.
    order = [e for t, e in r.events]
    stop = order.index("recording stop")
    assert stop < order.index("screen: SAVING") < order.index("screen: SAVED")
    assert not [e for e in order[order.index("recording start") + 1:stop] if e != "recording stop"]


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
    assert "screen: DEV  NO SLEEP" in r.between(0, 1)
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


# ---- the face

def test_the_ready_face_blinks_and_every_third_time_glances():
    # Only the eyes are repainted: no text is redrawn, so nothing flickers.
    r = run(run_for_s=14, saved_pin=11)
    idle = r.events[[e for t, e in r.events].index("screen: A START  B NEXT") + 1:]
    assert [e for t, e in idle if e.startswith("screen")] == []
    paints = [t for t, e in idle if e == "paint"][1:]      # the first is the battery icon
    # Blinks 4 s apart (shut, then open 0.15 s later); the third is a glance held for 0.9 s.
    assert len(paints) == 6
    shut1, open1, shut2, open2, glance, back = paints
    assert 4.4 <= shut1 < 4.7 and 0.1 < open1 - shut1 < 0.25
    assert 3.9 < shut2 - open1 < 4.2 and 0.1 < open2 - shut2 < 0.25
    assert 3.9 < glance - open2 < 4.2 and 0.85 < back - glance < 1.0


def test_the_face_gets_sleepy_five_seconds_before_the_screen_turns_off():
    r = run(run_for_s=25, saved_pin=11)
    sleepy = [t for t, e in r.events if e == "screen: Z Z Z"]
    off = r.times("backlight off")[0]
    assert len(sleepy) == 1 and 20.0 <= off < 20.7
    assert 4.9 < off - sleepy[0] < 5.1


def test_no_blinking_once_sleepy_or_dark():
    r = run(run_for_s=120, saved_pin=11)
    sleepy = [t for t, e in r.events if e == "screen: Z Z Z"][0]
    assert "paint" not in r.between(sleepy + 0.5, 120)


def test_waking_up_shows_the_ready_face_before_the_backlight_comes_on():
    r = run(presses=[press(40)], run_for_s=45, saved_pin=11)
    order = [e for t, e in r.events if t >= 40]
    assert order.index("screen: CURL") < order.index("backlight on")


def test_the_recording_face_is_drawn_once_and_never_touched_during_the_set():
    r = run(presses=[press(1), press(30)], run_for_s=32, saved_pin=11)
    order = [e for t, e in r.events]
    assert order.index("screen: REC") < order.index("recording start")
    assert r.between(1.5, 30) == []


def test_saved_is_a_splash_then_the_ready_face_comes_back():
    r = run(presses=[press(1), press(6)], run_for_s=14, saved_pin=11)
    saved = [t for t, e in r.events if e == "screen: SAVED"][0]
    back = [t for t, e in r.events if e == "screen: CURL" and t > saved]
    assert len(back) == 1 and 2.9 < back[0] - saved < 3.3


def test_synced_is_a_splash_too():
    r = run(b_presses=[press(5, hold=HOLD)], run_for_s=15, saved_pin=11)
    synced = [t for t, e in r.events if e == "screen: SYNCED"][0]
    assert [t for t, e in r.events if e == "screen: CURL" and 2.9 < t - synced < 3.3]


def test_a_problem_stays_on_screen_until_a_press():
    r = run(b_presses=[press(5, hold=HOLD)], run_for_s=18, saved_pin=11, sync_result=(0, 3, "no server"))
    oops = [t for t, e in r.events if e == "screen: OOPS"][0]
    assert not [e for t, e in r.events if e == "screen: CURL" and oops < t < oops + 9]


def test_the_splash_does_not_delay_the_dimming():
    r = run(presses=[press(1), press(6)], run_for_s=40, saved_pin=11)
    assert 26.0 <= r.times("backlight dim")[0] < 27.0   # still 20 s after the stop press


def test_saving_is_not_shown_as_sync():
    r = run(presses=[press(1), press(6)], run_for_s=8, saved_pin=11)
    assert "screen: SAVING" in r.between(6, 7) and "screen: SYNC" not in r.between(6, 8)


# ---- when things go wrong: the set and the watch both survive

def test_a_set_is_not_started_when_flash_cannot_hold_it():
    r = run(presses=[press(2)], run_for_s=5, saved_pin=11, free_blocks=20)      # 80 KB free
    assert not r.has("recording start")
    assert screens(r, 2, 3)[:2] == ["OOPS", "FLASH FULL  HOLD B"]
    assert "FLASH 2% FREE" in screens(r, 0, 1)         # and the warning was on screen from boot


def test_a_failed_save_is_reported_and_the_watch_keeps_working():
    r = run(presses=[press(1), press(4), press(8), press(10)], run_for_s=12, saved_pin=11,
            save_error=OSError(28))
    assert screens(r, 4, 5)[-2:] == ["OOPS", "NOT SAVED  FLASH FULL"]
    assert not r.has("reset")
    assert len(r.times("recording start")) == 2         # the next press still starts a set


def test_the_two_minute_limit_shows_saving_then_saved():
    r = run(presses=[press(1)], run_for_s=10, saved_pin=11, autostop_s=5)
    order = [e for t, e in r.events if t >= 5]
    assert order.index("recording stop") < order.index("screen: SAVING") < order.index("save") < order.index("screen: SAVED")


def test_the_screen_dims_20_s_after_an_automatic_stop():
    r = run(presses=[press(1)], run_for_s=40, saved_pin=11, autostop_s=5)
    assert 25.0 <= r.times("backlight dim")[0] < 26.0


def test_an_unexpected_error_shows_oops_and_restarts():
    r = run(run_for_s=20, saved_pin=11, crash_at_s=3)
    assert "screen: RUNTIMEERROR" in r.between(3, 4)
    assert len(r.times("reset")) == 1 and 6.0 <= r.times("reset")[0] < 6.5     # 3 s to read it


def test_an_unexpected_error_during_a_set_saves_the_set_first():
    r = run(presses=[press(1)], run_for_s=20, saved_pin=11, crash_at_s=4)
    order = [e for t, e in r.events]
    assert order.index("recording stop") < order.index("save") < order.index("reset")


def test_in_dev_mode_an_error_is_raised_for_thonny_instead_of_restarting():
    import pytest
    with pytest.raises(RuntimeError):
        run(run_for_s=20, saved_pin=11, crash_at_s=3, b_held=True)


def test_syncing_with_nothing_saved_says_so():
    r = run(b_presses=[press(5, hold=HOLD)], run_for_s=15, saved_pin=11, sync_result=(0, 0, None))
    assert screens(r, 9.5, 11)[:2] == ["SYNCED", "NOTHING NEW"]


def test_nothing_slow_happens_between_pressing_stop_and_saving():
    # From the stop press to the save: one face, no flash measurement, no sync, no sleep.
    r = run(presses=[press(1), press(6)], run_for_s=8, saved_pin=11)
    order = [e for t, e in r.events]
    between = order[order.index("recording stop") + 1:order.index("save")]
    assert between == ["beep", "beep", "paint", "screen: SAVING", "paint"]


# ---- knowing when and how to sync

def test_no_badge_when_nothing_is_waiting():
    r = run(run_for_s=2, saved_pin=11)
    assert screens(r, 0, 1) == ["CURL", "A START  B NEXT"]


def test_sets_already_on_the_watch_show_as_a_count_at_boot():
    r = run(run_for_s=2, saved_pin=11, waiting=3)
    assert screens(r, 0, 1) == ["CURL", "A START  B NEXT", "3"]


def test_saved_says_how_many_are_waiting_and_how_to_sync():
    r = run(presses=[press(1), press(4), press(9), press(12)], run_for_s=14, saved_pin=11, waiting=1)
    saved = [s for s in screens(r, 4, 14) if "TO SYNC" in s]
    assert saved == ["2 TO SYNC  HOLD B", "3 TO SYNC  HOLD B"]


def test_the_count_stays_on_the_ready_face_after_the_splash():
    r = run(presses=[press(1), press(4)], run_for_s=10, saved_pin=11)
    assert screens(r, 6.5, 10) == ["CURL", "A START  B NEXT", "1"]


def test_the_count_is_not_drawn_over_the_recording_dot():
    r = run(presses=[press(2)], run_for_s=4, saved_pin=11, waiting=3)
    assert screens(r, 2, 4) == ["REC", "CURL  A STOP"]


def test_a_full_sync_clears_the_count():
    r = run(b_presses=[press(5, hold=HOLD)], run_for_s=15, saved_pin=11, waiting=2, sync_result=(2, 0, None))
    assert screens(r, 12.5, 15) == ["CURL", "A START  B NEXT"]


def test_a_partial_sync_shows_what_is_left():
    r = run(b_presses=[press(5, hold=HOLD)], presses=[press(12)], run_for_s=14, saved_pin=11,
            waiting=5, sync_result=(2, 3, "no server"))
    assert screens(r, 9.5, 11) == ["OOPS", "NO SERVER  3 LEFT", "3"]


def test_dev_mode_shows_the_recording_quality_instead():
    r = run(presses=[press(3), press(6)], run_for_s=8, saved_pin=11, b_held=True, b_held_s=1)
    assert "100.0HZ LATE 0" in screens(r, 6, 8)


# ---- resting between sets: one press starts the next one

def test_after_a_set_the_screen_dims_and_stays_on():
    r = run(presses=[press(1), press(6)], run_for_s=200, saved_pin=11)
    dim = r.times("backlight dim")
    assert len(dim) == 1 and 26.0 <= dim[0] < 27.0
    assert not r.has("backlight off") and not r.has("light sleep")


def test_one_press_starts_the_next_set_while_resting():
    r = run(presses=[press(1), press(6), press(120)], run_for_s=125, saved_pin=11)
    starts = r.times("recording start")
    assert len(starts) == 2 and 120.0 <= starts[1] < 120.4          # no wake press needed
    order = [e for t, e in r.events if t >= 120]
    assert order.index("backlight on") < order.index("recording start")


def test_the_resting_face_is_the_ready_face_and_it_holds_still():
    r = run(presses=[press(1), press(6)], run_for_s=120, saved_pin=11)
    dim = r.times("backlight dim")[0]
    assert set(r.between(dim + 0.1, 120)) <= {"paint", "screen: 1"}     # only the battery and count refresh
    assert len(r.between(dim + 0.1, 120)) <= 12        # a refresh every 30 s, three events each: no blinking


def test_a_tap_on_b_while_resting_brightens_and_picks_the_next_exercise():
    r = run(presses=[press(1), press(6)], b_presses=[press(60)], run_for_s=65, saved_pin=11)
    assert 60.0 <= r.times("backlight on")[-1] < 60.5
    assert "SHOULDER" in screens(r, 60, 61)


def test_five_minutes_after_the_last_set_it_gets_sleepy_then_goes_dark():
    # With the end-of-workout sync off, so this is only about the rest window.
    r = run(presses=[press(1), press(6)], run_for_s=330, saved_pin=11, edit=set_one_edit("SYNC_AFTER_WORKOUT", False))
    stop = r.times("recording stop")[0]
    off = r.times("backlight off")
    sleepy = [t for t, e in r.events if e == "screen: Z Z Z"]
    assert len(off) == 1 and 300 <= off[0] - stop < 302
    assert len(sleepy) == 1 and 4.5 < off[0] - sleepy[0] < 5.5
    assert r.times("light sleep")[0] >= off[0]


def test_resting_can_be_switched_off():
    r = run(presses=[press(1), press(6)], run_for_s=40, saved_pin=11, edit=set_one_edit("DIM_BRIGHTNESS", 0))
    assert not r.has("backlight dim")
    assert 26.0 <= r.times("backlight off")[0] < 27.0


# ---- sound

def test_one_beep_before_the_set_starts_and_two_after_it_stops():
    r = run(presses=[press(1), press(6)], run_for_s=8, saved_pin=11)
    order = [e for t, e in r.events if e in ("beep", "recording start", "recording stop", "save")]
    assert order == ["beep", "recording start", "recording stop", "beep", "beep", "save"]


def test_two_beeps_when_the_time_limit_ends_the_set():
    r = run(presses=[press(1)], run_for_s=8, saved_pin=11, autostop_s=5)
    assert len(r.times("beep")) == 3 and r.times("beep")[1] >= 5


def test_sound_can_be_switched_off():
    r = run(presses=[press(1), press(6)], run_for_s=8, saved_pin=11, edit=set_one_edit("SOUND", False))
    assert not r.has("beep")


# ---- rep counts and syncing on charge

def test_synced_shows_the_rep_counts_the_server_sent_back():
    r = run(b_presses=[press(5, hold=HOLD)], run_for_s=15, saved_pin=11, sync_reps=(8, 8, 6))
    assert screens(r, 9.5, 11)[:2] == ["SYNCED", "REPS 8 8 6"]


def test_only_the_last_six_counts_are_shown():
    r = run(b_presses=[press(5, hold=HOLD)], run_for_s=15, saved_pin=11, sync_reps=(1, 2, 3, 4, 5, 6, 7, 8))
    assert screens(r, 9.5, 11)[1] == "REPS 3 4 5 6 7 8"


def test_without_counts_from_the_server_it_says_how_many_were_sent():
    r = run(b_presses=[press(5, hold=HOLD)], run_for_s=15, saved_pin=11)
    assert screens(r, 9.5, 11)[:2] == ["SYNCED", "2 SENT"]


def test_on_charge_with_sets_waiting_it_syncs_by_itself():
    r = run(run_for_s=30, saved_pin=11, charging=True, waiting=2)
    sync = r.times("sync")
    assert len(sync) == 1 and 10.0 <= sync[0] < 12.5


def test_no_auto_sync_with_nothing_waiting_or_on_battery_or_in_dev_mode():
    assert not run(run_for_s=60, saved_pin=11, charging=True, waiting=0).has("sync")
    assert not run(run_for_s=60, saved_pin=11, charging=False, waiting=2).has("sync")
    assert not run(run_for_s=60, saved_pin=11, charging=True, waiting=2, b_held=True).has("sync")


def test_a_failed_auto_sync_waits_five_minutes_before_trying_again():
    r = run(run_for_s=640, saved_pin=11, charging=True, waiting=2, sync_result=(0, 2, "no server"))
    sync = r.times("sync")
    assert len(sync) == 3
    assert 299 < sync[1] - sync[0] < 310 and 299 < sync[2] - sync[1] < 310


def test_auto_sync_wakes_a_dark_screen_to_show_what_it_is_doing():
    r = run(presses=[press(1), press(4)], run_for_s=200, saved_pin=11, charging=False,
            edit=set_one_edit("AUTO_SYNC_IDLE_MS", 1000))
    assert not r.has("sync")                # on battery, mid-workout: never


def test_auto_sync_never_interrupts_a_set():
    r = run(presses=[press(1), press(40)], run_for_s=42, saved_pin=11, charging=True, waiting=2)
    assert not [t for t in r.times("sync") if 1.3 < t < 40]


def test_auto_sync_can_be_switched_off():
    r = run(run_for_s=60, saved_pin=11, charging=True, waiting=2, edit=set_one_edit("AUTO_SYNC", False))
    assert not r.has("sync")


# ---- knowing it is plugged in

def test_usb_power_is_detected_by_its_voltage_even_when_the_charging_flag_says_no():
    # What the real watch reported while plugged in: isCharging False, USB line 4938 mV.
    r = run(run_for_s=900, saved_pin=11, charging=True)
    assert not r.has("light sleep") and not r.has("deep sleep")


def test_a_firmware_that_cannot_read_the_usb_voltage_falls_back_to_the_charging_flag():
    r = run(run_for_s=900, saved_pin=11, charging=True, has_vbus=False)
    assert not r.has("light sleep") and not r.has("deep sleep")


def test_unplugged_it_sleeps_whichever_way_usb_is_detected():
    assert run(run_for_s=60, saved_pin=11, has_vbus=True).has("light sleep")
    assert run(run_for_s=60, saved_pin=11, has_vbus=False).has("light sleep")


# ---- the health snapshot handed to a sync

def test_a_sync_is_given_the_watch_measurements():
    r = run(b_presses=[press(5, hold=HOLD)], run_for_s=15, saved_pin=11)
    assert r.health == {"accel_g": 1.0, "gyro_dps": 5.0, "battery_pct": 80, "free_pct": 90, "battery_mv": 3860}


def test_the_sync_face_is_up_before_the_sensor_is_read():
    r = run(b_presses=[press(5, hold=HOLD)], run_for_s=15, saved_pin=11)
    order = [e for t, e in r.events if t >= 5]
    assert order.index("screen: SYNC") < order.index("sync")


def test_a_watch_that_cannot_read_its_sensor_still_syncs():
    def no_imu(source):
        return source.replace("ax, ay, az = M5.Imu.getAccel()\n            gx, gy, gz", "ax, ay, az = M5.Imu.missing()\n            gx, gy, gz")
    r = run(b_presses=[press(5, hold=HOLD)], run_for_s=15, saved_pin=11, edit=no_imu)
    assert len(r.times("sync")) == 1 and r.health == {}


def test_an_auto_sync_on_charge_also_reports_health():
    r = run(run_for_s=30, saved_pin=11, charging=True, waiting=2)
    assert r.has("sync") and r.health["accel_g"] == 1.0


# ---- syncing by itself when the workout ends

def test_when_the_rest_window_runs_out_it_syncs_once_by_itself():
    # A set from 1 s to 6 s, then nothing. The rest window is 5 minutes.
    r = run(presses=[press(1), press(6)], run_for_s=400, saved_pin=11)
    sync = r.times("sync")
    assert len(sync) == 1 and 306 <= sync[0] < 312
    assert "SYNCED" in screens(r, sync[0], sync[0] + 6)


def test_after_that_sync_the_screen_goes_dark_as_usual():
    r = run(presses=[press(1), press(6)], run_for_s=400, saved_pin=11)
    off = [t for t in r.times("backlight off") if t > r.times("sync")[0]]
    assert off and 19 <= off[0] - r.times("sync")[0] < 27       # the sync's 4 s, then the usual 20 s


def test_no_wifi_at_the_gym_is_not_an_oops_and_it_does_not_keep_trying():
    r = run(presses=[press(1), press(6)], run_for_s=1000, saved_pin=11, sync_result=(0, 1, "no wifi"))
    assert len(r.times("sync")) == 1
    assert "OOPS" not in screens(r, 300, 1000)


def test_a_sync_that_crashes_by_itself_is_quiet_too():
    r = run(presses=[press(1), press(6)], run_for_s=400, saved_pin=11, sync_result=OSError("no wifi"))
    assert len(r.times("sync")) == 1 and "OOPS" not in screens(r, 300, 400)


def test_holding_b_still_shows_an_oops_when_it_fails():
    r = run(b_presses=[press(5, hold=HOLD)], run_for_s=15, saved_pin=11, sync_result=(0, 2, "no wifi"))
    assert "OOPS" in screens(r, 5, 15)


def test_another_set_restarts_the_wait():
    # Sets end at 6 s and at 206 s. The sync waits for 5 quiet minutes after the last one.
    r = run(presses=[press(1), press(6), press(200), press(206)], run_for_s=600, saved_pin=11)
    sync = r.times("sync")
    assert len(sync) == 1 and 506 <= sync[0] < 512


def test_it_never_syncs_by_itself_during_a_set():
    r = run(presses=[press(1), press(6), press(300)], run_for_s=400, saved_pin=11)
    assert not r.has("sync")                # a set is being recorded when the window would have run out


def test_nothing_waiting_means_no_sync_when_the_workout_ends():
    # The wearer already held B after the set.
    r = run(presses=[press(1), press(6)], b_presses=[press(10, hold=HOLD)], run_for_s=400, saved_pin=11)
    assert len(r.times("sync")) == 1 and r.times("sync")[0] < 13


def test_no_sync_by_itself_without_a_set_or_in_dev_mode_or_switched_off():
    assert not run(run_for_s=400, saved_pin=11, waiting=2).has("sync")
    assert not run(presses=[press(1), press(6)], run_for_s=400, saved_pin=11, b_held=True).has("sync")
    assert not run(presses=[press(1), press(6)], run_for_s=400, saved_pin=11,
                   edit=set_one_edit("SYNC_AFTER_WORKOUT", False)).has("sync")


# ---- the speaker is off while the screen is dark (it popped at every nap)

def test_the_speaker_goes_off_with_the_screen_before_the_first_nap():
    r = run(run_for_s=60, saved_pin=11)
    off = r.times("speaker off")
    assert len(off) == 1 and off[0] == r.times("backlight off")[0]
    assert off[0] <= r.times("light sleep")[0]


def test_the_speaker_is_back_on_before_the_beep_that_starts_the_next_set():
    # Dark by 21 s. A press at 30 s wakes the screen; a press at 33 s starts a set.
    r = run(presses=[press(30), press(33)], run_for_s=36, saved_pin=11)
    on = [t for t in r.times("speaker on") if t > 25]
    assert len(on) == 1 and 30 <= on[0] < 30.5
    assert on[0] < r.times("beep")[0]


def test_the_speaker_is_never_off_during_a_set_or_a_beep():
    r = run(presses=[press(1), press(6)], run_for_s=400, saved_pin=11)
    off = r.times("speaker off")
    assert off and all(t > max(r.times("beep")) for t in off)


def test_the_speaker_is_off_before_deep_sleep():
    r = run(run_for_s=900, saved_pin=11)
    assert r.times("speaker off")[0] < r.times("deep sleep")[0]
    assert len(r.times("speaker off")) == 1         # once, not at every nap


def test_the_speaker_switch_can_be_turned_off():
    r = run(presses=[press(1), press(6)], run_for_s=400, saved_pin=11,
            edit=set_one_edit("SPEAKER_OFF_WHEN_DARK", False))
    assert not r.has("speaker off") and not r.has("speaker on")
    assert len(r.times("beep")) == 3                # one to start, two to stop: unchanged


def test_a_firmware_without_speaker_control_still_sleeps_and_beeps():
    def no_control(source):
        return source.replace("M5.Speaker.end()", "M5.Speaker.no_such()").replace(
            "M5.Speaker.begin()", "M5.Speaker.no_such()")
    r = run(presses=[press(1), press(6)], run_for_s=400, saved_pin=11, edit=no_control)
    assert len(r.times("beep")) == 3 and r.has("light sleep")
