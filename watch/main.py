# main.py: the front button starts and stops a set.
import os
import M5
import time
from recorder import Recorder

BATTERY_EVERY_MS = 30000                    # refresh the battery line while idle
LOW_BATTERY = 20 # percent; shown in red below this
LOW_SPACE = 10


M5.begin()
lcd = M5.Lcd
lcd.setRotation(1)
lcd.setTextSize(2)


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
    lcd.setTextColor(0xFF5A52 if pct < LOW_BATTERY else 0x888888, 0x000000)
    lcd.drawString("Bat %2d%%" % pct, 10, 112)

def draw_status():
    free = percent_free()
    lcd.setTextColor(0xFF5A52 if free < LOW_SPACE else 0x888888, 0x000000)
    text = "Free %2d%%" % free
    lcd.drawString(text, lcd.width() - 4 - lcd.textWidth(text), 112)

def show(lines, color=0xFFFFFF):
    lcd.fillScreen(0x000000)
    lcd.setTextColor(color, 0x000000)
    for i, line in enumerate(lines):
        lcd.drawString(line, 6, 10 + i * 32)
    draw_battery()
    draw_status()


def show_saved(info):
    show(["Saved #" + info["set_id"][:5],
          "%d readings" % info["count"],
          "%.1f Hz late %d" % (info["rate_hz"], info["late"])], 0x30C080)


rec = Recorder()
show(["Ready", "A: start set"])
last_battery = time.ticks_ms()
last_status = time.tick_ms()

while True:
    M5.update()
    if M5.BtnA.wasPressed():
        if rec.recording:
            show_saved(rec.stop())
        else:
            show(["REC", "A: stop"], 0xFF5A52)   # draw before the set starts
            rec.start()
    info = rec.poll()
    if info:                                # the 2-minute limit stopped it
        show_saved(info)
    # Never draw during a set: it would delay readings.
    if not rec.recording and time.ticks_diff(time.ticks_ms(), last_battery) >= BATTERY_EVERY_MS:
        draw_battery()
        draw_status()
        last_battery = time.ticks_ms()