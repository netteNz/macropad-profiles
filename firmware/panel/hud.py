# HUD for the second Spotify panel, modelled on the oled-bonnet daemon:
# a few full-screen views that rotate on a timer and slide sideways between
# each other, and key/knob actions that pull the status view in for a while
# (the bonnet's "alert" preemption).
#
# Rendering: each view draws a whole 128x64 frame into a scratch buffer.
# Outside a slide, only pages that differ from what's on the panel are
# copied over and marked dirty, so a view can re-render freely and an
# unchanged frame costs no I2C. A slide copies column slices per page (the
# panel's page layout makes a sideways slide pure byte copying) and its last
# frame is byte-identical to the incoming view.
from adafruit_ticks import ticks_diff, ticks_ms

from panel import fonts, seg7, wx
from panel.hostdata import DAYS, MONTHS, hhmm12
from panel.art import FRAME_MS, IDLE_FRAME_MS, MAX_DT
from panel.canvas import PAGES, Canvas, W, text_width

DWELL_MS = 18000
SLIDE_MS = 300
PREEMPT_MS = 4000  # status stays up this long after the last action
FULL = (1 << PAGES) - 1
TOP = 16

BODY = fonts.SPLEEN
SMALL = fonts.SMALL
VOL_STEP = 2  # as ui/volume.py
VOL_TURN_MS = 1200  # a turn ends after this long without a detent
REPEAT = ("off", "all", "one")

CLOCK, WEATHER, STATUS = 0, 1, 2


