"""The server's announcements (ui.announcements = "banner"): a strip above the
lanes, one announcement at a time, until "Got it" — the server remembers that, so
the web interface and other clients stop showing it too."""

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ...i18n import _
from .text import clean, when

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
        self.win.bridge.call(self.win.core.announcements(), ok=self.got, fail=lambda _e: None)

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
        stamp = when(a.get("published_at") or "", _("months").split())
        self.head.setText(f"📢 {_('announce_title')} {stamp}{more}")
        self.body.setText(clean(a.get("content", ""), self.win.theme.css("link")))
        self._reactions(a)
        self.show()

    def _reactions(self, a):
        while self.reactions.count():
            item = self.reactions.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        if not self.win.core.supports("announcement_reactions"):
            return
        have = {r.get("name"): r for r in a.get("reactions") or [] if r.get("name")}
        for name in list(have) + [e for e in QUICK if e not in have]:
            r = have.get(name) or {"name": name, "count": 0, "me": False}
            if len(name) > 4 and not r.get("count"):
                continue  # a custom emoji nobody used: not offered
            b = QPushButton(f"{name} {r['count']}" if r.get("count") else name)
            b.setObjectName("primary" if r.get("me") else "tool")
            b.setFlat(True)
            b.setToolTip(_("announce_react_tip"))
            want = not r.get("me")
            b.clicked.connect(lambda _c=False, aid=a["id"], n=name, on=want:
                              self.react(aid, n, on))
            self.reactions.addWidget(b)
        self.reactions.addStretch(1)

    def react(self, aid, name, on):
        a = next((x for x in self.items if x["id"] == aid), None)
        if a is None:
            return
        rs = [dict(r) for r in a.get("reactions") or []]
        r = next((x for x in rs if x.get("name") == name), None)
        if r is None:
            r = {"name": name, "count": 0, "me": False}
            rs.append(r)
        if bool(r.get("me")) != on:
            r["me"] = on
            r["count"] = max(0, int(r.get("count") or 0) + (1 if on else -1))
        a["reactions"] = [x for x in rs if x.get("count")]
        self.render()
        self.win.bridge.call(self.win.core.react_announcement(aid, name, on),
                             fail=self.win.error)

    def dismiss(self):
        if not self.items:
            return self.hide()
        a = self.items.pop(0)
        self.win.bridge.call(self.win.core.dismiss_announcement(a["id"]),
                             fail=self.win.error)
        self.render()
