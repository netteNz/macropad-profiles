# Spotify: port of the original standalone script.
# Rows 1-2 are system media keys. Rows 3-4 go to the host bridge once it
# exists; until then (or with the host down) they fall back to Spotify's
# keyboard shortcuts, which need the Spotify window focused.
from adafruit_hid.consumer_control_code import ConsumerControlCode as CC
from adafruit_hid.keycode import Keycode as K

app = {
    "name": "Spotify",
    "order": 0,
    "apps": ["spotify.exe"],
    "knob": "spotify_volume",
    "leds": "rainbow",
    "macros": [
        # 1st row ----------
        (0x00FF40, "Prev", [[CC.SCAN_PREVIOUS_TRACK]]),
        (0x00FF40, "Play", [[CC.PLAY_PAUSE]]),
        (0x00FF40, "Next", [[CC.SCAN_NEXT_TRACK]]),
        # 2nd row ----------
        (0x0040FF, "Vol-", [[CC.VOLUME_DECREMENT]]),
        (0x0040FF, "Mute", [[CC.MUTE]]),
        (0x0040FF, "Vol+", [[CC.VOLUME_INCREMENT]]),
        # 3rd row ----------
        (0xFF8000, "Shufl", {"host": "shuffle", "fallback": [K.CONTROL, K.S]}),
        (0xFF8000, "Repeat", {"host": "repeat", "fallback": [K.CONTROL, K.R]}),
        (0xFF0040, "Like", {"host": "like", "fallback": [K.ALT, K.SHIFT, K.B]}),
        # 4th row ----------
        (0x8000FF, "Seek-", {"host": "seek -5000", "fallback": [K.SHIFT, K.LEFT_ARROW]}),
        (0x00FF40, "Open", {"host": "open", "fallback": [K.GUI, -K.GUI, 0.4, "spotify\n"]}),
        (0x8000FF, "Seek+", {"host": "seek +5000", "fallback": [K.SHIFT, K.RIGHT_ARROW]}),
    ],
}