def mmss(ms):
    s = ms // 1000
    return "%d:%02d" % (s // 60, s % 60)


def right(c, y, s, font=BODY, x1=W - 2):
    c.text(x1 - text_width(s, font), y, s, font)


def centre(c, y, s, font=BODY):
    c.text((W - text_width(s, font)) // 2, y, s, font)


class Hud:
    """State the views read, apart from the shared Transport."""

    def __init__(self):
        self.vol_turn = 0  # net change of the current turn
        self.vol_net = 0  # net change this session
        self._vol_at = None
        self.up_ms = 0  # session time, summed from frame dt (no wrap issues)

    def knob(self, delta, now):
        if self._vol_at is None or ticks_diff(now, self._vol_at) >= VOL_TURN_MS:
            self.vol_turn = 0
        self._vol_at = now
        self.vol_turn += delta * VOL_STEP
        self.vol_net += delta * VOL_STEP

    def turning(self, now):
        return self._vol_at is not None and ticks_diff(now, self._vol_at) < VOL_TURN_MS


def header(c, title, view, playing):
    """Yellow band shared by every view: title, play state, view dots."""
    c.text(2, 4, title, BODY)
    x = 100
    if playing:
        for i in range(4):
            c.vline(x + i, 4 + i, 7 - 2 * i)
    else:
        c.fill_rect(x, 4, 2, 7)
        c.fill_rect(x + 3, 4, 2, 7)
    for k in range(3):
        dx = 110 + k * 6
        if k == view:
            c.fill_rect(dx, 6, 3, 3)
        else:
            c.pixel(dx + 1, 7)


def song_strip(c, t, now):
    """Bottom strip: elapsed time, and a progress bar + length when known."""
    y = 58
    c.text(2, y, mmss(t.elapsed(now)), SMALL)
    d = t.duration_ms
    if d:
        right(c, y, mmss(d), SMALL)
        x0, x1 = 24, W - 24
        c.hline(x0, 61, x1 - x0)
        c.fill_rect(x0, 60, t.progress(now, x1 - x0), 3)


def draw_clock(c, t, hud, host, now):
    lt = host.local(now) if host is not None else None
    if lt is None:
        header(c, "CLOCK", CLOCK, t.playing)
        x0 = (W - seg7.width("--:--")) // 2
        seg7.text(c, x0, 19, "--:--")
        song_strip(c, t, now)
        return
    y, mo, d, wday, h, mi, sec = lt
    header(c, "%s %d %s" % (DAYS[wday], d, MONTHS[mo - 1]), CLOCK, t.playing)
    s = "%d:%02d" % (h % 12 or 12, mi)
    w = seg7.width(s)
    x0 = (W - w) // 2 - 8  # leaves room for AM/PM on the right
    seg7.text(c, x0, 19, s, colon=sec % 2 == 0)  # the colon ticks seconds
    c.text(x0 + w + 5, 19, "AM" if h < 12 else "PM", BODY)
    song_strip(c, t, now)


def draw_weather(c, t, hud, host, now):
    header(c, "WEATHER", WEATHER, t.playing)
    w = host.weather(now) if host is not None else None
    if w is None:
        centre(c, 30, "no link")
        return
    code, temp, feels, hi, lo, rain, is_day = w
    s = str(temp)
    x = seg7.text(c, 42, 19, s, 12, 24)
    wx.disc(c, x + 3, 21, 2)  # degree sign: ring
    wx.disc(c, x + 3, 21, 1, False)
    c.text(x + 7, 19, "F", BODY)
    right(c, 24, "H%d" % hi)
    right(c, 34, "L%d" % lo)
    c.text(42, 47, "FEELS %d" % feels, SMALL)
    moon = host.moon
    if not is_day and moon is not None:
        cycle, lit, rise, sset = moon
        c.text(2, 58, "%s %d%%" % (wx.moon_name(cycle), lit), SMALL)
        right(c, 58, "RISE " + hhmm12(rise), SMALL)
    else:
        c.text(2, 58, wx.condition(code), SMALL)
        right(c, 58, "RAIN %d%%" % rain, SMALL)


def anim_weather(c, t, hud, host, now):
    """The animated icon, drawn over the cached rest of the view."""
    w = host.weather(now) if host is not None else None
    if w is None:
        return False
    moon = host.moon
    wx.draw(c, wx.icon_for(w[0], w[6]), 2, 18, now, moon[0] if moon else 64)
    return True


def draw_status(c, t, hud, host, now):
    header(c, "SPOTIFY", STATUS, t.playing)
    y = 17
    c.text(2, y, "PLAYING" if t.playing else "PAUSED", BODY)
    right(c, y, "TRK %d" % (t.track_n + 1))
    y += 9
    # Volume: this turn's change while turning, else the session's net.
    v = hud.vol_turn if hud.turning(now) else hud.vol_net
    c.text(2, y, "VOL", BODY)
    right(c, y, "%+d" % v)
    bx, bw, mid = 22, 72, 22 + 36
    c.rect(bx, y + 1, bw, 5)
    n = min(abs(v), 50) * (bw // 2 - 1) // 50
    if v > 0:
        c.fill_rect(mid, y + 2, n, 3)
    elif v < 0:
        c.fill_rect(mid - n, y + 2, n, 3)
    c.vline(mid, y, 7)
    y += 9
    c.text(2, y, "SHUF " + ("on" if t.shuffle else "off"), BODY)
    right(c, y, "REP " + REPEAT[t.repeat])
    y += 9
    c.text(2, y, "LIKED" if t.liked else "LIKE", BODY)
    right(c, y, "<3" if t.liked else "--")
    y += 9
    c.text(2, y, "SKIPS %d" % t.skips, BODY)
    m = hud.up_ms // 60000
    right(c, y, "UP %d:%02d" % (m // 60, m % 60))


def sig_clock(t, hud, host, now):
    lt = host.local(now) if host is not None else None
    hm = lt[4] * 120 + lt[5] * 2 + (lt[6] & 1) if lt else -1  # colon blinks
    return (hm, lt[2] if lt else 0, t.elapsed(now) // 1000, t.playing, t.duration_ms)


def sig_weather(t, hud, host, now):
    if host is None:
        return t.playing
    return (host.weather(now), host.moon, t.playing)


def sig_status(t, hud, host, now):
    v = hud.vol_turn if hud.turning(now) else hud.vol_net
    return (t.playing, t.track_n, v, t.shuffle, t.repeat, t.liked, t.skips,
            hud.up_ms // 60000)


VIEWS = (draw_clock, draw_weather, draw_status)
SIGS = (sig_clock, sig_weather, sig_status)  # a view redraws only when its sig changes
ANIMS = (None, anim_weather, None)  # drawn every frame over the cached view
CHECK_MS = (250, 500, 100)  # how often to look at a view's sig
ANIM_MS = 66
ANIM_PAGES = (2, 7)  # the icon cell (rows 18-49) lives in pages 2..6
ANIM_DIRTY = ((1 << ANIM_PAGES[1]) - 1) & ~((1 << ANIM_PAGES[0]) - 1)

_warm = False


def warm():
    """Build the sprites (digits, clouds, suns) up front: a first-use build
    takes tens of ms on the board and would stall the loop mid-run."""
    global _warm
    if not _warm:
        seg7.warm(19)  # clock
        seg7.warm(19, 12, 24)  # temperature
        wx.warm(18)
        _warm = True


class HudScene:
    def __init__(self, canvas, transport, host=None):
        warm()
        self.c = canvas
        self.t = transport
        self.host = host  # PC helper data; None = no link
        self.hud = Hud()
        self._new = bytearray(W * PAGES)
        self._old = bytearray(W * PAGES)
        self._base = bytearray(W * PAGES)  # last full render, before animation
        self._scratch = Canvas(self._new)
        self._base_c = Canvas(self._base)
        self._base_view = None
        self._sig = None  # sig of what _base shows
        self._check_at = None
        self._anim_at = None
        self._last = None
        self.shown = None  # view index on the panel
        self.idx = CLOCK  # rotation position
        self._dwell_until = None
        self._pre_until = None  # status preempt, None = not preempted
        self._slide_at = None
        self._target = None
        self.title = None
        self.prof = [0, 0, 0, 0]  # worst ms: clock, weather, status render; anim

    # -- events (same interface as the other scenes) --
    def set_title(self, name):
        self.title = name  # the HUD draws its own titles

    def _poke(self, now):
        self._pre_until = now + PREEMPT_MS  # compared with ticks_diff
        self._check_at = None  # look at the status sig right away

    def key(self, k, now):
        self._poke(now)

    def knob(self, delta, now=0):
        if delta:
            self.hud.knob(delta, now)
            self._poke(now)

    # -- rotation --
    def _pick(self, now):
        """The view that should be on screen now (bonnet: _pick_target)."""
        if self._pre_until is not None:
            if ticks_diff(now, self._pre_until) < 0:
                return STATUS
            self._pre_until = None
            if self.shown == STATUS and self.idx != STATUS:
                self._dwell_until = None  # fresh dwell once we're back
                return self.idx
        if self.shown is None:
            return self.idx
        if self._dwell_until is not None and ticks_diff(now, self._dwell_until) >= 0:
            self.idx = (self.idx + 1) % len(VIEWS)
            return self.idx
        return self.shown

    def _render(self, v, now, full=True):
        """Compose view v into _new. full=False reuses the cached render and
        only redraws the animation on top. Returns True if it animates."""
        if full or self._base_view != v:
            t0 = ticks_ms()
            self._sig = SIGS[v](self.t, self.hud, self.host, now)
            bc = self._base_c
            bc.clear()
            VIEWS[v](bc, self.t, self.hud, self.host, now)
            self._base_view = v
            took = ticks_diff(ticks_ms(), t0)
            if took > self.prof[v]:
                self.prof[v] = took
        self._new[:] = self._base
        anim = ANIMS[v]
        if anim is None:
            return False
        t0 = ticks_ms()
        moving = anim(self._scratch, self.t, self.hud, self.host, now)
        took = ticks_diff(ticks_ms(), t0)
        if took > self.prof[3]:
            self.prof[3] = took
        return moving

    def busy(self, now):
        return self._slide_at is not None

    def tick(self, now):
        c = self.c
        if c.dirty:
            return False  # whole frames only: wait for the panel
        frame = FRAME_MS if self._slide_at is not None else IDLE_FRAME_MS // 2
        if self._last is None:
            dt = FRAME_MS
        else:
            dt = ticks_diff(now, self._last)
            if dt < frame:
                return False
            dt = min(dt, MAX_DT)
        self._last = now
        self.hud.up_ms += dt

        if self._slide_at is None:
            target = self._pick(now)
            if target != self.shown:
                if self.shown is None:  # first frame: no slide
                    self._render(target, now)
                    c.buf[:] = self._new
                    c.dirty = FULL
                    self._land(target, now)
                    return True
                self._old[:] = c.buf
                self._render(target, now)
                self._target = target
                self._slide_at = now
            else:
                return self._update(now)

        # Slide: the incoming view enters from the right.
        off = min(W, ticks_diff(now, self._slide_at) * W // SLIDE_MS)
        buf, old, new = c.buf, memoryview(self._old), memoryview(self._new)
        keep = W - off
        for p in range(PAGES):
            a = p * W
            buf[a:a + keep] = old[a + off:a + W]
            buf[a + keep:a + W] = new[a:a + off]
        c.dirty = FULL
        if off >= W:
            self._slide_at = None
            self._land(self._target, now)
        return True

    def _update(self, now):
        """Between slides: redraw when the view's content changed, and
        animate its icon. Sends only what changed."""
        v = self.shown
        c = self.c
        if self._check_at is None or ticks_diff(now, self._check_at) >= 0:
            self._check_at = now + CHECK_MS[v]
            if SIGS[v](self.t, self.hud, self.host, now) != self._sig:
                moving = self._render(v, now, True)
                self._anim_at = now + ANIM_MS if moving else None
                c.buf[:] = self._new
                c.dirty = FULL
                return True
        if self._anim_at is None or ticks_diff(now, self._anim_at) < 0:
            return False
        self._anim_at = now + ANIM_MS if self._render(v, now, False) else None
        a, b = ANIM_PAGES[0] * W, ANIM_PAGES[1] * W
        c.buf[a:b] = memoryview(self._new)[a:b]
        c.dirty |= ANIM_DIRTY
        return True

    def _land(self, v, now):
        self.shown = v
        self._check_at = now + CHECK_MS[v]
        self._anim_at = now + ANIM_MS if ANIMS[v] is not None else None
        self._dwell_until = now + DWELL_MS
