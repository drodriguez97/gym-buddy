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
# Button B (screen on, not recording) uploads the saved sets: see sync.py.
#
# Safety:
#   - Sleep needs button A's GPIO to wake the chip. The watch learns it from your first
#     press and saves it. Until then it only naps, it never sleeps.
#   - Sleeping drops the USB link to Thonny. Hold button B while it boots to stay awake.
import os
import M5
import time
import machine
import esp32
from recorder import Recorder

BLACK = 0x000000
WHITE = 0xFFFFFF
GREY  = 0x888888
RED   = 0xFF5A52
GREEN = 0x30C080
BATTERY_EVERY_MS = 30000    # refresh the battery line (screen on only)
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
    # Sleeping kills the USB serial link, so stay awake while charging.
    try:
        return M5.Power.isCharging()
    except Exception:
        return False


def screen_sleep():
    lcd.setBrightness(0)
    try:
        lcd.sleep()             # panel standby, not just backlight off
    except Exception:
        pass


def screen_wake():
    try:
        lcd.wakeup()
    except Exception:
        pass
    lcd.setBrightness(BRIGHTNESS)


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


def draw_battery():
    pct = battery_percent()
    if pct is None:
        return
    lcd.setTextColor(RED if pct < LOW_BATTERY else GREY, BLACK)
    lcd.drawString("Bat %2d%%" % pct, 10, 112)


def draw_status():
    free = percent_free()
    lcd.setTextColor(RED if free < LOW_SPACE else GREY, BLACK)
    text = "Free %2d%%" % free
    lcd.drawString(text, lcd.width() - 4 - lcd.textWidth(text), 112)


def show(lines, color=WHITE):
    lcd.fillScreen(BLACK)
    lcd.setTextColor(color, BLACK)
    for i, line in enumerate(lines):
        lcd.drawString(line, 6, 10 + i * 32)
    draw_battery()
    draw_status()


def show_saved(info):
    global flash_free
    flash_free -= info["count"] * 12 + 8192     # the readings, plus room for the .json and block rounding
    show(["Saved #" + info["set_id"][:5],
          "%d readings" % info["count"],
          "%.1f Hz late %d" % (info["rate_hz"], info["late"])], GREEN)


def run_sync():
    # Upload the saved sets and show the result. Takes seconds; never called during a set.
    show(["Syncing...", ""])
    try:
        import sync             # here, not at the top: recording must work without config.py
        sent, left, problem = sync.sync(lambda text: show(["Syncing...", text]))
    except Exception as e:
        show(["Sync failed", type(e).__name__], RED)
        radios_off()
        return
    radios_off()
    measure_flash()                         # sets were deleted; a sync takes seconds anyway
    if left == 0 and not problem:
        show(["Synced %d" % sent, "nothing left"], GREEN)
    else:
        show(["Synced %d" % sent, "%d left" % left, problem or ""], RED)


radios_off()
M5.update()
stay_awake = M5.BtnB.isPressed()            # held at boot: no sleep, Thonny stays connected
wake_pin = saved_wake_pin()
rec = Recorder()
measure_flash()
show(["Ready", "A: set  B: sync", "no sleep (B held)" if stay_awake else ""])
screen_wake()
screen_on = True
last_battery = time.ticks_ms()
last_activity = time.ticks_ms()
dark_ms = 0                                 # time spent DARK, counted nap by nap
wake_press = False                          # a press ended a nap; it only wakes the screen
quiet_until = None                          # ignoring the button until that wake press is released
b_ready = not stay_awake                    # B held at boot means "stay awake", not "sync"

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
        if not screen_on:
            screen_wake()                   # first press only wakes the screen
            screen_on = True
            last_battery = time.ticks_add(now, -BATTERY_EVERY_MS)   # redraw the status line now
        elif pressed and rec.recording:
            rec.halt()                      # stop taking readings first, then draw
            show(["Saving..."], GREEN)
            show_saved(rec.save())
        elif pressed:
            show(["REC", "A: stop"], RED)   # draw before the set starts
            rec.start()
        wake_press = False

    if not b_ready:
        b_ready = not M5.BtnB.isPressed()   # wait for the boot-time hold to end
    elif M5.BtnB.wasPressed() and screen_on and not rec.recording:
        run_sync()
        last_activity = time.ticks_ms()
        last_battery = last_activity
        continue

    info = rec.poll()
    if info:                                # the 2-minute limit stopped it
        show_saved(info)
        last_activity = time.ticks_ms()

    if rec.recording:                       # RECORDING
        time.sleep_ms(1)
        continue

    if screen_on:                           # AWAKE
        if time.ticks_diff(now, last_battery) >= BATTERY_EVERY_MS:
            lcd.fillRect(0, 108, lcd.width(), 27, BLACK)
            draw_battery()
            draw_status()
            last_battery = now
        if time.ticks_diff(now, last_activity) >= SCREEN_OFF_MS:
            screen_sleep()
            screen_on = False
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
