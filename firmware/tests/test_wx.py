import unittest

import _paths  # noqa: F401
from panel import seg7, wx
from panel.canvas import Canvas, W
from panel.demo import SCENES, Demo
from panel.hostdata import WX_STALE_MS, HostData, hhmm12
from panel.hud import CLOCK, WEATHER, HudScene
from panel.transport import Transport


def lit(c, x, y):
    return bool(c.buf[(y >> 3) * W + x] & (1 << (y & 7)))


def count(c, x0, y0, w, h):
    return sum(lit(c, x, y) for x in range(x0, x0 + w) for y in range(y0, y0 + h))


class HostDataTest(unittest.TestCase):
    def test_no_time_until_synced(self):
        h = HostData()
        self.assertIsNone(h.local(0))
        h.set_time(2026, 11, 25, 20, 59, 45, 2, 1000)
        self.assertEqual(h.local(1000), (2026, 11, 25, 2, 20, 59, 45))
        self.assertEqual(h.local(16000)[4:], (21, 0, 0))

    def test_midnight_rolls_date_month_year(self):
        h = HostData()
        h.set_time(2026, 12, 31, 23, 59, 59, 3, 0)
        self.assertEqual(h.local(2000), (2027, 1, 1, 4, 0, 0, 1))
        h.set_time(2028, 2, 28, 23, 59, 59, 0, 0)  # leap year
        self.assertEqual(h.local(1000)[:3], (2028, 2, 29))

    def test_weather_goes_stale(self):
        h = HostData()
        h.set_weather(0, 78, 80, 84, 72, 0, 1, 0)
        self.assertIsNotNone(h.weather(WX_STALE_MS - 1))
        self.assertIsNone(h.weather(WX_STALE_MS))

    def test_hhmm12(self):
        self.assertEqual(hhmm12(6 * 60 + 58), "6:58")
        self.assertEqual(hhmm12(0), "12:00")
        self.assertEqual(hhmm12(17 * 60 + 41), "5:41")


class Seg7Test(unittest.TestCase):
    def test_width_matches_drawing(self):
        c = Canvas()
        end = seg7.text(c, 0, 16, "12:34")
        self.assertEqual(end, seg7.width("12:34"))

    def test_eight_lights_more_than_one(self):
        a, b = Canvas(), Canvas()
        seg7.digit(a, 0, 16, "8")
        seg7.digit(b, 0, 16, "1")
        self.assertGreater(count(a, 0, 16, 14, 30), 2 * count(b, 0, 16, 14, 30))

    def test_colon_can_blink(self):
        a, b = Canvas(), Canvas()
        seg7.text(a, 0, 16, "1:00")
        seg7.text(b, 0, 16, "1:00", colon=False)
        self.assertNotEqual(bytes(a.buf), bytes(b.buf))


class WxTest(unittest.TestCase):
    def test_icon_mapping(self):
        self.assertEqual(wx.icon_for(0, 1), wx.SUN)
        self.assertEqual(wx.icon_for(0, 0), wx.NIGHT)
        self.assertEqual(wx.icon_for(2, 0), wx.NIGHT_PARTLY)
        self.assertEqual(wx.icon_for(45, 1), wx.FOG)
        self.assertEqual(wx.icon_for(65, 1), wx.HEAVY)
        self.assertEqual(wx.icon_for(53, 1), wx.RAIN)
        self.assertEqual(wx.icon_for(75, 1), wx.SNOW)
        self.assertEqual(wx.icon_for(96, 1), wx.STORM)
        self.assertEqual(wx.icon_for(3, 1), wx.CLOUDY)

    def test_moon_names(self):
        self.assertEqual(wx.moon_name(0), "NEW MOON")
        self.assertEqual(wx.moon_name(252), "NEW MOON")
        self.assertEqual(wx.moon_name(64), "FIRST QTR")
        self.assertEqual(wx.moon_name(128), "FULL MOON")
        self.assertEqual(wx.moon_name(30), "WAX CRES")
        self.assertEqual(wx.moon_name(100), "WAX GIBB")
        self.assertEqual(wx.moon_name(160), "WAN GIBB")
        self.assertEqual(wx.moon_name(225), "WAN CRES")

    def moon_lit(self, cycle):
        c = Canvas()
        wx.moon(c, 30, 40, 9, cycle)
        return c, count(c, 21, 31, 19, 19)

    def test_moon_phases(self):
        _, new = self.moon_lit(0)
        _, quarter = self.moon_lit(64)
        _, full = self.moon_lit(128)
        self.assertLess(new, quarter)
        self.assertLess(quarter, full)
        c, _ = self.moon_lit(64)  # first quarter: right half lit
        self.assertTrue(lit(c, 35, 40))
        self.assertFalse(lit(c, 25, 40))
        c, _ = self.moon_lit(192)  # last quarter: left half lit
        self.assertTrue(lit(c, 25, 40))
        self.assertFalse(lit(c, 35, 40))

    def test_every_icon_stays_in_its_cell_and_animates(self):
        for icon in range(10):
            frames = set()
            for t in range(0, 6000, 250):
                c = Canvas()
                wx.draw(c, icon, 40, 18, t, 96)
                outside = count(c, 0, 0, W, 64) - count(c, 40, 18, 32, 32)
                self.assertEqual(outside, 0, "icon %d leaks out of its cell" % icon)
                frames.add(bytes(c.buf))
            self.assertGreater(len(frames), 1, "icon %d doesn't move" % icon)


class HudDataTest(unittest.TestCase):
    def setUp(self):
        self.host = HostData()
        self.t = Transport()
        self.s = HudScene(Canvas(), self.t, self.host)

    def frame(self, v, now):
        self.s._render(v, now)
        return Canvas(bytearray(self.s._new))

    def test_clock_without_and_with_time(self):
        blank = self.frame(CLOCK, 0)
        self.host.set_time(2026, 11, 25, 20, 59, 45, 2, 0)
        timed = self.frame(CLOCK, 0)
        self.assertNotEqual(bytes(blank.buf), bytes(timed.buf))
        # the yellow band now has the date instead of "CLOCK"
        self.assertNotEqual(bytes(blank.buf[:256]), bytes(timed.buf[:256]))

    def test_weather_needs_data_and_animates(self):
        self.host.set_weather(95, 73, 79, 82, 70, 80, 1, 0)
        a = self.frame(WEATHER, 50)
        b = self.frame(WEATHER, 230)  # storm bolt flash on/off
        self.assertNotEqual(bytes(a.buf), bytes(b.buf))

    def test_night_strip_shows_moon(self):
        self.host.set_weather(0, 64, 64, 84, 72, 0, 0, 0)
        no_moon = self.frame(WEATHER, 0)
        self.host.set_moon(100, 80, 418, 1061)
        with_moon = self.frame(WEATHER, 0)
        last = 7 * W
        self.assertNotEqual(bytes(no_moon.buf[last:]), bytes(with_moon.buf[last:]))

    def test_demo_cycles_all_scenes(self):
        d = Demo(self.host, 0)
        seen = set()
        for n in range(len(SCENES)):
            d.tick(n * 3000)
            seen.add(self.host.wx[0:1] + self.host.wx[6:7])
        self.assertEqual(len(seen), len(set(s[0:1] + s[6:7] for s in SCENES)))
        self.assertTrue(self.host.has_time())


if __name__ == "__main__":
    unittest.main()
