import unittest

import _paths  # noqa: F401
from panel import font5x7
from panel.art import RIPPLE_MAX_R, RIPPLE_MS_PER_PX, TOP, Scene, key_center
from panel.canvas import Canvas, text_width
from panel.mux import Mux, find_mux, open_panels
from panel.oled import _INIT, Oled, find


class FakeI2C:
    def __init__(self, present=(0x3C,), fail=False):
        self.present = present
        self.fail = fail
        self.writes = []
        self.locked = False

    def try_lock(self):
        if self.locked:
            return False
        self.locked = True
        return True

    def unlock(self):
        self.locked = False

    def scan(self):
        return list(self.present)

    def writeto(self, addr, data):
        assert self.locked
        if self.fail:
            raise OSError(19)
        self.writes.append((addr, bytes(data)))


class CanvasTest(unittest.TestCase):
    def setUp(self):
        self.c = Canvas()
        self.c.dirty = 0

    def test_pixel_maps_to_page_byte_and_bit(self):
        self.c.pixel(0, 0)
        self.c.pixel(5, 13)
        self.assertEqual(self.c.buf[0], 0x01)
        self.assertEqual(self.c.buf[128 + 5], 1 << 5)
        self.assertEqual(self.c.dirty, 0b11)
        self.c.pixel(5, 13, False)
        self.assertEqual(self.c.buf[128 + 5], 0)

    def test_out_of_bounds_is_clipped(self):
        for x, y in ((-1, 0), (128, 0), (0, -1), (0, 64)):
            self.c.pixel(x, y)
        self.c.fill_rect(120, 60, 50, 50)
        self.assertEqual(self.c.buf[7 * 128 + 127], 0xF0)
        self.assertEqual(sum(self.c.buf), 8 * 0xF0)
        self.assertEqual(self.c.dirty, 1 << 7)

    def test_fill_rect_spans_pages(self):
        self.c.fill_rect(2, 6, 1, 4)  # rows 6..9
        self.assertEqual(self.c.buf[2], 0xC0)
        self.assertEqual(self.c.buf[128 + 2], 0x03)
        self.assertEqual(self.c.dirty, 0b11)
        self.c.fill_rect(2, 7, 1, 2, on=False)
        self.assertEqual(self.c.buf[2], 0x40)
        self.assertEqual(self.c.buf[128 + 2], 0x02)

    def test_clear_marks_pages(self):
        self.c.fill_rect(0, 0, 128, 64)
        self.c.dirty = 0
        self.c.clear(2, 4)
        self.assertEqual(self.c.dirty, 0b1100)
        self.assertEqual(self.c.buf[2 * 128], 0)
        self.assertEqual(self.c.buf[4 * 128], 0xFF)

    def test_text_aligned_and_shifted(self):
        end = self.c.text(0, 0, "L")
        self.assertEqual(end, 6)
        self.assertEqual(bytes(self.c.buf[0:5]), bytes((0x7F, 0x40, 0x40, 0x40, 0x40)))
        c = Canvas()
        c.text(0, 4, "L")  # straddles pages 0 and 1
        self.assertEqual(c.buf[0], (0x7F << 4) & 0xFF)
        self.assertEqual(c.buf[128], 0x7F >> 4)

    def test_text_unknown_char_is_question_mark(self):
        a, b = Canvas(), Canvas()
        a.text(0, 0, "é")
        b.text(0, 0, "?")
        self.assertEqual(a.buf, b.buf)

    def test_font_size_and_width(self):
        self.assertEqual(len(font5x7.GLYPHS), (font5x7.LAST - font5x7.FIRST + 1) * 5)
        self.assertEqual(text_width("MACROPAD"), 47)
        self.assertEqual(text_width(""), 0)



