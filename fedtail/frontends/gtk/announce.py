"""The server's announcements in the GTK window (ui.announcements = "banner"), as Qt's
strip: above the lanes, one at a time, with how people reacted and my reaction, until
"Got it" — the server remembers that, so other clients stop showing it too."""

from __future__ import annotations

import logging
from dataclasses import replace

from ...i18n import _
from ...model import Reaction
from .. import pango, richtext
from ..common.announce import react
from .gi_setup import Gtk, Pango, tip

log = logging.getLogger(__name__)

QUICK = ("👍", "❤️", "😂", "🎉")  # reactions offered under every announcement


class AnnounceBar(Gtk.Box):
    def __init__(self, win):
        super().__init__(spacing=10)
        self.win = win
        self.items = []
        self.add_css_class("ft-announce")
        for m in ("start", "end", "top", "bottom"):
            getattr(self, "set_margin_" + m)(6)
        col = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        self.head = Gtk.Label(xalign=0)
        self.head.add_css_class("ft-name")
        self.body = Gtk.Label(xalign=0, wrap=True)
        self.body.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
        self.body.connect("activate-link", lambda _l, u: (win.on_link(u), True)[1])
        self.reactions = Gtk.Box(spacing=4)
        col.append(self.head)
        col.append(self.body)
        col.append(self.reactions)
        self.append(col)
        self.ok = Gtk.Button(label=_("announce_ok"), valign=Gtk.Align.START)
        tip(self.ok, _("tip_announce_ok"))
        self.ok.connect("clicked", lambda _b: self.dismiss())
        self.append(self.ok)
        self.set_visible(False)

    def start(self):
        if self.win.cfg["ui"].get("announcements", "banner") == "off":
            return
        self.check()  # then the core asks again (announcements_updated → check)

    def check(self):
        self.win.call(self.win.view.announcements(), self.got, lambda _e: None)

    def got(self, items):
        self.items = list(items or ())
        log.info("announcements: %d not dismissed", len(self.items))
        self.render()

    def render(self):
        if not self.items:
            self.set_visible(False)
            return
        a = self.items[0]
        more = f" · {_('announce_more', n=len(self.items) - 1)}" if len(self.items) > 1 else ""
        stamp = self.win.theme.date(a.published) if a.published else ""
        self.head.set_text(f"📢 {_('announce_title')} {stamp}{more}")
        self.body.set_markup(pango.markup(richtext.clean(a.html), sanitized=True))
        self._reactions(a)
        self.set_visible(True)

    def _reactions(self, a):
        while (c := self.reactions.get_first_child()) is not None:
            self.reactions.remove(c)
        if not self.win.view.supports("announcement_reactions"):
            return
        have = {r.name: r for r in a.reactions}
        for name in list(have) + [e for e in QUICK if e not in have]:
            r = have.get(name) or Reaction(name)
            if len(name) > 4 and not r.count:
                continue  # a custom emoji nobody used: not offered
            b = Gtk.Button(label=f"{name} {r.count}" if r.count else name)
            b.add_css_class("flat" if not r.me else "ft-primary")
            tip(b, _("announce_react_tip"))
            b.connect("clicked", lambda _b, aid=a.id, n=name, on=not r.me:
                      self.react(aid, n, on))
            self.reactions.append(b)

    def react(self, aid, name, on):
        i = next((i for i, x in enumerate(self.items) if x.id == aid), None)
        if i is None:
            return
        a = self.items[i]
        self.items[i] = replace(a, reactions=react(a.reactions, name, on))
        self.render()
        self.win.call(self.win.core.react_announcement(aid, name, on))

    def dismiss(self):
        if not self.items:
            self.set_visible(False)
            return
        a = self.items.pop(0)
        self.win.call(self.win.core.dismiss_announcement(a.id))
        self.render()
