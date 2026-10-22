"""Pictures and files coming in from outside: dropped on the editor or the window, or
pasted with Ctrl+V (a file manager's copied files, a screenshot, an image copied from a
browser) — as Qt's (qt/compose.py: media_paths, save_image).

GTK 4 hands them over as values: a Gdk.FileList for files, a Gdk.Texture for a picture
without a file. A texture is kept as PNG in the profile's data folder (attachments/), so
the draft can refer to it like any file."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from ..common.compose import MEDIA_EXT
from .gi_setup import Gdk, GLib, GObject, Gtk

log = logging.getLogger(__name__)


def media_paths(files):
    """Local media files out of Gio.Files (anything else — a folder, a text file, a
    remote URL — is left out)."""
    out = []
    for f in files or ():
        path = f.get_path() if f is not None else None
        if path and path.lower().endswith(MEDIA_EXT):
            out.append(str(Path(path)))
    return out


def save_texture(data_dir, texture):
    """A picture without a file as PNG under data_dir/attachments; its path or None."""
    try:
        folder = Path(data_dir) / "attachments"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"pasted-{datetime.now():%Y%m%d-%H%M%S-%f}.png"
        return str(path) if texture.save_to_png(str(path)) else None
    except (OSError, GLib.Error) as e:
        log.warning("couldn't keep a pasted picture: %s", e)
        return None


def paths_of(value, data_dir):
    """What a drop or the clipboard gave (FileList, Texture, a Gio.File) as file paths."""
    if isinstance(value, Gdk.FileList):
        return media_paths(value.get_files())
    if isinstance(value, Gdk.Texture):
        saved = save_texture(data_dir, value)
        return [saved] if saved else []
    get_path = getattr(value, "get_path", None)
    if get_path is not None:
        return media_paths([value])
    return []


def add_drop(widget, data_dir, take):
    """Files and pictures dropped on `widget` go to take(paths). The target says yes
    only to what can be attachments, so a drop of text still lands in the text."""
    target = Gtk.DropTarget.new(GObject.TYPE_NONE, Gdk.DragAction.COPY)
    target.set_gtypes([Gdk.FileList, Gdk.Texture])

    def dropped(_t, value, _x, _y):
        paths = paths_of(value, data_dir())
        if paths:
            take(paths)
        return bool(paths)
    target.connect("drop", dropped)
    widget.add_controller(target)
    return target


def wants_paste(clipboard):
    """The clipboard holds files, or a picture with no text along: Ctrl+V means
    attach them (a picture copied with its text — a web page's selection — pastes as
    text, as in Qt)."""
    formats = clipboard.get_formats()
    if formats.contain_gtype(Gdk.FileList):
        return "files"
    mimes = formats.get_mime_types() or []
    if any(m.startswith("text/") for m in mimes) or formats.contain_gtype(str):
        return None
    # another program offers image/png and the like; our own window, a texture of some
    # kind (GdkMemoryTexture is a GdkTexture, but not the same type)
    if any(m.startswith("image/") for m in mimes) or any(
            GObject.type_is_a(t, Gdk.Texture) for t in (formats.get_gtypes() or [])):
        return "picture"
    return None


def paste(widget, data_dir, take, as_text=None):
    """Ctrl+V on `widget`: True when the clipboard's files or picture are taken (they
    come in a moment later — reading the clipboard is asynchronous). Files that turn out
    not to be media go in as text instead (as_text(str)), as a plain paste would."""
    clipboard = widget.get_clipboard()
    kind = wants_paste(clipboard)
    if kind is None:
        return False

    def got_files(cb, res):
        try:
            value = cb.read_value_finish(res)
        except GLib.Error as e:
            log.info("paste: %s", e.message)
            return
        paths = paths_of(value, data_dir())
        if paths:
            take(paths)
        elif as_text is not None:
            cb.read_text_async(None, lambda c, r: _text_in(c, r, as_text))

    def got_picture(cb, res):
        try:
            texture = cb.read_texture_finish(res)
        except GLib.Error as e:
            log.info("paste: %s", e.message)
            return
        paths = paths_of(texture, data_dir()) if texture is not None else []
        if paths:
            take(paths)

    if kind == "files":
        clipboard.read_value_async(Gdk.FileList, GLib.PRIORITY_DEFAULT, None, got_files)
    else:
        clipboard.read_texture_async(None, got_picture)
    return True


def _text_in(cb, res, as_text):
    try:
        text = cb.read_text_finish(res)
    except GLib.Error:
        return
    if text:
        as_text(text)
