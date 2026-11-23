# MacroPad profiles: per-app key layouts, encoder gestures, OLED UI.
# Loop: drain input -> gestures -> actions -> LEDs -> UI. No sleeps anywhere;
# every subsystem paces itself off ticks_ms.
import gc

import keypad
from adafruit_hid.consumer_control_code import ConsumerControlCode as CC
from adafruit_ticks import ticks_diff, ticks_ms

import hw
import profile_loader
from actions import KNOB, PRESS, Runner
from gestures import Encoder
from leds import Leds
from ui.keymap import KeymapView
from ui.manager import UI
from ui.picker import Picker
from ui.volume import VolumeOverlay

DEBUG = True  # loop/refresh stats on the serial console every 5 s; off once Phase 1 is signed off

ui = UI(hw.display)
keymap = KeymapView()
ui.add_base("keymap", keymap)
picker = Picker()
volume = VolumeOverlay()
leds = Leds(hw.pixels)
runner = Runner(hw.keyboard, hw.consumer, hw.layout)
encoder = Encoder()

profiles = profile_loader.load_all()
if not profiles:
    keymap.set_title("NO PROFILES FOUND")
    while True:  # keep ticking: the first tick can fall inside the frame throttle
        ui.tick(ticks_ms())
gc.collect()

current = None


def set_profile(i):
    global current
    current = profiles[i]
    runner.release_all()
    keymap.set_profile(current)
    leds.set_profile(current)


def on_turn(delta, now):
    knob = current["knob"]
    if knob in ("system_volume", "spotify_volume"):  # spotify_volume needs the host (Phase 2)
        code = CC.VOLUME_INCREMENT if delta > 0 else CC.VOLUME_DECREMENT
        for _ in range(abs(delta)):
            runner.consumer_send(code)
        volume.bump(delta, now)
        ui.show_overlay(volume, now)
    elif knob[0] == "keys":
        seq = knob[1] if delta > 0 else knob[2]
        for _ in range(abs(delta)):
            runner.queue(KNOB, seq, now)
    # ("host", cmd): reserved, no-op without the host.


def on_gesture(g, now):
    name = g[0]
    if name == "turn":
        on_turn(g[1], now)
    elif name == "press":
        runner.start(PRESS, current["press"], tap=True, now=now)
    elif name == "long_press":
        if not ui.toggle_base() and DEBUG:
            print("long-press: only one base view")
    elif name == "picker_open":
        picker.open([p["name"] for p in profiles], profiles.index(current))
        ui.show_overlay(picker, now, timeout_ms=None)
    elif name == "picker_move":
        picker.move(g[1])
    elif name == "picker_commit":
        ui.hide_overlay(picker)
        if profiles[picker.selected] is not current:
            set_profile(picker.selected)
            profile_loader.save_last(current["name"])


def poll_encoder(now):
    global last_pos
    pos = hw.encoder_position()
    if pos != last_pos:
        for g in encoder.rotate(pos - last_pos):
            on_gesture(g, now)
        last_pos = pos


set_profile(profile_loader.load_last(profiles))
event = keypad.Event()
last_pos = hw.encoder_position()

loops = 0
worst = 0
stats_at = ticks_ms()

while True:
    now = ticks_ms()

    while hw.keys.events.get_into(event):
        k = event.key_number
        if k == hw.ENC_KEY:
            if event.released:
                # Detents that piled up while the switch was held belong to the
                # hold (picker), not to a turn after release.
                poll_encoder(now)
            g = encoder.button(event.pressed, event.timestamp)
            if g:
                on_gesture(g, now)
        elif event.pressed:
            leds.set_held(k, True)
            runner.start(k, current["macros"][k][2], now=now)
        else:
            leds.set_held(k, False)
            runner.release(k)

    poll_encoder(now)

    runner.tick(now)
    leds.tick(now)
    ui.tick(now)

    if DEBUG:
        loops += 1
        took = ticks_diff(ticks_ms(), now)
        if took > worst:
            worst = took
        if ticks_diff(now, stats_at) >= 5000:
            secs = ticks_diff(now, stats_at) / 1000
            print(
                "loop %d Hz, worst %d ms | refresh %.1f fps, worst %d ms | free %d%s"
                % (loops / secs, worst, ui.refreshes / secs, ui.refresh_ms_max,
                   gc.mem_free(), " | KEY EVENTS OVERFLOWED" if hw.keys.events.overflowed else "")
            )
            # overflowed is read-only and sticky (only events.clear() resets it,
            # which would drop queued presses), so it's reported, not reset.
            loops = worst = ui.refreshes = ui.refresh_ms_max = 0
            stats_at = now
