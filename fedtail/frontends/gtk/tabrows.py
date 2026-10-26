"""The messages window's tabs in the split layout, as the Qt window has them
(qt/dock.py MessageTabs): every lane, thread, profile and talk a chip, in as many rows
as they take — a messenger's contacts, never scrolled sideways out of sight;
shape.tab_rows = "wrap" (the Agent, QIP) stretches the full rows to the edge, "one"
doesn't. The notebook keeps holding the pages, its own strip hidden: this bar only
says which is in front, and reads each page's title and ✕ from the notebook's tab."""

from __future__ import annotations

from .gi_setup import GLib, Gtk, Pango, forget, tip

SYNC_MS = 1000  # titles change with the counts: compared once a second


def _parts(tab):
    """(the title label, the ✕ button) of a notebook tab widget."""
    label = close = None
    child = tab.get_first_child() if tab is not None else None
    if isinstance(tab, Gtk.Label):
        return tab, None
    while child is not None:
        if label is None and isinstance(child, Gtk.Label):
            label = child
        elif close is None and isinstance(child, Gtk.Button):
            close = child
        child = child.get_next_sibling()
    return label, close


class Chip(Gtk.Box):
    def __init__(self, bar, page):
        super().__init__(spacing=2)
        self.bar, self.page = bar, page
        self.add_css_class("ft-tabchip")
        self.text = Gtk.Label(xalign=0)
        self.text.set_ellipsize(Pango.EllipsizeMode.END)
        self.text.set_max_width_chars(24)
        self.text.set_hexpand(True)
        self.append(self.text)
        self.x = Gtk.Button(icon_name="window-close-symbolic")
        self.x.add_css_class("flat")
        self.x.add_css_class("ft-tabchip-x")
        self.x.connect("clicked", lambda _b: bar.close(page))
        self.append(self.x)
        click = Gtk.GestureClick(button=0)
        click.connect("released", self._clicked)
        self.add_controller(click)
        self.title = None

    def _clicked(self, g, _n, _x, _y):
        if self.page is None:  # its tab closed already
            return
        if g.get_current_button() == 2:  # the middle button closes, as tabs do
            self.bar.close(self.page)
        elif g.get_current_button() == 1:
            nb = self.bar.notebook
            nb.set_current_page(nb.page_num(self.page))

    def set_title(self, text):
        if text != self.title:
            self.title = text
            self.text.set_text(text)
            self.text.set_width_chars(min(len(text) + 1, 14))
            tip(self, text)


class TabRows(Gtk.FlowBox):
    def __init__(self, notebook, hidden=(), wrap=True):
        super().__init__()
        self.notebook, self.hidden, self.wrap = notebook, set(hidden), wrap
        self.add_css_class("ft-tabrows")
        self.set_selection_mode(Gtk.SelectionMode.NONE)
        self.set_homogeneous(False)
        self.set_max_children_per_line(64)
        self.set_min_children_per_line(1)
        self.set_row_spacing(2)
        self.set_column_spacing(2)
        self.set_activate_on_single_click(False)
        self.chips = {}  # page -> FlowBoxChild
        for sig in ("page-added", "page-removed", "page-reordered"):
            notebook.connect(sig, lambda *_a: GLib.idle_add(self._sync_once))
        notebook.connect("switch-page", lambda _nb, page, _n: self._mark(page))
        self._queued = False
        self._timer = GLib.timeout_add(SYNC_MS, self._tick)
        self.connect("destroy", lambda *_a: self._stop())
        self.sync()

    def _stop(self):
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def _tick(self):
        if self.get_mapped():
            self.sync()
        return GLib.SOURCE_CONTINUE

    def _sync_once(self):
        self.sync()
        return GLib.SOURCE_REMOVE

    def pages(self):
        nb = self.notebook
        return [p for p in (nb.get_nth_page(i) for i in range(nb.get_n_pages()))
                if p is not None and p not in self.hidden]

    def sync(self):
        """The chips made to agree with the notebook: one a page, in its order, its
        title as the tab says now, the one in front marked."""
        pages = self.pages()
        for page in [p for p in self.chips if p not in pages]:
            child = self.chips.pop(page)
            self.remove(child)
            chip = child.get_child()
            if chip is not None:
                chip.page = None  # the closed tab no longer held through its chip
            forget(child)  # the chip's handlers name it: a loop through C, kept alive
        order = [self.chips.get(p) for p in pages]
        if any(c is None for c in order) or order != self._shown():
            for c in list(self.chips.values()):
                self.remove(c)
            for p in pages:
                child = self.chips.get(p)
                if child is None:
                    child = Gtk.FlowBoxChild()
                    child.set_child(Chip(self, p))
                    child.set_focusable(False)
                    self.chips[p] = child
                child.set_hexpand(self.wrap)
                self.append(child)
        for p in pages:
            label, _close = _parts(self.notebook.get_tab_label(p))
            self.chips[p].get_child().set_title(label.get_text() if label else "")
        nb = self.notebook
        self._mark(nb.get_nth_page(nb.get_current_page()))
        self.set_visible(bool(pages))

    def _shown(self):
        out, c = [], self.get_first_child()
        while c is not None:
            out.append(c)
            c = c.get_next_sibling()
        return out

    def _mark(self, current):
        for p, child in self.chips.items():
            (child.add_css_class if p is current else child.remove_css_class)("ft-current")

    def close(self, page):
        """The tab's own ✕ — whatever it does for that page."""
        _label, close = _parts(self.notebook.get_tab_label(page))
        if close is not None:
            close.emit("clicked")
        GLib.idle_add(self._sync_once)
