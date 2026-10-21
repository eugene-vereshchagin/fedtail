"""fedtail's own button pictures in GTK, as in Qt (qt/icons.py): which file and which
colours is the theme's picture pack's (frontends/iconpack.py); here they are only
drawn — an SVG through gdk-pixbuf's SVG loader (librsvg; Debian: librsvg2-common,
there with almost any GTK desktop), a PNG as it is. Shown where ui.additional_icons
says so (the split layout, by default); without a way to draw SVG only a pack's PNGs
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


def pack(theme):
    return iconpack.for_theme(theme)


def wanted(theme):
    """ui.additional_icons (theme.own_icons, set by theme.apply) and a way to draw."""
    if not getattr(theme, "own_icons", False):
        return False
    return svg_ok() or iconpack.has_png(pack(theme))


def texture(name, theme, size=16, scale=2):
    """A Gdk.Texture of the picture, size × scale pixels square (None if the pack, and
    all it inherits, has none, or it can't be drawn)."""
    p = pack(theme)
    accent = theme.c["accent"].name()
    pic = iconpack.picture(p, name, accent, svg_ok=svg_ok())
    if pic is None:
        return None
    key = (p.key, name, accent, size * scale)
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
    """A Gtk.Image of the picture, or None."""
    tex = texture(name, theme, size)
    if tex is None:
        return None
    img = Gtk.Image.new_from_paintable(tex)
    img.set_pixel_size(size)
    return img


def nobody(theme, size):
    """A face for nobody (no one under the pointer, no picture of theirs yet): the
    pack's grey silhouette, when pictures are on; else None."""
    return image("nobody", theme, size) if wanted(theme) else None


def dress(button, name, theme, words="", glyph=""):
    """A button with its picture (and its words, if any) when pictures are wanted;
    else the words, or the glyph standing in for a picture."""
    img = image(name, theme) if wanted(theme) else None
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
