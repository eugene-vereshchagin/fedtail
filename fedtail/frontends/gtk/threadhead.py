"""A thread's header in the GTK window, as Qt's: the root's first words, "a post and
N replies · #abc", why the replies reach me when I'm not subscribed (the server puts
replies between people I follow into Home), Subscribe (as on Point) and Refresh."""

from __future__ import annotations

from ...i18n import _
from ...model.text import snippet
from .gi_setup import Gtk, Pango, tip


class ThreadHead(Gtk.Box):
    def __init__(self, win, root_id):
        super().__init__(spacing=8)
        self.win, self.root_id = win, root_id
        self.root, self.info_text = None, ""
        self.add_css_class("ft-lane-header")
        words = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
        self.title = Gtk.Label(label=_("thread_loading"), xalign=0)
        self.title.add_css_class("ft-lane-title")
        self.title.set_ellipsize(Pango.EllipsizeMode.END)
        self.info = Gtk.Label(xalign=0)
        self.info.add_css_class("ft-muted")
        self.info.set_ellipsize(Pango.EllipsizeMode.END)
        words.append(self.title)
        words.append(self.info)
        self.append(words)
        self.sub = Gtk.ToggleButton(label=_("sub_thread"), valign=Gtk.Align.CENTER)
        tip(self.sub, _("sub_tip"))
        self.sub.set_sensitive(False)
        self._sub_signal = self.sub.connect("toggled", lambda _b: self._toggle())
        self.append(self.sub)
        again = Gtk.Button(label=_("refresh"), valign=Gtk.Align.CENTER)
        again.connect("clicked", lambda _b: self.win.reload_thread(self.root_id))
        self.append(again)

    def show(self, posts, short):
        """The thread as it came: posts in order, the root first; short: id → #abc."""
        if not posts:
            return
        self.root = posts[0]
        self.title.set_text(snippet(self.root, 60) or "@" + self.root.author.handle)
        sid = short.get(self.root.id)
        self.info_text = _("thread_info", n=len(posts) - 1) + (f" · #{sid}" if sid else "")
        self.info.set_text(self.info_text)
        tip(self.info, "")
        self._sub_state()
        self._why_it_reaches_me(posts)

    def _sub_state(self):
        on = bool(self.win.view.subscribed(self.root))
        self.sub.handler_block(self._sub_signal)
        self.sub.set_active(on)
        self.sub.handler_unblock(self._sub_signal)
        self.sub.set_label(_("subscribed") if on else _("sub_thread"))
        self.sub.set_sensitive(True)
        if on:
            self.info.set_text(self.info_text)
            tip(self.info, "")

    def _toggle(self):
        if self.root is None:
            return
        on = bool(self.win.view.subscribed(self.root))
        self.sub.set_sensitive(False)
        job = (self.win.view.unsubscribe if on else self.win.view.subscribe)(self.root)
        self.win.call(job, lambda _r: (self.win.status(_("unsubbed" if on else "subbed")),
                                        self._sub_state()),
                      lambda e: (self.win.error(e), self._sub_state()))

    def _why_it_reaches_me(self, posts):
        """Not subscribed, yet the comments come? Say why, as Qt does."""
        if self.win.view.subscribed(self.root):
            return
        root = self.root

        def show(followed):
            if not followed or self.root is not root or self.win.view.subscribed(root):
                return
            names = ", ".join("@" + a.handle.split("@")[0] for a in followed[:3])
            if len(followed) > 3:
                names += " " + _("and_more", n=len(followed) - 3)
            self.info.set_text(self.info_text + " · " + _("thread_via_home", names=names))
            tip(self.info, _("thread_via_home_tip"))
        self.win.call(self.win.view.followed_among([p.author for p in posts]), show,
                      lambda _e: None)
