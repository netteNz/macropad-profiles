# Spotify scenes for the extra panels.
#
# RecordScene: a vinyl record that spins while playing (Play/Pause stops and
# starts it, Next/Prev spin it up), a tonearm that swings on while playing and
# parks on pause, and a volume arc around the rim while the knob turns. With a
# known track length (from the host, later) the tonearm follows the song from
# the outer groove to the label, so the arm is the scrubber.
#
# The disc is all rings, so it looks the same at any angle: it's drawn once
# into a static copy, and each frame only slice-copies it back and draws the
# moving bits (a notch in the label, a dark stripe across the grooves, the
# arm and the arc). Integer tables only; same pacing rules as panel/art.py.
import math

from adafruit_ticks import ticks_diff

from panel.art import BLUE_PAGES, FRAME_MS, IDLE_FRAME_MS, MAX_DT, TOP
from panel.canvas import PAGES, Canvas, W, text_width

# 256-step circle, scaled by 127. Index 0 = right, 64 = down (y grows down).
COS = [int(127 * math.cos(i * 2 * math.pi / 256)) for i in range(256)]
SIN = [int(127 * math.sin(i * 2 * math.pi / 256)) for i in range(256)]

CX, CY = 44, 40  # disc centre
RIM = 21
GROOVES = (18, 15, 12)
LABEL = 7
ARC_R = 23  # volume arc, just outside the rim
PX, PY = 90, 18  # tonearm pivot
ARM_LEN = 44
# Arm angles in 1/16 table steps: parked off the disc, on the outer groove,
# and at the end of the song by the label.
ARM_PARK = 60 * 16
ARM_OUTER = 94 * 16
ARM_INNER = 102 * 16
ARM_EASE_MS = 250

SPIN = 142  # table steps per second: 33 1/3 rpm
SPIN_UP = 4  # speed multiple right after Next/Prev
SPIN_UP_MS = 400
SPIN_EASE_MS = 200

VOL_STEP = 2  # Windows volume points per detent (as ui/volume.py)
VOL_FULL = 50  # net change that draws a full circle
VOL_SHOW_MS = 1200  # as ui.manager.OVERLAY_MS
TITLE_CHARS = 18  # leaves room for the play/pause icon
ICON_X = 116
BLUE0 = (TOP >> 3) * W  # first byte of the blue area

_static = None


def _disc():
    """Disc, pivot and arm rest, drawn once (floats are fine here)."""
    global _static
    if _static is None:
        c = Canvas()
        for r in (RIM,) + GROOVES:
            for i in range(256):
                a = i * 2 * math.pi / 256
                c.pixel(CX + round(r * math.cos(a)), CY + round(r * math.sin(a)))
        for dy in range(-LABEL, LABEL + 1):
            for dx in range(-LABEL, LABEL + 1):
                if dx * dx + dy * dy <= LABEL * LABEL + 2:
                    c.pixel(CX + dx, CY + dy)
        c.pixel(CX, CY, False)  # spindle hole
        for i in range(0, 256, 8):
            a = i * 2 * math.pi / 256
            c.pixel(PX + round(2 * math.cos(a)), PY + round(2 * math.sin(a)))
        _static = bytes(c.buf[BLUE0:])
    return _static


def arm_tip(a16):
    """Tonearm tip for an angle in 1/16 table steps (linear between steps)."""
    i = (a16 >> 4) & 255
    j = (i + 1) & 255
    f = a16 & 15
    x = PX + (ARM_LEN * (COS[i] * (16 - f) + COS[j] * f) >> 11)
    y = PY + (ARM_LEN * (SIN[i] * (16 - f) + SIN[j] * f) >> 11)
    return x, y


def _plot(buf, x, y, on=True):
    if 0 <= x < W and TOP <= y < PAGES * 8:
        if on:
            buf[(y >> 3) * W + x] |= 1 << (y & 7)
        else:
            buf[(y >> 3) * W + x] &= ~(1 << (y & 7)) & 0xFF


def _line(buf, x0, y0, x1, y1):
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    while True:
        _plot(buf, x0, y0)
        if x0 == x1 and y0 == y1:
            return
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _ease(cur, target, dt, ms, snap):
    if abs(target - cur) <= snap or dt >= ms:
        return target
    d = target - cur  # move a dt/ms share of the gap, rounded up
    step = (abs(d) * dt + ms - 1) // ms
    return cur + step if d > 0 else cur - step


