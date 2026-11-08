# main.py: the front button starts and stops a set.
#
# Battery plan (idle is where the battery goes, not the sets):
#   screen on  -> normal polling, 20 ms naps
#   screen off -> light sleep: CPU and radios parked, wakes on the button
#   long idle  -> deep sleep (~microamps); the button reboots us, sets are safe on flash
import os
import M5
import time
import machine
from recorder import Recorder

BLACK = 0x000000
WHITE = 0xFFFFFF
GREY  = 0x888888
RED   = 0xFF5A52
GREEN = 0x30C080
BATTERY_EVERY_MS = 30000    # refresh the battery line while idle (screen on only)
SCREEN_OFF_MS = 20000       # screen off after 20 s idle (was 60 s; backlight is the #1 drain)
DEEP_SLEEP_MS = 10 * 60000  # deep sleep after 10 min idle; a press reboots into "Ready"
LIGHT_SLEEP_MS = 2000       # max nap while dark; the button wakes it early
BRIGHTNESS = 64             # was 128; plenty indoors, roughly halves backlight current
LOW_BATTERY = 20            # percent; shown in red below this
LOW_SPACE = 10
# GPIO of button A. Leave None until you've found it with the pin-finder snippet.
# None = no light/deep sleep (safe). Must be 0-21 on the ESP32-S3 to wake the chip.
BTN_A_PIN = None

M5.begin()
lcd = M5.Lcd
lcd.setRotation(1)
lcd.setTextSize(2)
machine.freq(80000000)


def radios_off():
    # Wi-Fi and BLE stay off until the uploader needs them; both cost tens of mA just sitting idle.
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
    # Sleeping kills the USB serial link, so stay awake while plugged in for development.
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


def setup_wake_pin():
    # Arm button A as a wake source for both light and deep sleep.
    # Returns the Pin, or None if sleep must stay off.
    if BTN_A_PIN is None or not (0 <= BTN_A_PIN <= 21):
        return None
    try:
        import esp32
        pin = machine.Pin(BTN_A_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
        esp32.wake_on_ext0(pin=pin, level=0)    # wake when pressed (pulled low)
        return pin
    except Exception:
        return None


def go_deep_sleep():
    screen_sleep()
    machine.deepsleep()         # only called when the wake pin is armed


def battery_percent():
    # None if this firmware can't read the battery, so the display never crashes.
    try:
        pct = M5.Power.getBatteryLevel()
    except Exception:
        return None
    return pct if pct >= 0 else None


def percent_free():
    s = os.statvfs("/flash")
    return 100 * s[4] // s[2]


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
    show(["Saved #" + info["set_id"][:5],
          "%d readings" % info["count"],
          "%.1f Hz late %d" % (info["rate_hz"], info["late"])], GREEN)


radios_off()
wake_pin = setup_wake_pin()
rec = Recorder()
show(["Ready", "A: start set"])
last_battery = time.ticks_ms()
last_activity = time.ticks_ms()
screen_wake()
screen_on = True
woke_by_button = False

while True:
    M5.update()
    now = time.ticks_ms()
    if M5.BtnA.wasPressed() or woke_by_button:
        woke_by_button = False
        last_activity = now
        if not screen_on:
            screen_wake()                   # first press only wakes the screen
            screen_on = True
        elif rec.recording:
            show_saved(rec.stop())
        else:
            show(["REC", "A: stop"], RED)   # draw before the set starts
            rec.start()
    info = rec.poll()
    if info:                                # the 2-minute limit stopped it
        show_saved(info)
        last_activity = time.ticks_ms()

    if rec.recording:
        time.sleep_ms(1)                    # never draw or sleep during a set: it would delay readings
        continue

    idle = time.ticks_diff(now, last_activity)
    if screen_on:
        # Only redraw while someone can see it.
        if time.ticks_diff(now, last_battery) >= BATTERY_EVERY_MS:
            lcd.fillRect(0, 108, lcd.width(), 27, BLACK)
            draw_battery()
            draw_status()
            last_battery = now
        if idle >= SCREEN_OFF_MS:
            screen_sleep()
            screen_on = False
        time.sleep_ms(20)
    elif wake_pin is None or on_usb():
        time.sleep_ms(20)                   # no safe wake source, or plugged in: plain polling
    elif idle >= DEEP_SLEEP_MS:
        go_deep_sleep()                     # a press reboots into "Ready"
    else:
        machine.lightsleep(LIGHT_SLEEP_MS)  # dark and idle; button A wakes it immediately
        if wake_pin.value() == 0:           # still held from the press that woke us
            woke_by_button = True           # count it even though wasPressed() missed the edge