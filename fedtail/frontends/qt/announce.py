"""The server's announcements (ui.announcements = "banner"): a strip above the
lanes, one announcement at a time, until "Got it" — the server remembers that, so
the web interface and other clients stop showing it too."""

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from ...i18n import _
from .text import clean, when

log = logging.getLogger(__name__)

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
        self.show()

    def dismiss(self):
        if not self.items:
            return self.hide()
        a = self.items.pop(0)
        self.win.bridge.call(self.win.core.dismiss_announcement(a["id"]),
                             fail=self.win.error)
        self.render()
