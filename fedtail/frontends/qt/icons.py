"""fedtail's own button pictures (data/icons/ui/*.svg): small SVGs in the spirit of the
2007 messengers, coloured by the theme — {c} its accent, {l} a light top for the gloss,
{d} the outline. Shown where ui.additional_icons says so (the split layout,
by default).
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
OWN = {"nobody": "#8a96a6", "status": "#36b02c", "warning": "#f2a400", "emoji": "#f5c400",
       "send": "#3aa63a", "star_full": "#f2b705"}
_cache = {}

try:
    from PySide6.QtSvg import QSvgRenderer
except ImportError:  # python3-pyside6.qtsvg not installed
    QSvgRenderer = None


def nobody(theme, size):
    """A face for nobody (no one under the cursor, no picture of theirs yet): a grey
    silhouette, Psi+'s in its theme. A QPixmap, or None without a way to draw it."""
    ic = icon("nobody", theme, size)
    return None if ic.isNull() else ic.pixmap(size, size)


def names():
    return sorted(p.stem for p in DIR.glob("*.svg"))


_said = []


PSI = Path(__file__).resolve().parents[2] / "data" / "icons" / "psi"  # Psi+'s, GPL


def wanted(theme):
    """fedtail's own pictures on buttons: ui.additional_icons (theme.own_icons, set by
    theme.apply) — and something to draw them with (Qt's SVG module, or Psi+'s PNGs)."""
    on = bool(getattr(theme, "own_icons", False))
    if not on:
        return False
    if icon_set(theme) == "psi":
        return True
    if QSvgRenderer is None and not _said:
        _said.append(1)
        log.warning("button pictures need Qt's SVG module (Debian: python3-pyside6.qtsvg);"
                    " words instead")
    return QSvgRenderer is not None


# a theme's set (shape.icon_set): the same drawings, drawn three ways — "gloss" (QIP:
# a gradient, a white shine, a dark outline), "agent" (the Agent: a brighter shine, a
# softer outline), "flat" (Psi on KDE: plain colour, no shine) — and the status picture
# of that messenger: a flower, an "@", a star
STATUS = {"gloss": "status", "qip": "status", "agent": "status-agent", "flat": "status-psi"}
OWN_SET = {"status-agent": "#3aa63a", "status-psi": "#f2c037"}
_SHINE = re.compile(r'<ellipse[^>]*opacity="\.35"/>')


def icon_set(theme):
    return theme.shape.get("icon_set", "gloss")


# QIP's way (shape.icon_set = "qip"): every picture in its own bright colour whatever
# the theme, a thick near-black outline, a strong shine — the chunky 16 px look of the
# XP years. Drawn for fedtail, not taken from anyone.
QIP_COLOURS = {
    "send": "#2fa82f", "reply": "#2fa82f", "boost": "#2fa82f", "follow": "#2fa82f",
    "star": "#f5c400", "star_full": "#f5c400", "emoji": "#f5c400",
    "talk": "#f2c230", "direct": "#f6cf55", "private": "#e3a600", "unlisted": "#e3a600",
    "public": "#2f86e0", "thread": "#2f6fd6", "profile": "#3b82d4", "accounts": "#3b82d4",
    "menu": "#2f6fd6", "expand": "#2f6fd6", "bookmark": "#d9342b", "unfollow": "#d9342b",
    "warning": "#f08c00", "attach": "#6f8fb8", "poll": "#3fae3a", "list": "#8b5fc4",
    "settings": "#8c8c8c", "status": "#33ad28", "nobody": "#8a96a6",
}
_WIDTH = re.compile(r'stroke-width="([\d.]+)"')


def _styled(text, style, base):
    if style == "qip":
        text = text.replace('opacity=".35"', 'opacity=".55"')
        text = _WIDTH.sub(lambda m: f'stroke-width="{float(m.group(1)) * 1.35:.2f}"', text)
        return text.replace("{c}", base.name()).replace("{l}", base.lighter(150).name()) \
            .replace("{d}", QColor(base).darker(300).name())
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


def _theme_own(name, theme, style, size):
    """The theme's own picture of this name (themefile.icon_dirs): a PNG as it is, an
    SVG coloured as ours are ({c} {l} {d}). None when the theme has none."""
    for d in getattr(theme, "icon_dirs", ()):
        for ext in (".svg", ".png"):
            p = Path(d) / f"{name}{ext}"
            if not p.is_file():
                continue
            key = ("own", str(p), style, theme.c["accent"].name(), size)
            if key in _cache:
                return _cache[key]
            if ext == ".png" or QSvgRenderer is None:
                if ext == ".svg":
                    continue
                _cache[key] = QIcon(str(p))
                return _cache[key]
            try:
                text = p.read_text(encoding="utf-8")
            except OSError as e:
                log.debug("icon %s: %s", p, e)
                continue
            base = QColor(OWN.get(name) or theme.c["accent"])
            _cache[key] = _render(_styled(text, style, base), size)
            return _cache[key]
    return None


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
    """A QIcon of this picture in the theme's colours and the theme's set (an empty one
    if there's none)."""
    style = icon_set(theme)
    own = _theme_own(name, theme, style, size)
    if own is not None:
        return own
    if style == "psi":  # Psi+'s own pictures where it has one, else ours drawn flat
        png = PSI / f"{name}.png"
        if png.is_file():
            key = ("psi", name)
            if key not in _cache:
                _cache[key] = QIcon(str(png))
            return _cache[key]
        style = "flat"
    if QSvgRenderer is None:
        return QIcon()
    if name == "status":
        name = STATUS.get(style, "status")
    if style == "qip":
        base = QColor(QIP_COLOURS.get(name) or OWN.get(name) or theme.c["accent"])
    else:
        base = QColor(OWN_SET.get(name) or OWN.get(name) or theme.c["accent"])
    key = (name, style, base.name(), size)
    if key in _cache:
        return _cache[key]
    try:
        text = (DIR / f"{name}.svg").read_text(encoding="utf-8")
    except OSError as e:
        log.debug("icon %s: %s", name, e)
        return QIcon()
    out = _render(_styled(text, style, base), size)
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
