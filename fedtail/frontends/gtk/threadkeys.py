"""The keys of a thread's tab in the GTK window: j / k walk its posts, r f b m o and
Enter act on the one under the cursor, ] / [ go to the next / previous top comment and
- folds a branch — the lanes' keys and Qt's thread keys, by the same rules
(common/postkeys). The tab had none of them: the keys lived in the lane only (23.11)."""

from __future__ import annotations

from ..common import postkeys
from .gi_setup import Gdk, GLib, Gtk


class ThreadKeys:
    def __init__(self, win, page):
        """win: the main window (on_link, cfg, tabs); page: the thread's tab (its items,
        box and, for a big thread, its ThreadWindow)."""
        self.win, self.page = win, page
        self.cursor = None
        self.folded, self.hidden = set(), set()
        # on the window, not the tab: a click in a thread's list leaves the focus where
        # GTK's list puts it — often nowhere, and the keys never came to the tab (23.11);
        # taken only while this tab is the one shown (_key)
        self.ctl = Gtk.EventControllerKey()
        self.ctl.connect("key-pressed", self._key)
        win.add_controller(self.ctl)

    def detach(self):
        """The tab closed: its keys leave the window."""
        if self.ctl is not None:
            self.win.remove_controller(self.ctl)
            self.ctl = None

    def _shown(self):
        tabs = getattr(self.win, "tabs", None)
        return tabs is not None and self.page.get_root() is not None and \
            tabs.get_nth_page(tabs.get_current_page()) is self.page

    def _show_hidden(self, keys):
        """These posts' cards in or out of sight, as self.hidden says now."""
        for k in keys:
            place = self._place(k)
            if place is not None:  # the card (or slot) and the list's row around it
                row = place.get_parent()
                for w in (place, row if isinstance(row, Gtk.ListBoxRow) else None):
                    if w is not None:
                        w.set_visible(k not in self.hidden)
        window = getattr(self.page, "window", None)
        if window is not None:
            window.soon()

    def unfold_for(self, sid):
        """The post to go to lies in a folded branch ("to the next new one"): the branch
        is shown again (common/postkeys)."""
        every = self._ids()
        head = postkeys.unfold_for(self.folded, self.hidden, every, sid, self._depth_of)
        if head is not None:
            self._show_hidden(postkeys.branch(every, head, self._depth_of)[1])

    # ---- the posts --------------------------------------------------------------------
    def _ids(self):
        return [it.post.id for it in self.page.items]

    def _depth_of(self, sid):
        return next((it.depth for it in self.page.items if it.post.id == sid), 0)

    def _place(self, sid):
        """The widget that stands for sid in the tab: its card, or a big thread's slot
        (its card built)."""
        from .window import _cards
        window = getattr(self.page, "window", None)
        if window is not None:
            return window.bring(sid)
        from ...model import real
        return next((c for c in _cards(self.page) if real(c.entry).id == sid), None)

    def _card(self, sid):
        w = self._place(sid)
        return getattr(w, "card", w) if w is not None else None

    def put_cursor(self, sid):
        """The cursor to sid: its card marked, and on screen."""
        old = self._card(self.cursor) if self.cursor is not None else None
        if old is not None:
            old.remove_css_class("ft-keyed")
        self.cursor = sid
        card = self._card(sid)
        if card is not None:
            card.add_css_class("ft-keyed")
        place = self._place(sid)
        if place is not None:
            from .window import _scroll_to
            GLib.idle_add(lambda: (_scroll_to(self.page, self.page.box, place),
                                   GLib.SOURCE_REMOVE)[1])

    # ---- the keys ---------------------------------------------------------------------
    def _key(self, _ctl, keyval, _code, state):
        from .keys import key_of
        if state & Gdk.ModifierType.SUPER_MASK or not self._shown():
            return False
        key = key_of(keyval, state)
        if postkeys.meaning(self.win.cfg, key) is None:
            return False
        focus = self.win.get_focus()
        if isinstance(focus, (Gtk.Text, Gtk.TextView, Gtk.Entry)):
            return False  # typing somewhere: its letters
        return self.press(key)

    def press(self, key):
        """A key (core.keys.Key, or as written: "j", "]") → whether it was the thread's:
        what it means is the config's ([keys], common/postkeys.meaning)."""
        if isinstance(key, str):
            from ...core import keys as keymap
            key = keymap.parse(key)
        what = postkeys.meaning(self.win.cfg, key)
        every = self._ids()
        posts = [k for k in every if k not in self.hidden]
        if what is None or not posts:
            return False
        kind, value = what
        if kind == "walk":
            from .window import _thread_on_top
            sid = postkeys.step(posts, self.cursor, value, _thread_on_top(self.page))
        elif kind == "top":
            sid = postkeys.top_comment(posts, self.cursor, value, self._depth_of)
        elif kind == "fold":
            if self.cursor not in posts:
                return False
            head, below = postkeys.branch(every, self.cursor, self._depth_of)
            if not postkeys.fold(self.folded, self.hidden, head, below):
                return False
            self._show_hidden(below)
            sid = head
        else:
            action = value
            if self.cursor not in posts:
                return False
            self.win.on_link(postkeys.link(action, self.cursor))
            return True
        if sid is None:
            return False
        self.put_cursor(sid)
        return True
