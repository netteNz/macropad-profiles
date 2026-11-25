# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

CircuitPython firmware for an Adafruit MacroPad RP2040 (12 keys, rotary encoder with push switch, 12 NeoPixels, 128×64 mono SH1106 OLED), plus an optional second OLED on the STEMMA QT port (see "Second OLED panel" below). It provides per-app key profiles, encoder gestures and an OLED UI. `docs/handoff.md` is the full spec and phase plan; `PHASE2_PLAN.md` is the (parked) plan for a Windows host daemon. `Macropad_Hotkeys/` is the old Adafruit Hotkeys II project kept for reference. It's gitignored, so don't edit it.

## Commands

All commands run from the repo root on Windows, using the repo `.venv`.

```powershell
# Run all tests (host-side CPython; pure-logic modules only)
.venv\Scripts\python -m unittest discover -s firmware/tests
# One file / one test
.venv\Scripts\python -m unittest discover -s firmware/tests -p test_profiles.py
.venv\Scripts\python -m unittest discover -s firmware/tests -k test_real_profile_files_validate

# Read the board's serial output (--reload soft-restarts code.py; interrupts the pad)
.venv\Scripts\python tools\serial_console.py [--reload] [--seconds N] [--port COMx]

# Deploy changed files to the board (CIRCUITPY drive, default F:\)
.venv\Scripts\python tools\deploy.py [--drive F:\] [--dry-run] [--prune]

# Board libraries (never hand-copy lib/)
circup install -r firmware/requirements.txt
```

Test deps are listed in `firmware/tests/requirements.txt`. `firmware/tests/_paths.py` puts `firmware/` on `sys.path` and stubs `usb_hid`; every test file imports it first.

## Working on the board

- **Never edit files directly on the CIRCUITPY drive.** Every write auto-reloads the board, and a reset mid-write can corrupt FAT. Edit `firmware/`, then run `tools/deploy.py`. It copies only changed files, writes `code.py` last, skips `tests/` and `lib/`, and with `--prune` deletes only stale files under `ui/`, `profiles/` and `panel/`.
- Deploying interrupts the running `code.py` and resets the screen. Tell Ema before deploying or running anything on the board (REPL, benchmarks). After each step, stop so Ema can test on the board.
- `boot.py` changes (USB endpoints) only take effect after a hard reset, and enabling too many USB devices sends the board into safe mode.

## Architecture (`firmware/`)

`code.py` is a single non-blocking loop: drain `keypad` events → encoder gestures → `actions.Runner.tick` → `leds.tick` → `ui.tick` → one `Scene.tick` + one page flush, round-robin across the extra OLEDs (when present). **No `time.sleep` anywhere.** Every subsystem paces itself with `adafruit_ticks` (`ticks_ms`/`ticks_diff`).

