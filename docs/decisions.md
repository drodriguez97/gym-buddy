# Decisions

One line per design choice, newest last.

- 2026-10-25: StickS3 axes, measured: +x points away from the USB-C port, +y across the short side, +z out of the screen.
- 2026-10-25: Set UIFlow `boot_option` to 0 so `main.py` runs at power-on instead of the UIFlow menu.
- 2026-10-25: Record at 100 Hz as 6 int16s per reading (accel in mg, gyro in 0.1 deg/s, 12 bytes), with a `.json` file per set.
- 2026-10-25: Set ID is a sequence number kept in NVS plus 6 random hex characters, so sets keep their order and never repeat.
- 2026-10-25: On the wrist, curls show up on y, because the long side (x) wraps around the wrist. `count_reps` picks the busiest axis instead of assuming one.
- 2026-10-29: With the strap, curls show up on x (the strap holds the stick 90° from the rubber band). Busiest axis still finds it.
- 2026-10-29: Sets start and end with the watch turned toward you to press the button. `active_window` ignores those parts, because they fooled the axis choice (sets 00004 and 00007 counted 8 and 5 instead of 6).
- 2026-10-29: Exercises are grouped into movement families by what the forearm does: tilt (curls, extensions, raises) and push/pull (presses, rows, pulldowns). The user picks the exercise on the watch, and the server counts with that family's settings. The families are a working guess until recordings of each exercise confirm them. See pain-points.md.
