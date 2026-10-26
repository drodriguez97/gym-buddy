# Decisions

One line per design choice, newest last.

- 2026-10-25: StickS3 axes, measured: +x points away from the USB-C port, +y across the short side, +z out of the screen.
- 2026-10-25: Set UIFlow `boot_option` to 0 so `main.py` runs at power-on instead of the UIFlow menu.
- 2026-10-25: Record at 100 Hz as 6 int16s per reading (accel in mg, gyro in 0.1 deg/s, 12 bytes), with a `.json` file per set.
- 2026-10-25: Set ID is a sequence number kept in NVS plus 6 random hex characters, so sets keep their order and never repeat.
- 2026-10-25: On the wrist, curls show up on y, because the long side (x) wraps around the wrist. `count_reps` picks the busiest axis instead of assuming one.
