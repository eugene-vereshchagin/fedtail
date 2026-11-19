"""The emoji picker of the GTK editor: a popover with a search line and two tabs — the
standard emoji (their characters) and the server's own (:blobcat:, drawn as pictures).
What each tab lists and how a search ranks is common/compose.py's (the core searches);
this only draws it and hands the click back: on_pick(text) with a character, or with
":code: " for a server's.
"""

from __future__ import annotations

from ...i18n import _
from ..common import compose as rules
from .gi_setup import Gtk, tip

PIC = 32   # a server emoji's picture, in pixels
CELL = 44  # a cell of the grid: room for the glyph's ink, which is wider than its advance
COLUMNS = 8


class EmojiPicker(Gtk.Popover):
    """The popover itself; `standard` / `server` are its two tabs' content boxes (the
    standard one is absent with post.emoji_standard off)."""

    def __init__(self, win, on_pick):
        super().__init__()
        self.win, self.view, self.on_pick = win, win.view, on_pick
        self.items = None       # the server's emoji, once they came; None: asked for
        self.failed = False
        self.has_standard = bool(win.cfg["post"].get("emoji_standard", True))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for m in ("start", "end", "top", "bottom"):
            getattr(box, "set_margin_" + m)(8)
        title = Gtk.Label(label=_("emoji_title"), xalign=0)
        title.add_css_class("ft-lane-title")
        box.append(title)
        self.search = Gtk.SearchEntry(placeholder_text=_("emoji_search"))
        self.search.connect("search-changed", lambda _e: self.refresh())
        box.append(self.search)
        self.tabs = Gtk.Notebook()
        self.standard = self._page(_("emoji_tab_standard")) if self.has_standard else None
        self.server = self._page(_("emoji_tab_server"))
        box.append(self.tabs)
        # the emoji's options, at hand where emoji are picked (none found them, 19.11)
        self.settings_btn = Gtk.Button(label=_("emoji_settings"), halign=Gtk.Align.START)
        self.settings_btn.add_css_class("flat")
        tip(self.settings_btn, _("emoji_settings_tip"))
        self.settings_btn.connect("clicked", lambda _b: self.open_settings())
        box.append(self.settings_btn)
        self.set_child(box)
        self.connect("show", lambda _p: self._shown())

    def open_settings(self):
        """The settings window, its search at the emoji options."""
        self.popdown()
        self.win.open_settings("emoji")

    def _page(self, label):
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for m in ("start", "end", "top", "bottom"):
            getattr(inner, "set_margin_" + m)(4)
        # never sideways: a row wider than the window cut its last emoji in half (19.11)
        # (then the content's own width is the window's: min_content_width counts no more)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        inner.set_size_request(COLUMNS * (CELL + 2) + 8, -1)
        scroll.set_min_content_height(300)
        scroll.set_child(inner)
        self.tabs.append_page(scroll, Gtk.Label(label=label))
        return inner

    def _shown(self):
        if self.items is None and not self.failed:
            self.items = []   # asked once; the answer fills it
            self.win.call(self.view.emoji_all(), self._came, self._not_came)
        self.refresh()
        self.search.grab_focus()

    def _came(self, items):
        self.items = list(items or [])
        self.refresh()

    def _not_came(self, _err):
        self.failed = True
        self.items = None
        self.refresh()

    def words(self):
        return self.search.get_text().strip()

    def refresh(self):
        """Both tabs drawn anew for what the search line says."""
        words = self.words()
        if self.standard is not None:
            self._fill(self.standard, rules.emoji_standard(self.view, words), "standard", words)
        self._fill(self.server, rules.emoji_server(self.items or [], words), "server", words)

    def _fill(self, box, groups, kind, words):
        child = box.get_first_child()
        while child is not None:
            nxt = child.get_next_sibling()
            box.remove(child)
            child = nxt
        if not groups:
            none = Gtk.Label(xalign=0, wrap=True)
            none.add_css_class("ft-muted")
            if words or kind == "standard":
                none.set_text(_("emoji_none"))
            elif self.items is None:
                none.set_text(_("load_failed", err=""))
            else:
                none.set_text(_("emoji_server_none"))
            box.append(none)
            return
        for name, items in groups:
            if name:
                head = Gtk.Label(label=name, xalign=0)
                head.add_css_class("ft-muted")
                box.append(head)
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=True,
                               min_children_per_line=1, max_children_per_line=COLUMNS,
                               column_spacing=2, row_spacing=2)
            for e in items:
                flow.append(self._button(e, kind))
            box.append(flow)

    def _button(self, e, kind):
        if kind == "standard":
            b = Gtk.Button(label=e["char"])
            tip(b, ":" + e["code"] + ":")
            b.connect("clicked", lambda _b, t=e["char"]: self.on_pick(t))
        else:
            code = e["shortcode"]
            b = self._picture_button(e) or Gtk.Button(label=":" + code + ":")
            tip(b, ":" + code + ":")
            b.connect("clicked", lambda _b, t=f":{code}: ": self.on_pick(t))
        b.add_css_class("flat")
        b.add_css_class("ft-emoji")
        # a square cell of its own; a button clips what sticks out of it (GTK's default),
        # and a colour emoji's ink is wider than the width it says it takes (19.11)
        b.set_size_request(CELL, CELL)
        b.set_overflow(Gtk.Overflow.VISIBLE)
        b.set_focus_on_click(False)
        return b

    def _picture_button(self, e):
        """A button with the emoji's picture (once it comes), or None: no picture to ask."""
        images = getattr(self.win, "images", None)
        url = e.get("static_url") or e.get("url")
        if images is None or not url:
            return None
        # Gtk.Image at a pixel size: the picture fits in PIC × PIC, its shape kept. A
        # Gtk.Picture took the picture's own size (64 px) and the button cut it (19.11)
        pic = Gtk.Image(pixel_size=PIC)
        b = Gtk.Button()
        b.set_child(pic)
        images.get(url, pic.set_from_paintable, max_side=PIC * 2, owner=pic)
        return b
