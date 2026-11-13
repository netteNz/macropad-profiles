# Discord. All keys are Discord's built-in shortcuts, so they need the Discord
# window focused. To make Mute/Deafen work from any app, add them in Discord >
# Settings > Keybinds and press the pad key when it asks for the shortcut.
# Knob: system volume (default).
from adafruit_hid.keycode import Keycode as K

app = {
    "name": "Discord",
    "order": 50,
    "leds": "static",
    "macros": [
        # 1st row ----------  voice
        (0xFF0020, "Mute", [K.CONTROL, K.SHIFT, K.M]),
        (0xFF0020, "Deafen", [K.CONTROL, K.SHIFT, K.D]),
        (0xA000FF, "Sndbrd", [K.CONTROL, K.SHIFT, K.B]),  # soundboard
        # 2nd row ----------  calls
        (0x00C060, "Answer", [K.CONTROL, K.ENTER]),
        (0xFF4000, "Declin", [K.ESCAPE]),
        (0x00C060, "Call", [K.CONTROL, K.QUOTE]),  # start call in DM/group
        # 3rd row ----------  navigation
        (0x5865F2, "Up", [K.ALT, K.UP_ARROW]),  # previous channel
        (0x5865F2, "Search", [K.CONTROL, K.K]),  # quick switcher
        (0x5865F2, "Down", [K.ALT, K.DOWN_ARROW]),  # next channel
        # 4th row ----------
        (0x5865F2, "Unread", [K.ALT, K.SHIFT, K.UP_ARROW]),  # previous unread channel
        (0x00FF40, "Open", [K.GUI, -K.GUI, 0.4, "discord\n"]),
        (0x404040, "MarkRd", [K.ESCAPE]),  # mark channel read
    ],
}
