"""Pictures for the GTK window: common/images.py's cache (the one the Qt window has:
memory and disk, newest first, retried when a server was only busy, the disk kept
within its size), with GTK's pictures — decoded in the workers by GdkPixbuf, already no
bigger than asked (a big JPEG is read small), and handed over as a Gdk.Texture, which
any thread may make and widgets take as they are."""

from __future__ import annotations

from ..common import images as common
from ..common.images import FEED_SIDE  # noqa: F401  (the size of a feed picture)
from .gi_setup import GLib

# imagesniff's names → GdkPixbuf's loaders
_LOADER = {"jpeg": "jpeg", "png": "png", "gif": "gif", "webp": "webp", "bmp": "bmp",
           "avif": "avif", "heic": "heif", "jxl": "jxl", "tiff": "tiff", "ico": "ico",
           "svg": "svg"}


def decode(data, max_side, fmt=None):
    """A Gdk.Texture of the picture in data, no bigger than max_side — or None. fmt:
    read by that loader only, not by whichever claims the bytes (core/imagesniff.py)."""
    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf

    if fmt is None:
        from ...core import imagesniff
        fmt, _why = imagesniff.readable(data)
        if fmt is None:
            return None
    try:
        loader = GdkPixbuf.PixbufLoader.new_with_type(_LOADER.get(fmt, fmt))
    except GLib.Error:  # no loader for it here: Pillow may know it
        return _with_pillow(data, max_side)

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
        return _with_pillow(data, max_side)
    pix = loader.get_pixbuf()
    if pix is None:
        return _with_pillow(data, max_side)
    return texture_of(pix)


def texture_of(pix):
    """A GdkPixbuf as a texture: the pixels as they are (new_for_pixbuf is deprecated
    in newer GTK)."""
    from gi.repository import Gdk
    try:
        fmt = Gdk.MemoryFormat.R8G8B8A8 if pix.get_has_alpha() else Gdk.MemoryFormat.R8G8B8
        return Gdk.MemoryTexture.new(pix.get_width(), pix.get_height(), fmt,
                                     pix.read_pixel_bytes(), pix.get_rowstride())
    except (AttributeError, TypeError, ValueError):  # bindings that lack it
        return Gdk.Texture.new_for_pixbuf(pix)


def _with_pillow(data, max_side):
    """What GdkPixbuf can't read (WebP — what GoToSocial serves — without
    webp-pixbuf-loader, AVIF…): through Pillow, when it's there. None otherwise."""
    try:
        import io

        from gi.repository import Gdk
        from PIL import Image
    except ImportError:
        return None
    try:
        img = Image.open(io.BytesIO(data))
        img.draft("RGB", (max_side, max_side))  # a JPEG read small
        img = img.convert("RGBA")
        img.thumbnail((max_side, max_side))
    except Exception:  # noqa: BLE001 — anything Pillow can't read: no picture
        return None
    w, h = img.size
    return Gdk.MemoryTexture.new(w, h, Gdk.MemoryFormat.R8G8B8A8,
                                 GLib.Bytes.new(img.tobytes()), w * 4)


class Images(common.Cache):
    FORMAT_HINT = ("GTK can't read this format — WebP needs webp-pixbuf-loader "
                   "(or python3-pil), AVIF libavif-gdk-pixbuf")

    def decode(self, data, max_side, fmt=None):
        return decode(data, max_side, fmt)

    def size(self, picture):
        return picture.get_width(), picture.get_height()

    def later(self, ms, fn):
        def once():
            fn()
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(int(ms), once)
