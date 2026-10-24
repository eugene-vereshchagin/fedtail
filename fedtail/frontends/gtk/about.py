"""About fedtail, as cards — Qt's window (qt/about.py) drawn by GTK: the opossum and the
name, a grid of tiles, rows, who made it, the links, "Copy the information"."""

from __future__ import annotations

from ...i18n import _
from ..common import about as facts_of
from .gi_setup import Gdk, GLib, Gtk, gtk_version

CSS = """
.ft-about-card { border-radius: 8px; padding: 8px 12px; }
.ft-about-name { font-size: 24pt; }
.ft-about-small { font-size: smaller; opacity: 0.7; }
.ft-about-muted { opacity: 0.7; }
"""


_provider = None


def _label(text, *classes, wrap=False, select=False):
    lab = Gtk.Label(label=text, xalign=0, wrap=wrap, selectable=select)
    for c in classes:
        lab.add_css_class(c)
    return lab


def _card():
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
    box.add_css_class("ft-about-card")
    box.add_css_class("ft-card")  # the theme's card colours
    return box


def show(win):
    a = facts_of.facts(win.view, "GTK", ".".join(str(x) for x in gtk_version()))
    dlg = Gtk.Window(transient_for=win, modal=True, title=_("about"))
    dlg.set_default_size(640, -1)
    global _provider
    if _provider is None:  # once a run: the cards' own few rules over the theme's
        _provider = Gtk.CssProvider()
        if hasattr(_provider, "load_from_string"):
            _provider.load_from_string(CSS)
        else:
            _provider.load_from_data(CSS, -1)
        Gtk.StyleContext.add_provider_for_display(
            dlg.get_display(), _provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 1)
    outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    for m in ("top", "bottom", "start", "end"):
        getattr(outer, f"set_margin_{m}")(18)

    head = _card()
    head.set_orientation(Gtk.Orientation.HORIZONTAL)
    head.set_spacing(18)
    try:
        from importlib import resources
        pic = Gtk.Image.new_from_paintable(Gdk.Texture.new_from_filename(
            str(resources.files("fedtail").joinpath("data/icons/fedtail.png"))))
        pic.set_pixel_size(96)
        head.append(pic)
    except (GLib.Error, OSError):
        pass
    words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
    name = _label("fedtail", "ft-about-name", "ft-active")
    words.append(name)
    words.append(_label(a.tagline, "ft-about-muted", wrap=True))
    words.append(_label(a.version, select=True))
    head.append(words)
    outer.append(head)

    grid = Gtk.Grid(column_spacing=10, row_spacing=10, column_homogeneous=True)
    for i, (label, value) in enumerate(a.tiles):
        tile = _card()
        tile.append(_label(label, "ft-about-small"))
        tile.append(_label(value, select=True))
        tile.set_hexpand(True)
        grid.attach(tile, i % 3, i // 3, 1, 1)
    outer.append(grid)

    for label, value in a.rows:
        row = _card()
        row.set_orientation(Gtk.Orientation.HORIZONTAL)
        left = _label(label, "ft-about-muted")
        left.set_size_request(130, -1)
        row.append(left)
        right = _label(value, wrap=True, select=True)
        right.set_hexpand(True)
        row.append(right)
        outer.append(row)

    outer.append(_label(a.made_by, "ft-about-muted", wrap=True))
    from urllib.parse import quote
    def href(u):  # the code in the browser; the author here, with Follow on the page
        return u if "github" in u else "fedtail:resolve/" + quote(u, safe="")
    links = " · ".join(f'<a href="{GLib.markup_escape_text(href(u))}">'
                       f"{GLib.markup_escape_text(w)}</a>" for w, u in a.links)
    link_line = Gtk.Label(xalign=0)
    link_line.set_markup(links)

    def go(_lab, uri):
        dlg.close()
        win.on_link(uri) if uri.startswith("fedtail:") else win.open_url(uri)
        return True
    link_line.connect("activate-link", go)
    outer.append(link_line)

    bar = Gtk.Box(spacing=8)
    copied = _label("", "ft-about-muted")
    copied.set_hexpand(True)
    bar.append(copied)
    copy = Gtk.Button(label=_("about_copy"))
    copy.add_css_class("ft-primary")
    copy.add_css_class("suggested-action")

    def do_copy(_b):
        dlg.get_clipboard().set(a.text())
        copied.set_text(_("about_copied"))
    copy.connect("clicked", do_copy)
    bar.append(copy)
    close = Gtk.Button(label=_("close"))
    close.connect("clicked", lambda _b: dlg.close())
    bar.append(close)
    outer.append(bar)
    dlg.set_child(outer)
    dlg.present()
    win._about = dlg  # (tests look at it)
    return dlg
