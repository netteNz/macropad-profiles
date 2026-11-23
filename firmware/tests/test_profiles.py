import importlib
import os
import unittest

import _paths
import profile_loader as pl
from adafruit_hid.keycode import Keycode as K

PROFILES_DIR = os.path.join(_paths.FIRMWARE, "profiles")


def _app(**kw):
    app = {"name": "T", "macros": [(0, "k%d" % i, [K.A]) for i in range(12)]}
    app.update(kw)
    return app


def _load(apps):
    """load_all over an in-memory {filename: app} dict."""
    return pl.load_all(listdir=lambda _: list(apps), importer=lambda m: apps[m + ".py"])


class ValidateTest(unittest.TestCase):
    def test_defaults(self):
        p = pl.validate(_app(), "t.py")
        self.assertEqual(p["knob"], "system_volume")
        self.assertEqual(p["press"], [[pl.PLAY_PAUSE]])
        self.assertEqual(p["leds"], "static")
        self.assertEqual(p["order"], 0)
        self.assertEqual(p["apps"], [])

    def test_needs_12_macros(self):
        with self.assertRaises(ValueError):
            pl.validate(_app(macros=[(0, "a", [K.A])] * 11), "t.py")

    def test_rejects_callables(self):
        bad = _app()
        bad["macros"][0] = (0, "x", [print])
        with self.assertRaises(ValueError):
            pl.validate(bad, "t.py")
        with self.assertRaises(ValueError):
            pl.validate(_app(press={"host": "x", "fallback": [print]}), "t.py")

    def test_rejects_non_finite_delays(self):
        for bad_delay in (float("nan"), float("inf"), float("-inf")):
            for action in ([K.A, bad_delay], [[0xCD, bad_delay]]):
                app = _app()
                app["macros"][0] = (0, "x", action)
                with self.assertRaises(ValueError):
                    pl.validate(app, "t.py")
        app = _app()
        app["macros"][0] = (0, "x", [K.A, 0.2, [0xCD, 0.1]])
        pl.validate(app, "t.py")  # finite delays still fine

    def test_label_truncated_and_ascii(self):
        app = _app()
        app["macros"][0] = (0, "Arcángel", [K.A])
        self.assertEqual(pl.validate(app, "t.py")["macros"][0][1], "Arc?ng")

    def test_single_keycode_action_wrapped(self):
        app = _app()
        app["macros"][0] = (0, "a", K.A)
        self.assertEqual(pl.validate(app, "t.py")["macros"][0][2], [K.A])

    def test_knob_kinds(self):
        self.assertEqual(pl.validate(_app(knob="spotify_volume"), "t")["knob"], "spotify_volume")
        k = pl.validate(_app(knob=("keys", [K.UP_ARROW], [K.DOWN_ARROW])), "t")["knob"]
        self.assertEqual(k, ("keys", [K.UP_ARROW], [K.DOWN_ARROW]))
        with self.assertRaises(ValueError):
            pl.validate(_app(knob="loud"), "t")

    def test_apps_lowercased(self):
        self.assertEqual(pl.validate(_app(apps=["Traktor.EXE"]), "t")["apps"], ["traktor.exe"])


class LoadAllTest(unittest.TestCase):
    def test_sort_by_order_then_filename(self):
        ps = _load({
            "b.py": _app(name="B", order=5),
            "a.py": _app(name="A", order=5),
            "z.py": _app(name="Z", order=1),
        })
        self.assertEqual([p["name"] for p in ps], ["Z", "A", "B"])

    def test_bad_file_skipped(self):
        ps = _load({"good.py": _app(name="G"), "bad.py": {"name": "X"}})
        self.assertEqual([p["name"] for p in ps], ["G"])

    def test_ignores_init_dotfiles_and_other_ext(self):
        ps = _load({"__init__.py": None, "._a.py": None, "notes.txt": None, "a.py": _app()})
        self.assertEqual(len(ps), 1)

    def test_real_profile_files_validate(self):
        names = [f for f in os.listdir(PROFILES_DIR) if f.endswith(".py") and f[0] not in "_."]
        ps = pl.load_all(
            path=PROFILES_DIR,
            importer=lambda m: importlib.import_module("profiles." + m).app,
        )
        self.assertEqual(len(ps), len(names))
        self.assertEqual(ps[0]["name"], "Spotify")  # fresh board boots like the old script


class NvmTest(unittest.TestCase):
    def setUp(self):
        self.ps = [{"name": "A"}, {"name": "Spotify"}]

    def test_roundtrip(self):
        nvm = bytearray(b"\xff" * 64)
        pl.save_last("Spotify", nvm)
        self.assertEqual(pl.load_last(self.ps, nvm), 1)

    def test_long_name_survives_truncation(self):
        long_name = "Very Long Profile Name For Testing NVM"  # > 30 bytes
        ps = self.ps + [{"name": long_name}]
        nvm = bytearray(b"\xff" * 64)
        pl.save_last(long_name, nvm)
        self.assertEqual(pl.load_last(ps, nvm), 2)

    def test_blank_or_unknown_falls_back(self):
        self.assertEqual(pl.load_last(self.ps, bytearray(b"\xff" * 64)), 0)
        nvm = bytearray(b"\xff" * 64)
        pl.save_last("Gone", nvm)
        self.assertEqual(pl.load_last(self.ps, nvm), 0)

    def test_no_write_when_unchanged(self):
        class Spy(bytearray):
            writes = 0

            def __setitem__(self, k, v):
                Spy.writes += 1
                super().__setitem__(k, v)

        nvm = Spy(b"\xff" * 64)
        pl.save_last("A", nvm)
        pl.save_last("A", nvm)
        self.assertEqual(Spy.writes, 1)


if __name__ == "__main__":
    unittest.main()
