# main.py: the front button starts and stops a set.
#
# Battery plan. The watch is in exactly one of these states:
#   RECORDING  CPU awake, screen on, 1 ms naps. Never sleeps or draws: readings come first.
#   AWAKE      screen on, 20 ms naps. Lasts SCREEN_OFF_MS after the last press.
#   DARK       screen and backlight off, CPU in light sleep. Button A wakes it at once.
#   OFF        deep sleep after DEEP_SLEEP_MS dark. Button A reboots into "Ready" (~3 s).
#              Sets are safe on flash.
# Wi-Fi and Bluetooth are off in every state; a sync turns Wi-Fi on and off again.
#
# Button B (screen on, not recording): a tap picks the next exercise, a long
# hold uploads the saved sets (sync.py). The exercise is saved with each set,
# because the server needs it to count correctly.
#
# The screen is the gym buddy's face (faces.py). While idle it blinks and
# glances around, and it looks sleepy before the screen turns off. Nothing is
# drawn during a set.
#
# Built for use mid-workout:
#   - After a set the screen dims but stays on for WORKOUT_MS, so ONE press of A
#     starts the next set. (This RESTING state costs more battery than DARK.)
#   - A beep confirms start (one) and stop (two), so you needn't look.
#   - Sets waiting to sync show as a count. They sync by themselves on charge,
#     and once when a workout ends (the rest window after the last set runs out).
#   - After a sync the rep counts come back from the server and are shown.
#
# Safety:
#   - Sleep needs button A's GPIO to wake the chip. The watch learns it from your first
#     press and saves it. Until then it only naps, it never sleeps.
#   - Sleeping drops the USB link to Thonny. Hold button B while it boots to stay awake.
#   - If anything unexpected goes wrong, the watch saves the set in progress, writes the
#     error to /flash/crash.txt, shows it, and restarts. It never sits frozen with the screen on.
import os
import sys
import M5
import time
import machine
import esp32
import faces
from recorder import Recorder

BLACK = 0x000000
GREY  = 0x888888
RED   = 0xFF5A52
BATTERY_EVERY_MS = 30000    # refresh the battery line (screen on only)
USB_EVERY_MS = 1000         # look whether the cable was plugged in or pulled, so the bolt follows within a second
SCREEN_OFF_MS = 20000       # AWAKE -> DARK; the backlight is the #1 drain
DEEP_SLEEP_MS = 10 * 60000  # DARK -> OFF
LIGHT_SLEEP_MS = 2000       # longest nap while DARK; button A ends it early
BRIGHTNESS = 64             # plenty indoors, roughly half the backlight current of 128
LOW_BATTERY = 20            # percent; shown in red below this
LOW_SPACE = 10
LIGHT_SLEEP = True          # set False if the screen lights up or the watch misbehaves while DARK
DEEP_SLEEP = True           # set False to never go OFF
BTN_A_CANDIDATES = (11, 12) # StickS3 buttons are on G11 and G12; the first press shows which is A
RELEASE_MS = 150            # after a wake press, ignore the button until it has been up this long
HOLD_MS = 800               # button B held this long syncs; a shorter tap picks the next exercise
SLEEPY_MS = 5000            # the face looks sleepy for this long before the screen turns off
BLINK_EVERY_MS = 4000       # the ready face blinks this often
BLINK_MS = 150              # and keeps its eyes shut this long
GLANCE_MS = 900             # every third blink is a glance to one side, this long
GLANCE_PX = 8
SET_ROOM = 160 * 1024       # bytes free needed to start a set: one full 2-minute set, with margin
SPLASH_MS = 3000            # "SAVED" and "SYNCED" show this long, then the ready face comes back
WORKOUT_MS = 5 * 60000      # after a set, stay on (dimmed) this long: one press starts the next set
DIM_BRIGHTNESS = 14         # the backlight while RESTING. 0 turns RESTING off.
SOUND = True                # beep on start and stop
SPEAKER_OFF_WHEN_DARK = True  # switch the speaker off with the screen. Left on, it pops at every nap and wastes battery.
VOLUME = 96
AUTO_SYNC = True            # sync by itself while charging, when sets are waiting
AUTO_SYNC_IDLE_MS = 10000   # ...after this long with no presses
AUTO_SYNC_EVERY_MS = 5 * 60000  # ...and not more often than this
SYNC_AFTER_WORKOUT = True   # when the rest window after the last set runs out, try one sync before the screen goes dark
USB_MV = 4000               # the USB power line reads above this (millivolts) when plugged in
# (name saved with the set and sent to the server, label on the screen), in the order B cycles them.
# Labels are at most 9 characters: that is what fits beside the face.
EXERCISES = (
    ("curl", "CURL"),
    ("shoulder_press", "SHOULDER"),
    ("chest_press", "CHEST"),
    ("row", "ROW"),
    ("pullup", "PULL-UP"),
    ("pushup", "PUSH-UP"),
)

