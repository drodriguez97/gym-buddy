"""watch/faces.py: every mood draws, stays on the screen, and survives a
firmware that lacks the rounder shapes."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
import faces  # noqa: E402

W, H = 240, 135


class Recorder:
    """A screen that records the box each drawing call covers."""

    def __init__(self, missing=(), char_w=6):
        self.boxes = []
        self.texts = []
        self.size = 2
        self.missing = missing
        self.char_w = char_w                # pixels per character at text size 1

    def __getattr__(self, name):
        if name in self.missing or not name.startswith("fill"):
            raise AttributeError(name)
        return getattr(self, "_" + name)

    def _fillScreen(self, color):
        pass

    def _fillRect(self, x, y, w, h, color):
        self.boxes.append((x, y, x + w, y + h, color))

    def _fillRoundRect(self, x, y, w, h, r, color):
        self.boxes.append((x, y, x + w, y + h, color))

    def _fillCircle(self, x, y, r, color):
        self.boxes.append((x - r, y - r, x + r + 1, y + r + 1, color))

    def _fillEllipse(self, x, y, rx, ry, color):
        self.boxes.append((x - rx, y - ry, x + rx + 1, y + ry + 1, color))

    def _fillTriangle(self, x0, y0, x1, y1, x2, y2, color):
        self.boxes.append((min(x0, x1, x2), min(y0, y1, y2), max(x0, x1, x2) + 1, max(y0, y1, y2) + 1, color))

    def setTextColor(self, color, background=0):
        pass

    def setTextSize(self, size):
        self.size = size

    def textWidth(self, text):
        return self.char_w * self.size * len(text)

    def drawString(self, text, x, y):
        self.texts.append((text, x, y, x + self.textWidth(text), y + 8 * self.size))


MOOD_NAMES = sorted(faces.MOODS)


def test_the_six_moods_exist():
    assert MOOD_NAMES == ["problem", "ready", "rec", "saved", "saving", "sleepy", "sync"]


@pytest.mark.parametrize("mood", MOOD_NAMES)
def test_every_coloured_shape_and_text_stays_on_the_screen(mood):
    screen = Recorder()
    faces.draw(screen, mood, "SHOULDER", "SHOULDER  A STOP")
    for x0, y0, x1, y1, color in screen.boxes:
        if color != faces.BLACK:            # black wipes may run past an edge harmlessly
            assert 0 <= x0 and x1 <= W and 0 <= y0 and y1 <= H, (mood, x0, y0, x1, y1)
    for text, x0, y0, x1, y1 in screen.texts:
        assert 0 <= x0 and x1 <= W and 0 <= y0 and y1 <= H, (mood, text)


@pytest.mark.parametrize("mood", MOOD_NAMES)
def test_the_face_does_not_run_into_the_text(mood):
    screen = Recorder()
    faces.draw(screen, mood, "SAVED", "100.0HZ LATE 3")
    for x0, y0, x1, y1, color in screen.boxes:
        if color != faces.BLACK:
            assert y1 <= faces.HINT_Y - 2, (mood, y1)      # clear of the hint line and the title below it


@pytest.mark.parametrize("mood", MOOD_NAMES)
def test_a_firmware_without_round_shapes_still_draws_a_face(mood):
    screen = Recorder(missing=("fillRoundRect", "fillCircle", "fillEllipse", "fillTriangle"))
    faces.draw(screen, mood, "CURL", "A START  B NEXT")
    assert len([b for b in screen.boxes if b[4] != faces.BLACK]) >= 2      # at least two eyes


def test_a_blink_only_touches_the_eye_band():
    screen = Recorder()
    faces.draw_eyes(screen, "ready", openness=12)
    left, right, cy = faces.eye_centers("ready")
    for x0, y0, x1, y1, color in screen.boxes:
        assert y1 <= 70, y1                 # the smile starts below this


def test_a_glance_moves_both_eyes_the_same_way():
    assert faces.eye_centers("ready", dx=8)[:2] == tuple(x + 8 for x in faces.eye_centers("ready")[:2])


def test_the_title_and_hint_are_drawn_where_main_expects():
    screen = Recorder()
    faces.draw(screen, "ready", "CURL", "A START  B NEXT")
    assert ("CURL",) + faces.TITLE_AT == screen.texts[0][:3]
    assert screen.texts[1][3] == faces.HINT_RIGHT       # the hint is right-aligned


@pytest.mark.parametrize("char_w", [6, 7, 8])
def test_a_long_label_never_runs_into_the_hint_whatever_the_font(char_w):
    # On the real watch "SHOULDER" ran into the hint when they shared a line.
    screen = Recorder(char_w=char_w)
    faces.draw(screen, "ready", "SHOULDER", "A START  B NEXT")
    (_, tx0, ty0, tx1, ty1), (_, hx0, hy0, hx1, hy1) = screen.texts
    assert hy1 <= ty0                       # the hint's line ends above the title's line
    assert tx1 <= W and hx0 >= 0


def test_saving_looks_busy_but_is_not_the_sync_colour():
    assert faces.MOODS["saving"][0] == faces.GREEN and faces.MOODS["sync"][0] == faces.AMBER
    assert faces.MOODS["saving"][1:] == faces.MOODS["sync"][1:]


def test_the_charging_bolt_is_two_green_triangles_inside_its_box():
    screen = Recorder()
    faces.draw_bolt(screen, 193, 6)
    assert len(screen.boxes) == 2 and all(box[4] == faces.GREEN for box in screen.boxes)
    assert all(193 <= x0 and x1 <= 193 + 7 and 6 <= y0 and y1 <= 6 + 13 for x0, y0, x1, y1, _ in screen.boxes)
    assert screen.boxes[0][3] > screen.boxes[1][1]          # the two halves overlap: one bolt, not two marks


def test_the_bolt_is_left_out_on_a_firmware_without_triangles():
    screen = Recorder(missing=("fillTriangle",))
    faces.draw_bolt(screen, 193, 6)
    assert screen.boxes == []