- **`hw.py`** sets up the hardware without `adafruit_macropad.MacroPad()`. The 12 keys and the encoder switch share one `keypad.Keys` (the encoder switch is `ENC_KEY = 12`), so presses are queued with timestamps even while a display refresh blocks. The encoder position is negated so clockwise is positive. HID devices are Keyboard, ConsumerControl and a US layout only; there is no mouse.
- **`profile_loader.py`** imports each `profiles/*.py`, keeps only its `app` dict, and drops the module to save RAM. It validates that profiles are *data only*: an action may contain only ints, floats, strs, lists of numbers, or the `{"host": ..., "fallback": ...}` dict. A bad file is skipped with a printed message and never crashes the pad. Profiles are sorted by `(order, filename)`. The last-used profile name is stored in `microcontroller.nvm` and written only when it changed (each write erases a flash sector).
- **`actions.py`**: `Runner` runs Hotkeys-format sequences without blocking, with one slot per physical key plus the `KNOB`/`PRESS` slots. A non-negative int presses a key and a negative int releases it, a float is a delay, a str is typed one character per tick, and `[[code, ...]]` sends consumer-control codes. Keys left pressed stay held until the physical key is released, which is how hold actions like push-to-talk work. Tap slots (knob detents, encoder press) release as soon as their sequence ends, and knob detents queue up to 8. `{"host", "fallback"}` actions always run the fallback, because the host bridge doesn't exist yet.
- **`gestures.py`**: the encoder state machine. A turn while the switch is up runs the profile's `knob`. Hold + turn opens the profile picker (`picker_open`/`picker_move`), and releasing commits. A release with no turn under 600 ms runs the profile's `press` (default Play/Pause). A longer release without turning toggles the base view. Turning while held never also fires press or long-press.
- **`ui/manager.py`**: one base view (`keymap` for now) plus at most one overlay (picker, volume), chosen by priority. Overlays time out after 1.2 s; the picker stays up until the switch is released. `display.auto_refresh` is off, and the manager calls `refresh()` only when a view is `dirty`, at most every 33 ms. Views keep their displayio objects and mutate them instead of rebuilding. `terminalio` is ASCII-only.
- **`panel/`**: the optional second OLED (SSD1306 128×64, yellow band = rows 0–15) on the STEMMA QT port. CircuitPython allows only one displayio display and `board.DISPLAY` holds it, so `oled.py` drives the panel with raw I²C writes. `hw.panels` is a list: empty when nothing answers, one `Oled` for a panel plugged in directly, or one per panel found behind a PCA9548A mux (`mux.py` finds it at 0x70–0x77, scans all 8 channels, and hands each `Oled` a `Channel` that looks like a `busio.I2C` and selects its channel before each write, only when it changed). An I²C error at runtime disables just that panel without crashing. `writeto` blocks, so the loop sends at most one dirty 128-byte page per pass across *all* panels (about 4 ms at 400 kHz) and renders at most one scene per pass. `canvas.py` draws into the page-layout buffer and marks pages dirty; it's pure logic, tested on the host. `art.py` draws the profile name in the yellow band, plus key ripples, a knob wave and stars below it. It uses integer tables only, so frames don't allocate.
- **`leds.py`**: `"static"` shows each macro's color (`0x000000` = off), `"rainbow"` cycles over time, and held keys show white.

## Second OLED panel (current state, Nov 2026)

- **Hardware:** one Elegoo SSD1306 128×64 (yellow rows 0–15, blue rows 16–63) at 0x3C, plugged straight into STEMMA QT. Built in PR #6 and confirmed working on the board. Mux support (PCA9548A at 0x70, two panels on ch 0/1, each running its own `Scene`) is board-tested (PR #7): mux only, one panel, two panels, and pulling one panel's SDA mid-run. With two panels at 400 kHz the bus is ~90% busy and the loop drops to ~200 Hz.
- **Bus:** `hw.PANEL_HZ = 400000`. 1 MHz (the RP2040 max) hasn't been tried. `Oled(..., flip=True)` rotates it 180°, but `hw.py` currently uses the default orientation.
- **What it shows:** pad-only reactive art from `panel/art.py`'s `Scene`. The profile name sits in the yellow band. Below it are a ripple from the pressed key's 3×4 grid position, a sine wave that scrolls with knob turns and fades out, and drifting stars. It runs at about 30 fps while something moves and about 15 fps when only the stars drift, and it sends whole frames only. `code.py` feeds it events through `scene.key()`, `scene.knob()` and `scene.set_title()`.
- **Measured cost:** the worst page write takes about 4 ms. The loop runs at about 960 Hz with the panel and about 2050 Hz without it. The worst loop pass is 13–14 ms, probably from frame rendering (not profiled yet). With `DEBUG` on, the loop stats line prints `panel page worst N ms`.
- **Known limits:** the knob wave gets coarse on fast turns, because the main OLED's volume-overlay refresh (25–45 ms) stalls the loop. Ema wants a better knob/volume visual than the sine.
- **Next:** the pad has no mic and can't hear the PC, so audio-reactive visuals need the host. The Phase 2 host FFT bars go on *this* panel, not the built-in OLED; `PHASE2_PLAN.md` still says the built-in one and needs updating. Ideas for later: a PCA9548A mux with 3 panels, plus now-playing info and weather, all of which need the host.
- **Tests:** `firmware/tests/test_panel.py` covers `canvas`, `oled` (with a fake I²C) and `art` on the host.

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
