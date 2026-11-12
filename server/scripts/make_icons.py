"""Draw the app icon (the buddy's face) as PNG files for phone home screens.

    ..\\.venv\\Scripts\\python.exe scripts\\make_icons.py      (from server\\)

Writes app/static/icon-180.png (iPhone), icon-192.png and icon-512.png
(Android). The files are kept in Git, so this only needs running again if the
face changes. Needs Pillow, which is a development tool, not something the
server uses.

The face is the same drawing as the logo in index.html, on a 28-unit grid:
two rounded eyes and a small smile, green on black. The background fills the
whole square because phones cut their own corner shape out of it.
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parents[1] / "app" / "static"
SIZES = (180, 192, 512)
GREEN = (124, 255, 107)
OVERSAMPLE = 4                  # draw big, then shrink: that is what smooths the edges


def smile_points(steps=40):
    # The logo's smile: a curve from (11, 20.5) to (17, 20.5) that dips to about y = 21.6.
    (x0, y0), (cx, cy), (x1, y1) = (11, 20.5), (14, 22.7), (17, 20.5)
    for i in range(steps + 1):
        t = i / steps
        yield ((1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t ** 2 * x1,
               (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t ** 2 * y1)


def draw(size):
    big = size * OVERSAMPLE
    unit = big / 28
    image = Image.new("RGB", (big, big), (0, 0, 0))
    pen = ImageDraw.Draw(image)
    for x in (5.5, 15.5):       # the eyes
        pen.rounded_rectangle([x * unit, 8 * unit, (x + 7) * unit, 17 * unit], radius=3 * unit, fill=GREEN)
    radius = 0.8 * unit         # the smile: a line 1.6 units thick with round ends
    for x, y in smile_points():
        pen.ellipse([x * unit - radius, y * unit - radius, x * unit + radius, y * unit + radius], fill=GREEN)
    return image.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    for size in SIZES:
        path = OUT / ("icon-%d.png" % size)
        draw(size).save(path, optimize=True)
        print(path.name, path.stat().st_size, "bytes")
