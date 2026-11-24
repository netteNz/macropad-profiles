# Raw SSD1306 128x64 driver over I2C (the STEMMA QT port).
#
# CircuitPython allows one displayio display and the built-in OLED holds it,
# so this panel is driven by hand. busio.I2C.writeto blocks for the whole
# transfer (~3 ms per 128-byte page at 400 kHz), so flush_step() sends at
# most one dirty page per call and the main loop never stalls for a full
# frame (~23 ms). The I2C object is passed in, so this module imports nothing
# board-specific and runs in the host tests.
from adafruit_ticks import ticks_diff, ticks_ms

from panel.canvas import PAGES, W, Canvas

ADDRS = (0x3C, 0x3D)

# Control byte 0x00 = "the rest are commands", then: display off, clock,
# multiplex 64, offset 0, start line 0, charge pump on, page addressing mode,
# segment remap + COM scan reversed (normal orientation), COM pins, contrast,
# precharge, VCOMH, resume from RAM, normal (not inverted), display on.
_INIT = bytes((
    0x00, 0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0x8D, 0x14,
    0x20, 0x02, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0xCF, 0xD9, 0xF1, 0xDB, 0x40,
    0xA4, 0xA6, 0xAF,
))
# Rotated 180 degrees: segment remap and COM scan back to the defaults.
_FLIP = bytes((0x00, 0xA0, 0xC0))


def find(i2c):
    """Return the first SSD1306 address that answers, or None."""
    while not i2c.try_lock():
        pass
    try:
        found = i2c.scan()
    finally:
        i2c.unlock()
    for a in ADDRS:
        if a in found:
            return a
    return None


class Oled:
    def __init__(self, i2c, addr, flip=False):
        self._i2c = i2c
        self._addr = addr
        self.canvas = Canvas()
        self._buf = memoryview(self.canvas.buf)
        self._cmd = bytearray((0x00, 0xB0, 0x00, 0x10))  # page p, column 0
        self._out = bytearray(W + 1)
        self._out[0] = 0x40  # control byte: the rest is display data
        self._next = 0
        self.alive = True
        self.flush_ms_max = 0
        self._write(_INIT)
        if flip:
            self._write(_FLIP)
        # Panel RAM is random at power-up: send every page once.
        self.canvas.dirty = (1 << PAGES) - 1

    def _write(self, data):
        i2c = self._i2c
        while not i2c.try_lock():
            pass
        try:
            i2c.writeto(self._addr, data)
        finally:
            i2c.unlock()

    def flush_step(self):
        """Send at most one dirty page. Returns True if a page went out."""
        c = self.canvas
        if not self.alive or not c.dirty:
            return False
        p = self._next
        while not c.dirty & (1 << p):
            p = (p + 1) % PAGES
        c.dirty &= ~(1 << p)
        self._next = (p + 1) % PAGES  # round-robin so no page starves
        self._cmd[1] = 0xB0 | p
        self._out[1:] = self._buf[p * W:(p + 1) * W]
        t = ticks_ms()
        try:
            self._write(self._cmd)
            self._write(self._out)
        except OSError as e:  # unplugged mid-run: stop, keep the pad going
            self.alive = False
            print("panel: lost (%s), disabled until reset" % e)
            return False
        took = ticks_diff(ticks_ms(), t)
        if took > self.flush_ms_max:
            self.flush_ms_max = took
        return True
