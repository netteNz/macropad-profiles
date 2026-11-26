# Pre-rendered shapes in the panel's page layout.
#
# A shape is drawn once, slowly, by any Canvas drawing function, and kept as
# two byte grids over its bounding box: `on` (bits to set) and `keep` (bits
# that survive; a dark outline clears bits). Blitting is then a byte loop,
# buf = (buf & keep) | on, or a straight slice copy for shapes drawn onto an
# empty area. Two bytearrays per shape instead of per-pixel work per frame.
from panel.canvas import PAGES, Canvas, W

_OX = 32  # drawing origin inside the build canvas (room for negative dx)
_SPAN = 24  # shapes reach at most this far left of their anchor, 2x right


def build(fn, *args):
    """fn(canvas, x, *args) draws the shape with its anchor at column x.
    Returns a sprite: (dx, w, p0, np, keep, on, plain)."""
    a = Canvas()
    fn(a, _OX, *args)
    b = Canvas(bytearray([0xFF]) * (W * PAGES))
    fn(b, _OX, *args)
    ab, bb = a.buf, b.buf
    c0, c1, p0, p1 = W, -1, PAGES, -1
    for p in range(PAGES):
        for col in range(_OX - _SPAN, _OX + 2 * _SPAN):  # shapes are small
            i = p * W + col
            if ab[i] or bb[i] != 0xFF:
                c0 = min(c0, col)
                c1 = max(c1, col)
                p0 = min(p0, p)
                p1 = max(p1, p)
    if c1 < 0:
        return (0, 0, 0, 0, b"", b"", True)
    w, n = c1 - c0 + 1, p1 - p0 + 1
    on = bytearray(w * n)
    keep = bytearray(w * n)
    plain = True
    for pi in range(n):
        for col in range(w):
            i = (p0 + pi) * W + c0 + col
            on[pi * w + col] = ab[i]
            keep[pi * w + col] = bb[i]
            if bb[i] != 0xFF:
                plain = False
    return (c0 - _OX, w, p0, n, keep, on, plain)


def blit(c, s, x):
    """Draw sprite s anchored at column x, respecting its outline."""
    dx, w, p0, n, keep, on, plain = s
    x0 = x + dx
    a = -x0 if x0 < 0 else 0
    b = W - x0 if x0 + w > W else w
    buf = c.buf
    for pi in range(n):
        base = (p0 + pi) * W + x0
        o = pi * w
        if plain:
            for col in range(a, b):
                buf[base + col] |= on[o + col]
        else:
            for col in range(a, b):
                i = base + col
                buf[i] = (buf[i] & keep[o + col]) | on[o + col]


def stamp(c, s, x):
    """Copy sprite s's bytes over whatever is there (its whole bounding box
    of page bytes). Fastest; only for shapes drawn before anything that
    shares their columns and pages."""
    dx, w, p0, n, keep, on, plain = s
    x0 = x + dx
    a = -x0 if x0 < 0 else 0
    b = W - x0 if x0 + w > W else w
    buf = c.buf
    mv = memoryview(on)
    for pi in range(n):
        base = (p0 + pi) * W + x0
        buf[base + a:base + b] = mv[pi * w + a:pi * w + b]
