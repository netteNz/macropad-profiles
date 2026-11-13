# Phase 2 plan: host daemon, visualizer, Spotify volume, auto-switch

Agreed with Ema on 2026-10-17. This plan departs from `docs/handoff.md` in the places noted.

## In plain English

Today the pad only sends key presses to the PC. Phase 2 adds a small program
on the PC (the **host**). It talks with the pad over a second, hidden USB
channel. **The pad still works fully without it.** When the host isn't
running, everything behaves the way it does at the end of Phase 1.

With the host running:

1. **Auto-switch.** Click into Spotify or Traktor, and the pad switches to
   that profile by itself.
2. **Spotify-only volume.** In the Spotify profile, the knob changes only
   Spotify's volume, not the whole PC's, and the screen shows the exact %.
   That's the Windows per-app level, the one in the Volume Mixer. Spotify's
   own slider won't move.
3. **Visualizer.** Long-press the knob to switch the screen to live bars
   that move with whatever is playing.

## Steps, each ending with a test stop

I stop after each step. The next step starts only after Ema confirms the
current one works.

| Step | What I do | What Ema does | Pass when |
|---|---|---|---|
| **1. Second channel + screen check** | Add `boot.py` to turn on the hidden channel (and turn off unused MIDI). Draw a screen test pattern with the real bar renderer: a tall bar at the far left, a short bar at the far right, a box around the edge, and an "L" top-left. | **Unplug and replug the pad** (only after I've deployed). Look at the screen and report where the tall bar is, whether the bars grow up from the bottom, and whether all four box edges are visible. | A new COM port appears, the pad doesn't drop into `>>>`, and the pattern is the right way round with no cut-off edge |
| **2. Host connects + auto-switch** | Write the host's connection part (find the port, heartbeat, reconnect) and the window watcher. Fix the Traktor profile's exe names. | Run the host. Click between Spotify, Traktor and other apps. Kill the host. Unplug the pad and plug it back in. | The profile follows the app you click into, other apps leave it alone, and everything recovers after a kill or an unplug |
| **3. Spotify volume** | Knob → host → Spotify's mixer level → exact % back on the screen. | Turn the knob with Spotify playing, then with Spotify closed. | Only Spotify's volume changes, the % is shown, and "Spotify: no audio" appears when Spotify is closed |
| **4. Visualizer** | Audio capture and FFT on the host; the bars view on the pad. | Long-press, play music, and mash keys while the bars move. | The bars move smoothly with the music (timing tuned for the Bluetooth speaker), at ≥20 fps, and the keys stay instant |

## Why the bars bypass displayio (measured on the board)

| Render path | Area | Draw | Refresh (blocks the loop) | Max fps |
|---|---|---|---|---|
| displayio Bitmap + `fill_region` (handoff spec) | 128×52 | 11.4 ms | 42.8 ms | 18 |
| displayio Bitmap + `fill_region` | 128×40 | 8.9 ms | 32.3 ms | 24 |
| displayio Bitmap + `fill_region` | 128×32 | 7.2 ms | 25.9 ms | 30 |
| Raw SH1106 page writes, changed pages only | 128×48 | 2.6 ms | 1.5 ms | 242 |

- **The SPI bus already runs at 10 MHz**, so the cost is displayio's
  per-pixel work (about 6.4 µs per pixel), and a faster clock wouldn't help.
- **The bars are written straight to the panel.** The SH1106 stores the
  screen as 8 pages of 128 bytes, and only changed pages are sent.
- **displayio still draws everything else:** the title row, overlays and the
  keymap.
- **displayio doesn't know about the bar pixels.** So raw drawing pauses while
  a full-screen overlay (the picker) is up, and the bars repaint in full after
  it closes or the view changes.

## Facts checked on this PC

- **COM ports.**
  - pyserial leaves `location` empty here, so it can't tell the console port
    from the data port.
  - The registry has the mapping at
    `HKLM\SYSTEM\CurrentControlSet\Enum\USB\VID_239A&PID_xxxx&MI_nn\*\Device Parameters\PortName`.
    Today COM6 = `MI_00`, the console.
  - The console is the lowest `MI`. **The host never opens the console**,
    because any byte written to it can drop the board into the REPL.
- **Traktor.** The exe is `Traktor Pro 4.exe`. Pro 3 (`Traktor.exe`) is
  installed too. The Phase 1 profile's `traktor.exe` alone would never match
  Pro 4.
- **Spotify.** It's the Microsoft Store build, version 1.305.
  - Its audio session belongs to the same `Spotify.exe` process as its main
    window.
  - The in-app slider is **independent** of the Windows per-app level: the
    slider is below max while the mixer level is 100%.
  - The handoff's acceptance line "moves Spotify's own volume slider" is
    reworded to: *"the knob changes Spotify's per-app volume and shows the
    exact %"*.
- **Audio output.** The default output is a Bluetooth speaker (JBL Go 4).
  Loopback captures audio before the Bluetooth delay, so the bars would lead
  the sound by about 150–250 ms. The host gets a `delay_ms` setting.
- **USB endpoints.** Enabling too many USB devices sends the board into safe
  mode, which is recoverable. MIDI is unused now, so `boot.py` disables it.

## Technical details

### Pad (firmware)
- **`boot.py`:** calls `usb_midi.disable()` and
  `usb_cdc.enable(console=True, data=True)`. It runs only at power-up or
  after a reset.
- **`link.py`:** a non-blocking line reader on the data port.
  - Lines are capped at 64 bytes; malformed lines are ignored.
  - Writes happen only while `usb_cdc.data.connected` is true (pyserial raises
    DTR when it opens the port), with `write_timeout = 0`.
  - The host counts as alive if an `H` arrived within the last 3 s.
- **Spotify volume** (`spotify_volume` knob, host alive):
  - The pad sends `C vol ±n`, combining detents, at most every 40 ms.
  - On `L<n>`, the title row shows `Spotify 42%` with a small bar. On `L-`,
    it shows `Spotify: no audio`.
  - With the host dead, the knob sends system volume keys, as today.
- **`nowplaying` view:** long-press switches to it.
  - The title row stays on displayio.
  - 16 bars with peak caps (a short hold, then a slow fall) are drawn in raw
    mode by `ui/bars.py`.
  - Without the host, the title row shows "no host" and the bars are empty.
- **Auto-switch:**
  - `A <exe>` takes the rest of the line, so names with spaces work.
  - A different exe from the last `A` switches to the first matching
    profile. This switch doesn't write to NVM.
  - A manual pick in the picker sticks until an `A` arrives for a different
    exe.

### Host (`host/`, Python 3.13, runs from the repo `.venv`)
- **Serial.**
  - The host finds the data port through the registry `MI_xx` mapping. The
    port can also be set in the config.
  - It reconnects every 2 s after an unplug, and sends `H` every 1 s.
  - A single writer thread sends everything.
- **Allowlist.** Pad → host lines must match `^C vol [+-]\d{1,2}$`.
  Anything else is logged and dropped, and nothing is ever executed.
- **Foreground.**
  - `SetWinEventHook(EVENT_SYSTEM_FOREGROUND)` runs on its own
    message-loop thread.
  - The host gets the exe name from the window's PID, debounces for
    200 ms, then sends `A <exe>`.
  - It resends the current exe whenever the pad reconnects.
- **Spotify volume.**
  - pycaw `ISimpleAudioVolume` changes every `spotify.exe` session, 2% per
    detent.
  - COM is initialised in each thread that uses it.
  - The host replies `L<n>`, or `L-` when Spotify has no audio session.
- **Visualizer.**
  - pyaudiowpatch WASAPI loopback of the default output, or a device set in
    the config.
  - numpy FFT: Hann window, 2048 samples, 16 log-spaced bands from 30 Hz to
    16 kHz, in dB.
  - Fast attack and slow decay, plus slow auto-gain.
  - The host sends `V<32 hex>` at about 30 fps, holding frames back by
    `delay_ms`.
  - After about 1 s of silence it sends one all-zero frame, then stops.
- **Config:** `%APPDATA%\macropad\config.toml` (port, audio device,
  `delay_ms`, volume step). It lives outside the repo; no secrets are involved.

### Protocol (ASCII lines, `\n`-terminated)
- **Host → pad:**
  - `H`: heartbeat.
  - `V<32 hex>`: 16 bands, 0–255 each.
  - `L<0-100>`: Spotify volume.
  - `L-` *(new)*: Spotify has no audio session.
  - `A <exe>`: foreground app changed; the exe name may contain spaces.
- **Pad → host:** only `C vol <±n>`.

## Acceptance (end of Phase 2)
- With the host off, the pad behaves exactly as at the end of Phase 1.
- With the host on:
  - The visualizer runs at ≥20 fps.
  - The knob changes Spotify's per-app volume and shows the exact %.
  - Focusing Traktor or Spotify switches the profile within about 300 ms,
    and an unmatched app leaves the profile alone.
- Pulling the USB cable or killing the host recovers cleanly on both sides.
