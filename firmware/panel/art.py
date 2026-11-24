# Reactive scene for the second panel (pad-only, no host needed).
#
# Yellow band (rows 0-15): the profile name. Blue area (rows 16-63):
# - key ripples: a ring expands from where the key sits on the 3x4 grid
# - knob wave: a sine that scrolls in the turn direction and fades out
# - idle drift: a few stars sliding left, always there underneath
# Integer math with precomputed tables only, so frames don't allocate floats
# (GC pauses stall the loop). Paced off ticks: ~30 fps while something moves,
# ~15 fps when only the stars drift, and never faster than the panel can
# take whole frames.
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
WAVE_PX_PER_S = 60  # scroll speed
WAVE_DECAY_MS = 600  # proportional fade time constant
MAX_DT = 100  # cap on catch-up after a long stall
BLUE_PAGES = 0xFC  # pages 2-7
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
        self._amp16 = 0  # wave amplitude in 1/16 px
        self._dir = 1
        self._phase16 = 0  # wave scroll in 1/16 px
        r = self._rng
        # x in 1/16 px, y, speed in 1/16 px per FRAME_MS
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
            self._amp16 = min(WAVE_MAX * 16, self._amp16 + WAVE_PER_DETENT * 16 * abs(delta))

    @property
    def amp(self):
        """Wave amplitude in whole pixels."""
        return self._amp16 >> 4

    def busy(self):
        return bool(self.ripples) or self._amp16 > 0

    def tick(self, now):
        """Render a frame if one is due. Returns True when it drew.

        A new frame waits until the previous one has fully reached the panel
        (no blue page still dirty), so the panel never shows strips from two
        different frames, e.g. while a main-OLED refresh stalls the loop.
        Motion is scaled by elapsed time, so a slower frame rate doesn't
        slow the animation down, it only makes it coarser."""
        c = self.c
        if c.dirty & BLUE_PAGES:
            return False
        frame = FRAME_MS if self.busy() else IDLE_FRAME_MS
        if self._last is None:
            dt = FRAME_MS
        else:
            dt = ticks_diff(now, self._last)
            if dt < frame:
                return False
            dt = min(dt, MAX_DT)
        self._last = now
        c.clear(TOP >> 3, H >> 3)
        buf = c.buf

        # Stars: speed is 1/16 px per FRAME_MS
        for s in self.stars:
            s[0] -= s[2] * dt // FRAME_MS
            if s[0] < 0:
                s[0] += W * 16
                s[1] = self._rng.randrange(TOP, H)
            y = s[1]
            buf[(y >> 3) * W + (s[0] >> 4)] |= 1 << (y & 7)

        # Knob wave: a continuous line, 64-px wavelength
        if self._amp16 > 0:
            self._phase16 = (self._phase16 + self._dir * dt * WAVE_PX_PER_S * 16 // 1000) & 1023
            amp, ph, mid = self._amp16 >> 4, (self._phase16 >> 4) & 63, (TOP + H) // 2
            prev = None
            for x in range(W):
                y = mid + ((amp * SIN64[(x - ph) & 63]) >> 7)
                if prev is None or prev == y:
                    lo = hi = y
                elif prev < y:  # join to the previous column, no gaps
                    lo, hi = prev + 1, y
                else:
                    lo, hi = y, prev - 1
                for yy in range(max(lo, TOP), min(hi, H - 1) + 1):
                    buf[(yy >> 3) * W + x] |= 1 << (yy & 7)
                prev = y
            # Fade: proportional plus a small constant, so it always ends (~1.2 s from max)
            self._amp16 = max(0, self._amp16 - self._amp16 * dt // WAVE_DECAY_MS - dt // 8)

        # Ripples (oldest first, so expired ones sit at the front; pop in place
        # rather than rebuilding the list every frame)
        rips = self.ripples
        while rips and ticks_diff(now, rips[0][2]) // RIPPLE_MS_PER_PX > RIPPLE_MAX_R:
            rips.pop(0)
        for rp in rips:
            r = ticks_diff(now, rp[2]) // RIPPLE_MS_PER_PX
            cx, cy = rp[0], rp[1]
            for dx, dy in RING:
                x = cx + ((r * dx) >> 7)
                y = cy + ((r * dy) >> 7)
                if 0 <= x < W and TOP <= y < H:
                    buf[(y >> 3) * W + x] |= 1 << (y & 7)
        return True
