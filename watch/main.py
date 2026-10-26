# main.py: the front button starts and stops a set.
import M5
from recorder import Recorder

M5.begin()
lcd = M5.Lcd
lcd.setRotation(1)
lcd.setTextSize(2)


def show(lines, color=0xFFFFFF):
    lcd.fillScreen(0x000000)
    lcd.setTextColor(color, 0x000000)
    for i, line in enumerate(lines):
        lcd.drawString(line, 6, 10 + i * 32)


def show_saved(info):
    show(["Saved #" + info["set_id"][:5],
          "%d readings" % info["count"],
          "%.1f Hz late %d" % (info["rate_hz"], info["late"])], 0x30C080)


rec = Recorder()
show(["Ready", "A: start set"])

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