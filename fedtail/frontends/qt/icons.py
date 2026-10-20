"""fedtail's own button pictures (data/icons/ui/*.svg): small SVGs in the spirit of the
2007 messengers, coloured by the theme — {c} its accent, {l} a light top for the gloss,
{d} the outline. Shown where ui.button_icons (or the theme's shape.icons) says so.
Without Qt's SVG module (a separate package on some systems) there are none and the
buttons keep their words."""

import logging
from pathlib import Path

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap

log = logging.getLogger(__name__)

DIR = Path(__file__).resolve().parents[2] / "data" / "icons" / "ui"
# pictures of their own colour, whatever the theme: a status flower is green, as ever
OWN = {"status": "#36b02c", "warning": "#f2a400", "emoji": "#f5c400", "send": "#3aa63a"}
_cache = {}

try:
    from PySide6.QtSvg import QSvgRenderer
except ImportError:  # python3-pyside6.qtsvg not installed
    QSvgRenderer = None


def names():
    return sorted(p.stem for p in DIR.glob("*.svg"))


_said = []


def wanted(theme):
    on = bool(theme.shape.get("icons"))
    if on and QSvgRenderer is None and not _said:
        _said.append(1)
        log.warning("button pictures need Qt's SVG module (Debian: python3-pyside6.qtsvg);"
                    " words instead")
    return QSvgRenderer is not None and on


def icon(name, theme, size=16):
    """A QIcon of this picture in the theme's colours (an empty one if there's none)."""
    if QSvgRenderer is None:
        return QIcon()
    base = QColor(OWN.get(name) or theme.c["accent"])
    key = (name, base.name(), size)
    if key in _cache:
        return _cache[key]
    try:
        text = (DIR / f"{name}.svg").read_text(encoding="utf-8")
    except OSError as e:
        log.debug("icon %s: %s", name, e)
        return QIcon()
    svg = text.replace("{c}", base.name()).replace("{l}", base.lighter(165).name()) \
        .replace("{d}", base.darker(170).name())
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
    _cache[key] = out
    return out


def dress(button, name, theme, words="", glyph=""):
    """A button with its picture (and its words, if it has any) when pictures are
    wanted; else the words, or the glyph standing in for a picture."""
    if wanted(theme):
        button.setIcon(icon(name, theme))
        button.setText(words)
    else:
        button.setIcon(QIcon())
        button.setText(words or glyph)
