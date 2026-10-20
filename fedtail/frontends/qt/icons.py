"""fedtail's own button pictures (data/icons/ui/*.svg): small SVGs in the spirit of the
2007 messengers, coloured by the theme — {c} its accent, {l} a light top for the gloss,
{d} the outline. Shown where ui.button_icons (or the theme's shape.icons) says so.
Without Qt's SVG module (a separate package on some systems) there are none and the
buttons keep their words."""

import logging
import re
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


# a theme's set (shape.icon_set): the same drawings, drawn three ways — "gloss" (QIP:
# a gradient, a white shine, a dark outline), "agent" (the Agent: a brighter shine, a
# softer outline), "flat" (Psi on KDE: plain colour, no shine) — and the status picture
# of that messenger: a flower, an "@", a star
STATUS = {"gloss": "status", "agent": "status-agent", "flat": "status-psi"}
OWN_SET = {"status-agent": "#3aa63a", "status-psi": "#f2c037"}
_SHINE = re.compile(r'<ellipse[^>]*opacity="\.35"/>')


def icon_set(theme):
    return theme.shape.get("icon_set", "gloss")


def _styled(text, style, base):
    if style == "flat":
        text = _SHINE.sub("", text).replace('fill="url(#g)"', 'fill="{c}"')
        dark = base.darker(140)
    elif style == "agent":
        text = text.replace('opacity=".35"', 'opacity=".6"')
        dark = base.darker(135)
    else:
        dark = base.darker(170)
    return text.replace("{c}", base.name()).replace("{l}", base.lighter(165).name()) \
        .replace("{d}", dark.name())


def icon(name, theme, size=16):
    """A QIcon of this picture in the theme's colours and the theme's set (an empty one
    if there's none)."""
    if QSvgRenderer is None:
        return QIcon()
    style = icon_set(theme)
    if name == "status":
        name = STATUS.get(style, "status")
    base = QColor(OWN_SET.get(name) or OWN.get(name) or theme.c["accent"])
    key = (name, style, base.name(), size)
    if key in _cache:
        return _cache[key]
    try:
        text = (DIR / f"{name}.svg").read_text(encoding="utf-8")
    except OSError as e:
        log.debug("icon %s: %s", name, e)
        return QIcon()
    svg = _styled(text, style, base)
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
