"""Render every mood of watch/faces.py to a PNG, without the watch.

    python watch/tests/render_faces.py            -> docs/presentation/watch_faces.png

A fake screen turns the watch's drawing calls into pixels (Pillow), so the
picture shows the same shapes the watch will draw, in DejaVu like the watch's
smooth fonts (exact letter shapes may differ slightly).
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).parents[2]
sys.path.insert(0, str(REPO / "watch"))
import faces  # noqa: E402

W, H, SCALE = 240, 135, 3


def rgb(color):
    return (color >> 16 & 255, color >> 8 & 255, color & 255)


def dejavu(px):
    import matplotlib
    return ImageFont.truetype(str(Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"), px)


class Fonts:
    DejaVu12 = 12
    DejaVu18 = 18


class Screen:
    """The drawing calls faces.py uses, on a Pillow image."""

    FONTS = Fonts

    def __init__(self):
        self.font = dejavu(12)
        self.image = Image.new("RGB", (W, H))
        self.d = ImageDraw.Draw(self.image)
        self.size = 2
        self.color = (255, 255, 255)

    def fillScreen(self, color):
        self.d.rectangle([0, 0, W, H], fill=rgb(color))

    def fillRect(self, x, y, w, h, color):
        if w > 0 and h > 0:
            self.d.rectangle([x, y, x + w - 1, y + h - 1], fill=rgb(color))

    def fillRoundRect(self, x, y, w, h, r, color):
        self.d.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=r, fill=rgb(color))

    def fillCircle(self, x, y, r, color):
        self.d.ellipse([x - r, y - r, x + r, y + r], fill=rgb(color))

    def fillEllipse(self, x, y, rx, ry, color):
        self.d.ellipse([x - rx, y - ry, x + rx, y + ry], fill=rgb(color))

    def fillTriangle(self, x0, y0, x1, y1, x2, y2, color):
        self.d.polygon([(x0, y0), (x1, y1), (x2, y2)], fill=rgb(color))

    def setTextColor(self, color, background=0):
        self.color = rgb(color)

    def setTextSize(self, size):
        self.size = size

    def setFont(self, px):
        self.font = dejavu(px)

    def textWidth(self, text):
        return int(self.font.getlength(text))

    def drawString(self, text, x, y):
        self.d.text((x, y - 2), text, fill=self.color, font=self.font)

    def width(self):
        return W


# (mood, word, hint, sets waiting to sync)
SCREENS = [
    ("ready", "SHOULDER", "A START  B NEXT", 0),
    ("rec", "REC", "SHOULDER  A STOP", 0),
    ("saving", "SAVING", "", 0),
    ("saved", "SAVED", "3 TO SYNC  HOLD B", 3),
    ("ready", "CURL", "A START  B NEXT", 3),
    ("sync", "SYNC", "SET 2 OF 3", 3),
    ("saved", "SYNCED", "REPS 8 8 6", 0),
    ("problem", "OOPS", "NO WI-FI  3 LEFT", 3),
    ("sleepy", "Z Z Z", "A WAKES", 0),
]


def battery(screen, percent=80):
    # The icon main.py draws at the top right.
    screen.fillRect(204, 8, 22, 9, faces.GREY)
    screen.fillRect(205, 9, 20, 7, faces.BLACK)
    screen.fillRect(226, 11, 2, 3, faces.GREY)
    screen.fillRect(206, 10, 18 * percent // 100, 5, faces.GREY)


def render(mood, title, hint, waiting=0):
    screen = Screen()
    faces.draw(screen, mood, title, hint)
    battery(screen)
    if mood != "rec":
        faces.draw_badge(screen, waiting)
    return screen.image


if __name__ == "__main__":
    pad = 8
    sheet = Image.new("RGB", (3 * (W + pad) + pad, 3 * (H + pad) + pad), (27, 29, 28))
    for i, (mood, title, hint, waiting) in enumerate(SCREENS):
        sheet.paste(render(mood, title, hint, waiting), (pad + (i % 3) * (W + pad), pad + (i // 3) * (H + pad)))
    sheet = sheet.resize((sheet.width * SCALE, sheet.height * SCALE), Image.NEAREST)
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / "docs" / "presentation" / "watch_faces.png"
    sheet.save(out)
    print(out)
