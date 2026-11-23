# Base view: profile name on top, then 4 rows of 3 key labels.
# terminalio.FONT is 6x12, so the 128x64 OLED fits 21 columns x 5 rows.
import displayio
import terminalio
from adafruit_display_text import bitmap_label

ROW_H = 12


def text_label(y, text="", x=0):
    return bitmap_label.Label(
        terminalio.FONT,
        text=text,
        color=0xFFFFFF,
        anchor_point=(0, 0),
        anchored_position=(x, y),
    )


class KeymapView:
    def __init__(self):
        self.group = displayio.Group()
        self.dirty = True
        self._rows = [text_label(i * ROW_H) for i in range(5)]
        for lbl in self._rows:
            self.group.append(lbl)

    def set_profile(self, app):
        self._rows[0].text = app["name"][:21]
        labels = [m[1] for m in app["macros"]]
        for r in range(4):
            self._rows[r + 1].text = "".join(
                "{:<7}".format(l) for l in labels[r * 3 : r * 3 + 3]
            ).rstrip()
        self.dirty = True

    def set_title(self, text):
        self._rows[0].text = text[:21]
        self.dirty = True
