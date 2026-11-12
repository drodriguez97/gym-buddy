# Battery plan

Written 2026-11-11. A plan, not yet built. Nothing here changes what the watch
records, the 100 Hz rate, the file format or the sync protocol.

**Read this first:** every current below is an estimate from datasheets and
M5Stack's documents. Nobody has measured this watch. Step 0 exists to replace
the guesses with numbers, and the order of the later steps may change once it
has.

## What the research found about this watch

The M5StickS3 has a small second chip (M5Stack calls it the PM1) that switches
four separate power rails. M5Stack publishes the current for each level:

| Level | What is powered | Current |
|---|---|---|
| Off | Only the PM1 | 0.014 mA |
| L1 | + the motion sensor | 0.05 mA |
| L2 | + the ESP32, asleep | **0.10 mA** |
| L3A | ESP32 running | 37 mA |
| L3B | + screen, backlight supply, audio chip, microphone | more; not published |

Three facts follow, and they drive the plan:

1. **Our OFF state is probably 10 to 30 times above what the hardware can do.**
   We deep-sleep the ESP32, but nothing tells the PM1 to switch off the screen
   and audio rail, and the motion sensor keeps running its accelerometer and
   gyro at full rate (about 0.7 to 1 mA by its datasheet) even though nobody
   reads it. M5Stack's 0.10 mA figure assumes both are dealt with. Ours is
   likely 1 to 3 mA.
2. **Between sets the CPU never sleeps.** The five-minute rest window keeps
   the ESP32 awake (about 22 to 36 mA) so that the dim face can stay on.
3. **Sync barely matters.** A sync is about 10 seconds of radio a few times a
   day: well under 1% of the battery. It is last in the plan for that reason.

## Where a day's battery goes now (estimate)

One 45-minute workout of 15 sets, watch untouched for the rest of the day.
The battery is 250 mAh; about 200 mAh is usable.

| State | Time per day | Current | Uses |
|---|---|---|---|
| OFF (deep sleep) | 23 h | 1 to 3 mA | 23 to 69 mAh |
| RESTING and AWAKE between sets | 34 min | about 42 mA | 24 mAh |
| RECORDING | 11 min | about 50 mA | 9 mAh |
| After the workout: rest window, sync, DARK | 15 min | mixed | 5 mAh |
| Sync | 10 s | about 120 mA | 0.3 mAh |
| **Total** | | | **60 to 105 mAh: 2 to 3 days per charge** |

If the steps below work as the documents suggest: about 16 mAh a day, or
roughly 10 days per charge, and months in a drawer instead of a week.

## Step 0: measure (nothing else starts before this)

There is no way to read current from the watch itself, and a USB meter can't
see milliamps. Two options:

- **Rundown tests (free, slow).** A script, `watch/power_check.py`, holds the
  watch in one state for a fixed time and logs the battery voltage to flash at
  the start and end, after a rest. One hour is enough for the awake states;
  OFF needs overnight. Voltage is a blunt tool: good for "is OFF 2 mA or
  0.1 mA", useless for a 2 mA difference while awake.
- **A Nordic PPK2 (about $100, exact).** Feeds the battery connector and plots
  current live. Worth it only if this continues past the demo.

Measure five things: OFF overnight, DARK for an hour, RESTING for an hour,
AWAKE at brightness 64 for an hour, RECORDING for 30 minutes.

`watch/power_check.py` is written (2026-11-11) and tested against a fake
watch; it has not run on the real one. The steps are at the top of the file.
In short: charge fully, run it from Thonny, pick a test with B, choose with A,
unplug, press A. Results are added to `/flash/power_log.csv`. Two of its
entries measure nothing: PROBE (stay on USB; prints what the firmware can do)
and NAP LOOK (watch whether the dim screen survives light sleep). OFF is
measured with the dashboard: sync, note the battery voltage on the Watch tab,
leave the watch overnight, sync again.

Also answered in this step, because later steps depend on them:
- Can MicroPython talk to the PM1 and the motion sensor directly (raw I2C at
  addresses 0x6E and 0x68) while M5Stack's own code is using the same wires?
- Does the dim backlight survive `machine.lightsleep`, or does it go dark or
  to full brightness? (A known MicroPython bug on this chip suggests it may.)
- Does the battery reach 4.1 V or more on a wall charger? The "70% while
  plugged in" reading is still unexplained.

## Step 1: fix the floor (biggest gain, no change the wearer can see)

Est. saving: 20 to 65 mAh a day. Applies to OFF first, then DARK.

