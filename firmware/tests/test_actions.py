import unittest

import _paths  # noqa: F401
from actions import KNOB, Runner
from adafruit_hid.consumer_control_code import ConsumerControlCode as CC
from adafruit_hid.keycode import Keycode as K


class FakeKbd:
    def __init__(self, log):
        self.log = log
        self.down = set()

    def press(self, *codes):
        self.down.update(codes)
        self.log.append(("press",) + codes)

    def release(self, *codes):
        self.down.difference_update(codes)
        self.log.append(("release",) + codes)

    def release_all(self):
        self.down.clear()
        self.log.append(("release_all",))


class FakeCC:
    def __init__(self, log):
        self.log = log
        self.down = None

    def press(self, code):
        self.down = code
        self.log.append(("cc", code))

    def release(self):
        if self.down is not None:
            self.log.append(("cc_up",))
        self.down = None


class FakeLayout:
    def keycodes(self, ch):
        if ch == "\n":
            return [K.ENTER]
        if ch.isupper():
            return [K.SHIFT, getattr(K, ch)]
        return [getattr(K, ch.upper())]


class RunnerTest(unittest.TestCase):
    def setUp(self):
        self.log = []
        self.kbd = FakeKbd(self.log)
        self.cc = FakeCC(self.log)
        self.r = Runner(self.kbd, self.cc, FakeLayout())

    def test_chord_held_until_physical_release(self):
        self.r.start(0, [K.CONTROL, K.S])
        self.r.tick(0)
        self.assertEqual(self.kbd.down, {K.CONTROL, K.S})
        self.r.tick(500)
        self.assertEqual(self.kbd.down, {K.CONTROL, K.S})
        self.r.release(0)
        self.assertEqual(self.kbd.down, set())
        self.assertFalse(self.r.busy())

    def test_delay_does_not_block_other_slots(self):
        self.r.start(0, [K.A, 0.4, K.B])
        self.r.start(1, [K.C])
        self.r.tick(0)
        self.assertIn(K.C, self.kbd.down)
        self.assertNotIn(K.B, self.kbd.down)
        self.r.tick(399)
        self.assertNotIn(K.B, self.kbd.down)
        self.r.tick(400)
        self.assertIn(K.B, self.kbd.down)

    def test_release_during_delay_defers(self):
        self.r.start(0, [K.GUI, -K.GUI, 0.4, "ab"])
        self.r.tick(0)
        self.r.release(0)  # key up while the delay is pending
        self.assertTrue(self.r.busy())
        for t in (400, 410, 420):
            self.r.tick(t)
        self.assertFalse(self.r.busy())
        typed = [e for e in self.log if e[0] == "press"]
        self.assertEqual(typed, [("press", K.GUI), ("press", K.A), ("press", K.B)])
        self.assertEqual(self.kbd.down, set())

    def test_typing_one_char_per_tick_keeps_modifiers(self):
        self.r.start(0, [K.SHIFT, "a"])
        self.r.tick(0)
        self.assertIn(K.SHIFT, self.kbd.down)  # typing 'a' must not drop held shift
        self.r.release(0)
        self.r.tick(1)
        self.assertEqual(self.kbd.down, set())

    def test_consumer_held_then_released(self):
        self.r.start(0, [[CC.PLAY_PAUSE]])
        self.r.tick(0)
        self.assertEqual(self.cc.down, CC.PLAY_PAUSE)
        self.r.release(0)
        self.assertIsNone(self.cc.down)

    def test_host_action_runs_fallback(self):
        self.r.start(0, {"host": "shuffle", "fallback": [K.CONTROL, K.S]})
        self.r.tick(0)
        self.assertEqual(self.kbd.down, {K.CONTROL, K.S})

    def test_tap_releases_at_end(self):
        self.r.start(13, [[CC.PLAY_PAUSE]], tap=True)
        self.r.tick(0)
        self.assertIsNone(self.cc.down)
        self.assertIn(("cc", CC.PLAY_PAUSE), self.log)

    def test_knob_queue_runs_each_detent(self):
        for _ in range(3):
            self.r.queue(KNOB, [K.UP_ARROW])
        for t in range(5):
            self.r.tick(t)
        self.assertEqual(self.log.count(("press", K.UP_ARROW)), 3)
        self.assertEqual(self.kbd.down, set())

    def test_restart_slot_releases_previous(self):
        self.r.start(0, [K.A])
        self.r.tick(0)
        self.r.start(0, [K.B])
        self.assertNotIn(K.A, self.kbd.down)

    def test_explicit_release_item(self):
        self.r.start(0, [K.GUI, -K.GUI])
        self.r.tick(0)
        self.assertEqual(self.kbd.down, set())


if __name__ == "__main__":
    unittest.main()
