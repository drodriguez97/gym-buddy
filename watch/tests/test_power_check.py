"""power_check.py against fake hardware: it must never reach the watch with a typo in it.

These check the flow (what it shows, what it holds, what it logs). The numbers
it would measure on the real watch are exactly what the laptop can't know.
"""
import builtins
import importlib.util
import sys
import types
from pathlib import Path

SCRIPT = Path(__file__).parents[1] / "power_check.py"


class Stop(BaseException):
    pass


class Watch:
    """The fake watch. a_presses and b_presses are the seconds at which each button is pressed."""

    def __init__(self, a_presses=(), b_presses=(), unplug_at_s=0, drain_mv_per_hour=80, wake_pin=11):
        self.ms = 0
        self.a = [int(s * 1000) for s in a_presses]
        self.b = [int(s * 1000) for s in b_presses]
        self.unplug_at = unplug_at_s * 1000
        self.drain = drain_mv_per_hour
        self.wake_pin = wake_pin
        self.screens = []           # (seconds, tuple of lines)
        self.brightness = []        # (seconds, value)
        self.naps = 0
        self.readings = 0
        self.log = []
        self.printed = []
        self.reset = False
        self.a_was = self.b_was = False

    def due(self, presses):
        if presses and presses[0] <= self.ms:
            presses.pop(0)
            return True
        return False

    def modules(self):
        w = self
        t = types.ModuleType("time")
        t.ticks_ms = lambda: w.ms
        t.ticks_diff = lambda a, b: a - b
        t.ticks_add = lambda a, b: a + b

        def sleep_ms(ms):
            w.ms += ms
        t.sleep_ms = sleep_ms

        lines = []

        class Lcd:
            def fillScreen(self, color):
                lines.clear()

            def drawString(self, text, x, y):
                lines.append(text)

            def setBrightness(self, value):
                w.screens.append((w.ms / 1000, tuple(lines)))
                w.brightness.append((w.ms / 1000, value))

            def __getattr__(self, name):
                return lambda *args: None

        def imu():
            w.readings += 1
            return (0.0, 0.6, 0.8)

        M5 = types.ModuleType("M5")
        M5.begin = lambda: None
        M5.Lcd = Lcd()

        def update():
            w.ms += 1
            w.a_was, w.b_was = w.due(w.a), w.due(w.b)
        M5.update = update
        M5.BtnA = types.SimpleNamespace(wasPressed=lambda: w.a_was)
        M5.BtnB = types.SimpleNamespace(wasPressed=lambda: w.b_was)
        M5.Power = types.SimpleNamespace(
            getBatteryVoltage=lambda: int(4000 - w.drain * w.ms / 3600000),
            getBatteryLevel=lambda: 80,
            getVBUSVoltage=lambda: 4900 if w.ms < w.unplug_at else 0,
            isCharging=lambda: False)
        M5.Imu = types.SimpleNamespace(getAccel=imu, getGyro=lambda: (1.0, 2.0, 3.0))
        M5.Speaker = types.SimpleNamespace(tone=lambda hz, ms: None)

        machine = types.ModuleType("machine")

        class Pin:
            IN, PULL_UP = 1, 2

            def __init__(self, number, *args):
                self.number = number

            def value(self):
                return 0 if w.a and w.a[0] <= w.ms else 1

        def lightsleep(ms):
            w.naps += 1
            w.ms += ms

        def reset():
            w.reset = True
            raise Stop
        machine.Pin, machine.lightsleep, machine.reset = Pin, lightsleep, reset
        machine.freq = lambda *args: 80000000

        class I2C:
            def __init__(self, *args, **kwargs):
                pass

            def scan(self):
                return [0x18, 0x68, 0x6E]

            def readfrom_mem(self, address, register, count):
                return bytes([0x24])
        machine.I2C = I2C

        esp32 = types.ModuleType("esp32")

        class NVS:
            def __init__(self, namespace):
                pass

            def get_i32(self, key):
                if w.wake_pin is None:
                    raise OSError("not found")
                return w.wake_pin
        esp32.NVS = NVS
        esp32.wake_on_ext0 = lambda pin, level: None
        return {"time": t, "M5": M5, "machine": machine, "esp32": esp32}


