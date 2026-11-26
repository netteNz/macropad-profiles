# Weather icons for the HUD: 32x32 cells, animated from a time in ms.
# Integer math and precomputed tables only (frames shouldn't allocate);
# shapes are built from fill_rect rows so a frame is cheap.
import math

from panel.spotify import COS, SIN
from panel.sprite import blit, build

# Half-widths of a filled disc per row, for every radius used: HALF[r][dy].
HALF = {r: [int(math.sqrt(r * r + r - dy * dy)) for dy in range(r + 1)]
        for r in range(1, 12)}

SUN, PARTLY, CLOUDY, FOG, RAIN, HEAVY, SNOW, STORM, NIGHT, NIGHT_PARTLY = range(10)


def icon_for(code, is_day):
    if code == 0:
        return SUN if is_day else NIGHT
    if code in (1, 2):
        return PARTLY if is_day else NIGHT_PARTLY
    if code in (45, 48):
        return FOG
    if 51 <= code <= 57 or code in (61, 63, 66, 80, 81):
        return RAIN
    if code in (65, 67, 82):
        return HEAVY
    if 71 <= code <= 77 or code in (85, 86):
        return SNOW
    if 95 <= code <= 99:
        return STORM
    return CLOUDY


def condition(code):
    if code == 0:
        return "CLEAR"
    if code == 1:
        return "MOSTLY CLEAR"
    if code == 2:
        return "PTLY CLOUDY"
    if code == 3:
        return "OVERCAST"
    if code in (45, 48):
        return "FOG"
    if 51 <= code <= 57:
        return "DRIZZLE"
    if code in (65, 67):
        return "HEAVY RAIN"
    if 61 <= code <= 67:
        return "RAIN"
    if 71 <= code <= 77:
        return "SNOW"
    if 80 <= code <= 82:
        return "SHOWERS"
    if code in (85, 86):
        return "SNOW SHOWERS"
    if code == 95:
        return "T-STORM"
    if code in (96, 99):
        return "T-STORM HAIL"
    return "WX %d" % code


def moon_name(cycle):
    """Same rules as oled-bonnet's MoonPhase.name: the 4 principal phases get
    +-1/30 of a cycle, the rest are waxing/waning crescent/gibbous."""
    for centre, name in ((0, "NEW MOON"), (64, "FIRST QTR"), (128, "FULL MOON"),
                         (192, "LAST QTR"), (256, "NEW MOON")):
        if abs(cycle - centre) <= 8:
            return name
    return ("WAX " if cycle < 128 else "WAN ") + ("CRES" if cycle < 64 or cycle > 192 else "GIBB")


# -- primitives --

def disc(c, cx, cy, r, on=True):
    h = HALF[r]
    for dy in range(-r, r + 1):
        w = h[abs(dy)]
        c.fill_rect(cx - w, cy + dy, 2 * w + 1, 1, on)


def _cloud_parts(x, y):
    return ((x + 7, y + 8, 5), (x + 14, y + 6, 7), (x + 21, y + 9, 4))


# -- sprites (see panel/sprite.py) --
# Keys are small ints, so a cache hit doesn't allocate. Moons depend on the
# phase, so only the last couple are kept.
_cache = {}
_moons = {}


def _cloud_shape(c, x, y, outline):
    parts = _cloud_parts(x, y)
    if outline:
        for cx, cy, r in parts:
            disc(c, cx, cy, r + 2, False)
        c.fill_rect(x + 1, y + 8, 26, 8, False)
    for cx, cy, r in parts:
        disc(c, cx, cy, r)
    c.fill_rect(x + 2, y + 9, 24, 5)


def cloud(c, x, y, outline=False):
    """A ~26x15 cloud; outline=True first carves a 1 px dark border so it
    reads on top of a sun or moon."""
    k = y * 2 + (1 if outline else 0)
    spr = _cache.get(k)
    if spr is None:
        spr = _cache[k] = build(_cloud_shape, y, outline)
    blit(c, spr, x)


def _disc_shape(c, cx, cy, r):
    disc(c, cx, cy, r)


def disc_fast(c, cx, cy, r):
    k = 100000 + cy * 100 + r
    spr = _cache.get(k)
    if spr is None:
        spr = _cache[k] = build(_disc_shape, cy, r)
    blit(c, spr, cx)


