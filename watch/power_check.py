# power_check.py: how fast does each state drain the battery? (docs/battery-plan.md, step 0)
#
# Holds the watch in ONE state for a fixed time and compares the battery
# voltage before and after. Changes nothing in main.py and nothing permanent
# except one line added to /flash/power_log.csv per test.
#
# How to run one test:
#   1. Charge the watch fully (every test should start from the same place).
#   2. Thonny: Ctrl+C to stop main.py, open this file, F5.
#   3. On the watch: B picks the test, A chooses it.
#   4. Unplug USB, then press A. The watch refuses to start while still plugged in.
#   5. Leave it alone. Pressing A ends the test early (the result is still logged).
#   6. The result stays on screen for two minutes, then the watch restarts as normal.
#   7. Later, in Thonny: open /flash/power_log.csv to see every result.
#
# The tests:
#   AWAKE      screen on at normal brightness, CPU napping 20 ms   60 min
#   RESTING    the same with the dim backlight (between sets)      60 min
#   RECORDING  screen on, reading the sensor 100 times a second    30 min
#   DARK       screen off, CPU in light sleep                      60 min
#   NAP LOOK   no measuring: does the dim backlight survive light sleep? Watch the screen.
#   PROBE      stay ON USB: prints what this firmware can do. Read it in Thonny.
#
# OFF (deep sleep) is not here: after deep sleep the watch restarts into
# main.py, not this file. Measure it with the dashboard instead: sync, note
# the battery voltage on the Watch tab, leave the watch alone overnight, sync
# again in the morning.
#
# The current it prints is rough. Voltage is a blunt measure of charge: trust
# "about 40 mA" against "about 5 mA", not 40 against 37.
import struct
import sys
import time
import machine
import esp32
import M5

BRIGHTNESS = 64             # the same numbers as main.py
DIM_BRIGHTNESS = 14
LIGHT_SLEEP_MS = 2000
USB_MV = 4000
BATTERY_MAH = 250
FULL_MV, EMPTY_MV = 4100, 3300      # the firmware's own straight line from voltage to percent
SETTLE_MS = 60000           # screen off and idle this long before each voltage reading
SAMPLES = 20                # then this many readings, half a second apart, averaged
RESULT_MS = 120000
LOG = "/flash/power_log.csv"
TESTS = (                   # name, label on screen, minutes
    ("awake", "AWAKE", 60),
    ("resting", "RESTING", 60),
    ("recording", "RECORDING", 30),
    ("dark", "DARK", 60),
    ("naps", "NAP LOOK", 0),
    ("probe", "PROBE", 0),
)

lcd = None                  # set by setup()


def setup():
    global lcd
    M5.begin()
    lcd = M5.Lcd
    lcd.setRotation(1)
    machine.freq(80000000)
    try:                                    # the same as main.py: radios off
        import network
        network.WLAN(network.STA_IF).active(False)
        network.WLAN(network.AP_IF).active(False)
    except Exception:
        pass


def show(*lines, brightness=BRIGHTNESS):
    lcd.fillScreen(0)
    lcd.setTextSize(2)
    lcd.setTextColor(0xFFFFFF, 0)
    for i, line in enumerate(lines):
        lcd.drawString(line, 6, 8 + i * 24)
    lcd.setBrightness(brightness)


def on_usb():
    # The USB line's voltage is what main.py trusts; isCharging() was wrong on this watch.
    try:
        return M5.Power.getVBUSVoltage() > USB_MV
    except Exception:
        pass
    try:
        return M5.Power.isCharging()
    except Exception:
        return False


def wait_for_a():
    while True:
        M5.update()
        if M5.BtnA.wasPressed():
            return
        time.sleep_ms(20)


def pick():
    # B: next test. A: choose it. Returns (name, label, minutes).
    i = 0
    while True:
        name, label, minutes = TESTS[i]
        show("POWER CHECK", label, "%d MIN" % minutes if minutes else "", "B NEXT  A CHOOSE")
        while True:
            M5.update()
            if M5.BtnA.wasPressed():
                return TESTS[i]
            if M5.BtnB.wasPressed():
                i = (i + 1) % len(TESTS)
                break
            time.sleep_ms(20)