class SceneTest(unittest.TestCase):
    def setUp(self):
        import random
        self.c = Canvas()
        self.s = Scene(self.c, rng=random.Random(1))
        self.c.dirty = 0  # as if the panel had sent everything

    def tick(self, now):
        drew = self.s.tick(now)
        self.c.dirty = 0  # the panel takes the whole frame
        return drew

    def yellow(self):
        return bytes(self.c.buf[:256])

    def test_title_centered_in_yellow_band_only(self):
        self.s.set_title("Spotify")
        band = self.yellow()
        self.assertTrue(any(band))
        self.assertFalse(any(self.c.buf[256:]))
        self.assertTrue(self.s.tick(0))  # a dirty title doesn't hold frames back
        self.assertEqual(self.yellow(), band)  # frames never touch the title

    def test_long_title_truncated(self):
        self.s.set_title("X" * 40)
        self.assertEqual(self.s.title, "X" * 40)
        self.assertTrue(self.c.buf[1])  # 21 chars start at x=1

    def test_key_centers_on_grid(self):
        self.assertEqual(key_center(0), (22, 22))
        self.assertEqual(key_center(11), (106, 58))
        for k in range(12):
            x, y = key_center(k)
            self.assertTrue(0 <= x < 128 and TOP <= y < 64)

    def test_ripples_expire_and_cap(self):
        for k in range(10):
            self.s.key(k, 0)
        self.assertEqual(len(self.s.ripples), 6)
        self.assertTrue(self.tick(0))
        self.tick((RIPPLE_MAX_R + 1) * RIPPLE_MS_PER_PX)
        self.assertEqual(self.s.ripples, [])

    def test_wave_grows_then_decays(self):
        self.s.knob(-2)
        self.assertEqual(self.s.amp, 12)
        self.s.knob(10)
        self.assertEqual(self.s.amp, 22)
        t = 0
        while self.s.amp and t < 10000:
            self.tick(t)
            t += 33
        self.assertEqual(self.s.amp, 0)
        self.assertLess(t, 3000)

    def test_frames_stay_in_blue_area_and_pace(self):
        self.s.key(0, 0)
        self.s.knob(5)
        self.assertTrue(self.s.tick(0))
        self.assertFalse(any(self.yellow()))
        self.c.dirty = 0
        self.assertFalse(self.s.tick(10))  # inside the frame throttle
        self.assertTrue(self.s.tick(33))
        self.assertEqual(self.c.dirty & 0b11, 0)  # title pages not resent

    def test_waits_for_previous_frame(self):
        self.s.knob(3)
        self.assertTrue(self.s.tick(0))
        self.assertFalse(self.s.tick(500))  # blue pages still unsent
        self.c.dirty = 0
        self.assertTrue(self.s.tick(500))

    def test_wave_is_a_continuous_line(self):
        self.s.stars = []
        self.s.knob(4)
        self.tick(0)
        for x in range(128):
            col = sum(self.c.buf[p * 128 + x] for p in range(2, 8))
            self.assertTrue(col, "gap at x=%d" % x)

    def test_wave_scroll_follows_time_not_frames(self):
        a, b = Scene(Canvas(), rng=__import__("random").Random(1)), Scene(Canvas(), rng=__import__("random").Random(1))
        for sc in (a, b):
            sc.c.dirty = 0
            sc.knob(3)
        for t in range(0, 200, 33):  # fast frames
            a.tick(t)
            a.c.dirty = 0
        b.tick(0)
        b.c.dirty = 0
        for t in (99, 198):  # slow frames (stalled loop)
            b.tick(t)
            b.c.dirty = 0
        self.assertLessEqual(abs(a._phase16 - b._phase16), 16)


class OledTest(unittest.TestCase):
    def setUp(self):
        self.i2c = FakeI2C()
        self.o = Oled(self.i2c, 0x3C)

    def pages_sent(self):
        return [w[1][1] & 0x0F for w in self.i2c.writes if w[1][0] == 0x00 and len(w[1]) == 4]

    def drain(self):
        n = 0
        while self.o.flush_step():
            n += 1
        return n

    def test_find(self):
        self.assertEqual(find(FakeI2C((0x10, 0x3D))), 0x3D)
        self.assertIsNone(find(FakeI2C(())))

    def test_init_then_every_page_once(self):
        self.assertEqual(self.i2c.writes[0], (0x3C, _INIT))
        self.i2c.writes.clear()
        self.assertTrue(self.o.flush_step())
        self.assertEqual(len(self.i2c.writes), 2)  # one page per call
        self.assertEqual(self.i2c.writes[0][1], bytes((0x00, 0xB0, 0x00, 0x10)))
        self.assertEqual(len(self.i2c.writes[1][1]), 129)
        self.assertEqual(self.i2c.writes[1][1][0], 0x40)
        self.assertEqual(self.drain(), 7)
        self.assertEqual(self.pages_sent(), list(range(8)))
        self.assertFalse(self.o.flush_step())

    def test_only_dirty_page_is_sent_with_data(self):
        self.drain()
        self.i2c.writes.clear()
        self.o.canvas.pixel(3, 42)  # page 5
        self.assertEqual(self.drain(), 1)
        self.assertEqual(self.pages_sent(), [5])
        data = self.i2c.writes[1][1]
        self.assertEqual(data[1 + 3], 1 << 2)

    def test_round_robin(self):
        self.drain()
        self.i2c.writes.clear()
        self.o.canvas.pixel(0, 0)
        self.o.canvas.pixel(0, 63)
        self.o.flush_step()
        self.o.canvas.pixel(1, 0)  # page 0 dirty again before page 7 went out
        self.drain()
        self.assertEqual(self.pages_sent(), [0, 7, 0])

    def test_unplug_disables(self):
        self.i2c.fail = True
        self.assertFalse(self.o.flush_step())
        self.assertFalse(self.o.alive)
        self.assertFalse(self.o.flush_step())


