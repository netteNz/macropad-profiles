# Reactive scene for the second panel (pad-only, no host needed).
#
# Yellow band (rows 0-15): the profile name. Blue area (rows 16-63):
# - key ripples: a ring expands from where the key sits on the 3x4 grid
# - knob wave: a sine that scrolls in the turn direction and fades out
# - idle drift: a few stars sliding left, always there underneath
# Integer math with precomputed tables only, so frames don't allocate floats
# (GC pauses stall the loop). Paced off ticks: ~30 fps while something moves,
# ~15 fps when only the stars drift.
import math
import random

from adafruit_ticks import ticks_diff

from panel.canvas import H, W, text_width

TOP = 16  # first blue row
FRAME_MS = 33
IDLE_FRAME_MS = 66
MAX_RIPPLES = 6
RIPPLE_MS_PER_PX = 15  # ring grows ~66 px/s
RIPPLE_MAX_R = 40
RING_PTS = 24
WAVE_MAX = 22  # amplitude cap in px
WAVE_PER_DETENT = 6
STARS = 10
TITLE_CHARS = 21

# 64-entry sine and RING_PTS-entry cos/sin, scaled by 127.
SIN64 = [int(127 * math.sin(i * 2 * math.pi / 64)) for i in range(64)]
RING = [(int(127 * math.cos(i * 2 * math.pi / RING_PTS)),
         int(127 * math.sin(i * 2 * math.pi / RING_PTS))) for i in range(RING_PTS)]


def key_center(k):
    """Screen point for key k (0 = top-left, 3 columns x 4 rows)."""
    return 22 + (k % 3) * 42, TOP + 6 + (k // 3) * 12


class Scene:
    def __init__(self, canvas, rng=None):
        self.c = canvas
        self._rng = rng or random  # CircuitPython's random has no Random class
        self._last = None
        self.ripples = []  # [cx, cy, t0]
        self.amp = 0
        self._dir = 1
        self._phase = 0
        r = self._rng
        # x in 1/16 px, y, speed in 1/16 px per frame
        self.stars = [[r.randrange(W * 16), r.randrange(TOP, H), r.randrange(4, 20)]
                      for _ in range(STARS)]
        self.title = None

    def set_title(self, name):
        if name == self.title:
            return
        self.title = name
        name = name[:TITLE_CHARS]
        self.c.clear(0, 2)
        self.c.text((W - text_width(name)) // 2, 4, name)

    def key(self, k, now):
        if len(self.ripples) >= MAX_RIPPLES:
            self.ripples.pop(0)  # oldest makes room
        cx, cy = key_center(k)
        self.ripples.append([cx, cy, now])

    def knob(self, delta):
        if delta:
            self._dir = 1 if delta > 0 else -1
            self.amp = min(WAVE_MAX, self.amp + WAVE_PER_DETENT * abs(delta))

    def busy(self):
        return bool(self.ripples) or self.amp > 0

    def tick(self, now):
        """Render a frame if one is due. Returns True when it drew."""
        frame = FRAME_MS if self.busy() else IDLE_FRAME_MS
        if self._last is not None and ticks_diff(now, self._last) < frame:
            return False
        self._last = now
        c = self.c
        c.clear(TOP >> 3, H >> 3)
        buf = c.buf

        # Stars
        for s in self.stars:
            s[0] -= s[2]
            if s[0] < 0:
                s[0] += W * 16
                s[1] = self._rng.randrange(TOP, H)
            y = s[1]
            buf[(y >> 3) * W + (s[0] >> 4)] |= 1 << (y & 7)

        # Knob wave: 2-px steps, 64-px wavelength
        if self.amp > 0:
            self._phase = (self._phase + 2 * self._dir) & 63
            amp, ph, mid = self.amp, self._phase, (TOP + H) // 2
            for x in range(0, W, 2):
                y = mid + ((amp * SIN64[(x - ph) & 63]) >> 7)
                if TOP <= y < H:
                    buf[(y >> 3) * W + x] |= 1 << (y & 7)
            self.amp -= max(1, amp >> 4)

        # Ripples
        live = []
        for rp in self.ripples:
            r = ticks_diff(now, rp[2]) // RIPPLE_MS_PER_PX
            if r > RIPPLE_MAX_R:
                continue
            live.append(rp)
            cx, cy = rp[0], rp[1]
            for dx, dy in RING:
                x = cx + ((r * dx) >> 7)
                y = cy + ((r * dy) >> 7)
                if 0 <= x < W and TOP <= y < H:
                    buf[(y >> 3) * W + x] |= 1 << (y & 7)
        self.ripples = live
        return True
