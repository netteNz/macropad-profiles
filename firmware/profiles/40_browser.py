# Browser: shortcuts shared by Chrome, Edge and Firefox, except Incog
# (Ctrl+Shift+N) which is Chrome/Edge only; Firefox uses Ctrl+Shift+P.
# Knob switches tabs; knob press stays Play/Pause (default).
from adafruit_hid.keycode import Keycode as K

app = {
    "name": "Browser",
    "order": 40,
    "knob": (
        "keys",
        [K.CONTROL, K.TAB],  # clockwise: next tab
        [K.CONTROL, K.SHIFT, K.TAB],  # counter-clockwise: previous tab
    ),
    "leds": "static",
    "macros": [
        # 1st row ----------
        (0x0080FF, "Back", [K.ALT, K.LEFT_ARROW]),
        (0x00C060, "Reload", [K.F5]),
        (0x0080FF, "Fwd", [K.ALT, K.RIGHT_ARROW]),
        # 2nd row ----------
        (0x00C060, "NewTab", [K.CONTROL, K.T]),
        (0xFF0020, "Close", [K.CONTROL, K.W]),
        (0xFFA000, "Reopen", [K.CONTROL, K.SHIFT, K.T]),
        # 3rd row ----------
        (0xA000FF, "Addr", [K.CONTROL, K.L]),
        (0xA000FF, "Find", [K.CONTROL, K.F]),
        (0x404040, "Incog", [K.CONTROL, K.SHIFT, K.N]),
        # 4th row ----------
        (0xFFD000, "Zoom-", [K.CONTROL, K.MINUS]),
        (0xFFD000, "Zoom0", [K.CONTROL, K.ZERO]),
        (0xFFD000, "Zoom+", [K.CONTROL, K.EQUALS]),
    ],
}
