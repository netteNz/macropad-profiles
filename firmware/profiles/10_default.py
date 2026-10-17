# Default: global media keys plus a few Windows shortcuts.
from adafruit_hid.consumer_control_code import ConsumerControlCode as CC
from adafruit_hid.keycode import Keycode as K

app = {
    "name": "Default",
    "order": 10,
    "macros": [
        # 1st row ----------
        (0x095E06, "Prev", [[CC.SCAN_PREVIOUS_TRACK]]),
        (0x544408, "Play", [[CC.PLAY_PAUSE]]),
        (0x095E06, "Next", [[CC.SCAN_NEXT_TRACK]]),
        # 2nd row ----------
        (0x000754, "Vol-", [[CC.VOLUME_DECREMENT]]),
        (0x540908, "Mute", [[CC.MUTE]]),
        (0x000754, "Vol+", [[CC.VOLUME_INCREMENT]]),
        # 3rd row ----------
        (0x034E59, "AudOut", [K.GUI, K.CONTROL, K.V]),  # Win11 output-device picker
        (0x4F0354, "Snip", [K.GUI, K.SHIFT, K.S]),
        (0x080808, "Lock", [K.GUI, K.L]),
        # 4th row ----------
        (0x034E59, "Desk", [K.GUI, K.D]),
        (0x540908, "TaskMg", [K.CONTROL, K.SHIFT, K.ESCAPE]),
        (0x00FF40, "Spotfy", [K.GUI, -K.GUI, 0.4, "spotify\n"]),
    ],
}
