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
    widget._ft_tip = text or ""
    # connected once, when there is a text at last (first given empty, then set: it
    # never showed)
    if not text or getattr(widget, "_ft_tip_on", False):
        return
    widget._ft_tip_on = True

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
                # the width the child will get — never below what it needs: measured at
                # less, GTK warned at every layout ("needs at least 814"), 20 000 lines
                # a bench, and the height came out for a width it never had
                lo_w = self.child.measure(Gtk.Orientation.HORIZONTAL, -1)[0]
                for_size = max(lo_w, min(for_size, self.max_width))
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


_FIT = []


def fit_box(child, width, height, least=96):
    """child in a box of width × height that narrows with the window, its shape kept
    (height for width) — never below `least` px wide. A size request instead was a
    minimum: a picture 800 px wide kept the lane past an 800 px window's edge, and an
    overlay over it told GTK two different least heights."""
    if not _FIT:
        class Fit(Gtk.Widget):
            def __init__(self, child, width, height, least):
                super().__init__()
                self.w, self.h = max(1, int(width)), max(1, int(height))
                self.least = min(self.w, least)
                self.child = child
                child.set_parent(self)
                self.set_overflow(Gtk.Overflow.HIDDEN)

            def do_get_request_mode(self):
                return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

            def do_measure(self, orientation, for_size):
                if orientation == Gtk.Orientation.HORIZONTAL:
                    return self.least, self.w, -1, -1
                # the least height is the same at any width (GTK holds a widget's least
                # height for a width never to grow as the width does: a picture's does,
                # and it said "Expect overlapping widgets"); the natural one keeps the
                # shape — a lane gives the natural one
                width = self.w if for_size < 0 else max(self.least, min(for_size, self.w))
                least = max(1, round(self.h * self.least / self.w))
                return least, max(least, round(self.h * width / self.w)), -1, -1

            def do_size_allocate(self, width, height, baseline):
                # given less height than the shape wants at this width (a parent that
                # hands out least heights — GTK 4.18's box did, and the picture's bottom
                # was cut off), the child narrows instead: smaller, never cut
                want = round(self.h * width / self.w)
                if height < want:
                    width = max(1, round(self.w * height / self.h))
                self.child.allocate(width, height, -1, None)

            def do_dispose(self):
                if self.child is not None:
                    self.child.unparent()
                    self.child = None
        _FIT.append(Fit)
    return _FIT[0](child, width, height, least)


_WRAP = []


