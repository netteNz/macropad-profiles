# Hardware setup without adafruit_macropad.MacroPad().
#
# MacroPad() claims board.BUTTON (the encoder switch) as a polled Debouncer,
# so a short press can be lost while a display refresh blocks the loop. Here
# the 12 keys and the encoder switch share one keypad.Keys, whose scanning
# runs in the background and queues timestamped events.
import board
import keypad
import neopixel
import rotaryio
import usb_hid
from adafruit_hid.consumer_control import ConsumerControl
from adafruit_hid.keyboard import Keyboard
from adafruit_hid.keyboard_layout_us import KeyboardLayoutUS

ENC_KEY = 12  # key_number of the encoder switch in `keys`
_DISPLAY_WAKE = 0xAF  # same command MacroPad() sends on init

keys = keypad.Keys(
    [getattr(board, "KEY%d" % (i + 1)) for i in range(12)] + [board.BUTTON],
    value_when_pressed=False,
    pull=True,
)

_encoder = rotaryio.IncrementalEncoder(board.ROTA, board.ROTB)


def encoder_position():
    # Negated so clockwise is positive, matching MacroPad.encoder.
    return -_encoder.position


pixels = neopixel.NeoPixel(board.NEOPIXEL, 12, brightness=0.3, auto_write=False)

display = board.DISPLAY
display.bus.send(_DISPLAY_WAKE, b"")

PANEL_HZ = 400000  # SSD1306 spec; 1 MHz is the RP2040 max, try per module


def _open_panel():
    # Optional second OLED on the STEMMA QT port. Any failure (nothing
    # plugged in, wrong address) leaves panel = None and the pad runs as before.
    try:
        import busio

        from panel.oled import Oled, find

        i2c = busio.I2C(board.SCL, board.SDA, frequency=PANEL_HZ)
        addr = find(i2c)
        if addr is None:
            i2c.deinit()
            print("panel: none found on STEMMA QT")
            return None
        print("panel: SSD1306 at 0x%02X, %d kHz" % (addr, PANEL_HZ // 1000))
        return Oled(i2c, addr)
    except Exception as e:  # noqa: BLE001 - never crash the pad over the panel
        print("panel: disabled (%s)" % e)
        return None


panel = _open_panel()

keyboard = Keyboard(usb_hid.devices)
consumer = ConsumerControl(usb_hid.devices)
layout = KeyboardLayoutUS(keyboard)
