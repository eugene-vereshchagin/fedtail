"""Pictures in the terminal, drawn with half blocks: each character is two pixels, the
upper one its colour, the lower one its background ("▀"). Works in any terminal with
true colour (Konsole, GNOME Terminal, kitty, xterm…) and inside Textual, which owns the
screen and has no room for sixel or kitty graphics.

Needs Pillow (python3-pil); without it `available()` is False and the interface says
so instead of drawing. No Textual here: tested on its own.
"""

import io
import logging

from rich.text import Text

log = logging.getLogger(__name__)

try:  # optional: the terminal interface works without pictures
    from PIL import Image
except ImportError:  # pragma: no cover — depends on what is installed
    Image = None

MAX_PIXELS = 40_000_000  # a decompression bomb is refused, not drawn


def available():
    return Image is not None


def blocks(data, cols, rows):
    """The picture in `data` as rich Text, at most `cols` characters wide and `rows`
    lines high, its proportions kept (a character is about twice as high as wide, so
    one character = one pixel across and two down). None when it can't be read."""
    if Image is None or not data or cols < 2 or rows < 1:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_PIXELS:
            return None
        img.draft("RGB", (cols * 4, rows * 8))  # a JPEG is read small, not whole
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
        img = Image.alpha_composite(bg, img).convert("RGB")
        scale = min(cols / img.width, rows * 2 / img.height)
        w = max(1, round(img.width * scale))
        h = max(2, round(img.height * scale))
        h += h % 2
        img = img.resize((w, h), Image.Resampling.LANCZOS)
    except Exception as e:  # noqa: BLE001 — any format Pillow can't read: no picture
        log.debug("picture: %s", e)
        return None
    px = img.load()
    out = Text(no_wrap=True, overflow="crop")
    for y in range(0, h, 2):
        if y:
            out.append("\n")
        for x in range(w):
            top, bottom = px[x, y], px[x, y + 1]
            out.append("▀", style=f"#{top[0]:02x}{top[1]:02x}{top[2]:02x} on "
                                  f"#{bottom[0]:02x}{bottom[1]:02x}{bottom[2]:02x}")
    return out
