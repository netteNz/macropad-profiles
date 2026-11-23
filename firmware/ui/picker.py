# Overlay: profile picker shown while the encoder is held and turned.
# Opaque full-screen panel, a header, then 4 scrolling rows. The selected
# row is drawn inverted by swapping that label's fg/bg colors; rows are
# padded to the full 21 columns so the inverted bar spans the screen.
import displayio
from ui.keymap import ROW_H, text_label

VISIBLE = 4
_COLS = 21
_BLACK = 0x000000
_WHITE = 0xFFFFFF


class Picker:
    kind = "picker"
    priority = 10

    def __init__(self):
        self.group = displayio.Group()
        self.dirty = True
        bg = displayio.Bitmap(128, 64, 1)
        pal = displayio.Palette(1)
        pal[0] = _BLACK
        self.group.append(displayio.TileGrid(bg, pixel_shader=pal))
        self._header = text_label(0)
        self.group.append(self._header)
        self._rows = [text_label((i + 1) * ROW_H) for i in range(VISIBLE)]
        for lbl in self._rows:
            self.group.append(lbl)
        self._names = []
        self.selected = 0
        self._top = 0

    def open(self, names, current):
        self._names = names
        self.selected = current
        self._top = max(0, min(current - 1, len(names) - VISIBLE))
        self._render()

    def move(self, delta):
        sel = max(0, min(len(self._names) - 1, self.selected + delta))
        if sel == self.selected:
            return
        self.selected = sel
        if sel < self._top:
            self._top = sel
        elif sel >= self._top + VISIBLE:
            self._top = sel - VISIBLE + 1
        self._render()

    def _render(self):
        self._header.text = "Profile %d/%d" % (self.selected + 1, len(self._names))
        for i, lbl in enumerate(self._rows):
            n = self._top + i
            text = self._names[n] if n < len(self._names) else ""
            lbl.text = ("{:<%d}" % _COLS).format(text[:_COLS])
            sel = n == self.selected
            lbl.color = _BLACK if sel else _WHITE
            lbl.background_color = _WHITE if sel else None
        self.dirty = True
