# Test setup: make firmware/ importable and stub the board-only modules that
# the pure-logic modules pull in transitively.
import os
import sys
import types

FIRMWARE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, FIRMWARE)

# adafruit_hid/__init__ imports usb_hid; Blinka's version only works on Linux.
_usb_hid = types.ModuleType("usb_hid")
_usb_hid.Device = object
sys.modules.setdefault("usb_hid", _usb_hid)
