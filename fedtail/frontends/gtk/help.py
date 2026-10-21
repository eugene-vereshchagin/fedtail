"""The help as a panel inside the main window, like the compose panel and as the Qt
one (qt/help.py): the contents on the left — the short pages, then the deep dive under
"In detail", then what the app itself knows (my server, the federation) — the page on
the right; Back / Forward, a search over all pages (Enter: the next place with the
word), ✕ or Esc to close. Closed, it's only hidden: the next ≡ → Help is back where it
was left.

A page is Markdown (frontends/helpdocs.py) made into Pango markup (pango.markdown), a
label a section: so a link to a heading (#anchor) scrolls to it."""

from __future__ import annotations

import logging
import re

from ...i18n import _
from .. import helpdocs, pango
from .gi_setup import GLib, Gtk, Pango, tip

log = logging.getLogger(__name__)

PCT = 90  # of the main window, as the compose panel's big size
APP_PAGES = [("app:server", "server_info"), ("app:federation", "fed_title")]
_HEADING = re.compile(r"^(#{1,6}) +(.+?)\s*$")


def sections(md):
    """[(anchor, markdown)]: the page cut before each heading (not inside ``` code)."""
    out, cur, anchor, code = [], [], "", False
    for line in (md or "").split("\n"):
        if line.strip().startswith("```"):
            code = not code
        m = None if code else _HEADING.match(line)
        if m and cur:
            out.append((anchor, "\n".join(cur)))
            cur = []
        if m:
            anchor = helpdocs.slug(m.group(2))
        cur.append(line)
    if cur:
        out.append((anchor, "\n".join(cur)))
    return out


