import unittest

import _paths  # noqa: F401
import profile_loader as pl
from adafruit_hid.keycode import Keycode as K
from panel.art import BLUE_PAGES
from panel.canvas import Canvas, W
from panel.spotify import (ARM_INNER, ARM_OUTER, ARM_PARK, CX, CY, LABEL, RIM,
                           RecordScene, arm_tip)
from panel.transport import NEXT, PLAY_PAUSE, PREV, Transport


class TransportTest(unittest.TestCase):
    def setUp(self):
        self.t = Transport()

    def test_starts_paused_at_zero(self):
        self.assertFalse(self.t.playing)
        self.assertEqual(self.t.elapsed(5000), 0)

    def test_play_pause_counts_only_while_playing(self):
        t = self.t
        t.play_toggle(1000)
        self.assertEqual(t.elapsed(3000), 2000)
        t.play_toggle(3000)
        self.assertEqual(t.elapsed(9000), 2000)
        t.play_toggle(9000)
        self.assertEqual(t.elapsed(10000), 3000)

    def test_track_resets_and_plays(self):
        t = self.t
        t.play_toggle(0)
        t.track(4000)
        self.assertTrue(t.playing)
        self.assertEqual(t.track_n, 1)
        self.assertEqual(t.elapsed(4500), 500)

    def test_seek_clamps(self):
        t = self.t
        t.play_toggle(0)
        t.seek(-5000, 2000)
        self.assertEqual(t.elapsed(2000), 0)
        t.duration_ms = 10000
        t.seek(60000, 2000)
        self.assertEqual(t.elapsed(5000), 10000)

    def test_progress_needs_duration(self):
        t = self.t
        t.play_toggle(0)
        self.assertIsNone(t.progress(1000, 100))
        t.duration_ms = 4000
        self.assertEqual(t.progress(1000, 100), 25)

    def test_on_action_reads_profile_data(self):
        t = self.t
        t.on_action([[PLAY_PAUSE]], 0)
        self.assertTrue(t.playing)
        t.on_action([[NEXT]], 100)
        t.on_action([[PREV]], 200)
        self.assertEqual(t.track_n, 2)
        t.on_action({"host": "seek +5000", "fallback": [K.SHIFT, K.RIGHT_ARROW]}, 200)
        self.assertEqual(t.elapsed(200), 5000)
        t.on_action({"host": "seek nope", "fallback": []}, 200)
        t.on_action([K.CONTROL, K.S, 0.1, "x"], 200)  # unrelated: no change
        self.assertTrue(t.playing)
        self.assertEqual(t.track_n, 2)

    def test_real_spotify_profile_keys(self):
        p = pl.validate(__import__("profiles.00_spotify", fromlist=["app"]).app, "00_spotify.py")
        self.assertEqual(p["panel"], "spotify")
        t = self.t
        t.on_action(p["macros"][1][2], 0)  # Play
        self.assertTrue(t.playing)
        t.on_action(p["macros"][2][2], 0)  # Next
        self.assertEqual(t.track_n, 1)
        t.on_action(p["macros"][11][2], 0)  # Seek+
        self.assertEqual(t.elapsed(0), 5000)
        t.on_action(p["press"], 0)  # knob press = Play/Pause
        self.assertFalse(t.playing)


class PanelKeyTest(unittest.TestCase):
    def _app(self, **kw):
        app = {"name": "T", "macros": [(0, "k", [K.A])] * 12}
        app.update(kw)
        return app

    def test_default_and_known(self):
        self.assertEqual(pl.validate(self._app(), "t.py")["panel"], "art")
        self.assertEqual(pl.validate(self._app(panel="spotify"), "t.py")["panel"], "spotify")

    def test_unknown_rejected(self):
        with self.assertRaises(ValueError):
            pl.validate(self._app(panel="lava"), "t.py")


def lit(c, x, y):
    return bool(c.buf[(y >> 3) * W + x] & (1 << (y & 7)))


