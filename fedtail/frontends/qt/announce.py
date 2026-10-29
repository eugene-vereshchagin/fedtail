"""The server's announcements (ui.announcements = "banner"): a strip above the
lanes, one announcement at a time, until "Got it" — the server remembers that, so
the web interface and other clients stop showing it too."""

import logging
from dataclasses import replace

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ...i18n import _
from ...model import Reaction
from ..common.announce import react
from .text import clean

log = logging.getLogger(__name__)

QUICK = ("👍", "❤️", "😂", "🎉")  # reactions offered under every announcement
RECHECK_MS = 30 * 60 * 1000  # admins post rarely; twice an hour is plenty


class AnnounceBar(QFrame):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setObjectName("announceBar")
        self.items = []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.head = QLabel()
        self.head.setObjectName("announceHead")
        self.body = QLabel()
        self.body.setObjectName("announceText")
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        self.body.setOpenExternalLinks(False)
        self.body.linkActivated.connect(win.on_link)
        col.addWidget(self.head)
        col.addWidget(self.body)
        # reactions to the announcement (Mastodon): how people reacted, and mine
        self.reactions = QHBoxLayout()
        self.reactions.setSpacing(4)
        col.addLayout(self.reactions)
        lay.addLayout(col, 1)
        self.ok = QPushButton(_("announce_ok"))
        self.ok.setToolTip(_("tip_announce_ok"))
        self.ok.clicked.connect(self.dismiss)
        lay.addWidget(self.ok, 0, Qt.AlignmentFlag.AlignTop)
        self.hide()
        self.timer = QTimer(self)
        self.timer.setInterval(RECHECK_MS)
        self.timer.timeout.connect(self.check)

    def start(self):
        if self.win.cfg["ui"]["announcements"] == "off":
            return
        self.check()
        self.timer.start()

    def check(self):
        self.win.bridge.call(self.win.ctx.view.announcements(), ok=self.got,
                             fail=lambda _e: None)

    def got(self, items):
        self.items = list(items)
        log.info("announcements: %d not dismissed", len(self.items))
        self.render()

    def render(self):
        if not self.items:
            self.hide()
            return
        a = self.items[0]
        more = f" · {_('announce_more', n=len(self.items) - 1)}" if len(self.items) > 1 else ""
        stamp = self.win.theme.date(a.published) if a.published else ""  # as a card's
        self.head.setText(f"📢 {_('announce_title')} {stamp}{more}")
        self.body.setText(clean(a.html, self.win.theme.css("link")))
        self._reactions(a)
        self.show()

    def _reactions(self, a):
        while self.reactions.count():
            item = self.reactions.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self.win.core.supports("announcement_reactions"):
            return
        have = {r.name: r for r in a.reactions}
        for name in list(have) + [e for e in QUICK if e not in have]:
            r = have.get(name) or Reaction(name)
            if len(name) > 4 and not r.count:
                continue  # a custom emoji nobody used: not offered
            b = QPushButton(f"{name} {r.count}" if r.count else name)
            b.setObjectName("primary" if r.me else "tool")
            b.setFlat(True)
            b.setToolTip(_("announce_react_tip"))
            want = not r.me
            b.clicked.connect(lambda _c=False, aid=a.id, n=name, on=want:
                              self.react(aid, n, on))
            self.reactions.addWidget(b)
        self.reactions.addStretch(1)

    def react(self, aid, name, on):
        i = next((i for i, x in enumerate(self.items) if x.id == aid), None)
        if i is None:
            return
        a = self.items[i]
        self.items[i] = replace(a, reactions=react(a.reactions, name, on))
        self.render()
        self.win.bridge.call(self.win.core.react_announcement(aid, name, on),
                             fail=self.win.error)

    def dismiss(self):
        if not self.items:
            return self.hide()
        a = self.items.pop(0)
        self.win.bridge.call(self.win.core.dismiss_announcement(a.id),
                             fail=self.win.error)
        self.render()

