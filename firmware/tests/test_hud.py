import os
import unittest

import _paths  # noqa: F401
from panel import fonts
from panel.canvas import PAGES, Canvas, W, text_width
from panel.hud import (CLOCK, DWELL_MS, PREEMPT_MS, SLIDE_MS, STATUS, WEATHER,
                       HudScene)
from panel.transport import Transport

BDF_DIR = r"D:\code\boards\oled\oled-bonnet\fonts"


class FontTest(unittest.TestCase):
    def test_tables_complete(self):
        for f in (fonts.SPLEEN, fonts.SMALL):
            self.assertEqual(len(f.GLYPHS), (f.LAST - f.FIRST + 1) * f.W)
            self.assertTrue(all(b < (1 << f.H) for b in f.GLYPHS))

    def test_space_is_blank_and_letters_are_not(self):
        for f in (fonts.SPLEEN, fonts.SMALL):
            self.assertEqual(sum(f.GLYPHS[:f.W]), 0)
            o = (ord("A") - f.FIRST) * f.W
            self.assertGreater(sum(f.GLYPHS[o:o + f.W]), 0)

    @unittest.skipUnless(os.path.isdir(BDF_DIR), "oled-bonnet fonts not here")
    def test_generated_file_is_current(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "build_fonts", os.path.join(_paths.FIRMWARE, "..", "tools", "build_fonts.py"))
        bf = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bf)
        w, h, g = bf.parse(os.path.join(BDF_DIR, "spleen-5x8.bdf"))
        o = (ord("g") - 32) * 5
        self.assertEqual(list(fonts.SPLEEN.GLYPHS[o:o + 5]), g[ord("g")])

    def test_canvas_text_with_font(self):
        c = Canvas()
        end = c.text(0, 0, "AB", fonts.SPLEEN)
        self.assertEqual(end, 10)
        self.assertEqual(text_width("AB", fonts.SMALL), 8)
        self.assertEqual(bytes(c.buf[:5]), fonts.SPLEEN.GLYPHS[(65 - 32) * 5:(66 - 32) * 5])


class HudTest(unittest.TestCase):
    def setUp(self):
        self.c = Canvas()
        self.t = Transport()
        self.s = HudScene(self.c, self.t)
        self.c.dirty = 0

    def tick(self, now):
        drew = self.s.tick(now)
        self.c.dirty = 0  # the panel takes the whole frame
        return drew

    def run_to(self, start, end, step=10):
        for now in range(start, end, step):
            self.tick(now)

    def frame_of(self, view, now=0):
        s = HudScene(Canvas(), self.t)
        s.hud = self.s.hud
        s._render(view, now)
        return bytes(s._new)

    def test_starts_on_clock_without_slide(self):
        self.assertTrue(self.tick(0))
        self.assertEqual(self.s.shown, CLOCK)
        self.assertIsNone(self.s._slide_at)

    def test_rotates_after_dwell_with_slide(self):
        self.tick(0)
        self.run_to(10, DWELL_MS - 50)
        self.assertEqual(self.s.shown, CLOCK)
        self.run_to(DWELL_MS - 50, DWELL_MS + 10)
        self.assertIsNotNone(self.s._slide_at)  # sliding to weather
        self.run_to(DWELL_MS + 10, DWELL_MS + SLIDE_MS + 100)
        self.assertEqual(self.s.shown, WEATHER)

    def test_slide_lands_byte_identical(self):
        self.tick(0)
        self.run_to(10, DWELL_MS + SLIDE_MS + 100)
        self.assertEqual(bytes(self.c.buf), self.frame_of(WEATHER, DWELL_MS + SLIDE_MS + 100))

    def test_slide_mid_frame_mixes_both(self):
        self.tick(0)
        old = bytes(self.c.buf)
        self.run_to(10, DWELL_MS)
        self.tick(DWELL_MS)  # picks weather, slide starts at offset 0
        self.tick(DWELL_MS + SLIDE_MS // 2)
        self.assertIsNotNone(self.s._slide_at)
        new = self.frame_of(WEATHER, DWELL_MS)
        buf = bytes(self.c.buf)
        self.assertNotEqual(buf, old)
        self.assertNotEqual(buf, new)

    def test_key_preempts_to_status_then_returns(self):
        self.tick(0)
        self.s.key(0, 1000)
        self.run_to(1000, 1000 + SLIDE_MS + 100)
        self.assertEqual(self.s.shown, STATUS)
        self.run_to(1400, 1000 + PREEMPT_MS + SLIDE_MS + 200)
        self.assertEqual(self.s.shown, CLOCK)
        # and the clock gets a fresh dwell after coming back
        back = 1000 + PREEMPT_MS + SLIDE_MS + 200
        self.run_to(back, back + DWELL_MS - 500)
        self.assertEqual(self.s.shown, CLOCK)

    def test_repeated_actions_extend_preempt(self):
        self.tick(0)
        for n in range(0, 10000, 1000):
            self.s.knob(1, 1000 + n)
            self.run_to(1000 + n, 2000 + n)
        self.assertEqual(self.s.shown, STATUS)

    def test_status_follows_transport(self):
        self.tick(0)
        self.s.key(1, 100)
        self.run_to(100, 600)
        before = bytes(self.c.buf)
        self.t.on_action({"host": "shuffle", "fallback": []}, 600)
        self.s.key(6, 600)
        self.run_to(600, 700)
        self.assertNotEqual(bytes(self.c.buf), before)

    def test_unchanged_view_sends_nothing(self):
        self.tick(0)
        self.c.dirty = 0
        for now in range(10, 3000, 10):
            self.s.tick(now)
        self.assertEqual(self.c.dirty, 0)  # clock placeholder, paused: static

    def test_waits_for_panel(self):
        self.s.tick(0)  # first frame left unsent
        self.assertFalse(self.s.tick(DWELL_MS + 100))

    def test_volume_turn_then_net(self):
        h = self.s.hud
        self.s.knob(2, 0)
        self.s.knob(1, 100)
        self.assertEqual(h.vol_turn, 6)
        self.s.knob(-1, 5000)
        self.assertEqual(h.vol_turn, -2)
        self.assertEqual(h.vol_net, 4)

    def test_song_strip_bar_only_with_length(self):
        self.t.play_toggle(0)
        no_len = self.frame_of(CLOCK, 1000)
        self.t.duration_ms = 4000
        with_len = self.frame_of(CLOCK, 1000)
        last = (PAGES - 1) * W
        self.assertNotEqual(no_len[last:], with_len[last:])


if __name__ == "__main__":
    unittest.main()
