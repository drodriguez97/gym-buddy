# timing_check.py: where does the time go? Run from Thonny with F5 (Ctrl+C first).
# Times each thing main.py and recorder.py do, so a slow one stands out.
# A reading is due every 10 ms, so anything near or over 5 ms in the recording
# loop makes readings late. Writes nothing permanent: its test file is removed.
import gc
import os
import time
import machine
import M5

M5.begin()
machine.freq(80000000)


def measure(name, fn, times=200):
    # Prints the average and the worst case in milliseconds.
    worst = 0
    start_all = time.ticks_us()
    for _ in range(times):
        start = time.ticks_us()
        fn()
        took = time.ticks_diff(time.ticks_us(), start)
        if took > worst:
            worst = took
    avg = time.ticks_diff(time.ticks_us(), start_all) / times
    print("%-34s avg %7.2f ms   worst %7.2f ms" % (name, avg / 1000, worst / 1000))


def loop_pass():
    # One pass of main.py's loop during a set, without the reading itself.
    M5.update()
    M5.BtnA.wasPressed()
    M5.BtnB.wasPressed()
    time.sleep_ms(1)


def reading():
    M5.Imu.getAccel()
    M5.Imu.getGyro()


try:
    names = os.listdir("/flash/sets")
except OSError:
    names = []
size = sum(os.stat("/flash/sets/" + n)[6] for n in names)
s = os.statvfs("/flash")
print("CPU %d MHz, %d files in /flash/sets (%d KB), flash %d%% free"
      % (machine.freq() // 1000000, len(names), size // 1024, 100 * s[4] // s[2]))
start = time.ticks_us()
gc.collect()
print("memory: %d KB free, %d KB in use; one clean-up (gc.collect) took %.1f ms"
      % (gc.mem_free() // 1024, gc.mem_alloc() // 1024, time.ticks_diff(time.ticks_us(), start) / 1000))
print()
print("During a set, every 10 ms:")
measure("time.sleep_ms(1)", lambda: time.sleep_ms(1))
measure("M5.update()", M5.update)
measure("one loop pass (update+buttons+nap)", loop_pass)
measure("one reading (accel + gyro)", reading)

print()
print("Once a second during a set:")
buf = bytearray(1200)
f = open("/flash/timing_check.tmp", "wb")
measure("write 100 readings to flash", lambda: f.write(buf), times=10)
f.close()

print()
print("When a set stops or the screen redraws:")
measure("os.statvfs (the Free % number)", lambda: os.statvfs("/flash"), times=5)
measure("battery level", M5.Power.getBatteryLevel, times=5)
start = time.ticks_us()
os.remove("/flash/timing_check.tmp")
print("%-34s %7.2f ms" % ("remove the test file", time.ticks_diff(time.ticks_us(), start) / 1000))
print()
print("Done. Paste all of this back.")
