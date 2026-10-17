# Overlay: system volume feedback in the title row, so key labels stay visible.
# The pad can't read the real level, but Windows moves 2 points per volume
# key, so the net change since the turn started is exact (except when
# Windows clamps at 0/100). Phase 2 replaces this with Spotify's exact %.
import displayio
from adafruit_ticks import ticks_diff
from ui.keymap import ROW_H, text_label
from ui.manager import OVERLAY_MS

STEP = 2  # Windows volume points per VOLUME_INCREMENT/DECREMENT


class VolumeOverlay:
    kind = "volume"
    priority = 1

    def __init__(self):
        self.group = displayio.Group()
        self.dirty = True
        bg = displayio.Bitmap(128, ROW_H, 1)
        pal = displayio.Palette(1)
        pal[0] = 0x000000
        self.group.append(displayio.TileGrid(bg, pixel_shader=pal))  # hides the title
        self._label = text_label(0)
        self.group.append(self._label)
        self._total = 0
        self._last = None

    def bump(self, delta, now):
        # A new turn starts once the previous overlay would have timed out.
        if self._last is None or ticks_diff(now, self._last) >= OVERLAY_MS:
            self._total = 0
        self._last = now
        self._total += delta * STEP
        self._label.text = "Vol %+d       %s" % (self._total, ">>>" if delta > 0 else "<<<")
        self.dirty = True
