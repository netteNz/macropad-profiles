# Encoder gesture state machine. Pure logic: fed switch edges (with keypad
# timestamps) and detent deltas, returns gesture events for code.py to route.
#
#   turn while up              -> ("turn", n)
#   first turn while held      -> ("picker_open",) then ("picker_move", n)
#   further turns while held   -> ("picker_move", n)
#   release after turning      -> ("picker_commit",)
#   release, no turn, < 600 ms -> ("press",)
#   release, no turn, >= 600ms -> ("long_press",)
#
# Long-press fires on release rather than at the threshold, so holding past
# 600 ms and then turning still only opens the picker.
from adafruit_ticks import ticks_diff

LONG_PRESS_MS = 600


class Encoder:
    def __init__(self):
        self.held = False
        self.turned = False
        self._down_at = 0

    def button(self, pressed, timestamp):
        if pressed:
            self.held = True
            self.turned = False
            self._down_at = timestamp
            return None
        if not self.held:
            return None
        self.held = False
        if self.turned:
            return ("picker_commit",)
        if ticks_diff(timestamp, self._down_at) >= LONG_PRESS_MS:
            return ("long_press",)
        return ("press",)

    def rotate(self, delta):
        """Returns a list of events for a detent delta (may be empty)."""
        if not delta:
            return []
        if not self.held:
            return [("turn", delta)]
        if self.turned:
            return [("picker_move", delta)]
        self.turned = True
        return [("picker_open",), ("picker_move", delta)]
