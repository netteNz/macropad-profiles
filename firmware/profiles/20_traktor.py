# Traktor Pro 4. Bindings are placeholders until they're copied from the
# Traktor keyboard mapping (Preferences > Controller Manager). Empty actions
# do nothing.
from adafruit_hid.keycode import Keycode as K

app = {
    "name": "Traktor",
    "order": 20,
    "apps": ["traktor.exe"],
    "knob": ("keys", [K.UP_ARROW], [K.DOWN_ARROW]),  # TODO: confirm browser scroll keys
    "leds": "static",
    "macros": [
        # 1st row ----------
        (0x00FF40, "Play", []),  # TODO
        (0xFF8000, "Cue", []),  # TODO: hold-to-preview works, keys stay down while held
        (0x0080FF, "Sync", []),  # TODO
        # 2nd row ----------
        (0xFF0040, "1stMk", []),  # TODO: jump to first marker
        (0x000000, "", []),
        (0x000000, "", []),
        # 3rd row ----------
        (0x000000, "", []),
        (0x000000, "", []),
        (0x000000, "", []),
        # 4th row ----------
        (0x000000, "", []),
        (0x000000, "", []),
        (0x000000, "", []),
    ],
}