| Change | Why | Risk |
|---|---|---|
| Suspend the motion sensor whenever no set is being recorded, and wake it on the press that starts a set | 0.7 to 1 mA becomes 0.004 mA in every state except RECORDING | The gyro needs tens of milliseconds to start. The face and beep already take longer than that before recording begins, but the first readings of a set must be checked against a recording made today |
| Switch off the screen and audio rail (through the PM1) before deep sleep | The audio chip, microphone and screen electronics are powered all night for nothing | Waking from OFF is already a full restart that sets everything up again, so this is the safe place to start |
| Make sure the speaker amplifier is switched off after each beep | An idle amplifier can draw a few mA | Low; measure before and after |
| Go from DARK to OFF after 1 minute instead of 10 | Light sleep costs roughly 20 times what deep sleep does. During a workout the rest window already covers the gaps, so this only applies once the workout is over | Waking takes 3 seconds instead of being instant, 9 minutes sooner than today |

## Step 2: sleep between sets (biggest gain during a workout; needs your decision)

Est. saving: about 20 mAh per workout, 8% of the battery.

Today RESTING shows a dim face for five minutes so that one press of A starts
the next set. The CPU could be in light sleep for nearly all of that time and
still start a set on one press. What decides how is the backlight test in step 0:

- **If the dim backlight survives light sleep:** sleep in short naps and wake
  on either button. Nothing changes for the wearer.
- **If it doesn't:** the choice is yours. Either the screen goes dark between
  sets and one press of A still starts the next set (large saving, the dim
  face is lost), or RESTING stays as it is.

## Step 3: smaller things, each a choice about how the watch looks

| Change | Est. saving | What you'd notice |
|---|---|---|
| Dim the backlight a few seconds into a set | 1 to 3 mAh per workout | The REC face goes dim. A brightness change is one pin, not a screen draw, so the "nothing is drawn during a set" rule holds; it must still be timed |
| Normal brightness 64 down to about 40 | Proportional to screen-on time | A dimmer screen indoors |
| Run the CPU at 40 MHz when not recording or syncing | Up to 9 mA while the screen is on | Nothing, if it works. It may break USB and must be raised again before Wi-Fi, or the watch hangs. Test last |

## Step 4: sync (small, but cheap)

- **Take the time from our own server instead of NTP.** The health report's
  answer already carries `server_time`. That removes a separate internet
  request (up to 3 seconds of radio) from every sync.
- **Give up sooner on the automatic end-of-workout sync.** At a gym with no
  Wi-Fi it searches for 15 seconds at about 100 mA after every workout. Six
  seconds is plenty when the network is there.
- **Remember the router (its BSSID) and skip the scan.** Measured elsewhere to
  cut a connection from about 8 seconds to 2. Left for last because a phone
  hotspot, which the demo uses, can change it.

## Looked at and not recommended

- **Having the sensor batch readings (its FIFO) so the CPU can nap during a
  set.** It would save a few mA for 11 minutes a day and rewrite the one part
  of the watch that must never go wrong. Not worth it.
- **Powering fully off instead of deep sleep.** 0.014 mA instead of 0.10 mA,
  but the watch forgets the time and button A can no longer wake it.
- **Custom firmware.** Real gains in light sleep and boot time, at the cost of
  leaving UIFlow2.
- **Bluetooth.** Already never started.

## Order and the demo

Sleep code is the riskiest code on the watch: the first attempt at it left the
watch unable to wake. Steps 1 to 4 should not go on the demo watch before
Monday 2026-11-16 unless step 0 shows the battery can't last the day, which
the estimate says it can several times over. Step 0 changes nothing in
`main.py` and can run any night this week.

Every step follows the same loop: measure, change one thing behind a switch at
the top of `main.py` (like `LIGHT_SLEEP`), test on the fake watch, flash,
measure again, and keep it only if the number moved.

## Sources

- M5StickS3 product page and low-power page: docs.m5stack.com/en/core/StickS3, docs.m5stack.com/en/arduino/m5sticks3/m5pm1
- ESP32-S3 datasheet v2.2, current tables 5-7, 5-9, 5-10
- BMI270 datasheet rev 1.6 (currents per mode, power registers 0x7C and 0x7D)
- MicroPython ESP32 source and issues #17973 (backlight in light sleep) and #18427 (Wi-Fi below 80 MHz)
- Qoitech's measured ESP32-S3 sleep currents; voltsandbits.com on Wi-Fi fast connect
