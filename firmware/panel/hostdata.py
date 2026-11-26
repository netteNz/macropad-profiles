# What the PC helper tells the pad: local time, weather, moon and sun.
# Pure logic. Until the helper exists (step 5) it's empty, or fed by
# panel/demo.py. Times are kept against ticks_ms, so the clock keeps running
# between updates; the helper resyncs it every few minutes.
from adafruit_ticks import ticks_diff

DAY_MS = 86400000
WX_STALE_MS = 30 * 60000  # weather older than this shows as missing
_MDAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
DAYS = ("MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN")
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN",
          "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


def _mdays(y, mo):
    if mo == 2 and y % 4 == 0 and (y % 100 != 0 or y % 400 == 0):
        return 29
    return _MDAYS[mo - 1]


class HostData:
    def __init__(self):
        self._date = None  # (y, mo, d, wday) at the anchor, wday 0 = Monday
        self._sod = 0  # ms since midnight at the anchor
        self._t_at = 0
        # weather: code, temp, feels, hi, lo, rain %, is_day
        self.wx = None
        self._wx_at = 0
        # moon: cycle 0..255 (0 new, 128 full), lit %, rise / set in minutes
        self.moon = None

    # -- updates (from the link, or the demo) --
    def set_time(self, y, mo, d, h, mi, s, wday, now):
        self._date = (y, mo, d, wday)
        self._sod = ((h * 60 + mi) * 60 + s) * 1000
        self._t_at = now

    def set_weather(self, code, temp, feels, hi, lo, rain, is_day, now):
        self.wx = (code, temp, feels, hi, lo, rain, is_day)
        self._wx_at = now

    def set_moon(self, cycle, lit, rise, sset):
        self.moon = (cycle & 255, lit, rise, sset)

    # -- reads --
    def has_time(self):
        return self._date is not None

    def local(self, now):
        """(y, mo, d, wday, h, mi, s), or None before the first sync."""
        if self._date is None:
            return None
        ms = self._sod + ticks_diff(now, self._t_at)
        days, ms = divmod(ms, DAY_MS)
        y, mo, d, wday = self._date
        for _ in range(days):  # rarely more than one
            wday = (wday + 1) % 7
            d += 1
            if d > _mdays(y, mo):
                d = 1
                mo += 1
                if mo > 12:
                    mo = 1
                    y += 1
        s = ms // 1000
        return y, mo, d, wday, s // 3600, s // 60 % 60, s % 60

    def weather(self, now):
        if self.wx is None or ticks_diff(now, self._wx_at) >= WX_STALE_MS:
            return None
        return self.wx


def hhmm12(minutes):
    """'6:58' from minutes since midnight (no am/pm: context makes it clear)."""
    h = minutes // 60 % 24
    return "%d:%02d" % (h % 12 or 12, minutes % 60)