def battery_mv():
    # The same conditions every time, so two readings can be compared: screen
    # off, CPU idle, a minute for the voltage to settle, then an average.
    lcd.setBrightness(0)
    time.sleep_ms(SETTLE_MS)
    total = 0
    for _ in range(SAMPLES):
        total += M5.Power.getBatteryVoltage()
        time.sleep_ms(500)
    return total // SAMPLES


def a_pressed():
    M5.update()
    return M5.BtnA.wasPressed()


def hold_awake(label, brightness, limit_ms):
    # AWAKE and RESTING: what main.py's loop does with the screen on and nothing happening.
    show("TEST: " + label, "A ENDS IT", brightness=brightness)
    start = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), start) < limit_ms:
        if a_pressed():
            break
        time.sleep_ms(20)


def hold_recording(label, limit_ms):
    # What a set costs: a reading every 10 ms into memory, 1 ms naps. Nothing is saved.
    show("TEST: " + label, "A ENDS IT")
    buf = bytearray(12 * 100)               # one second's worth, written over and over
    start = time.ticks_ms()
    due = start
    count = 0
    while time.ticks_diff(time.ticks_ms(), start) < limit_ms:
        if a_pressed():
            break
        if time.ticks_diff(time.ticks_ms(), due) >= 0:
            due = time.ticks_add(due, 10)
            ax, ay, az = M5.Imu.getAccel()
            gx, gy, gz = M5.Imu.getGyro()
            struct.pack_into("<6h", buf, (count % 100) * 12,
                             int(ax * 1000), int(ay * 1000), int(az * 1000),
                             int(gx * 10), int(gy * 10), int(gz * 10))
            count += 1
        time.sleep_ms(1)


def wake_pin():
    # Button A's GPIO, learned by main.py on its first press. None if it never was.
    try:
        pin = machine.Pin(esp32.NVS("gymbuddy").get_i32("btn_a_pin"), machine.Pin.IN, machine.Pin.PULL_UP)
        esp32.wake_on_ext0(pin=pin, level=0)
        return pin
    except Exception:
        return None


def hold_dark(pin, limit_ms):
    # DARK: panel in standby, CPU in light sleep, exactly as main.py does it.
    lcd.setBrightness(0)
    try:
        lcd.sleep()
    except Exception:
        pass
    slept = 0                               # counted nap by nap, as main.py does
    while slept < limit_ms:
        machine.lightsleep(LIGHT_SLEEP_MS)
        if pin.value() == 0:                # button A: end early
            break
        slept += LIGHT_SLEEP_MS
    try:
        lcd.wakeup()
    except Exception:
        pass
    return slept


def estimate_ma(start_mv, end_mv, ms):
    # Percent of the battery used (the firmware's straight line) turned into an average current.
    if ms <= 0:
        return 0
    used_mah = (start_mv - end_mv) * BATTERY_MAH / (FULL_MV - EMPTY_MV)
    return used_mah / (ms / 3600000)


def measure(name, label, minutes, pin=None):
    # One whole test. Returns (minutes it really ran, start mV, end mV, mA).
    show("TEST: " + label, "READING BATTERY", "70 S, SCREEN OFF")
    time.sleep_ms(2000)
    start_mv = battery_mv()
    began = time.ticks_ms()
    limit_ms = minutes * 60000
    if name == "awake":
        hold_awake(label, BRIGHTNESS, limit_ms)
    elif name == "resting":
        hold_awake(label, DIM_BRIGHTNESS, limit_ms)
    elif name == "recording":
        hold_recording(label, limit_ms)
    elif name != "dark":
        raise ValueError(name)
    ran_ms = time.ticks_diff(time.ticks_ms(), began)
    if name == "dark":
        ran_ms = hold_dark(pin, limit_ms)
    end_mv = battery_mv()
    ma = estimate_ma(start_mv, end_mv, ran_ms)
    ran_min = ran_ms / 60000
    try:
        with open(LOG, "a") as f:
            f.write("%s,%.1f,%d,%d,%.1f\n" % (name, ran_min, start_mv, end_mv, ma))
    except OSError:
        pass                                # a full flash must not lose the result on screen
    return ran_min, start_mv, end_mv, ma