def sun(c, cx, cy, r, t):
    disc_fast(c, cx, cy, r)
    spin = (t // 40) & 255  # a full turn every ~10 s
    for k in range(8):
        a = (k * 32 + spin) & 255
        grow = 1 if SIN[(t // 6 + k * 32) & 255] > 0 else 0  # rays breathe
        for d in range(r + 3, r + 6 + grow):
            c.pixel(cx + (d * COS[a] >> 7), cy + (d * SIN[a] >> 7))


def moon(c, cx, cy, r, cycle):
    k = (cy * 100 + r) * 256 + (cycle & 255)
    spr = _moons.get(k)
    if spr is None:
        if len(_moons) >= 2:
            _moons.clear()
        spr = _moons[k] = build(_moon_shape, cy, r, cycle)
    blit(c, spr, cx)


def _moon_shape(c, cx, cy, r, cycle):
    """Disc lit at phase `cycle` (0 new .. 128 full .. 255), northern view,
    with a rim so a new moon still shows. Port of oled-bonnet's moon_disc."""
    h = HALF[r]
    k = COS[cycle & 255]
    waxing = cycle < 128
    for dy in range(-r, r + 1):
        w = h[abs(dy)]
        edge = k * w >> 7
        if waxing:
            if w > edge:
                c.fill_rect(cx + edge + 1, cy + dy, w - edge, 1)
        elif -edge > -w:
            c.fill_rect(cx - w, cy + dy, w - edge, 1)
        c.pixel(cx - w, cy + dy)
        c.pixel(cx + w, cy + dy)
    for dx in range(-r, r + 1):
        w = h[abs(dx)]
        c.pixel(cx + dx, cy - w)
        c.pixel(cx + dx, cy + w)


def star(c, x, y, size):
    if size <= 0:
        return
    c.pixel(x, y)
    if size > 1:
        c.pixel(x - 1, y)
        c.pixel(x + 1, y)
        c.pixel(x, y - 1)
        c.pixel(x, y + 1)


def _drops(c, x, y, t, n, speed, heavy):
    for k in range(n):
        dx = 5 + k * 22 // max(n - 1, 1)
        dy = (t * speed // 1000 + k * 7) % 12
        px, py = x + dx - dy // 4, y + 18 + dy
        c.pixel(px, py)
        c.pixel(px - 1, py + 1)
        if heavy:
            c.pixel(px - 1, py + 2)


BOLT = ((17, 17), (16, 18), (15, 19), (14, 20), (13, 21), (14, 21), (15, 21),
        (16, 21), (17, 21), (16, 22), (15, 23), (14, 24), (13, 25), (12, 26),
        (11, 27), (12, 27))


def warm(y):
    """Build every cloud and sun sprite the icons use in a cell at row y, so
    the first frame of a new icon doesn't stall the loop (run at startup)."""
    for dy, outline in ((14, True), (3, False), (13, True), (2, False), (1, False)):
        cloud(_NullCanvas, 0, y + dy, outline)
    disc_fast(_NullCanvas, 0, y + 16, 7)
    disc_fast(_NullCanvas, 0, y + 11, 5)


class _Null:
    buf = bytearray(1024)


_NullCanvas = _Null()


# -- icons: draw(c, x, y, t, cycle) into the 32x32 cell at x, y --

def draw(c, icon, x, y, t, cycle=0):
    if icon == SUN:
        sun(c, x + 16, y + 16, 7, t)
    elif icon == PARTLY:
        sun(c, x + 11, y + 11, 5, t)
        drift = SIN[(t // 30) & 255] * 3 >> 7
        cloud(c, x + 4 + drift, y + 14, outline=True)
    elif icon == CLOUDY:
        d = SIN[(t // 40) & 255] * 2 >> 7
        cloud(c, x + 4 - d, y + 3)
        cloud(c, x + 1 + d, y + 13, outline=True)
    elif icon == FOG:
        for k in range(4):
            s = SIN[(t // 20 + k * 64) & 255] * 3 >> 7
            yy = y + 9 + k * 5
            c.fill_rect(x + 3 + s, yy, 13, 1)
            c.fill_rect(x + 18 + s, yy, 10, 1)
            c.fill_rect(x + 4 + s, yy + 1, 9, 1)
            c.fill_rect(x + 20 + s, yy + 1, 7, 1)
    elif icon in (RAIN, HEAVY):
        cloud(c, x + 3, y + 2)
        heavy = icon == HEAVY
        _drops(c, x, y, t, 6 if heavy else 4, 60 if heavy else 40, heavy)
    elif icon == SNOW:
        cloud(c, x + 3, y + 2)
        for k in range(5):
            dy = (t * 10 // 1000 + k * 5) % 12
            sway = SIN[(t // 10 + k * 50) & 255] * 2 >> 7
            star(c, x + 5 + k * 5 + sway, y + 18 + dy, 2)
    elif icon == STORM:
        cloud(c, x + 3, y + 1)
        _drops(c, x, y - 1, t, 3, 50, False)
        f = t % 4000  # double flash every 4 s
        if f < 120 or 220 <= f < 300:
            for bx, by in BOLT:
                c.pixel(x + bx, y + by)
                c.pixel(x + bx + 1, y + by)
    elif icon == NIGHT:
        moon(c, x + 15, y + 16, 9, cycle)
        for k, (sx, sy) in enumerate(((28, 4), (3, 5), (29, 26), (5, 28))):
            size = (t // 350 + k * 3) % 6
            star(c, x + sx, y + sy, 2 if size == 0 else (1 if size < 3 else 0))
    elif icon == NIGHT_PARTLY:
        moon(c, x + 11, y + 11, 7, cycle)
        drift = SIN[(t // 30) & 255] * 3 >> 7
        cloud(c, x + 4 + drift, y + 14, outline=True)
        star(c, x + 27, y + 4, 2 if (t // 500) % 4 == 0 else 1)
