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
from panel.art import Scene
from panel.spotify import RecordScene
from panel.transport import Transport
from ui.keymap import KeymapView
from ui.manager import UI
from ui.picker import Picker
from ui.volume import VolumeOverlay

# Spotify's second panel: the clock/weather/status HUD needs real time and
# weather (parked, see docs/next-hud-data.md), so it shows the particles for
# now. HUD = True brings it back; DEMO feeds it fake data. With HUD off the
# HUD modules aren't even imported (saves RAM).
HUD = False
DEMO = False
DEBUG = True  # loop/refresh stats on the serial console every 5 s; off once Phase 1 is signed off

ui = UI(hw.display)
keymap = KeymapView()
ui.add_base("keymap", keymap)
picker = Picker()
volume = VolumeOverlay()
leds = Leds(hw.pixels)
runner = Runner(hw.keyboard, hw.consumer, hw.layout)
encoder = Encoder()
panels = hw.panels  # extra OLEDs on STEMMA QT (direct or behind a mux), may be empty
transport = Transport()  # play state guessed from what the pad sends
HudScene = None
if HUD:
    from panel.hostdata import HostData
    from panel.hud import HudScene

    host_data = HostData()  # time/weather/moon from the PC helper (none yet)
if HUD and DEMO:
    from panel.demo import Demo

    demo = Demo(host_data, ticks_ms())
scenes = []  # one per panel, built from the profile's "panel" kind
scene_kind = None
tick_i = 0  # round-robin: one scene render per loop pass
flush_i = 0  # round-robin: one page write per loop pass, across all panels


def flush_any():
    # Send one dirty page from the next panel that has one. All panels share
    # one I2C bus, so this keeps the worst loop pass at one page write.
    global flush_i
    n = len(panels)
    for j in range(n):
        i = (flush_i + j) % n
        if panels[i].flush_step():
            flush_i = (i + 1) % n
            return

profiles = profile_loader.load_all()
if not profiles:
    keymap.set_title("NO PROFILES FOUND")
    while True:  # keep ticking: the first tick can fall inside the frame throttle
        ui.tick(ticks_ms())
gc.collect()

current = None


def build_scenes(kind):
    # "spotify": the record on the first panel, the HUD on the second; any
    # others keep the ambient art.
    out = []
    for i, p in enumerate(panels):
        if kind == "spotify" and i == 0:
            out.append(RecordScene(p.canvas, transport))
        elif kind == "spotify" and i == 1 and HUD:
            out.append(HudScene(p.canvas, transport, host_data))
        else:
            out.append(Scene(p.canvas))
    return out


def set_profile(i):
    global current, scenes, scene_kind, tick_i
    current = profiles[i]
    runner.release_all()
    keymap.set_profile(current)
    leds.set_profile(current)
    if current["panel"] != scene_kind:
        scene_kind = current["panel"]
        scenes = []  # drop the old ones before building, to keep peak RAM down
        gc.collect()
        scenes = build_scenes(scene_kind)
        tick_i = 0
    for s in scenes:
        s.set_title(current["name"])


def panel_volume():
    """True when volume shows on an extra panel, so the main OLED skips its
    overlay (its refresh stalls the loop 25-45 ms, the fast-turn stutter)."""
    if scene_kind != "spotify" or not panels:
        return False
    if HUD:  # the record and the HUD's status view both show volume
        return any(p.alive for p in panels)
    return panels[0].alive  # only the record does


def on_turn(delta, now):
    for s in scenes:
        s.knob(delta, now)
    knob = current["knob"]
    if knob in ("system_volume", "spotify_volume"):  # spotify_volume needs the host (Phase 2)
        code = CC.VOLUME_INCREMENT if delta > 0 else CC.VOLUME_DECREMENT
        for _ in range(abs(delta)):
            runner.consumer_send(code)
        volume.bump(delta, now)
        if not panel_volume():
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
        transport.on_action(current["press"], now)
        for s in scenes:
            if HUD and isinstance(s, HudScene):
                s.key(-1, now)  # a knob press is an action too: show status
        runner.start(PRESS, current["press"], tap=True, now=now)
    elif name == "long_press":
        if current["panel"] == "spotify":
            # The pad can't see Spotify's real play state (no PC helper yet),
            # so a long press corrects its guess without sending anything.
            transport.play_toggle(now)
            for s in scenes:
                if HUD and isinstance(s, HudScene):
                    s.key(-1, now)  # pop the status view to show the new state
        elif not ui.toggle_base() and DEBUG:
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


def panel_stats():
    alive = [p for p in panels if p.alive]
    if not alive:
        return "off"
    return "page worst %d ms (%d/%d alive)" % (
        max(p.flush_ms_max for p in alive), len(alive), len(panels))


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
scene_worst = [0] * 8  # per panel, ms
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
            for s in scenes:
                s.key(k, now)
            action = current["macros"][k][2]
            transport.on_action(action, now)
            runner.start(k, action, now=now)
        else:
            leds.set_held(k, False)
            runner.release(k)

    poll_encoder(now)
    if HUD and DEMO:
        demo.tick(now)

    runner.tick(now)
    leds.tick(now)
    ui.tick(now)
    if scenes:
        # One render per pass: two scenes due together would double the stall.
        if DEBUG:
            t0 = ticks_ms()
            scenes[tick_i].tick(now)
            took = ticks_diff(ticks_ms(), t0)
            if took > scene_worst[tick_i]:
                scene_worst[tick_i] = took
        else:
            scenes[tick_i].tick(now)
        tick_i = (tick_i + 1) % len(scenes)
        flush_any()

    if DEBUG:
        loops += 1
        took = ticks_diff(ticks_ms(), now)
        if took > worst:
            worst = took
        if ticks_diff(now, stats_at) >= 5000:
            secs = ticks_diff(now, stats_at) / 1000
            print(
                "loop %d Hz, worst %d ms | refresh %.1f fps, worst %d ms | panel %s | scene %s %s ms | free %d%s"
                % (loops / secs, worst, ui.refreshes / secs, ui.refresh_ms_max,
                   panel_stats(), scene_kind, scene_worst[:len(scenes)],
                   gc.mem_free(), " | KEY EVENTS OVERFLOWED" if hw.keys.events.overflowed else "")
            )
            for s in scenes:
                prof = getattr(s, "prof", None)
                if prof:
                    print("  hud render worst: clock %d, weather %d, status %d, icon %d ms" % tuple(prof))
                    for i in range(len(prof)):
                        prof[i] = 0
            for p in panels:
                p.flush_ms_max = 0
            # overflowed is read-only and sticky (only events.clear() resets it,
            # which would drop queued presses), so it's reported, not reset.
            loops = worst = ui.refreshes = ui.refresh_ms_max = 0
            for i in range(len(scene_worst)):
                scene_worst[i] = 0
            stats_at = now
