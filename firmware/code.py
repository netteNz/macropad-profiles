# MacroPad Spotify controller: rainbow LEDs, media keys, knob = volume.
import time
from rainbowio import colorwheel
from adafruit_macropad import MacroPad

macropad = MacroPad()
macropad.pixels.brightness = 0.3
macropad.pixels.auto_write = False
CC = macropad.ConsumerControlCode
K = macropad.Keycode


def open_spotify():
    macropad.keyboard.send(K.GUI)
    time.sleep(0.4)
    macropad.keyboard_layout.write("spotify\n")


# (label, action), top-left to bottom-right.
# Rows 1-2 are system media keys and work anywhere.
# Rows 3-4 are Spotify shortcuts and need the Spotify window focused.
KEYS = [
    ("Prev", CC.SCAN_PREVIOUS_TRACK), ("Play", CC.PLAY_PAUSE), ("Next", CC.SCAN_NEXT_TRACK),
    ("Vol-", CC.VOLUME_DECREMENT), ("Mute", CC.MUTE), ("Vol+", CC.VOLUME_INCREMENT),
    ("Shufl", (K.CONTROL, K.S)), ("Repeat", (K.CONTROL, K.R)), ("Like", (K.ALT, K.SHIFT, K.B)),
    ("Seek-", (K.SHIFT, K.LEFT_ARROW)), ("Open", open_spotify), ("Seek+", (K.SHIFT, K.RIGHT_ARROW)),
]

# OLED: one line per key row
text = macropad.display_text(title="Spotify  knob=vol")
for row in range(4):
    text[row].text = "".join("{:<7}".format(label) for label, _ in KEYS[row * 3:row * 3 + 3])
text.show()

hue = 0
held = set()
last_pos = macropad.encoder

while True:
    # Rainbow across the keys; held keys flash white
    for i in range(12):
        macropad.pixels[i] = 0xFFFFFF if i in held else colorwheel((hue + i * 21) & 255)
    macropad.pixels.show()
    hue = (hue + 1) & 255

    event = macropad.keys.events.get()
    if event:
        if event.pressed:
            held.add(event.key_number)
            action = KEYS[event.key_number][1]
            if callable(action):
                action()
            elif isinstance(action, tuple):
                macropad.keyboard.send(*action)
            else:
                macropad.consumer_control.send(action)
        else:
            held.discard(event.key_number)

    # Knob turns volume, knob press toggles play/pause
    pos = macropad.encoder
    while pos > last_pos:
        macropad.consumer_control.send(CC.VOLUME_INCREMENT)
        last_pos += 1
    while pos < last_pos:
        macropad.consumer_control.send(CC.VOLUME_DECREMENT)
        last_pos -= 1

    macropad.encoder_switch_debounced.update()
    if macropad.encoder_switch_debounced.pressed:
        macropad.consumer_control.send(CC.PLAY_PAUSE)

    time.sleep(0.01)