class HelpPanel(Gtk.Box):
    def __init__(self, win):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.win = win
        self.lang = helpdocs.language()
        self.history, self.at = [], -1
        self.current = None
        self.found_at = -1  # the section Enter in the search found last
        self.add_css_class("ft-compose-panel")
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, vexpand=True)
        for m in ("top", "bottom", "start", "end"):
            getattr(inner, "set_margin_" + m)(14)
        self.append(inner)

        head = Gtk.Box(spacing=6)
        head.add_css_class("ft-compose-head")
        self.back_btn = self._tool("←", _("help_back"), self.back)
        self.fwd_btn = self._tool("→", _("help_forward"), self.forward)
        head.append(self.back_btn)
        head.append(self.fwd_btn)
        title = Gtk.Label(label=_("help_title"), xalign=0, hexpand=True)
        title.add_css_class("ft-lane-title")
        head.append(title)
        self.search = Gtk.SearchEntry(placeholder_text=_("help_search"))
        self.search.set_size_request(220, -1)
        self.search.connect("search-changed", lambda e: self._filter(e.get_text()))
        self.search.connect("activate", lambda _e: self.find_next())
        head.append(self.search)
        head.append(self._tool("✕", _("help_close_tip") + " (Esc)", self.close))
        inner.append(head)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        side = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.toc = Gtk.ListBox()
        self.toc.add_css_class("ft-help-toc")
        self.toc.connect("row-activated", self._picked)
        self.toc.set_activate_on_single_click(True)
        toc_scroll = Gtk.ScrolledWindow(vexpand=True)
        toc_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        toc_scroll.set_child(self.toc)
        side.append(toc_scroll)
        self.found = Gtk.Label(xalign=0, visible=False)
        self.found.add_css_class("ft-muted")
        side.append(self.found)
        side.set_size_request(200, -1)
        paned.set_start_child(side)
        paned.set_resize_start_child(False)
        paned.set_shrink_start_child(False)
        self.page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        for m in ("top", "bottom", "start", "end"):
            getattr(self.page, "set_margin_" + m)(10)
        self.scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scroll.set_child(self.page)
        self.scroll.add_css_class("ft-view")
        paned.set_end_child(self.scroll)
        paned.set_position(240)
        inner.append(paned)
        self.blocks = []  # [(anchor, label, plain text)] of the page shown

        key = Gtk.EventControllerKey()
        key.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        key.connect("key-pressed", self._key)
        self.add_controller(key)
        self._fill_toc()
        self._ticking = 0

    def _tool(self, glyph, tip_text, fn):
        b = Gtk.Button(label=glyph)
        b.add_css_class("flat")
        tip(b, tip_text)
        b.connect("clicked", lambda _b: fn())
        return b

    # ---- in the window -----------------------------------------------------------------
    def open(self, page="index", anchor=""):
        win = self.win
        if self.get_parent() is None:
            win.overlay.add_overlay(self)
        self.set_visible(True)
        if not self._ticking:
            self._ticking = self.add_tick_callback(lambda *_a: self._place())
        self._place()
        if page != "index" or anchor or self.current is None:
            self.show_page(page, anchor)
        self.scroll.grab_focus()
        return self

    def _place(self):
        parent = self.win.overlay
        w, h = parent.get_width(), parent.get_height()
        if w <= 0 or h <= 0:
            return GLib.SOURCE_CONTINUE
        pw, ph = max(480, int(w * PCT / 100) - 20), max(360, int(h * PCT / 100) - 20)
        pw, ph = min(pw, w), min(ph, h)
        mx, my = max(0, (w - pw) // 2), max(0, (h - ph) // 2)
        if (self.get_margin_start(), self.get_margin_top(), self.get_margin_end(),
                self.get_margin_bottom()) != (mx, my, w - pw - mx, h - ph - my):
            self.set_margin_start(mx)
            self.set_margin_end(w - pw - mx)
            self.set_margin_top(my)
            self.set_margin_bottom(h - ph - my)
        return GLib.SOURCE_CONTINUE

    def close(self):
        """✕ or Esc: hidden, not destroyed."""
        if self._ticking:
            self.remove_tick_callback(self._ticking)
            self._ticking = 0
        self.set_visible(False)

    def _key(self, _c, keyval, _code, _state):
        from .gi_setup import Gdk
        if Gdk.keyval_name(keyval) == "Escape":
            self.close()
            return True
        return False

    # ---- the contents --------------------------------------------------------------------
    def _row(self, text, name=None, deep=False, about=""):
        row = Gtk.ListBoxRow(selectable=name is not None, activatable=name is not None)
        lab = Gtk.Label(label=text, xalign=0)
        lab.set_ellipsize(Pango.EllipsizeMode.END)
        if name is None:
            lab.add_css_class("ft-help-deep")
        elif deep:
            lab.set_margin_start(16)
        row.set_child(lab)
        row.name = name
        tip(row, text + (f"\n{about}" if about else ""))
        self.toc.append(row)
        return row

    def _fill_toc(self, only=None):
        """The pages in the index's order; only — {page: matches} of a search."""
        while (c := self.toc.get_first_child()) is not None:
            self.toc.remove(c)
        deep_head = False
        for p in helpdocs.pages(self.lang):
            if only is not None and p.name not in only:
                continue
            if p.deep and not deep_head:
                self._row(_("help_deep"))
                deep_head = True
            label = p.title if only is None else f"{p.title}  ({only[p.name]})"
            self._row(label, p.name, p.deep, p.about)
        if only is None:
            self._row(_("info_head"))
            for name, word in APP_PAGES:
                self._row(_(word), name, True)
        self._mark_current()

    def _mark_current(self):
        row = self.toc.get_first_child()
        while row is not None:
            if getattr(row, "name", None) == self.current and self.current:
                self.toc.select_row(row)
                return
            row = row.get_next_sibling()
        self.toc.unselect_all()

    def _picked(self, _lb, row):
        name = getattr(row, "name", None)
        if name and name != self.current:
            self.show_page(name)
            if self.search.get_text().strip():
                self.found_at = -1
                self.find_next(from_top=True)

    # ---- pages ---------------------------------------------------------------------------
    def show_page(self, name, anchor="", record=True):
        if name.startswith("app:"):  # what the app knows: in its own window, as before
            if name == "app:server":
                self.win.show_server_info()
            elif name == "app:federation":
                self.win.federation_status()
            self._mark_current()
            return True
        text = helpdocs.page(self.lang, name)
        if text is None:
            log.info("help: no page %s", name)
            self.win.status(_("help_missing", name=name))
            return False
        if name != self.current:
            self._render(text)
            self.current = name
            self.found_at = -1
        self._scroll_to(anchor)
        if record:
            del self.history[self.at + 1:]
            self.history.append((name, anchor))
            self.at = len(self.history) - 1
        self._mark_current()
        self.back_btn.set_sensitive(self.at > 0)
        self.fwd_btn.set_sensitive(self.at < len(self.history) - 1)
        log.info("help: %s%s", name, f"#{anchor}" if anchor else "")
        return True

    def _render(self, md):
        while (c := self.page.get_first_child()) is not None:
            self.page.remove(c)
        self.blocks = []
        for anchor, chunk in sections(md):
            lab = Gtk.Label(xalign=0, yalign=0, wrap=True)
            lab.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            lab.set_markup(pango.markdown(chunk))
            lab.connect("activate-link", lambda _l, uri: (self.follow(uri), True)[1])
            self.page.append(lab)
            self.blocks.append((anchor, lab, helpdocs.plain(chunk).lower()))

    def _scroll_to(self, anchor="", index=None):
        adj = self.scroll.get_vadjustment()
        target = None
        if index is not None and 0 <= index < len(self.blocks):
            target = self.blocks[index][1]
        elif anchor:
            target = next((lab for a, lab, _t in self.blocks if a == anchor), None)
        if target is None:
            adj.set_value(0)
            return

        from .lane import y_in
        tries = [0]

        def go():
            y = y_in(target, self.page)
            first = target is self.page.get_first_child()
            if (y is None or (y == 0 and not first)) and tries[0] < 20:
                tries[0] += 1
                return GLib.SOURCE_CONTINUE  # not laid out yet
            adj.set_value(max(0.0, (y or 0) - 6))
            return GLib.SOURCE_REMOVE
        GLib.timeout_add(30, go)

    def follow(self, link):
        """A link on the page: another help page (and the place on it), or the browser."""
        target = helpdocs.resolve(link, self.lang, self.current or "index")
        if target.url:
            self.win.open_url(target.url)
        elif target.page:
            self.show_page(target.page, target.anchor)

    def back(self):
        if self.at > 0:
            self.at -= 1
            self.show_page(*self.history[self.at], record=False)

    def forward(self):
        if self.at < len(self.history) - 1:
            self.at += 1
            self.show_page(*self.history[self.at], record=False)

    # ---- search --------------------------------------------------------------------------
    def _filter(self, text):
        query = text.strip()
        self.found_at = -1
        if not query:
            self.found.set_visible(False)
            self._fill_toc()
            return
        hits = helpdocs.search(self.lang, query)
        self._fill_toc({p.name: n for p, n in hits})
        self.found.set_text(_("help_found", n=len(hits)) if hits else _("help_none"))
        self.found.set_visible(True)

    def find_next(self, from_top=False):
        """Enter in the search: the next part of the page with the query's first word;
        past the end, the next page that has it."""
        words = [helpdocs._stem(w) for w in self.search.get_text().lower().split()]
        if not words:
            return
        start = 0 if from_top else self.found_at + 1
        for i in range(start, len(self.blocks)):
            if words[0] in self.blocks[i][2]:
                self.found_at = i
                self._scroll_to(index=i)
                return
        names = []
        row = self.toc.get_first_child()
        while row is not None:
            if getattr(row, "name", None) and not row.name.startswith("app:"):
                names.append(row.name)
            row = row.get_next_sibling()
        if not names:
            return
        i = names.index(self.current) if self.current in names else -1
        nxt = names[(i + 1) % len(names)]
        if nxt != self.current:
            self.show_page(nxt)
        self.found_at = -1
        for j, (_a, _l, text) in enumerate(self.blocks):
            if words[0] in text:
                self.found_at = j
                self._scroll_to(index=j)
                return


def open_help(win, page="index", anchor=""):
    """≡ → Help: the panel over the lanes (in the split layout, the messages window's)."""
    if not win.get_visible():
        win.present()
    if win.help_panel is None:
        win.help_panel = HelpPanel(win)
    return win.help_panel.open(page, anchor)