M5.begin()
lcd = M5.Lcd
lcd.setRotation(1)
lcd.setTextSize(2)
machine.freq(80000000)
nvs = esp32.NVS("gymbuddy")


def radios_off():
    # Both cost tens of mA just sitting idle.
    try:
        import network
        network.WLAN(network.STA_IF).active(False)
        network.WLAN(network.AP_IF).active(False)
    except Exception:
        pass
    try:
        import bluetooth
        bluetooth.BLE().active(False)
    except Exception:
        pass


def on_usb():
    # True while USB power is connected. Sleeping kills the USB serial link, so the
    # watch stays awake then, and it is also when sets sync by themselves.
    # Measured on this watch: plugged in, isCharging() said False while the USB
    # line read 4.9 V, so the voltage is what is trusted.
    try:
        return M5.Power.getVBUSVoltage() > USB_MV
    except Exception:
        pass
    try:
        return M5.Power.isCharging()
    except Exception:
        return False


def speaker_off():
    # The amplifier stays live after a beep. Each light-sleep nap then stops and
    # restarts the audio lines feeding it, which it turns into a small pop every
    # couple of seconds (heard 2026-11-11). Nothing beeps while the screen is dark.
    if not SPEAKER_OFF_WHEN_DARK:
        return
    try:
        M5.Speaker.end()
    except Exception:
        pass                    # this firmware can't: it stays as it was


def speaker_on():
    if not SPEAKER_OFF_WHEN_DARK:
        return
    try:
        M5.Speaker.begin()
        M5.Speaker.setVolume(VOLUME)
    except Exception:
        pass


def screen_sleep():
    lcd.setBrightness(0)
    try:
        lcd.sleep()             # panel standby, not just backlight off
    except Exception:
        pass
    speaker_off()


def beep(times):
    # One short beep = started, two = stopped. Never called while readings are being taken.
    if not SOUND:
        return
    try:
        for i in range(times):
            M5.Speaker.tone(2400, 60)
            time.sleep_ms(140 if i + 1 < times else 60)
    except Exception:
        pass                    # no speaker on this firmware: stay silent


def screen_wake(draw=None):
    # Panel out of standby, then draw, then the backlight: a stale picture is never lit.
    try:
        lcd.wakeup()
    except Exception:
        pass
    speaker_on()                # before any press can ask for a beep
    global dimmed
    if draw:
        draw()
    lcd.setBrightness(BRIGHTNESS)
    dimmed = False


dimmed = False                              # RESTING: backlight low, screen still on


def undim():
    global dimmed
    if dimmed:
        lcd.setBrightness(BRIGHTNESS)
        dimmed = False


def arm_wake_pin(number):
    # Button A (pressed = low) wakes the chip from light and deep sleep.
    pin = machine.Pin(number, machine.Pin.IN, machine.Pin.PULL_UP)
    esp32.wake_on_ext0(pin=pin, level=0)
    return pin


