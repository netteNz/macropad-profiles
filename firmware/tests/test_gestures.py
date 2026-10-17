import unittest

import _paths  # noqa: F401
from gestures import Encoder


class GestureTest(unittest.TestCase):
    def setUp(self):
        self.e = Encoder()

    def test_turn_while_up(self):
        self.assertEqual(self.e.rotate(2), [("turn", 2)])
        self.assertEqual(self.e.rotate(0), [])

    def test_short_press(self):
        self.e.button(True, 1000)
        self.assertEqual(self.e.button(False, 1200), ("press",))

    def test_long_press(self):
        self.e.button(True, 1000)
        self.assertEqual(self.e.button(False, 1600), ("long_press",))

    def test_hold_turn_commits_only(self):
        self.e.button(True, 1000)
        self.assertEqual(self.e.rotate(1), [("picker_open",), ("picker_move", 1)])
        self.assertEqual(self.e.rotate(-1), [("picker_move", -1)])
        self.assertEqual(self.e.button(False, 1100), ("picker_commit",))

    def test_hold_past_threshold_then_turn(self):
        self.e.button(True, 1000)
        events = self.e.rotate(1)  # turned at ~1700 ms in real life
        self.assertNotIn(("long_press",), events)
        self.assertEqual(self.e.button(False, 2500), ("picker_commit",))

    def test_turned_flag_resets(self):
        self.e.button(True, 0)
        self.e.rotate(1)
        self.e.button(False, 100)
        self.e.button(True, 200)
        self.assertEqual(self.e.button(False, 300), ("press",))

    def test_stray_release_ignored(self):
        self.assertIsNone(self.e.button(False, 0))

    def test_ticks_wraparound(self):
        top = (1 << 29) - 100
        self.e.button(True, top)
        self.assertEqual(self.e.button(False, 50), ("press",))  # 150 ms later


if __name__ == "__main__":
    unittest.main()
