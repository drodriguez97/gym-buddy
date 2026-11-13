# faces.py: the gym buddy's face.
#
# Each mood is one row of numbers in MOODS (eye size, shape, position, mouth),
# and draw() can draw any of them, so a new mood is one new row.
# Screen is 240 x 135 (landscape): eyes and mouth on top, one word bottom left,
# and a small hint on its own line just above it, on the right. They are on
# separate lines so a long word can never run into the hint, whatever the font.
# main.py adds the battery icon.
#
# Only simple shapes are used. If this firmware lacks one of the rounder ones,
# the helpers fall back to rectangles, so a face always appears.
import math

BLACK  = 0x000000
GREEN  = 0x7CFF6B
DIM    = 0x4FA846
RED    = 0xFF6A4D
AMBER  = 0xFFC233
ORANGE = 0xFF8A4C
BLUE   = 0x5CC8FF
GREY   = 0xA8A8A8               # hints: light enough to read at arm's length

CENTER_X = 120
TITLE_AT = (10, 113)
HINT_Y = 96                     # right-aligned to HINT_RIGHT; its own line above the title
HINT_RIGHT = 232

# name: (colour, eye width, left eye height, right eye height, corner radius,
#        lid slant in % of height (+ inner side lower = focused, - outer side lower = worried),
#        happy (bottom of the eye pushed up by a cheek), eye centre y, gap between eyes, mouth)
MOODS = {
    "ready":   (GREEN,  46, 48, 48, 20,   0, False, 42, 30, "smile"),
    "rec":     (RED,    58, 50, 50, 17,  30, False, 52, 22, None),
    "saved":   (GREEN,  48, 44, 44, 21,   0, True,  40, 30, "grin"),
    "sync":    (AMBER,  44, 50, 50, 19,   0, False, 39, 30, "dots"),
    "saving":  (GREEN,  44, 50, 50, 19,   0, False, 39, 30, "dots"),    # busy like sync, but green: nothing is being sent
    "sleepy":  (DIM,    62, 13, 13,  6,   0, False, 62, 22, None),
    "problem": (ORANGE, 54, 62, 38, 18, -35, False, 52, 22, None),
}


def set_font(lcd, big):
    # A smooth 18 px font for the word and 12 px for the hint. If this firmware
    # doesn't have them, the built-in blocky font is used instead.
    try:
        lcd.setFont(lcd.FONTS.DejaVu18 if big else lcd.FONTS.DejaVu12)
        lcd.setTextSize(1)
    except Exception:
        lcd.setTextSize(2 if big else 1)


def _round_rect(lcd, x, y, w, h, r, color):
    try:
        lcd.fillRoundRect(x, y, w, h, r, color)
    except AttributeError:
        lcd.fillRect(x, y, w, h, color)


def _circle(lcd, x, y, r, color):
    try:
        lcd.fillCircle(x, y, r, color)
    except AttributeError:
        lcd.fillRect(x - r, y - r, 2 * r + 1, 2 * r + 1, color)


def _ellipse(lcd, x, y, rx, ry, color):
    try:
        lcd.fillEllipse(x, y, rx, ry, color)
    except AttributeError:
        lcd.fillRect(x - rx, y - ry, 2 * rx, 2 * ry, color)


def _triangle(lcd, x0, y0, x1, y1, x2, y2, color):
    try:
        lcd.fillTriangle(x0, y0, x1, y1, x2, y2, color)
    except AttributeError:
        pass                    # the face just loses its slant


def eye_centers(mood, dx=0):
    # (left x, right x, y) of the two eye centres. dx slides both: the glance.
    color, w, hl, hr, r, lid, happy, cy, gap, mouth = MOODS[mood]
    return CENTER_X - gap // 2 - w // 2 + dx, CENTER_X + gap // 2 + w // 2 + dx, cy


