"""The pictures on the buttons in GTK, as in Qt (qt/icons.py). Which one, from where
and in which colours is frontends/iconpack.py's (the theme's [shape] icons, ui.icons,
the theme's set); here they are only drawn: the desktop's from the icon theme, the
theme's own SVG through gdk-pixbuf's SVG loader (librsvg; Debian: librsvg2-common,
there with almost any GTK desktop), a PNG as it is. Without an SVG loader only PNGs
are drawn, and the buttons keep their words."""

from __future__ import annotations

import logging

from .. import iconpack
from .gi_setup import Gtk

log = logging.getLogger(__name__)

_cache = {}
_svg = []  # [bool]: can gdk-pixbuf read SVG here (asked once)


def svg_ok():
    if not _svg:
        try:
            from gi.repository import GdkPixbuf
            _svg.append(any(f.get_name() == "svg" for f in GdkPixbuf.Pixbuf.get_formats()))
        except Exception:  # noqa: BLE001 — no GdkPixbuf at all
            _svg.append(False)
        if not _svg[0]:
            log.info("no SVG loader for gdk-pixbuf (Debian: librsvg2-common): button "
                     "pictures from PNG packs only")
    return _svg[0]


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


def _shown(name, theme):
    return bool(name) and iconpack.shown(how(theme), name,
                                         getattr(theme, "split_layout", False))


def _desktop_name(name):
    """The first of the picture's freedesktop names the icon theme has, or None."""
    key = ("desktop", name)
    if key not in _cache:
        _cache[key] = None
        try:
            from .gi_setup import Gdk
            display = Gdk.Display.get_default()
            have = Gtk.IconTheme.get_for_display(display) if display is not None else None
        except Exception:  # noqa: BLE001
            have = None
        for n in iconpack.FREEDESKTOP.get(name, ()):
            if have is not None and have.has_icon(n):
                _cache[key] = n
                break
    return _cache[key]


def texture(name, theme, size=16, scale=2):
    """A Gdk.Texture of the theme's own picture, size × scale pixels square (None if
    neither its set nor the fallback has one, or it can't be drawn)."""
    p = pset(theme)
    accent = theme.c["accent"].name()
    bg = theme.c["card"].name()
    pic = iconpack.picture(p, name, accent, svg_ok=svg_ok(), bg=bg)
    if pic is None:
        return None
    key = (p, name, accent, bg, size * scale)
    if key in _cache:
        return _cache[key]
    tex = None
    try:
        from gi.repository import GdkPixbuf
        px = size * scale
        if pic.kind == "png":
            path = pic.path2x if pic.path2x and scale > 1 else pic.path
            pb = GdkPixbuf.Pixbuf.new_from_file_at_scale(path, px, px, True)
        else:
            loader = GdkPixbuf.PixbufLoader.new_with_type("svg")
            loader.set_size(px, px)
            loader.write(pic.text.encode())
            loader.close()
            pb = loader.get_pixbuf()
        if pb is not None:
            from .images import texture_of
            tex = texture_of(pb)
    except Exception as e:  # noqa: BLE001 — a broken file: no picture, the words stay
        log.debug("picture %s: %s", name, e)
    _cache[key] = tex
    return tex


def image(name, theme, size=16):
    """A Gtk.Image of the picture as the theme has it, or None (without one: "words",
    a messenger's picture outside its place, none to be found)."""
    if not _shown(name, theme):
        return None
    if how(theme) == "desktop":
        n = _desktop_name(name)
        if n is None:
            return None
        img = Gtk.Image.new_from_icon_name(n)
        img.set_pixel_size(size)
        return img
    tex = texture(name, theme, size)
    if tex is None:
        return None
    img = Gtk.Image.new_from_paintable(tex)
    img.set_pixel_size(size)
    return img


def nobody(theme, size):
    """A face for nobody (no one under the pointer, no picture of theirs yet): the
    theme's grey silhouette, or None."""
    return image("nobody", theme, size)


def dress(button, name, theme, words="", glyph=""):
    """A button with its picture (and its words, if any); without a picture, the
    words, or the glyph standing in for it."""
    img = image(name, theme)
    if img is None:
        button.set_child(None)
        button.set_label(words or glyph)
        return False
    if words:
        box = Gtk.Box(spacing=4)
        box.append(img)
        box.append(Gtk.Label(label=words))
        button.set_child(box)
    else:
        button.set_child(img)
    return True
