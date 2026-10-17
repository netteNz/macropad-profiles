# Key LEDs: "rainbow" cycles by time, "static" shows each macro's color.
# Held keys show white in both modes. Updates are capped at ~50 Hz, and in
# static mode pixels.show() only runs when something actually changed.
from adafruit_ticks import ticks_diff
from rainbowio import colorwheel

_FRAME_MS = 20
_HUE_PER_S = 80  # roughly the per-loop speed of the original script
_WHITE = 0xFFFFFF


class Leds:
    def __init__(self, pixels):
        self._px = pixels
        self._colors = [0] * 12
        self._rainbow = False
        self._last = None
        self._held = set()
        self._dirty = True

    def set_profile(self, app):
        self._rainbow = app["leds"] == "rainbow"
        self._colors = [m[0] for m in app["macros"]]
        self._dirty = True

    def set_held(self, key, down):
        if down:
            self._held.add(key)
        else:
            self._held.discard(key)
        self._dirty = True

    def tick(self, now):
        if self._last is not None and ticks_diff(now, self._last) < _FRAME_MS:
            return
        if not (self._rainbow or self._dirty):
            return
        self._last = now
        self._dirty = False
        held = self._held
        if self._rainbow:
            hue = now * _HUE_PER_S // 1000
            for i in range(12):
                self._px[i] = _WHITE if i in held else colorwheel((hue + i * 21) & 255)
        else:
            for i in range(12):
                self._px[i] = _WHITE if i in held else self._colors[i]
        self._px.show()
