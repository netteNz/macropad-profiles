# Playback state shared by the Spotify panel scenes. Pure logic.
#
# Without the host the pad can't see the player, so this is a guess built
# from what the pad itself sends: Play/Pause toggles, Next/Prev starts a new
# track (and implies playing), and "seek +-N" host actions move the clock.
# Later the host's now-playing lines overwrite the guess through sync().
from adafruit_ticks import ticks_diff

PLAY_PAUSE = 0xCD  # ConsumerControlCode values
NEXT = 0xB5
PREV = 0xB6


class Transport:
    def __init__(self):
        self.playing = False
        self.duration_ms = None  # unknown until the host says
        self.track_n = 0  # bumps on every track change, for scenes to react
        self.skips = 0  # Next presses this session
        self.shuffle = False
        self.repeat = 0  # 0 off, 1 all, 2 one (Spotify's cycle order)
        self.liked = False  # for the current track
        self._base = 0  # elapsed ms at _anchor
        self._anchor = 0

    def elapsed(self, now):
        if not self.playing:
            return self._base
        e = self._base + ticks_diff(now, self._anchor)
        d = self.duration_ms
        return e if d is None or e < d else d

    def _set(self, ms, now):
        self._base = ms if ms > 0 else 0
        self._anchor = now

    def play_toggle(self, now):
        self._set(self.elapsed(now), now)
        self.playing = not self.playing

    def track(self, now):
        self._set(0, now)
        self.playing = True
        self.track_n += 1
        self.liked = False
        self.duration_ms = None  # unknown until the host sends the new one

    def seek(self, ms, now):
        e = self.elapsed(now) + ms
        d = self.duration_ms
        self._set(e if d is None or e < d else d, now)

    def progress(self, now, scale):
        """Elapsed as 0..scale of the track, or None without a known length."""
        d = self.duration_ms
        if not d:
            return None
        return self.elapsed(now) * scale // d

    def on_action(self, action, now):
        """Update the guess from an action (a profile's validated data) that
        the pad just started running."""
        if isinstance(action, dict):
            host = action["host"]
            if host.startswith("seek "):
                try:
                    self.seek(int(host[5:]), now)
                except ValueError:
                    pass
            elif host == "shuffle":
                self.shuffle = not self.shuffle
            elif host == "repeat":
                self.repeat = (self.repeat + 1) % 3
            elif host == "like":
                self.liked = not self.liked
            action = action["fallback"]
        for item in action:
            if isinstance(item, list):
                for code in item:
                    if code == PLAY_PAUSE:
                        self.play_toggle(now)
                    elif code == NEXT:
                        self.skips += 1
                        self.track(now)
                    elif code == PREV:
                        self.track(now)