class RecordScene:
    def __init__(self, canvas, transport):
        self.c = canvas
        self.t = transport
        self._static = _disc()
        self._last = None
        self.rot16 = 0  # disc angle, 1/16 table steps
        self.speed = 0  # 1/16 table steps per second
        self.arm = ARM_PARK
        self._track_n = transport.track_n
        self._boost_at = None
        self.vol = 0  # net volume change of the current turn
        self._vol_at = None
        self.title = None
        self._icon = None

    # -- events (same interface as art.Scene) --
    def set_title(self, name):
        if name == self.title:
            return
        self.title = name
        name = name[:TITLE_CHARS]
        c = self.c
        c.clear(0, TOP >> 3)
        c.text((ICON_X - text_width(name)) // 2, 4, name)
        self._icon = None  # redraw it too

    def key(self, k, now):
        pass

    def knob(self, delta, now=0):
        if not delta:
            return
        if self._vol_at is None or ticks_diff(now, self._vol_at) >= VOL_SHOW_MS:
            self.vol = 0
        self._vol_at = now
        self.vol += delta * VOL_STEP

    # -- state --
    def _arm_target(self, now):
        t = self.t
        if not t.playing:
            return ARM_PARK
        p = t.progress(now, 1024)
        if p is None:
            return ARM_OUTER
        return ARM_OUTER + (ARM_INNER - ARM_OUTER) * p // 1024

    def _vol_shown(self, now):
        return self._vol_at is not None and ticks_diff(now, self._vol_at) < VOL_SHOW_MS

    def busy(self, now):
        return bool(self.speed) or self.arm != self._arm_target(now) or self._vol_shown(now)

    def _draw_icon(self):
        playing = self.t.playing
        if playing == self._icon:
            return
        self._icon = playing
        c = self.c
        c.fill_rect(ICON_X, 0, W - ICON_X, 16, False)
        if playing:
            for i in range(5):
                c.vline(ICON_X + 3 + i, 4 + i, 9 - 2 * i)
        else:
            c.fill_rect(ICON_X + 3, 4, 2, 9)
            c.fill_rect(ICON_X + 7, 4, 2, 9)

    def tick(self, now):
        """Render a frame if one is due. Returns True when it drew."""
        c = self.c
        self._draw_icon()  # yellow band, only when the state changed
        if c.dirty & BLUE_PAGES:
            return False
        frame = FRAME_MS if self.busy(now) else IDLE_FRAME_MS
        if self._last is None:
            dt = FRAME_MS
        else:
            dt = ticks_diff(now, self._last)
            if dt < frame:
                return False
            dt = min(dt, MAX_DT)
        self._last = now
        t = self.t

        # Spin: ease toward 33 1/3 rpm (x4 right after a track change) or 0.
        if t.track_n != self._track_n:
            self._track_n = t.track_n
            self._boost_at = now
        target = SPIN * 16 if t.playing else 0
        if self._boost_at is not None:
            if ticks_diff(now, self._boost_at) < SPIN_UP_MS:
                target = SPIN * 16 * SPIN_UP
            else:
                self._boost_at = None
        self.speed = _ease(self.speed, target, dt, SPIN_EASE_MS, 16)
        self.rot16 = (self.rot16 + self.speed * dt // 1000) & 4095
        self.arm = _ease(self.arm, self._arm_target(now), dt, ARM_EASE_MS, 8)

        buf = c.buf
        buf[BLUE0:] = self._static
        c.dirty |= BLUE_PAGES

        # Moving marks: a notch in the label and a dark stripe across the
        # grooves on the opposite side.
        r = self.rot16 >> 4
        cs, sn = COS[r], SIN[r]
        for d in range(2, LABEL):
            _plot(buf, CX + (d * cs >> 7), CY + (d * sn >> 7), False)
        for d in range(GROOVES[-1] - 1, RIM + 1):
            _plot(buf, CX - (d * cs >> 7), CY - (d * sn >> 7), False)

        # Tonearm with a small head at the tip.
        x, y = arm_tip(self.arm)
        _line(buf, PX, PY, x, y)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                _plot(buf, x + dx, y + dy)

        # Volume arc from 12 o'clock: clockwise up, counter-clockwise down.
        if self._vol_shown(now) and self.vol:
            n = min(abs(self.vol), VOL_FULL) * 256 // VOL_FULL
            sign = 1 if self.vol > 0 else -1
            for j in range(0, n, 2):
                i = (192 + sign * j) & 255
                _plot(buf, CX + (ARC_R * COS[i] >> 7), CY + (ARC_R * SIN[i] >> 7))
        return True
