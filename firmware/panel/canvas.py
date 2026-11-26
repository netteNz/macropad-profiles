# Drawing on a 128x64 1-bit buffer in SSD1306 page layout: byte
# page * 128 + x holds 8 vertical pixels, bit 0 at the top. Every write marks
# its page in `dirty` (bit p = page p) so the driver sends only those pages.
# Pure logic, no board imports, so it runs in the host tests.
from panel import font5x7

W = 128
H = 64
PAGES = 8
_ZERO_PAGE = bytes(W)


class Canvas:
    def __init__(self, buf=None):
        self.buf = buf if buf is not None else bytearray(W * PAGES)
        self.dirty = (1 << PAGES) - 1

    def clear(self, p0=0, p1=PAGES):
        """Blank pages p0..p1-1 (whole 8-row bands, fast slice fill)."""
        b = self.buf
        for p in range(p0, p1):
            b[p * W:(p + 1) * W] = _ZERO_PAGE  # reused: no per-frame allocation
            self.dirty |= 1 << p

    def pixel(self, x, y, on=True):
        if 0 <= x < W and 0 <= y < H:
            i = (y >> 3) * W + x
            if on:
                self.buf[i] |= 1 << (y & 7)
            else:
                self.buf[i] &= ~(1 << (y & 7)) & 0xFF
            self.dirty |= 1 << (y >> 3)

    def fill_rect(self, x, y, w, h, on=True):
        x0 = max(x, 0)
        x1 = min(x + w, W)
        y0 = max(y, 0)
        y1 = min(y + h, H)
        if x0 >= x1 or y0 >= y1:
            return
        b = self.buf
        for p in range(y0 >> 3, ((y1 - 1) >> 3) + 1):
            top = max(y0 - p * 8, 0)
            bot = min(y1 - p * 8, 8)
            mask = ((0xFF << top) & (0xFF >> (8 - bot))) & 0xFF
            base = p * W
            if on:
                for i in range(base + x0, base + x1):
                    b[i] |= mask
            else:
                inv = ~mask & 0xFF
                for i in range(base + x0, base + x1):
                    b[i] &= inv
            self.dirty |= 1 << p

    def hline(self, x, y, w, on=True):
        self.fill_rect(x, y, w, 1, on)

    def vline(self, x, y, h, on=True):
        self.fill_rect(x, y, 1, h, on)

    def rect(self, x, y, w, h, on=True):
        self.hline(x, y, w, on)
        self.hline(x, y + h - 1, w, on)
        self.vline(x, y, h, on)
        self.vline(x + w - 1, y, h, on)

    def text(self, x, y, s, font=font5x7):
        """ASCII text at any y. Returns end x. Default font: 5x7 with a 1 px
        gap (6 px per char); panel/fonts.py has the HUD fonts.
        Characters outside 0x20..0x7E draw as '?'."""
        # Hot path (the HUD draws a lot of text): bounds, page offsets and
        # dirty bits are worked out once per string, not per glyph column.
        g = font.GLYPHS
        fw = font.W
        first, last = font.FIRST, font.LAST
        adv = getattr(font, "ADV", fw + 1)
        b = self.buf
        shift = y & 7
        p = y >> 3
        top = p * W if 0 <= p < PAGES else -1
        bot = (p + 1) * W if shift and 0 <= p + 1 < PAGES else -1
        if top >= 0:
            self.dirty |= 1 << p
        if bot >= 0:
            self.dirty |= 1 << (p + 1)
        rshift = 8 - shift
        for ch in s:
            c = ord(ch)
            if c < first or c > last:
                c = 0x3F
            o = (c - first) * fw
            c0 = -x if x < 0 else 0
            c1 = W - x if x + fw > W else fw
            for col in range(c0, c1):
                bits = g[o + col]
                if bits:
                    if top >= 0:
                        b[top + x + col] |= (bits << shift) & 0xFF
                    if bot >= 0:
                        b[bot + x + col] |= bits >> rshift
            x += adv
        return x


def text_width(s, font=font5x7):
    """Inked width: the trailing gap isn't counted for the 5x7 font."""
    if not s:
        return 0
    adv = getattr(font, "ADV", None)
    return len(s) * adv if adv else len(s) * (font.W + 1) - 1
