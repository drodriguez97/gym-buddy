"""Run watch/main.py on the laptop against fake hardware and a virtual clock.

main.py is an endless loop written for MicroPython, so it can't be imported.
run() swaps in fake M5, machine, esp32, recorder, time and os modules, executes
the file, and returns what happened as a list of (seconds, event) pairs.

Events: "backlight on", "backlight off", "screen: <text>", "status line",
"recording start", "recording stop", "light sleep", "woke by button",
"deep sleep", "pin saved <n>", "sync", "radios off".
"""
import sys
import types
from pathlib import Path

MAIN = Path(__file__).parents[1] / "main.py"


class Result:
    def __init__(self, events, armed):
        self.events = events
        self.armed = armed                  # GPIO numbers armed as wake sources

    def times(self, name):
        return [t for t, e in self.events if e == name]

    def has(self, name):
        return bool(self.times(name))

    def between(self, start_s, end_s):
        return [e for t, e in self.events if start_s <= t < end_s]


def run(presses=(), run_for_s=60, charging=False, b_held=False, saved_pin=None,
        a_gpio=11, edit=None, b_presses=(), b_held_s=None, sync_result=(2, 0, None)):
    """presses: (down_s, up_s) pairs for button A. a_gpio: the GPIO it is really on.
    b_presses: the same for button B. b_held: B is down at boot (for the whole run,
    or for b_held_s seconds). sync_result: what the fake sync returns, or an
    exception for it to raise. edit: function applied to main.py's source first."""
    clock = [0]                             # virtual milliseconds
    events = []
    armed = []

    def say(event):
        events.append((clock[0] / 1000, event))

    def held():
        return any(down * 1000 <= clock[0] < up * 1000 for down, up in presses)

    def b_down():
        if b_held and (b_held_s is None or clock[0] < b_held_s * 1000):
            return True
        return any(down * 1000 <= clock[0] < up * 1000 for down, up in b_presses)

    class Stop(Exception):
        pass

    # ---- time
    fake_time = types.ModuleType("time")
    fake_time.ticks_ms = lambda: clock[0]
    fake_time.ticks_diff = lambda a, b: a - b
    fake_time.ticks_add = lambda a, b: a + b

    def sleep_ms(ms):
        clock[0] += ms
    fake_time.sleep_ms = sleep_ms

    # ---- os
    fake_os = types.ModuleType("os")
    fake_os.statvfs = lambda path: (4096, 0, 1000, 0, 900)

    # ---- M5
    class Lcd:
        brightness = None

        def setBrightness(self, value):
            if value != self.brightness:
                say("backlight off" if value == 0 else "backlight on")
            self.brightness = value

        def drawString(self, text, x, y):
            if y >= 100:
                say("status line")
            elif text:
                say("screen: " + text)

        def width(self):
            return 240

        def textWidth(self, text):
            return 12 * len(text)

        def __getattr__(self, name):        # fillScreen, setTextColor, sleep, wakeup, ...
            return lambda *args: None

    class Button:
        # Debounced like the real one: the press shows up 3 updates late.
        def __init__(self, down):
            self.down = down
            self.history = [False] * 3
            self.was = False

        def tick(self):
            before = all(self.history)
            self.history = self.history[1:] + [self.down()]
            self.was = all(self.history) and not before

        def wasPressed(self):
            return self.was

        def isPressed(self):
            return self.down()

    M5 = types.ModuleType("M5")
    M5.Lcd = Lcd()
    M5.BtnA = Button(held)
    M5.BtnB = Button(b_down)                # held at boot still reports "was pressed": the worst case
    M5.Power = types.SimpleNamespace(isCharging=lambda: charging, getBatteryLevel=lambda: 80)
    M5.begin = lambda: None

    def update():
        if clock[0] >= run_for_s * 1000:
            raise Stop
        clock[0] += 1                       # a pass of the loop takes time, so no bug can freeze the clock
        M5.BtnA.tick()
        M5.BtnB.tick()
    M5.update = update

    # ---- machine
    machine = types.ModuleType("machine")
    wake_reason = [0]

    class Pin:
        IN = 1
        PULL_UP = 2

        def __init__(self, number, *args):
            self.number = number

        def value(self):
            return 0 if (self.number == a_gpio and held()) else 1

    def lightsleep(ms):
        say("light sleep")
        end = clock[0] + ms
        while clock[0] < end:
            if held() and a_gpio in armed:  # only an armed pin can wake the chip
                wake_reason[0] = 2
                say("woke by button")
                return
            clock[0] += 10
        wake_reason[0] = 4                  # timer

    def deepsleep():
        say("deep sleep")
        raise Stop

    machine.Pin = Pin
    machine.freq = lambda hz: None
    machine.EXT0_WAKE = 2
    machine.wake_reason = lambda: wake_reason[0]
    machine.lightsleep = lightsleep
    machine.deepsleep = deepsleep

    # ---- esp32
    esp32 = types.ModuleType("esp32")
    store = {} if saved_pin is None else {"btn_a_pin": saved_pin}

    class NVS:
        def __init__(self, namespace):
            pass

        def get_i32(self, key):
            if key not in store:
                raise OSError("not found")
            return store[key]

        def set_i32(self, key, value):
            store[key] = value
            say("pin saved %d" % value)

        def commit(self):
            pass

    esp32.NVS = NVS
    esp32.wake_on_ext0 = lambda pin, level: armed.append(pin.number)

    # ---- recorder
    recorder = types.ModuleType("recorder")

    class Recorder:
        recording = False

        def start(self):
            self.recording = True
            say("recording start")

        def stop(self):
            self.recording = False
            say("recording stop")
            return {"set_id": "00030-abcdef", "count": 500, "rate_hz": 100.0, "late": 0}

        def poll(self):
            return None

    recorder.Recorder = Recorder

    # ---- sync, network
    fake_sync = types.ModuleType("sync")

    def sync(report=None):
        say("sync")
        if isinstance(sync_result, Exception):
            raise sync_result
        if report:
            report("set 1 of 2")
        clock[0] += 4000                    # a sync takes a few seconds
        return sync_result
    fake_sync.sync = sync

    network = types.ModuleType("network")

    class WLAN:
        def __init__(self, interface):
            pass

        def active(self, on):
            if not on:
                say("radios off")
    network.WLAN = WLAN
    network.STA_IF = 0
    network.AP_IF = 1

    fakes = {"time": fake_time, "os": fake_os, "M5": M5, "machine": machine,
             "esp32": esp32, "recorder": recorder, "sync": fake_sync, "network": network}
    source = MAIN.read_text(encoding="utf-8")
    if edit:
        source = edit(source)
    real = {name: sys.modules.get(name) for name in fakes}
    sys.modules.update(fakes)
    try:
        exec(compile(source, str(MAIN), "exec"), {"__name__": "__main__"})
    except Stop:
        pass
    finally:
        for name, module in real.items():
            if module is None:
                del sys.modules[name]
            else:
                sys.modules[name] = module
    return Result(events, armed)