class FakeMuxBus(FakeI2C):
    """A bus with a mux at 0x70; each channel has its own devices."""

    def __init__(self, channels, mux=0x70):
        super().__init__(present=(mux,))
        self.mux = mux
        self.channels = channels  # {ch: (addrs...)}
        self.mask = 0
        self.dead = set()  # channels whose devices raise on write

    def scan(self):
        found = [self.mux]
        for ch, addrs in self.channels.items():
            if self.mask & (1 << ch):
                found.extend(addrs)
        return found

    def writeto(self, addr, data):
        assert self.locked
        if addr == self.mux:
            self.mask = data[0]
        elif any(self.mask & (1 << ch) for ch in self.dead):
            raise OSError(5)
        self.writes.append((addr, bytes(data)))


class MuxTest(unittest.TestCase):
    def test_find_mux(self):
        self.assertEqual(find_mux(FakeI2C((0x3C, 0x71))), 0x71)
        self.assertIsNone(find_mux(FakeI2C((0x3C,))))

    def test_select_only_when_changed(self):
        bus = FakeMuxBus({})
        m = Mux(bus, 0x70)
        self.assertEqual(bus.writes, [(0x70, bytes((0,)))])
        bus.writes.clear()
        bus.try_lock()
        m.select_locked(3)
        m.select_locked(3)
        m.select_locked(1)
        bus.unlock()
        self.assertEqual(bus.writes, [(0x70, bytes((8,))), (0x70, bytes((2,)))])

    def test_no_mux_returns_none(self):
        self.assertIsNone(open_panels(FakeI2C((0x3C,))))

    def test_mux_without_panels(self):
        panels, msg = open_panels(FakeMuxBus({}))
        self.assertEqual(panels, [])
        self.assertIn("no panels", msg)

    def test_scan_ignores_mux_address(self):
        bus = FakeMuxBus({2: (0x3C,)})
        c = Mux(bus, 0x70).channel(2)
        self.assertIsNone(find(Mux(bus, 0x70).channel(0)))
        self.assertEqual(find(c), 0x3C)

    def test_two_panels_each_page_on_its_channel(self):
        bus = FakeMuxBus({0: (0x3C,), 1: (0x3C,)})
        panels, msg = open_panels(bus)
        self.assertEqual(len(panels), 2)
        self.assertIn("ch 0, ch 1", msg)
        bus.writes.clear()
        a, b = panels
        a.flush_step()  # cmd + data, both on ch 0: one select
        a.flush_step()  # still ch 0: no select
        b.flush_step()  # switch to ch 1
        sel = [w[1][0] for w in bus.writes if w[0] == 0x70]
        self.assertEqual(sel, [1 << 0, 1 << 1])  # boot scan left the mux on ch 7
        self.assertEqual(len([w for w in bus.writes if w[0] == 0x3C]), 6)

    def test_selects_track_channel(self):
        bus = FakeMuxBus({0: (0x3C,), 1: (0x3C,)})
        a, b = open_panels(bus)[0]
        log = []
        real = bus.writeto

        def spy(addr, data):
            real(addr, data)
            if addr == 0x3C:
                log.append(bus.mask)
        bus.writeto = spy
        for _ in range(4):
            a.flush_step()
            b.flush_step()
        self.assertEqual(log, [1, 1, 2, 2] * 4)

    def test_dead_channel_disables_only_that_panel(self):
        bus = FakeMuxBus({0: (0x3C,), 1: (0x3C,)})
        a, b = open_panels(bus)[0]
        bus.dead.add(1)
        self.assertFalse(b.flush_step())
        self.assertFalse(b.alive)
        self.assertTrue(a.flush_step())
        self.assertTrue(a.alive)

    def test_panel_failing_init_is_skipped(self):
        bus = FakeMuxBus({0: (0x3C,), 1: (0x3C,)})
        bus.dead.add(0)
        panels, msg = open_panels(bus)
        self.assertEqual(len(panels), 1)
        self.assertIn("ch 0 failed", msg)


if __name__ == "__main__":
    unittest.main()
