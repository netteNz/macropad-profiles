# Windows: window snapping, virtual desktops and shell shortcuts.
# Knob switches virtual desktops; knob press opens Task View.
from adafruit_hid.keycode import Keycode as K

app = {
    "name": "Windows",
    "order": 30,
    "knob": (
        "keys",
        [K.GUI, K.CONTROL, K.RIGHT_ARROW],  # clockwise: next desktop
        [K.GUI, K.CONTROL, K.LEFT_ARROW],  # counter-clockwise: previous desktop
    ),
    "press": [K.GUI, K.TAB],  # Task View
    "leds": "static",
    "macros": [
        # 1st row ----------
        (0x0040FF, "SnapL", [K.GUI, K.LEFT_ARROW]),
        (0x0040FF, "Max", [K.GUI, K.UP_ARROW]),
        (0x0040FF, "SnapR", [K.GUI, K.RIGHT_ARROW]),
        # 2nd row ----------
        (0x0040FF, "Min", [K.GUI, K.DOWN_ARROW]),
        (0xFF0020, "Close", [K.ALT, K.F4]),
        (0x00C060, "NewDsk", [K.GUI, K.CONTROL, K.D]),
        # 3rd row ----------
        (0xFFA000, "Explr", [K.GUI, K.E]),
        (0xA000FF, "Clip", [K.GUI, K.V]),  # clipboard history
        (0xFFD000, "Emoji", [K.GUI, K.PERIOD]),
        # 4th row ----------
        (0x4F0354, "Snip", [K.GUI, K.SHIFT, K.S]),
        (0x404040, "Settng", [K.GUI, K.I]),
        (0x080808, "Lock", [K.GUI, K.L]),
    ],
}