def run(watch, monkeypatch):
    for name, module in watch.modules().items():
        monkeypatch.setitem(sys.modules, name, module)
    real_open = builtins.open

    def fake_open(path, mode="r", *args, **kwargs):
        if path != "/flash/power_log.csv":
            return real_open(path, mode, *args, **kwargs)
        return LogFile(watch)
    monkeypatch.setattr(builtins, "open", fake_open)
    monkeypatch.setattr(builtins, "print", lambda *args: watch.printed.append(" ".join(str(a) for a in args)))
    spec = importlib.util.spec_from_file_location("power_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        module.main()
    except Stop:
        pass
    # 240 px wide, 12 px a character, 6 px margin: 19 characters fit on a line.
    too_long = [line for line in shown(watch) if len(line) > 19]
    assert not too_long, too_long
    return module


class LogFile:
    def __init__(self, watch):
        self.watch = watch

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def write(self, text):
        self.watch.log.append(text)


def shown(watch):
    return [line for _, lines in watch.screens for line in lines]


def test_awake_runs_an_hour_at_normal_brightness_and_logs_one_line(monkeypatch):
    # A chooses the first test at 1 s, and starts it at 5 s (USB already unplugged).
    watch = Watch(a_presses=[1, 5])
    run(watch, monkeypatch)
    assert len(watch.log) == 1
    name, minutes, start_mv, end_mv, ma = watch.log[0].strip().split(",")
    assert name == "awake" and 59.9 <= float(minutes) <= 60.1
    assert int(start_mv) > int(end_mv)
    # 80 mV an hour is 10% of a 250 mAh battery an hour: 25 mA. The second
    # settling minute is part of the drain, so a little over.
    assert 25 <= float(ma) <= 26.5
    assert "TEST: AWAKE" in shown(watch)
    assert watch.reset                      # hands the watch back to main.py


def test_the_battery_is_read_with_the_screen_off_both_times(monkeypatch):
    watch = Watch(a_presses=[1, 5])
    run(watch, monkeypatch)
    off = [t for t, value in watch.brightness if value == 0]
    assert len(off) == 2 and off[1] - off[0] > 3600


def test_it_will_not_start_while_still_on_usb(monkeypatch):
    # Chosen at 1 s; A pressed at 5 s while plugged in; unplugged at 8 s; A again at 10 s.
    watch = Watch(a_presses=[1, 5, 10], unplug_at_s=8)
    run(watch, monkeypatch)
    assert "STILL ON USB." in shown(watch)
    reading = [t for t, lines in watch.screens if "READING BATTERY" in lines]
    assert reading and reading[0] >= 10


def test_b_picks_the_test_and_resting_uses_the_dim_backlight(monkeypatch):
    watch = Watch(b_presses=[1], a_presses=[2, 5])
    run(watch, monkeypatch)
    assert watch.log[0].startswith("resting,")
    held = [value for t, value in watch.brightness if 200 < t < 3600]
    assert held == [] and (14 in [value for _, value in watch.brightness])


def test_recording_reads_the_sensor_a_hundred_times_a_second(monkeypatch):
    watch = Watch(b_presses=[1, 2], a_presses=[3, 6])
    run(watch, monkeypatch)
    assert watch.log[0].startswith("recording,30.0,")
    assert 0.9 * 100 * 1800 <= watch.readings <= 1.02 * 100 * 1800


def test_dark_sleeps_in_naps_and_counts_the_time_by_them(monkeypatch):
    watch = Watch(b_presses=[1, 2, 3], a_presses=[4, 7])
    run(watch, monkeypatch)
    assert watch.log[0].startswith("dark,60.0,")
    assert watch.naps == 1800


def test_dark_without_a_learned_button_pin_refuses(monkeypatch):
    watch = Watch(b_presses=[1, 2, 3], a_presses=[4, 7], wake_pin=None)
    run(watch, monkeypatch)
    assert "DARK NEEDS" in shown(watch)
    assert watch.log == [] and watch.naps == 0


def test_pressing_a_ends_a_test_early_and_still_logs_it(monkeypatch):
    watch = Watch(a_presses=[1, 5, 700])
    run(watch, monkeypatch)
    minutes = float(watch.log[0].split(",")[1])
    assert 9 <= minutes <= 11


def test_nap_look_naps_three_times_and_measures_nothing(monkeypatch):
    watch = Watch(b_presses=[1, 2, 3, 4], a_presses=[5, 8, 60])
    run(watch, monkeypatch)
    assert watch.naps == 3 and watch.log == []
    assert "NAP 3 OF 3" in shown(watch)


def test_probe_prints_what_the_firmware_can_do_without_unplugging(monkeypatch):
    watch = Watch(b_presses=[1, 2, 3, 4, 5], a_presses=[6, 9], unplug_at_s=10**6)
    run(watch, monkeypatch)
    text = "\n".join(watch.printed)
    assert "raw I2C" in text and "0x68" in text and "CHIP_ID=0x24" in text
    assert "PM1 driver in firmware" in text and "FAILED" in text      # no such driver on the laptop
    assert watch.log == []