def saved_wake_pin():
    # The pin learned on an earlier boot, armed. None if not learned yet.
    try:
        return arm_wake_pin(nvs.get_i32("btn_a_pin"))
    except Exception:
        return None


def learn_wake_pin():
    # Call while button A is held: the one candidate that reads low is button A.
    low = []
    for number in BTN_A_CANDIDATES:
        try:
            if machine.Pin(number, machine.Pin.IN, machine.Pin.PULL_UP).value() == 0:
                low.append(number)
        except Exception:
            pass
    if len(low) != 1:
        return None             # unclear; try again on the next press
    try:
        pin = arm_wake_pin(low[0])
        nvs.set_i32("btn_a_pin", low[0])
        nvs.commit()
        return pin
    except Exception:
        return None


def woke_by_pin():
    try:
        return machine.wake_reason() == getattr(machine, "EXT0_WAKE", 2)
    except Exception:
        return False


def battery_percent():
    # None if this firmware can't read the battery, so the display never crashes.
    try:
        pct = M5.Power.getBatteryLevel()
    except Exception:
        return None
    return pct if pct >= 0 else None


flash_total = 1                             # bytes; set by measure_flash()
flash_free = 0


def measure_flash():
    # Asking the flash how full it is takes about half a second (measured with
    # timing_check.py), so it is only done at boot and after a sync. In between,
    # percent_free() subtracts what each set used.
    global flash_total, flash_free
    s = os.statvfs("/flash")
    flash_total = s[0] * s[2]
    flash_free = s[0] * s[4]


def percent_free():
    return 100 * max(flash_free, 0) // flash_total


waiting = 0                                 # sets saved on the watch and not yet synced


def count_waiting():
    # Counted from the files at boot and after a sync; saves add one in between.
    try:
        return len([name for name in os.listdir("/flash/sets") if name.endswith(".json")])
    except OSError:
        return 0


def health_snapshot():
    # What the watch can measure about itself, for the server to judge: the
    # sensor at rest (0.3 s of readings), battery and storage. Never during a set.
    try:
        accel = gyro = 0
        for _ in range(30):
            ax, ay, az = M5.Imu.getAccel()
            gx, gy, gz = M5.Imu.getGyro()
            accel += (ax * ax + ay * ay + az * az) ** 0.5
            gyro += (gx * gx + gy * gy + gz * gz) ** 0.5
            time.sleep_ms(10)
        snapshot = {"accel_g": round(accel / 30, 3), "gyro_dps": round(gyro / 30, 1),
                    "battery_pct": battery_percent(), "free_pct": percent_free()}
    except Exception:
        return {}
    try:
        snapshot["battery_mv"] = M5.Power.getBatteryVoltage()
    except Exception:
        pass
    return snapshot


def reps_hint(reps, sent):
    # "REPS 8 8 6" for the sets just synced (the last six fit), or how many were sent.
    if not reps:
        return "%d SENT" % sent
    return "REPS " + " ".join(str(n) for n in reps[-6:])


usb_shown = False                           # is the bolt on screen?


