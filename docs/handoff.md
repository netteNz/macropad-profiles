# Handoff: MacroPad profiles, UI, and Spotify bridge + visualizer

## Working agreement
- Peer-level, no hand-holding. **Propose the plan for each phase and validate it with Ema before writing code.** Explain non-obvious choices inline as you build.
- **Stop at the end of every phase** so Ema can test on the board. Don't start the next phase until he confirms.
- **Subagents:** if you spawn any, run them on **Sonnet 5.5** (`model: sonnet`, i.e. `claude-sonnet-5-5`). Don't spawn them for work you can do inline.
- Security posture:
  - No secrets in the repo; tokens live outside the working tree.
  - The host accepts only an allowlisted command set from the pad.
  - Profile files are data only.

## Environment
- Repo: `D:\code\boards\macropad`, branch `profiles-bridge`. `main` keeps Hotkeys II intact for now.
- Layout:
  - `firmware/` — boot.py, code.py, `ui/`, `profiles/`, lib requirements
  - `host/` — Windows daemon
  - `docs/` — this file
- The board is an Adafruit MacroPad RP2040 with a 128×64 mono SH1106 OLED. Its CIRCUITPY drive is `F:`, and Ema adds it with `/add-dir F:\`.
  - **Never develop directly on F:.** Every write auto-reloads the board, and FAT corruption is possible if the board resets mid-write.
  - Deploy with a small script that copies only changed files from `firmware/` to `F:\`. Install libraries with `circup install -r firmware/requirements.txt`; don't hand-copy `lib/`.
- Baseline: `firmware/code.py` is a copy of the standalone script currently on the board.
  - It is pure HID: rows 1–2 are media keys; rows 3–4 are Spotify shortcuts (`Ctrl+S` shuffle, `Ctrl+R` repeat, `Alt+Shift+B` like, `Shift+←/→` seek), which need the Spotify window focused; "Open" presses Win and types `spotify⏎`.
  - The knob sends system volume, and pressing it toggles play/pause.
  - LEDs run a rainbow cycle, with held keys flashing white.
  - The OLED shows a title plus 4 rows of key labels.

## Global rules (all phases)
- **The pad works fully without the host.** Host-dependent features degrade to today's HID behavior.
- **The main loop is non-blocking:**
  - Drain input, handle keys and encoder, update LEDs, then render.
  - The display has its own refresh cadence: `display.auto_refresh = False`, with an explicit `display.refresh()` throttled to the target fps.
  - No `time.sleep` inside handlers.
- **Encoder gestures:**
  - Plain turn runs the active profile's `knob` action.
  - **Hold + turn** opens the profile picker.
  - Press and release **without turning** runs the profile's `press` action (default: consumer PLAY_PAUSE).
  - Long-press (>600 ms) **without turning** toggles the base view.
  - Track "turned while held" so that a hold + turn never also fires press or long-press.

---

## Phase 1 — Firmware: UI manager + profiles (no host)

### `firmware/ui/` display manager
- **Base view:** one active at a time.
  - Phase 1 has only `keymap`: the profile name, then 4 rows of 3 labels.
  - Later phases add `nowplaying` (visualizer, then metadata).
- **Overlays:** drawn on top of the base view. Each has a priority and a timeout (~1.2 s by default), and the base view comes back automatically when it expires.
  - Higher priority replaces lower; the same overlay type refreshes its timer.
  - Phase 1 overlays:
    - **Profile picker** (while held): a vertical list with the current selection inverted, about 4 visible rows, scrolling. Releasing the encoder commits the selection; releasing without turning cancels.
    - **Volume (relative)** for the `system_volume` knob: a direction marker and a short decaying bar. The pad can't know the true system level, so don't fake a percentage.
- Use `displayio` groups, keeping the labels and bitmaps per view alive; mutate them rather than rebuilding on every frame.
- `terminalio` is ASCII-only.

### `firmware/profiles/`
- One `app` dict per file, loaded at boot and sorted by `order` and then by filename.
- Use the Adafruit Hotkeys macro format so its templates port straight over, extended with optional fields:

```python
# firmware/profiles/traktor.py
from adafruit_hid.keycode import Keycode as K
app = {
    "name": "Traktor",
    "order": 20,
    "apps": ["traktor.exe"],           # foreground exe names for auto-switch (used in Phase 2)
    "knob": ("keys", [K.UP_ARROW], [K.DOWN_ARROW]),
    "press": [K.SPACE],                # optional; default = consumer PLAY_PAUSE
    "leds": "static",                  # "static" (macro colors) | "rainbow"
    "macros": [                        # exactly 12; (color, label ≤6 chars, action)
        (0x00FF40, "Play", [K.SPACE]),
        (0xFF8000, "Cue",  [K.C]),
        # ...
    ],
}
```

- **Actions** follow Hotkeys semantics:
  - Keycode int → press. Negative int → release. Float → delay (non-blocking). String → type it. `[[ConsumerControlCode.X]]` → consumer control. Everything still held is released at the end.
  - Reserve `{"host": "<cmd>", "fallback": <action>}` now. In Phase 1, always run `fallback`.
- **Knob kinds:**
  - `"system_volume"` (the default).
  - `"spotify_volume"` — behaves as `system_volume` until Phase 2.
  - `("keys", cw_seq, ccw_seq)` — runs the sequence once per detent.
  - `("host", "<cmd>")` — reserved for later.
- **Profiles:**
  - **Spotify:** an exact port of the current layout; rows 3–4 as `host` actions with the existing shortcuts as fallback; knob set to `spotify_volume`; `leds: "rainbow"`.
  - **Default:** a global media profile.
  - **Traktor:** play, cue, sync, jump-to-first-marker. **Ask Ema for the bindings** from his Traktor 4 keyboard mapping; don't guess.
  - FL Studio is deferred.
- The last-used profile is remembered across resets only if that's cheap. Writing to NVM is fine; writing to the filesystem is not.

### Phase 1 acceptance
- The Spotify profile behaves the same as the current `code.py`.
- Hold + turn shows the picker, and release switches profiles. A hold + turn never fires play/pause.
- Adding a profile means adding a file only, with no changes to `code.py`.
- Key and encoder response doesn't lag while overlays or LEDs animate.

**→ Stop. Ema tests on the board.**

---

## Phase 2 — Host daemon: visualizer, Spotify volume, auto-switch (no Spotify account)

### Transport
- `boot.py`: `usb_cdc.enable(console=True, data=True)`. Protocol traffic goes on the data port; the console stays free for debugging. It takes effect after a hard reset.
- The host (Python, Windows) uses pyserial and auto-detects the MacroPad **data** port: VID `0x239A`, distinguishing the data CDC interface from the console one. Verify empirically how it appears on Windows. Allow a config override for the port, and reconnect on unplug.
- **Heartbeat:**
  - The host sends `H` about every 1 s. The pad treats the host as alive if it has seen one within the last 3 s.
  - Alive: `host` actions and the knob kinds that depend on the host are active.
  - Dead: fallbacks.

### Visualizer (headline feature)
- **Host:**
  - Capture WASAPI loopback of the render device Spotify plays through, using **pyaudiowpatch**. Make the device configurable.
  - numpy FFT (Hann window, ~2048 samples).
  - About 16 log-spaced bands from 30 Hz to 16 kHz, on a dB scale.
  - Attack/decay smoothing and slow auto-gain.
  - Quantize to 0–255 and send at roughly 30 fps.
  - Send zeros or nothing when the audio is silent.
  - Known limitation: it captures all audio on that device, not just Spotify. Per-process loopback is a stretch goal.
- **Pad:**
  - New base view `nowplaying`, toggled with a long-press.
  - Bars render into a 2-color `displayio.Bitmap` (about 128×48) in a `TileGrid`. Clear and draw with `bitmaptools.fill_region` each frame; don't use per-pixel Python loops.
  - Peak-hold caps with slow fall.
  - Leave a top strip for the profile name, or for track info in Phase 3.
  - Measure real fps on the SH1106 and tune the band count and size. **Target ≥20 fps with no missed key or encoder events.**
- Spotify's audio-analysis / audio-features endpoints are deprecated. **Don't use them.**

### Spotify volume
- For the knob kind `spotify_volume` while the host is alive:
  - The pad sends `C vol ±n`, with deltas coalesced.
  - The host sets `ISimpleAudioVolume` on the `Spotify.exe` session via **pycaw**, then replies `L<0-100>`.
  - The pad shows the **exact-% volume overlay**.
- Don't use the Web API volume endpoint for this; it's laggy and rate-limited.

### Auto-switch
- The host watches foreground changes with `SetWinEventHook(EVENT_SYSTEM_FOREGROUND)` rather than polling, resolves the lowercase exe name, debounces about 250 ms, and sends `A <exe>`.
- The pad switches to the first profile whose `apps` contains that exe. If none matches, it stays where it is.
- A manual picker selection sticks until the next `A` message for a *different* exe.

### Protocol (ASCII lines, `\n`-terminated)
- Host → pad:
  - `H` — heartbeat
  - `V<32 hex chars>` — visualizer frame
  - `L<0-100>` — Spotify volume level
  - `A <exe>` — foreground app changed
- Pad → host (allowlist; anything else is ignored and logged):
  - `C vol <±n>`
  - Phase 3 adds more commands.

### Phase 2 acceptance
- With the daemon off, the board behaves exactly as at the end of Phase 1.
- With the daemon on:
  - The visualizer runs at ≥20 fps.
  - The knob moves Spotify's own volume slider and shows the exact %.
  - Focusing Traktor or Spotify switches the profile within about 300 ms, and an unmatched app leaves the profile alone.
- Pulling the USB cable or killing the daemon recovers cleanly on both sides.

**→ Stop. Ema tests on the board.**

---

## Phase 3 — Spotify Web API (optional polish)
- **First, verify the current Web API development-mode restrictions and endpoint availability, and report back before building.** Playback control requires Premium.
- Auth:
  - spotipy with **PKCE** (no client secret).
  - Scopes: `user-read-playback-state`, `user-modify-playback-state`, `user-library-read`, `user-library-modify`.
  - The token cache lives under `%APPDATA%`; the client ID goes in a gitignored config or env var.
- Poll `GET /me/player` about every 1 s, interpolating progress between polls.
- New host → pad messages:
  - `M{json}` — metadata on track change, transliterated to ASCII (track names like "Arcángel" come up)
  - `P<ms>,<0|1>` — progress
  - `S{json}` — shuffle, repeat and like state on change
- New pad → host commands: `C shuffle` · `C repeat` · `C like` · `C seek <±ms>` · `C open`
- **Pad:**
  - The `nowplaying` view gains a marquee title / artist line and a scrubber above or below the bars.
  - **State-confirmation overlays** for shuffle on/off, repeat mode and "Liked ✓", driven by the host's `S` reply, not optimistically. There's no overlay for plain media-key presses.

### Phase 3 acceptance
- Rows 3–4 work while Spotify is minimized.
- The overlays reflect Spotify's actual state.
- No tokens, client IDs or secrets are tracked by git.

**→ Stop. Ema tests.**

---

## Later / optional
- A system telemetry view (CPU, RAM, audio device) via psutil, as a third base view.
- LEDs react to the bass band.
- Run the daemon at login (tray app or scheduled task).
- Per-process (Spotify-only) loopback capture.
- An FL Studio profile.
