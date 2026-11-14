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

PIC = 32  # a server emoji's picture, in pixels


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
        self.set_child(box)
        self.connect("show", lambda _p: self._shown())

    def _page(self, label):
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for m in ("start", "end", "top", "bottom"):
            getattr(inner, "set_margin_" + m)(4)
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_width(380)
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
            flow = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                               min_children_per_line=1, max_children_per_line=12,
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
        b.set_focus_on_click(False)
        return b

    def _picture_button(self, e):
        """A button with the emoji's picture (once it comes), or None: no picture to ask."""
        images = getattr(self.win, "images", None)
        url = e.get("static_url") or e.get("url")
        if images is None or not url:
            return None
        pic = Gtk.Picture()
        pic.set_size_request(PIC, PIC)
        pic.set_can_shrink(True)
        pic.set_alternative_text(":" + e["shortcode"] + ":")
        b = Gtk.Button()
        b.set_child(pic)
        images.get(url, pic.set_paintable, max_side=PIC * 2, owner=pic)
        return b
