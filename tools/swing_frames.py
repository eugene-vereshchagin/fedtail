"""The swinging opossum's frames for GTK: GTK 4 draws no GIF by itself, and reading one
through GdkPixbuf's animation iterator wants GLib's deprecated time values. So the GIF
(fedtail/data/icons/fedtail-swing.gif, a Telegram sticker as the icon) is laid out once
into a sheet of frames, row by row, with each frame's time beside it:

    fedtail/data/icons/fedtail-swing.png   COLS frames a row, SIDE px each
    fedtail/data/icons/fedtail-swing.json  {"side", "cols", "ms": [each frame's time]}

Run it again when the GIF changes:  python3 tools/swing_frames.py   (needs Pillow)
"""

import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "fedtail" / "data" / "icons"
SIDE, COLS = 144, 10  # the curtain shows 96 px: half again for a scaled screen


def main():
    gif = Image.open(ICONS / "fedtail-swing.gif")
    frames, ms = [], []
    for i in range(gif.n_frames):
        gif.seek(i)
        frames.append(gif.convert("RGBA").resize((SIDE, SIDE), Image.LANCZOS))
        ms.append(int(gif.info.get("duration") or 40))
    rows = -(-len(frames) // COLS)
    sheet = Image.new("RGBA", (SIDE * COLS, SIDE * rows), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        sheet.paste(f, ((i % COLS) * SIDE, (i // COLS) * SIDE))
    # a palette of 256 with its alpha (the sticker has few colours): a third of the size
    sheet.quantize(256, method=Image.Quantize.FASTOCTREE).save(
        ICONS / "fedtail-swing.png", optimize=True)
    (ICONS / "fedtail-swing.json").write_text(
        json.dumps({"side": SIDE, "cols": COLS, "ms": ms}) + "\n", "utf-8")
    print(f"{len(frames)} frames, {sum(ms)} ms, into {ICONS / 'fedtail-swing.png'}")


if __name__ == "__main__":
    main()