def draw_status(mood=None):
    # Top right: a battery icon, red when low, with a green bolt beside it while
    # USB power is connected. Top left: how many sets are waiting
    # for a sync (not while recording: the recording dot lives there), and a
    # warning when flash is nearly full.
    global usb_shown
    lcd.fillRect(192, 6, 40, 13, BLACK)
    usb_shown = on_usb()
    if usb_shown:
        faces.draw_bolt(lcd, 193, 6)
    if mood != "rec":
        faces.draw_badge(lcd, waiting)
    pct = battery_percent()
    if pct is not None:
        color = RED if pct < LOW_BATTERY else GREY
        lcd.fillRect(204, 8, 22, 9, color)
        lcd.fillRect(205, 9, 20, 7, BLACK)
        lcd.fillRect(226, 11, 2, 3, color)
        lcd.fillRect(206, 10, 18 * min(pct, 100) // 100, 5, color)
    free = percent_free()
    if free < LOW_SPACE:
        lcd.setTextSize(1)
        lcd.setTextColor(RED, BLACK)
        lcd.drawString("FLASH %d%% FREE" % free, 56, 9)


face_mood = None                            # the mood on screen now
eyes_moved = False                          # mid-blink or mid-glance
blink_at = 0                                # when the next blink or glance starts, or the current one ends
blinks = 0                                  # counts them: every third is a glance
shown_at = 0                                # when the current face was drawn


def face(mood, title, hint=""):
    # Draw a whole screen: the face, one word, a small hint and the battery.
    global face_mood, eyes_moved, blink_at, shown_at
    faces.draw(lcd, mood, title, hint)
    draw_status(mood)
    face_mood = mood
    eyes_moved = False
    shown_at = time.ticks_ms()
    blink_at = time.ticks_add(shown_at, BLINK_EVERY_MS)


def animate(now):
    # The ready face blinks, and every third time glances to one side instead.
    # Only the eyes are redrawn.
    global eyes_moved, blink_at, blinks
    if eyes_moved:
        faces.draw_eyes(lcd, "ready")
        eyes_moved = False
        blink_at = time.ticks_add(now, BLINK_EVERY_MS)
        return
    blinks += 1
    eyes_moved = True
    if blinks % 3 == 0:
        faces.draw_eyes(lcd, "ready", dx=GLANCE_PX if blinks % 6 == 0 else -GLANCE_PX)
        blink_at = time.ticks_add(now, GLANCE_MS)
    else:
        faces.draw_eyes(lcd, "ready", openness=12)
        blink_at = time.ticks_add(now, BLINK_MS)


def show_saved(info):
    # Tells you what to do next. In dev mode it shows the rate and late count
    # instead: they prove the recording was good.
    global flash_free, waiting
    flash_free -= info["count"] * 12 + 8192     # the readings, plus room for the .json and block rounding
    waiting += 1
    if stay_awake:
        face("saved", "SAVED", "%.1fHZ LATE %d" % (info["rate_hz"], info["late"]))
    else:
        face("saved", "SAVED", "%d TO SYNC  HOLD B" % waiting)


def saved_exercise():
    # Index into EXERCISES, kept across restarts and deep sleep.
    try:
        return nvs.get_i32("exercise") % len(EXERCISES)
    except Exception:
        return 0


def show_ready():
    face("ready", EXERCISES[exercise][1], "DEV  NO SLEEP" if stay_awake else "A START  B NEXT")


def finish_set():
    # The set has been halted. Save it and say so; if the save fails, say that instead.
    face("saving", "SAVING")                # to the watch's own flash; nothing is sent until a sync
    try:
        info = rec.save()
    except OSError:
        measure_flash()
        face("problem", "OOPS", "NOT SAVED  FLASH FULL")
        return
    show_saved(info)


def crashed(e):
    # Something unexpected. Keep the set, keep the evidence, show it, restart clean.
    try:
        if rec.recording:
            rec.halt()
            rec.save()
    except Exception:
        pass
    try:
        with open("/flash/crash.txt", "w") as f:
            sys.print_exception(e, f)
    except Exception:
        pass
    try:
        face("problem", "OOPS", type(e).__name__.upper())
    except Exception:
        pass
    if stay_awake:
        raise e                             # dev mode: let Thonny show the traceback
    time.sleep_ms(3000)
    machine.reset()


def run_sync(quiet=False):
    # Upload the saved sets and show the result. Takes seconds; never called during a set.
    # quiet: nobody asked for this sync, so a failure is not an OOPS. The ready
    # face comes back with the waiting count, and hold B still works later.
    global waiting
    undim()
    face("sync", "SYNC")
    reps = []
    try:
        import sync             # here, not at the top: recording must work without config.py
        sent, left, problem = sync.sync(lambda text: face("sync", "SYNC", text.upper()), health_snapshot())
        reps = getattr(sync, "last_reps", [])
    except Exception as e:
        radios_off()
        waiting = count_waiting()
        if quiet:
            show_ready()
        else:
            face("problem", "OOPS", type(e).__name__.upper())
        return
    radios_off()
    measure_flash()                         # sets were deleted; a sync takes seconds anyway
    waiting = left
    if left == 0 and not problem:
        face("saved", "SYNCED", reps_hint(reps, sent) if sent else "NOTHING NEW")
    elif quiet:
        show_ready()                        # no Wi-Fi at the gym is normal, not a problem
    else:
        face("problem", "OOPS", "%s  %d LEFT" % ((problem or "").upper(), left))


radios_off()
M5.update()
stay_awake = M5.BtnB.isPressed()            # held at boot: no sleep, Thonny stays connected
wake_pin = saved_wake_pin()
rec = Recorder()
measure_flash()
waiting = count_waiting()
exercise = saved_exercise()
screen_wake(show_ready)
screen_on = True
last_battery = time.ticks_ms()
last_usb = time.ticks_ms()
last_activity = time.ticks_ms()
dark_ms = 0                                 # time spent DARK, counted nap by nap
wake_press = False                          # a press ended a nap; it only wakes the screen
quiet_until = None                          # ignoring the button until that wake press is released
b_ready = not stay_awake                    # B held at boot means "stay awake", not a tap or a sync
b_since = None                              # when the current B press began
b_synced = False                            # this press already started a sync
rest_until = None                           # RESTING until then: a set finished recently
next_auto_sync = time.ticks_ms()            # earliest time to look at auto-sync again
try:
    M5.Speaker.setVolume(VOLUME)
except Exception:
    pass

try:
    while True:
        M5.update()
        now = time.ticks_ms()
        pressed = M5.BtnA.wasPressed()

        if quiet_until is not None:
            # The press that woke us must not also start a set once the debounce catches up.
            pressed = False
            if wake_pin.value() == 0:
                quiet_until = time.ticks_add(now, RELEASE_MS)
            elif time.ticks_diff(now, quiet_until) >= 0:
                quiet_until = None

        if pressed and wake_pin is None:
            wake_pin = learn_wake_pin()         # first press ever: find button A's GPIO

        if pressed or wake_press:
            last_activity = now
            dark_ms = 0
            undim()
            if not screen_on:
                screen_wake(show_ready)         # first press only wakes the screen
                screen_on = True
                last_battery = now
            elif pressed and rec.recording:
                rec.halt()                      # stop taking readings first, then beep and draw
                beep(2)
                finish_set()
                rest_until = time.ticks_add(time.ticks_ms(), WORKOUT_MS)
            elif pressed and flash_free < SET_ROOM:
                face("problem", "OOPS", "FLASH FULL  HOLD B")   # a set that can't be saved isn't worth starting
            elif pressed:
                face("rec", "REC", EXERCISES[exercise][1] + "  A STOP")  # draw and beep before the set starts
                beep(1)
                rec.start(EXERCISES[exercise][0])
            wake_press = False

        b_down = M5.BtnB.isPressed()
        b_usable = screen_on and not rec.recording
        if not b_ready:
            b_ready = not b_down                # wait for the boot-time hold to end
        elif b_down:
            if b_since is None:
                b_since = now
                b_synced = False
            elif not b_synced and b_usable and time.ticks_diff(now, b_since) >= HOLD_MS:
                b_synced = True                 # long hold: sync once, however long it stays down
                run_sync()
                last_activity = time.ticks_ms()
                last_battery = last_activity
                continue
        elif b_since is not None:               # released
            if not b_synced and b_usable:       # a tap: next exercise
                exercise = (exercise + 1) % len(EXERCISES)
                nvs.set_i32("exercise", exercise)
                nvs.commit()
                undim()
                show_ready()
                last_activity = now
                last_battery = now
            b_since = None

        if rec.poll():                          # the 2-minute limit halted it
            beep(2)
            finish_set()
            last_activity = time.ticks_ms()
            rest_until = time.ticks_add(last_activity, WORKOUT_MS)

        if rec.recording:                       # RECORDING
            time.sleep_ms(1)
            continue

        idle = time.ticks_diff(now, last_activity)

        # Charging with sets waiting: sync without being asked. Looked at every 2 s at most.
        if (AUTO_SYNC and waiting and not stay_awake and idle >= AUTO_SYNC_IDLE_MS
                and time.ticks_diff(now, next_auto_sync) >= 0):
            next_auto_sync = time.ticks_add(now, 2000)
            if on_usb():
                next_auto_sync = time.ticks_add(now, AUTO_SYNC_EVERY_MS)
                if not screen_on:
                    screen_wake()
                    screen_on = True
                run_sync()
                last_activity = time.ticks_ms()
                last_battery = last_activity
                continue

        if screen_on:                           # AWAKE, or RESTING between sets
            # How much of the rest window is left. While it lasts, the screen dims instead of turning off.
            rest_left = time.ticks_diff(rest_until, now) if rest_until is not None and DIM_BRIGHTNESS else 0
            if face_mood != "sleepy" and idle >= SCREEN_OFF_MS - SLEEPY_MS and rest_left <= SLEEPY_MS:
                face("sleepy", "Z Z Z", "A WAKES")
            elif face_mood == "saved" and time.ticks_diff(now, shown_at) >= SPLASH_MS:
                show_ready()                # good news is a splash; problems stay until a press
            elif not dimmed and idle >= SCREEN_OFF_MS and rest_left > SLEEPY_MS:
                if face_mood != "ready":
                    show_ready()
                lcd.setBrightness(DIM_BRIGHTNESS)   # RESTING: one press of A starts the next set
                dimmed = True
            elif face_mood == "ready" and not dimmed and time.ticks_diff(now, blink_at) >= 0:
                animate(now)
            if time.ticks_diff(now, last_usb) >= USB_EVERY_MS:
                last_usb = now
                if on_usb() != usb_shown:       # the cable went in or came out: don't wait for the battery refresh
                    draw_status(face_mood)
                    last_battery = now
            if time.ticks_diff(now, last_battery) >= BATTERY_EVERY_MS:
                draw_status(face_mood)
                last_battery = now
            if idle >= SCREEN_OFF_MS and rest_left <= 0:
                if (SYNC_AFTER_WORKOUT and waiting and not stay_awake
                        and rest_until is not None and time.ticks_diff(now, rest_until) >= 0):
                    # The workout is over: nobody has pressed anything for the whole rest window.
                    # One try, whether or not it works; after that it is hold B, or the charger.
                    rest_until = None
                    run_sync(quiet=True)
                    last_activity = time.ticks_ms()
                    last_battery = last_activity
                    continue
                screen_sleep()
                screen_on = False
                dimmed = False
                dark_ms = 0
            time.sleep_ms(20)
            continue

        # DARK
        if wake_pin is None or stay_awake or not LIGHT_SLEEP or on_usb():
            time.sleep_ms(20)                   # no safe way to sleep: plain polling, screen still off
            continue
        if DEEP_SLEEP and dark_ms >= DEEP_SLEEP_MS:
            machine.deepsleep()                 # OFF; button A reboots us
        machine.lightsleep(LIGHT_SLEEP_MS)
        if wake_pin.value() == 0 or woke_by_pin():
            wake_press = True
            quiet_until = time.ticks_add(time.ticks_ms(), RELEASE_MS)
        else:
            dark_ms += LIGHT_SLEEP_MS
except Exception as e:
    crashed(e)