def _eye(lcd, cx, cy, w, h, r, color, side, lid, happy):
    x = cx - w // 2
    y = cy - h // 2
    _round_rect(lcd, x, y, w, h, min(r, w // 2, h // 2), color)
    if lid:
        # A black triangle over the top of the eye. side is -1 for the left eye.
        x0, x1, y0 = x - 2, x + w + 2, y - 2
        inner = x1 if (lid > 0) == (side < 0) else x0
        outer = x0 if inner == x1 else x1
        _triangle(lcd, outer, y0, inner, y0, inner, y0 + abs(lid) * h // 100, BLACK)
    if happy:
        _ellipse(lcd, cx, cy + h * 68 // 100, w * 74 // 100, h * 42 // 100, BLACK)


def draw_eyes(lcd, mood, openness=100, dx=0):
    # Wipes the eye band and redraws both eyes. openness under 100 squashes
    # them (the blink); dx slides them sideways (the glance).
    color, w, hl, hr, r, lid, happy, cy, gap, mouth = MOODS[mood]
    tall = max(hl, hr)
    lcd.fillRect(CENTER_X - gap // 2 - w - 12, cy - tall // 2 - 3, 2 * w + gap + 24, tall + 6, BLACK)
    left, right, cy = eye_centers(mood, dx)
    _eye(lcd, left, cy, w, max(6, hl * openness // 100), r, color, -1, lid, happy)
    _eye(lcd, right, cy, w, max(6, hr * openness // 100), r, color, 1, lid, happy)


def _mouth(lcd, kind, color):
    if kind == "smile":         # a thick arc, made of small dots
        for degrees in range(40, 141, 5):
            a = math.radians(degrees)
            _circle(lcd, CENTER_X + int(26 * math.cos(a)), 58 + int(26 * math.sin(a)), 2, color)
    elif kind == "grin":        # the lower half of a disc, drawn as stacked strips
        radius = 22
        for dy in range(0, radius, 2):
            half = int(math.sqrt(radius * radius - dy * dy))
            lcd.fillRect(CENTER_X - half, 71 + dy, 2 * half, 2, color)
    elif kind == "dots":        # busy: three dots where the mouth goes
        for i in range(3):
            _circle(lcd, 106 + i * 14, 86, 3, color)


def _extras(lcd, mood, color):
    left, right, cy = eye_centers(mood)
    w = MOODS[mood][1]
    if mood == "rec":
        x, y = right + w // 2 + 11, cy - 16     # one drop of sweat: effort
        _triangle(lcd, x, y - 8, x + 5, y + 1, x - 5, y + 1, BLUE)
        _circle(lcd, x, y + 2, 5, BLUE)
        _circle(lcd, 16, 15, 5, color)          # the recording dot
        for y in (cy + 3, cy + 13):             # two effort marks
            lcd.fillRect(left - w // 2 - 17, y, 8, 3, color)
    elif mood == "problem":
        x, y = right + w // 2 + 12, cy - 20     # an exclamation mark
        _round_rect(lcd, x - 3, y - 12, 6, 16, 3, color)
        _circle(lcd, x, y + 11, 3, color)
    elif mood == "saved":
        for x in (40, 198):                     # two small sparkles, clear of the corner icons
            lcd.fillRect(x - 3, 33, 8, 2, color)
            lcd.fillRect(x, 30, 2, 8, color)
    elif mood == "sleepy":
        lcd.setTextColor(color, BLACK)
        set_font(lcd, False)
        lcd.drawString("z", 176, 34)
        lcd.drawString("z", 186, 22)


def draw_badge(lcd, count):
    # Top left: an up arrow and how many sets are waiting to be synced.
    # Amber, the Wi-Fi colour, because holding B is what clears it.
    if count <= 0:
        return
    _triangle(lcd, 12, 6, 6, 13, 18, 13, AMBER)
    lcd.fillRect(10, 13, 5, 5, AMBER)
    lcd.setTextColor(AMBER, BLACK)
    set_font(lcd, False)
    lcd.drawString(str(count), 23, 6)


def draw_bolt(lcd, x, y, color=GREEN):
    # A lightning bolt 7 wide and 13 tall, its top-left corner at (x, y): USB power is connected.
    _triangle(lcd, x + 5, y, x, y + 7, x + 4, y + 7, color)
    _triangle(lcd, x + 2, y + 5, x + 6, y + 5, x + 1, y + 12, color)


def draw(lcd, mood, title, hint=""):
    # The whole screen: face, one word, one small hint. Returns the mood's colour.
    color = MOODS[mood][0]
    lcd.fillScreen(BLACK)
    draw_eyes(lcd, mood)
    _extras(lcd, mood, color)
    _mouth(lcd, MOODS[mood][9], color)
    lcd.setTextColor(color, BLACK)
    set_font(lcd, True)
    lcd.drawString(title, TITLE_AT[0], TITLE_AT[1])
    if hint:
        lcd.setTextColor(GREY, BLACK)
        set_font(lcd, False)
        lcd.drawString(hint, HINT_RIGHT - lcd.textWidth(hint), HINT_Y)
    return color