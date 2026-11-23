# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

CircuitPython firmware for an Adafruit MacroPad RP2040 (12 keys, rotary encoder with push switch, 12 NeoPixels, 128×64 mono SH1106 OLED). It provides per-app key profiles, encoder gestures and an OLED UI. `docs/handoff.md` is the full spec and phase plan; `PHASE2_PLAN.md` is the (parked) plan for a Windows host daemon. `Macropad_Hotkeys/` is the old Adafruit Hotkeys II project kept for reference. It's gitignored, so don't edit it.

## Commands

All commands run from the repo root on Windows, using the repo `.venv`.

```powershell
# Run all tests (host-side CPython; pure-logic modules only)
.venv\Scripts\python -m unittest discover -s firmware/tests
# One file / one test
.venv\Scripts\python -m unittest discover -s firmware/tests -p test_profiles.py
.venv\Scripts\python -m unittest discover -s firmware/tests -k test_real_profile_files_validate

# Deploy changed files to the board (CIRCUITPY drive, default F:\)
.venv\Scripts\python tools\deploy.py [--drive F:\] [--dry-run] [--prune]

# Board libraries (never hand-copy lib/)
circup install -r firmware/requirements.txt
```

Test deps are listed in `firmware/tests/requirements.txt`. `firmware/tests/_paths.py` puts `firmware/` on `sys.path` and stubs `usb_hid`; every test file imports it first.

## Working on the board

- **Never edit files directly on the CIRCUITPY drive.** Every write auto-reloads the board, and a reset mid-write can corrupt FAT. Edit `firmware/`, then run `tools/deploy.py`. It copies only changed files, writes `code.py` last, skips `tests/` and `lib/`, and with `--prune` deletes only stale files under `ui/` and `profiles/`.
- Deploying interrupts the running `code.py` and resets the screen. Tell Ema before deploying or running anything on the board (REPL, benchmarks). After each step, stop so Ema can test on the board.
- `boot.py` changes (USB endpoints) only take effect after a hard reset, and enabling too many USB devices sends the board into safe mode.

## Architecture (`firmware/`)

`code.py` is a single non-blocking loop: drain `keypad` events → encoder gestures → `actions.Runner.tick` → `leds.tick` → `ui.tick`. **No `time.sleep` anywhere.** Every subsystem paces itself with `adafruit_ticks` (`ticks_ms`/`ticks_diff`).

- **`hw.py`** sets up the hardware without `adafruit_macropad.MacroPad()`. The 12 keys and the encoder switch share one `keypad.Keys` (the encoder switch is `ENC_KEY = 12`), so presses are queued with timestamps even while a display refresh blocks. The encoder position is negated so clockwise is positive. HID devices are Keyboard, ConsumerControl and a US layout only; there is no mouse.
- **`profile_loader.py`** imports each `profiles/*.py`, keeps only its `app` dict, and drops the module to save RAM. It validates that profiles are *data only*: an action may contain only ints, floats, strs, lists of numbers, or the `{"host": ..., "fallback": ...}` dict. A bad file is skipped with a printed message and never crashes the pad. Profiles are sorted by `(order, filename)`. The last-used profile name is stored in `microcontroller.nvm` and written only when it changed (each write erases a flash sector).
- **`actions.py`**: `Runner` runs Hotkeys-format sequences without blocking, with one slot per physical key plus the `KNOB`/`PRESS` slots. A non-negative int presses a key and a negative int releases it, a float is a delay, a str is typed one character per tick, and `[[code, ...]]` sends consumer-control codes. Keys left pressed stay held until the physical key is released, which is how hold actions like push-to-talk work. Tap slots (knob detents, encoder press) release as soon as their sequence ends, and knob detents queue up to 8. `{"host", "fallback"}` actions always run the fallback, because the host bridge doesn't exist yet.
- **`gestures.py`**: the encoder state machine. A turn while the switch is up runs the profile's `knob`. Hold + turn opens the profile picker (`picker_open`/`picker_move`), and releasing commits. A release with no turn under 600 ms runs the profile's `press` (default Play/Pause). A longer release without turning toggles the base view. Turning while held never also fires press or long-press.
- **`ui/manager.py`**: one base view (`keymap` for now) plus at most one overlay (picker, volume), chosen by priority. Overlays time out after 1.2 s; the picker stays up until the switch is released. `display.auto_refresh` is off, and the manager calls `refresh()` only when a view is `dirty`, at most every 33 ms. Views keep their displayio objects and mutate them instead of rebuilding. `terminalio` is ASCII-only.
- **`leds.py`**: `"static"` shows each macro's color (`0x000000` = off), `"rainbow"` cycles over time, and held keys show white.

## Profiles (`firmware/profiles/NN_name.py`)

Adding a profile means adding a file; nothing else changes. Each file defines `app`:

```python
app = {
    "name": "Browser",            # picker/title, ≤21 chars shown
    "order": 40,                  # sort key; Spotify (order 0) must stay first (test_profiles asserts it)
    "apps": ["chrome.exe"],       # optional; for future host auto-switch
    "knob": ("keys", cw_seq, ccw_seq),  # or "system_volume" (default) / "spotify_volume"
    "press": [...],               # optional; default consumer PLAY_PAUSE
    "leds": "static",             # or "rainbow"
    "macros": [(0xRRGGBB, "Label", action), ...],  # exactly 12, labels ≤6 ASCII chars
}
```

`test_real_profile_files_validate` loads every real profile file, so run the tests after adding or editing one. `spotify_volume` currently behaves like `system_volume` (it needs the host). Global shortcuts for apps such as Discord need the app focused unless the user binds them in the app's own keybind settings.
