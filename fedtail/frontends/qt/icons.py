"""The pictures on the buttons in Qt. Which one, from where and in which colours is
frontends/iconpack.py's (the theme's [shape] icons, ui.icons, the theme's set in
themes/<theme>/icons/); here they are only drawn: the desktop's by QIcon.fromTheme,
the theme's own SVG by QtSvg, a PNG as it is.
Without Qt's SVG module (a separate package on some systems) only PNGs are drawn, and
buttons without a picture keep their words."""

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

_said = []


def how(theme):
    """"desktop", "own", "additional" or "words" (theme.icon_mode, set by theme.apply)."""
    return getattr(theme, "icon_mode", "desktop")


def pictures(theme):
    """Any pictures at all (not "words")."""
    return how(theme) != "words"


def pset(theme):
    return iconpack.for_theme(theme)


def wanted(theme):
    """The messengers' pictures (iconpack.EXTENDED) go on their buttons here: the split
    layout, or ui.icons = "additional"."""
    return iconpack.shown(how(theme), "send", getattr(theme, "split_layout", False))


def names():
    return sorted(iconpack.NAMES)


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


def _desktop(name):
    """The desktop icon theme's (looking one up is slow: once a name)."""
    key = ("desktop", name)
    if key not in _cache:
        _cache[key] = QIcon()
        for n in iconpack.FREEDESKTOP.get(name, ()):
            ic = QIcon.fromTheme(n)
            if not ic.isNull():
                _cache[key] = ic
                break
    return _cache[key]


def icon(name, theme, size=16):
    """A QIcon of this picture as the theme has it (an empty one when it goes without:
    "words", a messenger's picture outside its place, none to be found)."""
    mode = how(theme)
    if not name or not iconpack.shown(mode, name, getattr(theme, "split_layout", False)):
        return QIcon()
    if mode == "desktop":
        return _desktop(name)
    s = pset(theme)
    accent = theme.c["accent"].name()
    if QSvgRenderer is None and not _said:
        _said.append(1)
        log.warning("the theme's pictures need Qt's SVG module (Debian: "
                    "python3-pyside6.qtsvg); its PNGs only, words for the rest")
    pic = iconpack.picture(s, name, accent, svg_ok=QSvgRenderer is not None)
    if pic is None:
        return QIcon()
    key = (s, name, accent, size)
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


def nobody(theme, size):
    """A face for nobody (no one under the cursor, no picture of theirs yet): the theme's
    grey silhouette. A QPixmap, or None without one."""
    ic = icon("nobody", theme, size)
    return None if ic.isNull() else ic.pixmap(size, size)


def dress(button, name, theme, words="", glyph=""):
    """A button with its picture (and its words, if it has any); without a picture,
    the words, or the glyph standing in for it."""
    ic = icon(name, theme)
    if not ic.isNull():
        button.setIcon(ic)
        button.setText(words)
    else:
        button.setIcon(QIcon())
        button.setText(words or glyph)
