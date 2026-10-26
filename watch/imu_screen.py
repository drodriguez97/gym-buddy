# imu_screen.py: milestone 1, show the BMI270 accelerometer on screen
# and print it over USB so Thonny's Plotter can graph it.
import time
import M5

M5.begin()
lcd = M5.Lcd
imu = M5.Imu

lcd.setRotation(1)                 # landscape: 240 wide x 135 tall
lcd.fillScreen(0x000000)
lcd.setTextSize(2)

W = lcd.width()
BAR_X = 70                        # bars start right of the numbers
BAR_W = W - BAR_X - 6
MID = BAR_X + BAR_W // 2            # the zero line
FULL_SCALE = 2.0                  # bar touches the edge at +/-2 g
ROWS = (6, 36, 66)                # y position of the x, y, z rows
COLORS = (0xFF5A52, 0xFFC233, 0x4C9AFF)  # x red, y amber, z blue
BG = 0x000000
TRACK = 0x202020


def draw_bar(row_y, value, color):
    # Erase the old bar, then grow a new one left or right of zero.
    lcd.fillRect(BAR_X, row_y, BAR_W, 22, TRACK)
    length = int(min(abs(value) / FULL_SCALE, 1.0) * (BAR_W // 2))
    if value >= 0:
        lcd.fillRect(MID, row_y, length, 22, color)
    else:
        lcd.fillRect(MID - length, row_y, length, 22, color)
    lcd.fillRect(MID, row_y, 1, 22, 0xFFFFFF)


last_draw = 0
while True:
    M5.update()                       # UIFlow wants this once per loop
    ax, ay, az = imu.getAccel()
    gx, gy, gz = imu.getGyro()

    # One line per reading: Thonny's Plotter turns these into a graph.
    print("x {:.2f} y {:.2f} z {:.2f}".format(ax, ay, az))

    # Drawing is slow, so redraw 10x a second, not on every reading.
    now = time.ticks_ms()
    if time.ticks_diff(now, last_draw) >= 100:
        last_draw = now
        for row_y, value, color in zip(ROWS, (ax, ay, az), COLORS):
            lcd.setTextColor(color, BG)   # 2nd color paints over old digits
            lcd.drawString("{:+.2f}".format(value), 0, row_y + 3)
            draw_bar(row_y, value, color)
        spin = (gx * gx + gy * gy + gz * gz) ** 0.5
        lcd.setTextColor(0xAAAAAA, BG)
        lcd.drawString("spin {:4.0f} dps ".format(spin), 0, 104)

    time.sleep_ms(20)                # about 50 readings a second