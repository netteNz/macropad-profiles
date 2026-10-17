# Display manager: one base view plus at most one overlay on top.
#
# A view is any object with `.group` (a displayio.Group), a `.dirty` flag the
# view sets when it mutates its labels/bitmaps, and an optional
# `tick(now)` for animation. Overlays also carry `.kind` and `.priority`.
# The manager owns the refresh cadence: auto_refresh is off, and refresh()
# runs only when something is dirty and at most every FRAME_MS.
import displayio
from adafruit_ticks import ticks_add, ticks_diff, ticks_ms

FRAME_MS = 33
OVERLAY_MS = 1200


class UI:
    def __init__(self, display):
        self._display = display
        display.auto_refresh = False
        self._root = displayio.Group()
        self._base_layer = displayio.Group()
        self._overlay_layer = displayio.Group()
        self._root.append(self._base_layer)
        self._root.append(self._overlay_layer)
        display.root_group = self._root
        self._bases = []  # [(name, view)] in toggle order
        self._base = None
        self.overlay = None
        self._until = None  # overlay expiry, None = sticky
        self._dirty = True
        self._last = ticks_ms()
        self.refreshes = 0
        self.refresh_ms_max = 0

    def add_base(self, name, view):
        self._bases.append((name, view))
        if self._base is None:
            self._show_base(view)

    def _show_base(self, view):
        if self._base is not None:
            self._base_layer.remove(self._base.group)
        self._base = view
        self._base_layer.append(view.group)
        self._dirty = True

    def toggle_base(self):
        """Cycle base views; returns False when there's only one."""
        if len(self._bases) < 2:
            return False
        names = [v for _, v in self._bases]
        self._show_base(names[(names.index(self._base) + 1) % len(names)])
        return True

    def show_overlay(self, view, now, timeout_ms=OVERLAY_MS):
        cur = self.overlay
        if cur is not None and cur is not view and cur.priority > view.priority:
            return False  # something more important is up
        if cur is not view:
            if cur is not None:
                self._overlay_layer.remove(cur.group)
            self._overlay_layer.append(view.group)
            self.overlay = view
            self._dirty = True
        self._until = None if timeout_ms is None else ticks_add(now, timeout_ms)
        return True

    def hide_overlay(self, view=None):
        if self.overlay is None or (view is not None and self.overlay is not view):
            return
        self._overlay_layer.remove(self.overlay.group)
        self.overlay = None
        self._until = None
        self._dirty = True

    def tick(self, now):
        if self._until is not None and ticks_diff(now, self._until) >= 0:
            self.hide_overlay()
        dirty = self._dirty
        for view in (self._base, self.overlay):
            if view is None:
                continue
            if hasattr(view, "tick"):
                view.tick(now)
            if view.dirty:
                dirty = True
        if not dirty or ticks_diff(now, self._last) < FRAME_MS:
            return
        self._last = now
        self._display.refresh(target_frames_per_second=None)
        took = ticks_diff(ticks_ms(), now)
        if took > self.refresh_ms_max:
            self.refresh_ms_max = took
        self.refreshes += 1
        self._dirty = False
        for view in (self._base, self.overlay):
            if view is not None:
                view.dirty = False