def nap_look():
    # Step 2 of the plan depends on this: with the backlight dim, does the
    # screen stay dim through light sleep, go dark, or jump to full brightness?
    for i in range(3):
        show("NAP %d OF 3" % (i + 1), "DIM NOW. WATCH:", "STAYS DIM? DARK?", "OR BRIGHT?", brightness=DIM_BRIGHTNESS)
        time.sleep_ms(4000)
        machine.lightsleep(5000)
        show("AWAKE AGAIN", brightness=BRIGHTNESS)
        time.sleep_ms(2000)
    show("DURING THE NAPS", "IT STAYED DIM,", "WENT DARK, OR", "WENT BRIGHT?", "TELL CLAUDE")


def probe():
    # Read-only. Prints what later steps need to know. Run on USB and read it in Thonny.
    def line(what, fn):
        try:
            print("%-28s %s" % (what, fn()))
        except Exception as e:
            print("%-28s FAILED: %s %s" % (what, type(e).__name__, e))

    print("---- power_check probe ----")
    line("CPU frequency", machine.freq)
    line("battery mV", M5.Power.getBatteryVoltage)
    line("battery %", M5.Power.getBatteryLevel)
    line("USB line mV", M5.Power.getVBUSVoltage)
    line("isCharging", M5.Power.isCharging)
    line("button A pin saved", lambda: esp32.NVS("gymbuddy").get_i32("btn_a_pin"))
    line("M5.Power can", lambda: " ".join(n for n in dir(M5.Power) if not n.startswith("_")))
    line("M5.Speaker can", lambda: " ".join(n for n in dir(M5.Speaker) if not n.startswith("_")))
    line("M5.Imu can", lambda: " ".join(n for n in dir(M5.Imu) if not n.startswith("_")))
    line("esp32 wake functions", lambda: " ".join(n for n in dir(esp32) if "wake" in n or "hold" in n))
    line("PM1 driver in firmware", lambda: __import__("driver.m5pm1") and "yes")
    line("sensor before raw I2C", M5.Imu.getAccel)

    def raw_i2c():
        # The internal bus: SCL 48, SDA 47. Sensor at 0x68, power chip (PM1) at 0x6E. Reads only.
        bus = machine.I2C(0, scl=machine.Pin(48), sda=machine.Pin(47), freq=400000)
        found = " ".join(hex(a) for a in bus.scan())
        regs = " ".join("%s=%s" % (name, hex(bus.readfrom_mem(0x68, reg, 1)[0]))
                        for name, reg in (("CHIP_ID", 0x00), ("ACC_CONF", 0x40), ("GYR_CONF", 0x42),
                                          ("PWR_CONF", 0x7C), ("PWR_CTRL", 0x7D)))
        return "devices %s | sensor %s" % (found, regs)
    line("raw I2C", raw_i2c)
    line("sensor after raw I2C", M5.Imu.getAccel)
    print("---- copy everything above to Claude ----")
    show("PROBE DONE", "READ THONNY", "A RESTARTS")


def main():
    setup()
    name, label, minutes = pick()
    if name == "probe":
        probe()
        wait_for_a()
        machine.reset()
    pin = None
    if name == "dark":
        pin = wake_pin()
        if pin is None:
            show("DARK NEEDS", "BUTTON A'S PIN.", "RUN MAIN.PY AND", "PRESS A ONCE.", "A RESTARTS")
            wait_for_a()
            machine.reset()
    show(label, "UNPLUG USB,", "THEN PRESS A")
    while True:
        wait_for_a()
        if not on_usb():
            break
        show(label, "STILL ON USB.", "UNPLUG, PRESS A")
    if name == "naps":
        nap_look()
        wait_for_a()
        machine.reset()
    ran_min, start_mv, end_mv, ma = measure(name, label, minutes, pin)
    show(label + " %d MIN" % ran_min, "%d > %d MV" % (start_mv, end_mv), "ABOUT %d MA" % ma,
         "SAVED TO LOG", brightness=DIM_BRIGHTNESS)
    time.sleep_ms(RESULT_MS)
    machine.reset()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.print_exception(e)              # shown in Thonny if it is still connected
        try:
            show("POWER CHECK", "STOPPED:", type(e).__name__.upper())
            time.sleep_ms(10000)
        except Exception:
            pass
        machine.reset()
