# Fake PC-helper data so the HUD's clock and weather can be checked on the
# board before the helper exists. code.py runs it only when DEMO is True.
# It sets a fixed clock once, then cycles through every weather icon (day
# and night, with the moon stepping through its phases).
from adafruit_ticks import ticks_diff

from panel.spotify import COS

STEP_MS = 3000
# (WMO code, temp, feels, hi, lo, rain %, is_day)
SCENES = (
    (0, 78, 83, 84, 72, 0, 1),
    (2, 76, 79, 84, 72, 10, 1),
    (3, 74, 74, 80, 70, 20, 1),
    (45, 66, 66, 75, 61, 5, 1),
    (61, 71, 73, 77, 69, 60, 1),
    (65, 70, 72, 76, 68, 90, 1),
    (95, 73, 79, 82, 70, 80, 1),
    (73, 30, 22, 33, 25, 70, 1),
    (0, 64, 64, 84, 72, 0, 0),
    (1, 63, 63, 84, 72, 0, 0),
)


class Demo:
    def __init__(self, host, now):
        self.host = host
        host.set_time(2026, 11, 25, 20, 59, 45, 2, now)  # Wed, 15 s to 9 PM
        self._at = None
        self._i = -1
        self._cycle = 0

    def tick(self, now):
        if self._at is not None and ticks_diff(now, self._at) < STEP_MS:
            return
        self._at = now
        self._i = (self._i + 1) % len(SCENES)
        code, temp, feels, hi, lo, rain, is_day = SCENES[self._i]
        self.host.set_weather(code, temp, feels, hi, lo, rain, is_day, now)
        if not is_day:
            self._cycle = (self._cycle + 37) & 255  # a different phase each time
        lit = 50 - 50 * COS[self._cycle] // 127
        self.host.set_moon(self._cycle, lit, 6 * 60 + 58, 17 * 60 + 41)

