# Review guidance for macropad-profiles

CircuitPython 10 firmware for one Adafruit MacroPad RP2040, used by its owner
on a Windows PC. It is a hobby device, not a product: there is one user, the
profiles are written by that user, and anything can be fixed and redeployed in
minutes. See `CLAUDE.md` for the architecture.

## Worth flagging

- Anything that can crash or stop `code.py` (an uncaught exception in the main
  loop leaves the pad dead until a reset).
- Keys or consumer codes left stuck down, or released while still held.
- Behaviour that contradicts `CLAUDE.md` (gestures, hold semantics, profiles
  being data only, no `time.sleep`, NVM written only on change).
- Bugs a person can hit with the real profiles in `firmware/profiles/` and
  normal hands on the keys and knob.
- Wrong or misleading shortcuts in a profile.
- Second OLED (`firmware/panel/`): anything that can crash the pad when the
  panel is missing or an I²C write fails (`hw.panel` may be `None`), any
  flush that sends more than one page per loop pass, or any per-frame
  allocation in `art.py`.

## Please skip

- Races narrower than one display refresh (~30 ms) unless they cause a crash
  or a stuck key.
- Contrived inputs no real profile uses (e.g. names over 30 bytes that share a
  prefix, absurd delays) unless they crash the pad.
- Fixes the hardware API can't support. `rotaryio` exposes only a position:
  there are no timestamps or edge events for the encoder.
- Trade-offs already declined in a reply on this or an earlier PR.
- Style nits, naming, and suggestions to add abstraction. Code size and RAM
  matter on the board, so simpler beats more general.

## Platform notes

- CircuitPython, not CPython: no threads or asyncio here, a limited `math`,
  and `adafruit_ticks` for time. Tests under `firmware/tests/` run on
  host CPython with stubs.
- Only one displayio display is allowed and the built-in OLED holds it, so
  the second SSD1306 (STEMMA QT, 0x3C) is driven with raw I²C writes on
  purpose. Don't suggest `adafruit_displayio_ssd1306`.
- `adafruit_hid` holds at most six regular keys and one consumer code at a
  time.
