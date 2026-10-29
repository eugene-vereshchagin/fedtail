"""Pictures in the terminal.

Real ones where the terminal can show them: with the optional package textual-image
(`pip install textual-image`) a picture goes out as sixel (Konsole, WezTerm, foot,
xterm in vt340 mode…) or the kitty graphics protocol (kitty). textual-image asks the
terminal what it can do — before Textual takes the screen, so `prepare()` runs at the
start of the terminal interface — and gives a Textual widget to mount
(`graphic(data, rows)`).

Otherwise characters: chafa's (`text()`, when chafa is installed — it picks among many
glyph shapes, far finer than ours), or our half blocks: each character is two pixels,
the upper one its colour, the lower one its background ("▀"). Works in any terminal
with true colour.

Needs Pillow (python3-pil); without it `available()` is False and the interface says
so instead of drawing. No Textual imported here: tested on its own.
"""

import io
import logging
import os
import shutil
import subprocess
import sys
import tempfile

from rich.text import Text

log = logging.getLogger(__name__)

try:  # optional: the terminal interface works without pictures
    from PIL import Image
except ImportError:  # pragma: no cover — depends on what is installed
    Image = None

MAX_PIXELS = 40_000_000  # a decompression bomb is refused, not drawn

# tui.pictures: "auto" — real pictures where the terminal can, half blocks elsewhere;
# "blocks" — half blocks always; "key" — only on v; "off" — none. "inline" (before
# 0.19) is "auto".
MODES = ("auto", "blocks", "key", "off")
_graphics = {"cls": None, "kind": None}


def mode(cfg):
    """tui.pictures of a config, the old "inline" read as "auto"."""
    got = (cfg.get("tui") or {}).get("pictures", "auto")
    return "auto" if got == "inline" else got


def available():
    return Image is not None


def prepare(want="auto", stdout=None):
    """Before Textual starts: load textual-image when it is installed and asked for
    ("auto"), on a real terminal. It asks the terminal at import what it can show; the
    answer (its best widget class) is kept. Returns "sixel", "kitty" or None (then half
    blocks)."""
    _graphics.update(cls=None, kind=None)
    stdout = sys.__stdout__ if stdout is None else stdout
    if want not in ("auto", "inline") or Image is None or not (stdout and stdout.isatty()):
        return None
    try:
        from textual_image import widget as tiw
    except Exception as e:  # noqa: BLE001 — not installed, or failed asking: blocks
        log.info("textual-image: %s", e)
        return None
    renderable = getattr(tiw.Image, "_Renderable", None)
    if tiw.Image is getattr(tiw, "SixelImage", None):
        kind = "sixel"
    elif renderable is not None and renderable.__name__ == "Image" and \
            renderable.__module__.endswith(".tgp"):
        kind = "kitty"
    else:  # its own half cells or unicode: ours are the same, and cached
        log.info("textual-image: no graphics in this terminal")
        return None
    _graphics.update(cls=tiw.Image, kind=kind)
    log.info("pictures: %s through textual-image", kind)
    return kind


def graphics():
    """"sixel", "kitty" or None: what prepare() found."""
    return _graphics["kind"]


def opened(data, box=None):
    """The picture in data as a Pillow image (RGB), read small when box (w, h) is
    given; None when it can't be read or is too big."""
    if Image is None or not data:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        if img.width * img.height > MAX_PIXELS:
            return None
        if box:
            img.draft("RGB", box)
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (0, 0, 0, 255))
        return Image.alpha_composite(bg, img).convert("RGB")
    except Exception as e:  # noqa: BLE001 — any format Pillow can't read: no picture
        log.debug("picture: %s", e)
        return None


def graphic(data, rows, cols=0, **kw):
    """A widget showing the picture for real (sixel or kitty), `rows` lines high and at
    most `cols` wide (0: as wide as its proportions say), or None (no textual-image,
    or not a picture)."""
    cls = _graphics["cls"]
    if cls is None:
        return None
    img = opened(data, (max(cols, rows * 2) * 20, rows * 40))
    if img is None:
        return None
    w = cls(img, **kw)
    w.styles.height = rows
    w.styles.width = cols if cols else "auto"
    return w


def blocks(data, cols, rows):
    """The picture in `data` as rich Text, at most `cols` characters wide and `rows`
    lines high, its proportions kept (a character is about twice as high as wide, so
    one character = one pixel across and two down). None when it can't be read."""
    if Image is None or not data or cols < 2 or rows < 1:
        return None
    img = opened(data, (cols * 4, rows * 8))  # a JPEG is read small, not whole
    if img is None:
        return None
    scale = min(cols / img.width, rows * 2 / img.height)
    w = max(1, round(img.width * scale))
    h = max(2, round(img.height * scale))
    h += h % 2
    img = img.resize((w, h), Image.Resampling.LANCZOS)
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


CHAFA_TIMEOUT = 8  # s: a picture chafa can't draw by then is drawn by us


def _chafa():
    return shutil.which("chafa")


def text(data, cols, rows):
    """The picture as rich Text `cols` × `rows` at most: by chafa when it is there (its
    symbols, true colour — chafa installed changed nothing before: only the v viewer
    used it, 29.10), else our half blocks. None when it can't be read."""
    path = _chafa()
    if path and data:
        drawn = _by_chafa(path, data, cols, rows)
        if drawn is not None:
            return drawn
    return blocks(data, cols, rows)


_chafa_said = {"failed": False}


def how(want="auto"):
    """In words, how the lane's pictures are drawn now — said in the log at start and by
    tools/tui_check.py: "chafa installed, nothing changed" was not to be told from
    outside (29.10)."""
    if Image is None:
        return "none: Pillow (python3-pil) is missing"
    if want not in ("auto", "blocks", "inline"):
        return f"none in the lane (tui.pictures = {want!r}), v shows them"
    kind = graphics() if want != "blocks" else None
    if kind:
        return f"{kind} through textual-image"
    path = _chafa()
    if path:
        return f"chafa's symbols ({path}); real pixels need textual-image"
    return "half blocks (no chafa, no textual-image)"


def _failed(what):
    """Why chafa didn't draw: said once at warning (the half blocks drawn instead
    looked like "chafa does nothing"), then at debug."""
    (log.debug if _chafa_said["failed"] else log.warning)("chafa: %s — half blocks "
                                                         "instead", what)
    _chafa_said["failed"] = True


def _by_chafa(path, data, cols, rows):
    if opened(data, (8, 8)) is None:  # not a picture we would draw: nor chafa
        return None
    fd, tmp = tempfile.mkstemp(prefix="fedtail-", suffix=".img")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        got = subprocess.run([path, "-f", "symbols", "-c", "full", "--animate", "off",
                              "--polite", "on", "--size", f"{max(2, cols)}x{max(1, rows)}",
                              tmp], capture_output=True, timeout=CHAFA_TIMEOUT, check=False)
    except (OSError, subprocess.SubprocessError) as e:
        _failed(e)
        return None
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    if got.returncode != 0 or not got.stdout:
        _failed(f"exit {got.returncode} {got.stderr[:200]!r}")
        return None
    out = Text.from_ansi(got.stdout.decode("utf-8", "replace").rstrip("\n"),
                         no_wrap=True, overflow="crop")
    return out
