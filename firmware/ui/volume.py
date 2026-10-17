# Overlay: relative volume feedback for the system_volume knob.
# The pad can't read the real system level, so this shows direction and a
# short bar that grows with each detent and decays back to empty. No %.
import bitmaptools
import displayio
from adafruit_ticks import ticks_diff
from ui.keymap import text_label

_W, _H = 128, 24
_Y = 20  # vertical placement on the 64 px screen
_BAR_X0, _BAR_X1 = 46, _W - 4
_BAR_Y0, _BAR_Y1 = 8, 16
_BAR_MAX = _BAR_X1 - _BAR_X0
_PER_DETENT = 10  # px added per detent
_DECAY = 60  # px per second


class VolumeOverlay:
    kind = "volume"
    priority = 1

    def __init__(self):
        self.group = displayio.Group(y=_Y)
        self.dirty = True
        self._bmp = displayio.Bitmap(_W, _H, 2)
        pal = displayio.Palette(2)
        pal[0] = 0x000000
        pal[1] = 0xFFFFFF
        self.group.append(displayio.TileGrid(self._bmp, pixel_shader=pal))
        # 1 px frame, drawn once.
        bitmaptools.fill_region(self._bmp, 0, 0, _W, 1, 1)
        bitmaptools.fill_region(self._bmp, 0, _H - 1, _W, _H, 1)
        bitmaptools.fill_region(self._bmp, 0, 0, 1, _H, 1)
        bitmaptools.fill_region(self._bmp, _W - 1, 0, _W, _H, 1)
        self._label = text_label(6, "VOL +", x=4)
        self.group.append(self._label)
        self._dir = 1
        self._level = 0.0
        self._drawn = -1
        self._last = None

    def bump(self, delta, now):
        self.tick(now)  # apply decay accrued while the overlay was hidden
        d = 1 if delta > 0 else -1
        if d != self._dir:
            self._dir = d
            self._label.text = "VOL +" if d > 0 else "VOL -"
            self._level = 0.0
            self.dirty = True
        self._level = min(_BAR_MAX, self._level + _PER_DETENT * abs(delta))
        self._last = now
        self._draw()

    def tick(self, now):
        if self._last is None or self._level <= 0:
            return
        dt = ticks_diff(now, self._last)
        self._last = now
        self._level = max(0.0, self._level - _DECAY * dt / 1000)
        self._draw()

    def _draw(self):
        w = int(self._level)
        if w == self._drawn:
            return
        self._drawn = w
        bitmaptools.fill_region(self._bmp, _BAR_X0, _BAR_Y0, _BAR_X1, _BAR_Y1, 0)
        if w:
            bitmaptools.fill_region(self._bmp, _BAR_X0, _BAR_Y0, _BAR_X0 + w, _BAR_Y1, 1)
        self.dirty = True
