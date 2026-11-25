# PCA9548A / TCA9548A I2C mux, so several SSD1306s at the same address
# (0x3C) can share the STEMMA QT bus.
#
# Writing one byte to the mux picks the downstream channels (bit N = channel
# N); after that, writes to 0x3C reach only the panel on that channel. A
# Channel looks like a busio.I2C to Oled (try_lock / unlock / writeto / scan),
# so the panel driver doesn't know the mux exists. Pure logic: runs in the
# host tests with a fake bus.
from panel.oled import Oled, find

MUX_ADDRS = tuple(range(0x70, 0x78))
CHANNELS = 8


def find_mux(i2c):
    """Return the first mux address that answers, or None."""
    while not i2c.try_lock():
        pass
    try:
        found = i2c.scan()
    finally:
        i2c.unlock()
    for a in MUX_ADDRS:
        if a in found:
            return a
    return None


class Mux:
    def __init__(self, i2c, addr):
        self._i2c = i2c
        self.addr = addr
        self._sel = bytearray(1)
        self._cur = -1  # unknown until the first write
        while not i2c.try_lock():
            pass
        try:
            self._set(0)  # all channels off
        finally:
            i2c.unlock()

    def _set(self, mask):
        self._cur = -1  # if the write fails, the mux state is unknown
        self._sel[0] = mask
        self._i2c.writeto(self.addr, self._sel)
        self._cur = mask

    def select_locked(self, ch):
        """Connect only channel ch. Caller holds the bus lock."""
        mask = 1 << ch
        if mask != self._cur:
            self._set(mask)

    def channel(self, ch):
        return Channel(self, ch)


class Channel:
    """One mux channel, shaped like a busio.I2C for Oled and find()."""

    def __init__(self, mux, ch):
        self._mux = mux
        self._i2c = mux._i2c
        self.ch = ch

    def try_lock(self):
        return self._i2c.try_lock()

    def unlock(self):
        self._i2c.unlock()

    def writeto(self, addr, data):
        self._mux.select_locked(self.ch)
        self._i2c.writeto(addr, data)

    def scan(self):
        self._mux.select_locked(self.ch)
        # The mux answers on every channel; it isn't a downstream device.
        return [a for a in self._i2c.scan() if a != self._mux.addr]


def open_panels(i2c):
    """Open one Oled per SSD1306 found behind a mux.

    Returns (panels, message), or None when there is no mux on the bus.
    One panel failing to init doesn't drop the others.
    """
    addr = find_mux(i2c)
    if addr is None:
        return None
    mux = Mux(i2c, addr)
    panels = []
    found = []
    for ch in range(CHANNELS):
        c = mux.channel(ch)
        try:
            a = find(c)
            if a is None:
                continue
            panels.append(Oled(c, a))
            found.append("ch %d" % ch)
        except OSError as e:
            found.append("ch %d failed (%s)" % (ch, e))
    if found:
        msg = "panel: mux at 0x%02X, SSD1306 on %s" % (addr, ", ".join(found))
    else:
        msg = "panel: mux at 0x%02X, no panels on any channel" % addr
    return panels, msg
