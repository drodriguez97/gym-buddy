"""watch/recorder.py with a fake sensor, clock and flash folder.

Checks the file format, that nothing touches flash while a set is running, and
the timing bookkeeping. Can't check the real sensor or how fast real flash is.
"""
import importlib.util
import json
import struct
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).parents[2]


class Bench:
    """recorder.py loaded on the laptop."""

    def __init__(self, tmp_path):
        self.flash = tmp_path / "sets"
        self.clock = 0
        self.reading = ((0.012, -0.985, 0.068), (0.3, -0.1, 12.5))     # accel g, gyro deg/s
        self.sensor_reads = 0
        self.seq = {}
        bench = self

        def get_accel():
            bench.sensor_reads += 1
            return bench.reading[0]

        class NVS:
            def __init__(self, namespace):
                pass

            def get_i32(self, key):
                if key not in bench.seq:
                    raise OSError("not found")
                return bench.seq[key]

            def set_i32(self, key, value):
                bench.seq[key] = value

            def commit(self):
                pass

        fakes = {
            "M5": types.SimpleNamespace(Imu=types.SimpleNamespace(
                getAccel=get_accel, getGyro=lambda: bench.reading[1])),
            "esp32": types.SimpleNamespace(NVS=NVS),
            "ubinascii": types.SimpleNamespace(hexlify=lambda b: b.hex().encode()),
            "time": types.SimpleNamespace(ticks_ms=lambda: bench.clock, ticks_diff=lambda a, b: a - b,
                                          ticks_add=lambda a, b: a + b),
        }
        real = {name: sys.modules.get(name) for name in fakes}
        sys.modules.update(fakes)
        try:
            spec = importlib.util.spec_from_file_location("watch_recorder", REPO / "watch" / "recorder.py")
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        finally:
            for name, old in real.items():
                if old is None:
                    del sys.modules[name]
                else:
                    sys.modules[name] = old
        self.module.SET_DIR = str(self.flash).replace("\\", "/")
        self.flash.mkdir()
        self.rec = self.module.Recorder()

    def run(self, ms, step=1):
        # Let time pass, polling like main.py's loop does. Returns info if the set stopped itself.
        for _ in range(0, ms, step):
            info = self.rec.poll()
            if info:
                return info
            self.clock += step
        return None

    def files(self):
        return sorted(p.name for p in self.flash.iterdir())


@pytest.fixture
def bench(tmp_path):
    return Bench(tmp_path)


def test_nothing_is_written_to_flash_while_a_set_is_running(bench):
    bench.rec.start()
    bench.run(5000)
    assert bench.files() == []              # flash writes stall for up to half a second


def test_stop_writes_the_bin_and_then_the_json(bench):
    bench.rec.start()
    bench.run(3000)
    info = bench.rec.stop()
    set_id = info["set_id"]
    assert bench.files() == [set_id + ".bin", set_id + ".json"]
    assert json.loads((bench.flash / (set_id + ".json")).read_text()) == info
    assert (bench.flash / (set_id + ".bin")).stat().st_size == info["count"] * 12


def test_readings_are_stored_as_int16_mg_and_tenths_of_a_degree(bench):
    bench.rec.start()
    bench.run(50)
    bench.reading = ((1.0, 0.0, -2.5), (-250.0, 0.0, 1999.9))
    bench.run(50)
    info = bench.rec.stop()
    raw = (bench.flash / (info["set_id"] + ".bin")).read_bytes()
    readings = [struct.unpack_from("<6h", raw, i) for i in range(0, len(raw), 12)]
    assert readings[0] == (12, -985, 68, 3, -1, 125)
    assert readings[-1] == (1000, 0, -2500, -2500, 0, 19999)


def test_the_json_has_the_fields_the_server_and_analyzer_read(bench):
    bench.rec.start()
    bench.run(2000)
    info = bench.rec.stop()
    assert set(info) == {"set_id", "count", "duration_ms", "rate_hz", "late", "format", "accel_unit", "gyro_unit"}
    assert info["format"] == "<6h" and info["accel_unit"] == "mg" and info["gyro_unit"] == "0.1 dps"


def test_100_readings_a_second_on_a_steady_loop(bench):
    bench.rec.start()
    bench.run(10000)
    info = bench.rec.stop()
    assert info["count"] == 1000 and info["late"] == 0
    assert info["rate_hz"] == pytest.approx(100.0)


def test_a_stall_is_caught_up_and_counted_as_late(bench):
    bench.rec.start()
    bench.run(1000)
    bench.clock += 300                      # the loop was stuck for 0.3 s
    bench.run(1000)
    info = bench.rec.stop()
    assert info["count"] == 230             # no readings lost: 2.3 s at 100 Hz
    assert 30 <= info["late"] <= 35         # the missed ones, taken back to back while catching up


def test_duration_is_fixed_when_the_set_halts_not_when_the_save_finishes(bench):
    bench.rec.start()
    bench.run(4000)
    bench.rec.halt()
    bench.clock += 1500                     # drawing "Saving..." and a slow flash write
    info = bench.rec.save()
    assert info["duration_ms"] == 4000
    assert info["rate_hz"] == pytest.approx(100.0)


def test_no_readings_after_halt(bench):
    bench.rec.start()
    bench.run(1000)
    bench.rec.halt()
    before = bench.sensor_reads
    assert bench.run(500) is None
    assert bench.sensor_reads == before


def test_a_set_stops_itself_after_two_minutes_and_fits_the_buffer(bench):
    bench.rec.start()
    info = bench.run(130000, step=2)
    assert info is not None and not bench.rec.recording
    assert 120000 <= info["duration_ms"] <= 120010
    assert info["count"] * 12 <= len(bench.rec.buf)
    assert (bench.flash / (info["set_id"] + ".bin")).stat().st_size == info["count"] * 12


def test_a_runaway_set_can_never_overflow_the_buffer(bench):
    # If readings came faster than planned, the buffer limit stops the set.
    bench.rec.start()
    bench.module.PERIOD_MS = 5
    info = bench.run(130000)
    assert info is not None
    assert info["count"] == bench.module.MAX_READINGS


def test_set_ids_count_up_and_never_repeat(bench):
    ids = []
    for _ in range(3):
        bench.rec.start()
        bench.run(100)
        ids.append(bench.rec.stop()["set_id"])
    assert [i[:5] for i in ids] == ["00001", "00002", "00003"]
    assert len(set(ids)) == 3


def test_a_recorded_set_loads_in_the_analyzer(bench):
    sys.path.insert(0, str(REPO / "server"))
    from app.analysis import load_set
    bench.rec.start()
    bench.run(3000)
    info = bench.rec.stop()
    meta, t, accel, gyro = load_set(bench.flash / (info["set_id"] + ".bin"))
    assert accel.shape == (300, 3) and gyro.shape == (300, 3)
    assert accel[0].tolist() == pytest.approx([0.012, -0.985, 0.068])
    assert gyro[0].tolist() == pytest.approx([0.3, -0.1, 12.5])
