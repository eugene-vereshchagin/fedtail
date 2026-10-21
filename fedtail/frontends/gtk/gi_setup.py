"""PyGObject imports in one place: GTK 4 always, libadwaita when it's there and wanted
(ui.adwaita = auto | on | off). Everything else in the package imports from here."""

try:
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Gdk", "4.0")
    from gi.repository import Gdk, Gio, GLib, GObject, Gtk, Pango
except (ImportError, ValueError) as e:  # no PyGObject, or no GTK 4 typelib
    raise ImportError(f"GTK 4 for Python not found: {e}") from e

MIN_GTK = (4, 10)

Adw = None


def gtk_version():
    return (Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version())


def load_adwaita(mode):
    """libadwaita if ui.adwaita allows and it is installed; None otherwise. "on" without
    it is an error the caller reports; "auto" just goes without."""
    global Adw
    if mode == "off":
        return None
    try:
        gi.require_version("Adw", "1")
        from gi.repository import Adw as _adw
    except (ImportError, ValueError):
        if mode == "on":
            raise
        return None
    Adw = _adw
    return Adw


__all__ = ["Adw", "Gdk", "Gio", "GLib", "GObject", "Gtk", "Pango", "MIN_GTK", "gtk_version",
           "load_adwaita"]



def tip(widget, text):
    """A tooltip given when it's asked for, not set ahead (once per widget):
    Gtk.Widget.set_tooltip_text also updates the widget's accessible description, and
    with an accessibility bus about (KDE's) every such update is a round trip — a few
    of them per card held the window for a third of a second per batch of cards.
    Called again on the same widget: the new text (or none)."""
    first = not hasattr(widget, "_ft_tip")
    widget._ft_tip = text or ""
    if not first or not text:
        return

    def query(w, _x, _y, _kb, tooltip):
        text = getattr(w, "_ft_tip", "")
        if not text:
            return False
        if HINTS["on"]:  # ≡ → What's this?: the help's word on it, if it has one
            rich = _hint(text)
            if rich:
                tooltip.set_markup(rich)
                return True
        tooltip.set_text(text)
        return True
    widget.set_has_tooltip(True)
    widget.connect("query-tooltip", query)


def set_markup(label, markup):
    """label.set_markup, only when it changed: each change is a trip to the accessibility
    bus (see tip), and the roster sets every row's text on every count."""
    if getattr(label, "_ft_markup", None) != markup:
        label._ft_markup = markup
        label.set_markup(markup)


def hscroll(child, end=False):
    """A row of buttons that takes its natural width where there's room and scrolls
    sideways where there isn't — never pushing the window past its edge."""
    sc = Gtk.ScrolledWindow()
    sc.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.NEVER)
    sc.set_propagate_natural_width(True)
    sc.set_propagate_natural_height(True)
    sc.set_has_frame(False)
    sc.set_child(child)
    sc.set_hexpand(not end)
    if end:
        sc.set_halign(Gtk.Align.END)
    sc.add_css_class("ft-hscroll")
    return sc


HINTS = {"on": False}


def _hint(text):
    from .. import helpdocs, pango
    found = helpdocs.hint_for(text)
    if not found:
        return None
    return pango.markup(helpdocs.hint_html(text, found[1]))


def clamp(child, max_width):
    """child no wider than max_width, centred — and narrower when the window is (a
    size request would be a minimum: the lane went past the window's edge). Adw.Clamp
    when libadwaita is there, else a widget of ours doing the same."""
    if Adw is not None and hasattr(Adw, "Clamp"):
        c = Adw.Clamp(maximum_size=max_width, tightening_threshold=max_width)
        c.set_child(child)
        return c
    return _clamp_class()(child, max_width)


def set_clamp(c, max_width):
    """A clamp made by clamp() to another width (↔: the posts across the window)."""
    if hasattr(c, "set_maximum_size"):
        c.set_maximum_size(max_width)
        c.set_tightening_threshold(max_width)
    else:
        c.max_width = max_width
        c.queue_resize()


_CLAMP = []


def _clamp_class():
    if _CLAMP:
        return _CLAMP[0]

    class Clamp(Gtk.Widget):
        def __init__(self, child, max_width):
            super().__init__()
            self.max_width = max_width
            self.child = child
            child.set_parent(self)

        def do_measure(self, orientation, for_size):
            if orientation == Gtk.Orientation.VERTICAL and for_size >= 0:
                for_size = min(for_size, self.max_width)
            lo, nat, lo_b, nat_b = self.child.measure(orientation, for_size)
            if orientation == Gtk.Orientation.HORIZONTAL:
                nat = max(lo, min(nat, self.max_width))
            return lo, nat, -1, -1

        def do_size_allocate(self, width, height, baseline):
            lo = self.child.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
            w = max(lo, min(width, self.max_width))
            alloc = Gdk.Rectangle()
            alloc.x, alloc.y, alloc.width, alloc.height = max(0, (width - w) // 2), 0, w, height
            self.child.size_allocate(alloc, -1)

        def do_get_request_mode(self):
            return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

        def do_dispose(self):
            if self.child is not None:
                self.child.unparent()
                self.child = None

    _CLAMP.append(Clamp)
    return Clamp
