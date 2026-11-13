# recorder.py: record one set from the BMI270, then save it to flash.
# Each reading is 6 int16s: accel in mg, gyro in 0.1 deg/s (12 bytes).
#
# Readings go into memory while the set runs and are written to flash when it
# stops. Writing during the set was measured (timing_check.py) to stall for up
# to half a second, which made up to half the readings of a set late.
# The .bin format and the 100 Hz rate are unchanged.
#
# Saving is all-or-nothing. The readings go to a .tmp file, then the .json is
# written, then the .tmp is renamed to .bin. If power is lost part-way, the
# next boot finishes the job (a .tmp with a .json) or throws the scrap away
# (a .tmp alone). sync.py therefore never sees half a set.
import gc
import json
import os
import struct
import time
import ubinascii
import esp32
import M5
import clock

RATE_HZ = 100
PERIOD_MS = 1000 // RATE_HZ
FMT = "<6h"                     # 6 little-endian int16s
SIZE = struct.calcsize(FMT)       # 12 bytes
LATE_MS = 5                       # a reading this far past due counts as late
MAX_SET_MS = 120000               # stop on its own after 2 minutes
MAX_READINGS = MAX_SET_MS // PERIOD_MS + 100    # what the memory buffer holds (145 KB)
SET_DIR = "/flash/sets"


def _next_set_id():
    # Sequence number (kept in NVS) for order, random hex for uniqueness.
    nvs = esp32.NVS("gymbuddy")
    try:
        seq = nvs.get_i32("set_seq") + 1
    except OSError:
        seq = 1                       # first set ever
    nvs.set_i32("set_seq", seq)
    nvs.commit()
    return "%05d-%s" % (seq, ubinascii.hexlify(os.urandom(3)).decode())


class Recorder:
    def __init__(self):
        try:
            os.mkdir(SET_DIR)
        except OSError:
            pass                        # already exists
        self.recover()
        # Made once at boot and reused, so recording never asks for new memory.
        self.buf = bytearray(MAX_READINGS * SIZE)
        self.recording = False

    def recover(self):
        # Finish or discard a save that lost power part-way.
        names = os.listdir(SET_DIR)
        for name in names:
            if name.endswith(".tmp"):
                path = "%s/%s" % (SET_DIR, name)
                if name[:-4] + ".json" in names:
                    os.rename(path, path[:-4] + ".bin")     # complete: the .json is only written after the readings
                else:
                    os.remove(path)

    def start(self, exercise=None):
        # exercise: the name picked on the watch; the server counts with it.
        gc.collect()                    # tidy memory now, so a clean-up is less likely mid-set
        self.exercise = exercise
        self.started_at = clock.unix_now()      # None until a sync has set the clock
        self.clock_checked = getattr(clock, "checked", True)    # False: stamped by a clock nobody has checked yet
        self.set_id = _next_set_id()
        self.count = 0
        self.late = 0
        self.started = time.ticks_ms()
        self.next_due = self.started
        self.recording = True

    def poll(self):
        # Call as often as possible. Takes a reading only when one is due.
        # Returns True if the time limit just halted the set (the caller then
        # calls save()), else None.
        if not self.recording:
            return None
        now = time.ticks_ms()
        behind = time.ticks_diff(now, self.next_due)
        if behind < 0:
            return None                 # not due yet
        if behind > LATE_MS:
            self.late += 1
        self.next_due = time.ticks_add(self.next_due, PERIOD_MS)

        ax, ay, az = M5.Imu.getAccel()
        gx, gy, gz = M5.Imu.getGyro()
        # +-16 g and +-2000 deg/s both fit in an int16 at these scales.
        struct.pack_into(FMT, self.buf, self.count * SIZE,
                         int(ax * 1000), int(ay * 1000), int(az * 1000),
                         int(gx * 10), int(gy * 10), int(gz * 10))
        self.count += 1

        if time.ticks_diff(now, self.started) >= MAX_SET_MS or self.count >= MAX_READINGS:
            self.halt()
            return True
        return None

    def halt(self):
        # End the set: no more readings. The duration is fixed here, before the
        # slow save, because rate_hz is worked out from it.
        self.duration_ms = time.ticks_diff(time.ticks_ms(), self.started)
        self.recording = False

    def save(self):
        # Write the set to flash: readings to .tmp, then the .json, then rename
        # .tmp to .bin. Raises OSError (flash full, say) with nothing left behind.
        base = "%s/%s" % (SET_DIR, self.set_id)
        info = {
            "set_id": self.set_id,
            "count": self.count,
            "duration_ms": self.duration_ms,
            "rate_hz": self.count * 1000 / self.duration_ms if self.duration_ms else 0,
            "late": self.late,
            "format": FMT,
            "accel_unit": "mg",
            "gyro_unit": "0.1 dps",
            "exercise": self.exercise,
            "started_at": self.started_at,
            "clock_checked": self.clock_checked,
        }
        try:
            with open(base + ".tmp", "wb") as f:
                f.write(memoryview(self.buf)[: self.count * SIZE])
            with open(base + ".json", "w") as f:
                json.dump(info, f)
            os.rename(base + ".tmp", base + ".bin")
        except OSError:
            for path in (base + ".tmp", base + ".json"):
                try:
                    os.remove(path)
                except OSError:
                    pass
            raise
        return info

    def stop(self):
        self.halt()
        return self.save()
