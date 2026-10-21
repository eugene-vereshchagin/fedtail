"""Pictures for the GTK window: common/images.py's cache (the one the Qt window has:
memory and disk, newest first, retried when a server was only busy, the disk kept
within its size), with GTK's pictures — decoded in the workers by GdkPixbuf, already no
bigger than asked (a big JPEG is read small), and handed over as a Gdk.Texture, which
any thread may make and widgets take as they are."""

from __future__ import annotations

from ..common import images as common
from ..common.images import FEED_SIDE  # noqa: F401  (the size of a feed picture)
from .gi_setup import GLib


def decode(data, max_side):
    """A Gdk.Texture of the picture in data, no bigger than max_side — or None."""
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gdk, GdkPixbuf

    loader = GdkPixbuf.PixbufLoader()

    def prepared(ld, w, h):
        if max(w, h) > max_side:
            k = max_side / max(w, h)
            ld.set_size(max(1, round(w * k)), max(1, round(h * k)))
    loader.connect("size-prepared", prepared)
    try:
        loader.write(data)
        loader.close()
    except GLib.Error:
        try:
            loader.close()
        except GLib.Error:
            pass
        return None
    pix = loader.get_pixbuf()
    if pix is None:
        return None
    try:  # the pixels as they are (new_for_pixbuf is deprecated in newer GTK)
        fmt = Gdk.MemoryFormat.R8G8B8A8 if pix.get_has_alpha() else Gdk.MemoryFormat.R8G8B8
        return Gdk.MemoryTexture.new(pix.get_width(), pix.get_height(), fmt,
                                     pix.read_pixel_bytes(), pix.get_rowstride())
    except (AttributeError, TypeError, ValueError):  # bindings that lack it
        return Gdk.Texture.new_for_pixbuf(pix)


class Images(common.Cache):
    FORMAT_HINT = "GdkPixbuf can't read this format (webp-pixbuf-loader?)"

    def decode(self, data, max_side):
        return decode(data, max_side)

    def size(self, picture):
        return picture.get_width(), picture.get_height()

    def later(self, ms, fn):
        def once():
            fn()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(int(ms), once)