class RecordSceneTest(unittest.TestCase):
    def setUp(self):
        self.c = Canvas()
        self.t = Transport()
        self.s = RecordScene(self.c, self.t)
        self.s.set_title("Spotify")
        self.c.dirty = 0

    def tick(self, now):
        drew = self.s.tick(now)
        self.c.dirty &= ~BLUE_PAGES  # the panel takes the whole frame
        return drew

    def run_to(self, start, end, step=10):
        for now in range(start, end, step):
            self.tick(now)

    def test_draws_disc_inside_blue_area(self):
        self.assertTrue(self.tick(0))
        self.assertTrue(lit(self.c, CX + RIM, CY))
        self.assertFalse(lit(self.c, CX, CY))  # spindle hole
        self.assertTrue(lit(self.c, CX + LABEL - 1, CY))

    def test_title_and_icon_stay_in_yellow(self):
        before = bytes(self.c.buf[:256])
        self.t.play_toggle(0)
        self.tick(0)
        self.assertNotEqual(bytes(self.c.buf[:256]), before)  # icon changed
        self.assertTrue(self.c.dirty & 0b11)

    def test_paused_disc_stays_still_and_arm_parks(self):
        self.run_to(0, 1000)
        self.assertEqual(self.s.speed, 0)
        self.assertEqual(self.s.arm, ARM_PARK)
        self.assertFalse(self.s.busy(1000))

    def test_play_spins_and_arm_swings_on(self):
        self.t.play_toggle(0)
        self.run_to(0, 1000)
        self.assertEqual(self.s.speed, 142 * 16)
        self.assertEqual(self.s.arm, ARM_OUTER)
        rot = self.s.rot16
        self.run_to(1000, 1500)
        self.assertNotEqual(self.s.rot16, rot)

    def test_pause_spins_down(self):
        self.t.play_toggle(0)
        self.run_to(0, 1000)
        self.t.play_toggle(1000)
        self.run_to(1000, 2000)
        self.assertEqual(self.s.speed, 0)
        self.assertEqual(self.s.arm, ARM_PARK)

    def test_track_change_spins_up(self):
        self.t.play_toggle(0)
        self.run_to(0, 1000)
        self.t.track(1000)
        self.run_to(1000, 1300)
        self.assertGreater(self.s.speed, 142 * 16 * 2)
        self.run_to(1300, 2500)
        self.assertEqual(self.s.speed, 142 * 16)

    def test_arm_follows_progress_with_known_length(self):
        t = self.t
        t.duration_ms = 4000
        t.play_toggle(0)
        self.run_to(0, 2000)
        mid = ARM_OUTER + (ARM_INNER - ARM_OUTER) // 2
        self.assertLessEqual(abs(self.s.arm - mid), 16)
        self.run_to(2000, 4500)
        self.assertEqual(self.s.arm, ARM_INNER)

    def test_arm_geometry(self):
        def dist2(a):
            x, y = arm_tip(a)
            return (x - CX) ** 2 + (y - CY) ** 2
        self.assertGreater(dist2(ARM_PARK), (RIM + 3) ** 2)  # off the disc
        self.assertLessEqual(dist2(ARM_OUTER), RIM ** 2)  # on the grooves
        self.assertGreater(dist2(ARM_INNER), LABEL ** 2)  # stops at the label
        for a in (ARM_PARK, ARM_OUTER, ARM_INNER):
            x, y = arm_tip(a)
            self.assertTrue(0 <= x < W and 16 <= y < 64)

    def test_volume_arc_shows_then_hides(self):
        self.tick(0)
        top = (CX, CY - 23)
        self.s.knob(3, 100)
        self.tick(100)
        self.assertTrue(lit(self.c, *top))
        self.assertEqual(self.s.vol, 6)
        self.run_to(110, 1400)
        self.assertFalse(lit(self.c, *top))
        self.s.knob(-1, 2000)  # a new turn starts from zero
        self.assertEqual(self.s.vol, -2)

    def test_frame_pacing(self):
        self.assertTrue(self.tick(0))
        self.assertFalse(self.tick(10))  # idle: 66 ms frames
        self.assertTrue(self.tick(70))
        self.s.tick(140)  # leave the frame unsent
        self.assertFalse(self.s.tick(300))  # waits for the panel


if __name__ == "__main__":
    unittest.main()
