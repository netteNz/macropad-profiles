# Non-blocking runner for Adafruit Hotkeys-style action sequences.
#
# Sequence items:
#   int >= 0   press keycode          int < 0  release keycode
#   float      delay (seconds)        str      type it, one char per tick
#   list       consumer control codes (floats inside are delays)
# A whole action may also be {"host": cmd, "fallback": seq}; until the host
# bridge exists the fallback always runs.
#
# Each physical key gets its own slot, so a delay in one key's macro never
# stalls another. Keys a sequence leaves pressed stay held until the physical
# key is released (Hotkeys semantics); "tap" slots (knob detents, encoder
# press) release as soon as their sequence ends.
from adafruit_ticks import ticks_add, ticks_diff

_PRESS = 0
_RELEASE = 1
_DELAY = 2
_TYPE = 3
_CONSUMER = 4

KNOB = 12  # slot ids beyond the 12 keys
PRESS = 13
_QUEUE_MAX = 8


def _compile(action, host_alive):
    if isinstance(action, dict):
        # Phase 2 sends action["host"] when host_alive() is true.
        action = action.get("fallback", [])
    if not isinstance(action, list):
        action = [action]
    steps = []
    for item in action:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            steps.append((_PRESS, item) if item >= 0 else (_RELEASE, -item))
        elif isinstance(item, float):
            steps.append((_DELAY, int(item * 1000)))
        elif isinstance(item, str):
            if item:  # "" types nothing; a _TYPE step with no chars would crash
                steps.append((_TYPE, item))
        elif isinstance(item, list):
            for code in item:
                if isinstance(code, float):
                    steps.append((_DELAY, int(code * 1000)))
                elif isinstance(code, int):
                    steps.append((_CONSUMER, code))
    return steps


class _Slot:
    def __init__(self, steps, tap):
        self.steps = steps
        self.i = 0
        self.resume = None  # ticks_ms when a delay ends
        self.chars = None  # remaining text of a _TYPE step
        self.held = []  # keycodes this slot pressed and still holds
        self.released = tap  # physical key already up (or never held)
        self.queue = []


class Runner:
    def __init__(self, keyboard, consumer, layout, host_alive=lambda: False):
        self._kbd = keyboard
        self._cc = consumer
        self._layout = layout
        self._host_alive = host_alive
        self._slots = {}
        # The consumer report holds one code at a time, so the newest press owns
        # it; an older slot finishing must not release someone else's code.
        self._cc_owner = None

    def busy(self):
        return bool(self._slots)

    def start(self, slot, action, tap=False, now=None):
        """Run `action` in `slot`, cutting short whatever was running there.

        With `now`, the first steps run immediately, so a second press of the
        same key drained from the same event batch can't replace an action
        that hasn't sent anything yet.
        """
        old = self._slots.pop(slot, None)
        if old:
            self._let_go(old)
        s = _Slot(_compile(action, self._host_alive), tap)
        self._slots[slot] = s
        if now is not None:
            self._advance(slot, s, now)

    def queue(self, slot, action, now=None):
        """Append a tap action behind whatever `slot` is running (knob detents)."""
        s = self._slots.get(slot)
        if s is None:
            self.start(slot, action, tap=True, now=now)
        elif len(s.queue) < _QUEUE_MAX:
            s.queue.append(action)

    def release(self, slot):
        """The physical key for `slot` went up."""
        s = self._slots.get(slot)
        if s is None:
            return
        s.released = True
        # A trailing delay still counts as running: finish when it expires.
        if s.i >= len(s.steps) and s.chars is None and s.resume is None:
            self._finish(slot, s)

    def release_all(self):
        for s in self._slots.values():
            self._let_go(s)
        self._slots.clear()
        self._kbd.release_all()
        self._cc.release()
        self._cc_owner = None

    def consumer_send(self, code):
        """One-shot consumer tap outside any slot (knob volume). It empties the
        report, so whichever slot held a consumer code no longer owns it."""
        self._cc.send(code)
        self._cc_owner = None

    def tick(self, now):
        for slot in list(self._slots):
            self._advance(slot, self._slots[slot], now)

    def _advance(self, slot, s, now):
        if s.resume is not None:
            if ticks_diff(now, s.resume) < 0:
                return
            s.resume = None
        if s.chars is not None:
            self._type_one(s)
            return
        while s.i < len(s.steps):
            kind, arg = s.steps[s.i]
            s.i += 1
            if kind == _PRESS:
                self._kbd.press(arg)
                if arg not in s.held:
                    s.held.append(arg)
            elif kind == _RELEASE:
                if arg in s.held:
                    s.held.remove(arg)
                if not self._held_elsewhere(arg, s):
                    self._kbd.release(arg)
            elif kind == _CONSUMER:
                self._cc.release()  # so a repeated code registers as a new press
                self._cc.press(arg)
                self._cc_owner = s
            elif kind == _DELAY:
                s.resume = ticks_add(now, arg)
                return
            elif kind == _TYPE:
                s.chars = arg
                self._type_one(s)
                return
        if s.released:
            self._finish(slot, s)

    def _type_one(self, s):
        # layout.write() would block for the whole string and release_all(),
        # dropping modifiers the sequence is holding. One char per tick instead.
        ch, s.chars = s.chars[0], s.chars[1:] or None
        try:
            codes = self._layout.keycodes(ch)
        except ValueError:
            print("actions: can't type %r" % ch)
            return
        self._kbd.press(*codes)
        up = [c for c in codes if c not in s.held and not self._held_elsewhere(c, s)]
        if up:
            self._kbd.release(*up)

    def _finish(self, slot, s):
        self._let_go(s)
        if s.queue:
            nxt = _Slot(_compile(s.queue.pop(0), self._host_alive), True)
            nxt.queue = s.queue
            self._slots[slot] = nxt
        else:
            del self._slots[slot]

    def _held_elsewhere(self, code, s):
        # The keyboard report doesn't know who pressed what: a key two slots
        # hold (e.g. Control) stays down until the last of them lets go.
        for o in self._slots.values():
            if o is not s and code in o.held:
                return True
        return False

    def _let_go(self, s):
        if s.held:
            up = [c for c in s.held if not self._held_elsewhere(c, s)]
            if up:
                self._kbd.release(*up)
            s.held = []
        if self._cc_owner is s:
            self._cc.release()
            self._cc_owner = None
