# Big 7-segment digits with beveled ends, drawn with fill_rect so they
# cost a handful of page writes rather than per-pixel work.
#
#    aaa
#   f   b
#   f   b
#    ggg
#   e   c
#   e   c
#    ddd
from panel.sprite import build, stamp

SEGS = {
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
    "5": "afgcd", "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg",
    "-": "g", " ": "",
}
GAP = 4  # between digits
COLON_W = 7
_cache = {}  # pre-rendered digits, see panel/sprite.py


def _h(c, x, y, w, t):
    """Horizontal segment: t rows, the outer rows shortened (bevel)."""
    for i in range(t):
        inset = 1 + (t // 2 - min(i, t - 1 - i))
        c.fill_rect(x + inset + 1, y + i, w - 2 * inset - 2, 1)


def _v(c, x, y, h, t):
    for i in range(t):
        inset = 1 + (t // 2 - min(i, t - 1 - i))
        c.fill_rect(x + i, y + inset + 1, 1, h - 2 * inset - 2)


def digit(c, x, y, ch, w=14, h=30, t=3):
    on = SEGS.get(ch, "")
    m = h // 2
    if "a" in on:
        _h(c, x, y, w, t)
    if "g" in on:
        _h(c, x, y + m - t // 2 - 1, w, t)
    if "d" in on:
        _h(c, x, y + h - t, w, t)
    if "f" in on:
        _v(c, x, y, m, t)
    if "b" in on:
        _v(c, x + w - t, y, m, t)
    if "e" in on:
        _v(c, x, y + m - 1, h - m + 1, t)
    if "c" in on:
        _v(c, x + w - t, y + m - 1, h - m + 1, t)


def _digit_shape(c, x, y, ch, w, h):
    digit(c, x, y, ch, w, h)


def _sprite(ch, w, h, y):
    k = ((ord(ch) * 64 + w) * 64 + h) * 64 + y
    s = _cache.get(k)
    if s is None:
        s = _cache[k] = build(_digit_shape, y, ch, w, h)
    return s


def warm(y, w=14, h=30, chars="0123456789-"):
    for ch in chars:
        _sprite(ch, w, h, y)


def text(c, x, y, s, w=14, h=30, colon=True):
    """Draw digits, '-', ' ' and ':' (colon=False leaves its gap blank, for
    blinking). Returns the end x. Digits are stamped from cached sprites, so
    draw them before any text that shares their columns."""
    for ch in s:
        if ch == ":":
            if colon:
                c.fill_rect(x + 2, y + h // 3 - 1, 3, 3)
                c.fill_rect(x + 2, y + 2 * h // 3 - 1, 3, 3)
            x += COLON_W
        else:
            if ch != " ":
                stamp(c, _sprite(ch, w, h, y), x)
            x += w + GAP
    return x - GAP if s and s[-1] != ":" else x


def width(s, w=14):
    n = 0
    for ch in s:
        n += COLON_W if ch == ":" else w + GAP
    return n - GAP if s and s[-1] != ":" else n