def wrap_box(spacing=4, row_spacing=2, align_end=False):
    """Children in a row that wraps to the next line where the width runs out, each at
    its natural width, lines left (or right) aligned — what a FlowBox isn't (a grid:
    columns as wide as the widest, a narrow one stacks them all). append(w), remove(w),
    get_first_child() as a box's."""
    if not _WRAP:
        class Wrap(Gtk.Widget):
            def __init__(self, spacing, row_spacing, align_end):
                super().__init__()
                self.spacing, self.row_spacing, self.align_end = \
                    spacing, row_spacing, align_end

            _cache = None  # width -> lines, while the children stay as they are

            def append(self, w):
                w.set_parent(self)
                self._cache = None

            def remove(self, w):
                w.unparent()
                self._cache = None

            def _kids(self):
                c = self.get_first_child()
                while c is not None:
                    if c.get_visible():
                        yield c
                    c = c.get_next_sibling()

            def _lines(self, width):
                """[(height, [(child, w, h)])] for this width — the same width asked by
                the measure and then the allocation is worked out once."""
                cache = self._cache
                if cache is None:
                    cache = self._cache = {}
                got = cache.get(width)
                if got is None:
                    if len(cache) > 6:
                        cache.clear()
                    got = cache[width] = self._lay(width)
                return got

            def _lay(self, width):
                lines, line, used, tall = [], [], 0, 0
                hor, ver = Gtk.Orientation.HORIZONTAL, Gtk.Orientation.VERTICAL
                for c in self._kids():
                    lo, nat = c.measure(hor, -1)[:2]
                    w = max(lo, min(nat, width))
                    if line and used + self.spacing + w > width:
                        lines.append((tall, line))
                        line, used, tall = [], 0, 0
                    h = c.measure(ver, w)[1]
                    used += (self.spacing if line else 0) + w
                    tall = max(tall, h)
                    line.append((c, w, h))
                if line:
                    lines.append((tall, line))
                return lines

            def do_get_request_mode(self):
                return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

            def do_measure(self, orientation, for_size):
                kids = list(self._kids())
                if orientation == Gtk.Orientation.HORIZONTAL:
                    # a layout starts with the width: what the children say may have
                    # changed (a counter, a theme), so the lines are worked out anew
                    self._cache = None
                    lo = max((c.measure(orientation, -1)[0] for c in kids), default=0)
                    nat = sum(c.measure(orientation, -1)[1] for c in kids) + \
                        self.spacing * max(0, len(kids) - 1)
                    return lo, max(lo, nat), -1, -1
                if for_size < 0:  # at the least width: the most lines
                    for_size = self.do_measure(Gtk.Orientation.HORIZONTAL, -1)[0]
                lines = self._lines(for_size)
                h = sum(t for t, _ in lines) + self.row_spacing * max(0, len(lines) - 1)
                return h, h, -1, -1

            def do_size_allocate(self, width, height, baseline):
                y = 0
                for tall, line in self._lines(width):
                    used = sum(w for _, w, _ in line) + self.spacing * (len(line) - 1)
                    x = max(0, width - used) if self.align_end else 0
                    for c, w, _h in line:
                        r = Gdk.Rectangle()
                        r.x, r.y, r.width, r.height = x, y, w, tall
                        c.size_allocate(r, -1)
                        x += w + self.spacing
                    y += tall + self.row_spacing

            def do_dispose(self):
                while (c := self.get_first_child()) is not None:
                    c.unparent()
        _WRAP.append(Wrap)
    return _WRAP[0](spacing, row_spacing, align_end)


_SIDE = []


def side_by_side(left, right, spacing=8):
    """left at its natural width (narrower when it must, down to its least), right in
    the rest — a header's words and its buttons. Not a horizontal box: GTK 4.18 takes a
    box's least height as its children's at their least width, and a row of buttons
    that wraps is tallest there ("GtkBox reported min height 210 and natural height
    87"). Here the height is asked at the width each one gets."""
    if not _SIDE:
        class Side(Gtk.Widget):
            def __init__(self, left, right, spacing):
                super().__init__()
                self.left, self.right, self.spacing = left, right, spacing
                left.set_parent(self)
                right.set_parent(self)

            def _split(self, width):
                hor = Gtk.Orientation.HORIZONTAL
                l_lo, l_nat = self.left.measure(hor, -1)[:2]
                r_lo = self.right.measure(hor, -1)[0]
                room = max(0, width - self.spacing)
                lw = max(l_lo, min(l_nat, room - r_lo))
                return lw, max(r_lo, room - lw)

            def do_get_request_mode(self):
                return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

            def do_measure(self, orientation, for_size):
                hor = Gtk.Orientation.HORIZONTAL
                if orientation == hor:
                    l_lo, l_nat = self.left.measure(hor, -1)[:2]
                    r_lo, r_nat = self.right.measure(hor, -1)[:2]
                    return (l_lo + self.spacing + r_lo, l_nat + self.spacing + r_nat,
                            -1, -1)
                if for_size < 0:
                    for_size = self.do_measure(hor, -1)[1]
                lw, rw = self._split(for_size)
                ver = Gtk.Orientation.VERTICAL
                h = max(self.left.measure(ver, lw)[1], self.right.measure(ver, rw)[1])
                return h, h, -1, -1

            def do_size_allocate(self, width, height, baseline):
                lw, rw = self._split(width)
                a = Gdk.Rectangle()
                a.x, a.y, a.width, a.height = 0, 0, lw, height
                self.left.size_allocate(a, -1)
                b = Gdk.Rectangle()
                b.x, b.y, b.width, b.height = width - rw, 0, rw, height
                self.right.size_allocate(b, -1)

            def do_dispose(self):
                for c in (self.left, self.right):
                    if c is not None and c.get_parent() is self:
                        c.unparent()
                self.left = self.right = None
        _SIDE.append(Side)
    return _SIDE[0](left, right, spacing)
