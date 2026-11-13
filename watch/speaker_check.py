# speaker_check.py: which way of switching the speaker off stops the pop while napping?
#
# main.py calls M5.Speaker.end() when the screen goes dark, and the pop was
# still heard (2026-11-12). This tries each way in turn so your ears can say
# which one works. Nothing here is saved; it changes no settings.
#
# Run from Thonny with F5 (Ctrl+C first so main.py stops), then UNPLUG the USB
# cable or hold the watch to your ear: the test is by ear, the screen only says
# which step is running. Each step shows its number for 3 seconds, then naps
# six times (about 12 s, screen may go dark). Note the numbers where you hear
# a pop. The last screen stays up.
#
#   1  speaker left as it is after a beep        (expected: pops; this is the fault)
#   2  after M5.Speaker.stop()
#   3  after M5.Speaker.setVolume(0)
#   4  after M5.Speaker.end()                     (what main.py does today)
#   5  after end(), waiting WITHOUT napping       (expected: silent; if this pops, it isn't the naps)
import time
import machine
import M5

NAPS = 6
NAP_MS = 2000

M5.begin()
lcd = M5.Lcd
lcd.setRotation(1)
lcd.setBrightness(64)
speaker = M5.Speaker


def show(big, small=""):
    lcd.fillScreen(0x000000)
    lcd.setTextColor(0xFFFFFF, 0x000000)
    lcd.setTextSize(5)
    lcd.drawString(big, 20, 30)
    lcd.setTextSize(2)
    lcd.drawString(small, 20, 100)


def attempt(name):
    # Call speaker.<name>() if this firmware has it. Returns "ok", "missing" or "error".
    method = getattr(speaker, name, None)
    if method is None:
        return "missing"
    try:
        method(0) if name == "setVolume" else method()
        return "ok"
    except Exception:
        return "error"


def beep():
    try:
        speaker.begin()
        speaker.setVolume(96)
        speaker.tone(2400, 60)
        time.sleep_ms(200)
    except Exception:
        pass


def naps(sleeping=True):
    for _ in range(NAPS):
        if sleeping:
            machine.lightsleep(NAP_MS)
        else:
            time.sleep_ms(NAP_MS)


results = []
for number, call in ((1, None), (2, "stop"), (3, "setVolume"), (4, "end"), (5, "end")):
    beep()                                  # every step starts from the same state: just beeped
    outcome = attempt(call) if call else "-"
    results.append("%d %s %s" % (number, call or "as is", outcome))
    show(str(number), "%s: %s" % (call or "as is", outcome))
    time.sleep_ms(3000)
    naps(sleeping=number != 5)

lcd.fillScreen(0x000000)
lcd.setTextSize(2)
lcd.setTextColor(0xFFFFFF, 0x000000)
lcd.drawString("Which steps popped?", 4, 4)
for row, line in enumerate(results):
    lcd.drawString(line, 4, 28 + 20 * row)
print("\n".join(results))
