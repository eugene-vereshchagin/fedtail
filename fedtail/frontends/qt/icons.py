"""fedtail's own button pictures in Qt: which file and which colours is the theme's
picture pack's (frontends/iconpack.py: data/icons/packs/, ~/.config/fedtail/icons/,
themes/<theme>/icons/); here they are only drawn. Shown where ui.additional_icons says
so (the split layout, by default).
Without Qt's SVG module (a separate package on some systems) only a pack's PNGs are
drawn, and buttons without a picture keep their words."""

import logging

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

from .. import iconpack

log = logging.getLogger(__name__)

_cache = {}

try:
    from PySide6.QtSvg import QSvgRenderer
except ImportError:  # python3-pyside6.qtsvg not installed
    QSvgRenderer = None


def pack(theme):
    return iconpack.for_theme(theme)


def nobody(theme, size):
    """A face for nobody (no one under the cursor, no picture of theirs yet): a grey
    silhouette, in the theme's pack. A QPixmap, or None without a way to draw it."""
    ic = icon("nobody", theme, size)
    return None if ic.isNull() else ic.pixmap(size, size)


def names():
    return sorted(iconpack.NAMES)


_said = []


def wanted(theme):
    """fedtail's own pictures on buttons: ui.additional_icons (theme.own_icons, set by
    theme.apply) — and something to draw them with (Qt's SVG module, or a pack of PNGs)."""
    if not getattr(theme, "own_icons", False):
        return False
    if QSvgRenderer is not None or iconpack.has_png(pack(theme)):
        return True
    if not _said:
        _said.append(1)
        log.warning("button pictures need Qt's SVG module (Debian: python3-pyside6.qtsvg);"
                    " words instead")
    return False


def icon_set(theme):
    return pack(theme).name


def _render(svg, size):
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    out = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        renderer.render(p)
        p.end()
        pm.setDevicePixelRatio(scale)
        out.addPixmap(pm)
    return out


def icon(name, theme, size=16):
    """A QIcon of this picture from the theme's pack, in the theme's colours (an empty
    one if the pack, and all it inherits, has none)."""
    p = pack(theme)
    accent = theme.c["accent"].name()
    pic = iconpack.picture(p, name, accent, svg_ok=QSvgRenderer is not None)
    if pic is None:
        return QIcon()
    key = (p.key, name, accent, size)
    if key in _cache:
        return _cache[key]
    if pic.kind == "png":
        out = QIcon(pic.path)
        if pic.path2x:
            out.addFile(pic.path2x)
    else:
        out = _render(pic.text, size)
    _cache[key] = out
    return out


def dress(button, name, theme, words="", glyph=""):
    """A button with its picture (and its words, if it has any) when pictures are
    wanted; else the words, or the glyph standing in for a picture."""
    ic = icon(name, theme) if wanted(theme) else QIcon()
    if not ic.isNull():
        button.setIcon(ic)
        button.setText(words)
    else:  # no pictures, or none of this one in the pack: the words
        button.setIcon(QIcon())
        button.setText(words or glyph)
