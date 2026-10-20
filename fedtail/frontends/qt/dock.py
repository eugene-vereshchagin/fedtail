"""The input line at the bottom of the messages window (``ui.layout = "split"``), as in
QIP or the Mail.ru Agent: always there, under whatever tab is in front. In a thread's
tab it answers the thread (its newest post — a private talk stays private); in a lane's
tab it writes a new post. Small buttons around it: who sees it, a content warning, and
⤢ — the same words in the full Compose window (pictures, polls, language, drafts,
schedule)."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...i18n import _
from ...model import VISIBILITIES
from ...model.text import reply_mentions
from .card import VIS_KEY

log = logging.getLogger(__name__)

VIS_MARK = {"public": "🌐", "unlisted": "🔓", "private": "🔒", "direct": "✉"}


class InputDock(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("inputDock")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.target = None      # the Post answered, None: a new post
        self._prefill = ""      # the mentions put in for it (still untouched: replaced)
        v = QVBoxLayout(self)
        v.setContentsMargins(6, 4, 6, 6)
        v.setSpacing(4)
        bar = QHBoxLayout()
        bar.setSpacing(2)
        self.vis_btn = self._mini("", _("web_visibility"))
        self.vis_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.vis_btn)
        for vis in VISIBILITIES:
            menu.addAction(_('vis_' + VIS_KEY.get(vis, vis)),
                           lambda x=vis: self.set_visibility(x))
        self.vis_btn.setMenu(menu)
        bar.addWidget(self.vis_btn)
        self.cw_btn = self._mini("CW", _("dock_cw"))
        self.cw_btn.setCheckable(True)
        self.cw_btn.toggled.connect(self._cw_toggled)
        bar.addWidget(self.cw_btn)
        full = self._mini("⤢", _("dock_full"))
        full.clicked.connect(self.open_full)
        bar.addWidget(full)
        self.about = QLabel()
        self.about.setObjectName("muted")
        bar.addWidget(self.about, 1)
        self.count = QLabel()
        self.count.setObjectName("muted")
        bar.addWidget(self.count)
        v.addLayout(bar)
        self.cw = QLineEdit()
        self.cw.setPlaceholderText(_("dock_cw"))
        self.cw.hide()
        v.addWidget(self.cw)
        row = QHBoxLayout()
        self.text = QPlainTextEdit()
        self.text.setObjectName("dockText")
        self.text.setFixedHeight(64)
        self.text.textChanged.connect(self._count)
        self.text.installEventFilter(self)
        row.addWidget(self.text, 1)
        self.send_btn = QPushButton(_("dock_send"))
        self.send_btn.setObjectName("compose")
        self.send_btn.setToolTip(_("dock_send") + " (Ctrl+Enter)")
        self.send_btn.clicked.connect(self.send)
        row.addWidget(self.send_btn, 0, Qt.AlignmentFlag.AlignBottom)
        v.addLayout(row)
        self.visibility = win.ctx.view.reply_visibility(None)
        self._show_visibility()
        self._count()

    def _mini(self, text, tip):
        b = QToolButton()
        b.setObjectName("menu")
        b.setText(text)
        b.setToolTip(tip)
        b.setAutoRaise(True)
        return b

    # ---- what it answers -------------------------------------------------------------
    def follow(self, widget):
        """The tab in front changed: a thread is answered, anything else — a new post."""
        from .feed import ThreadWidget
        post = None
        if isinstance(widget, ThreadWidget):
            posts = getattr(widget, "posts", None) or []
            post = posts[-1] if posts else None
        self.set_target(post)

    def set_target(self, post):
        if post is not None and self.target is not None and post.id == self.target.id:
            return
        self.target = post
        view = self.win.ctx.view
        typed = self.text.toPlainText()
        if typed.strip() == self._prefill.strip():  # nothing of mine yet: start anew
            me = view.me if self.win.core.me else None
            self._prefill = reply_mentions(post, me.handle if me else "") if post else ""
            self.text.setPlainText(self._prefill)
            self.text.moveCursor(QTextCursor.MoveOperation.End)
        self.visibility = view.reply_visibility(post)
        self._show_visibility()
        self.about.setText(_("dock_reply", name=post.author.username) if post
                           else _("dock_new"))

    def set_visibility(self, vis):
        self.visibility = vis
        self._show_visibility()

    def _show_visibility(self):
        vis = self.visibility
        self.vis_btn.setText(VIS_MARK.get(vis, "?") + " ▾")
        self.vis_btn.setToolTip(f"{_('web_visibility')}: "
                                f"{_('vis_' + VIS_KEY.get(vis, vis))}")

    def _cw_toggled(self, on):
        self.cw.setVisible(on)
        if on:
            self.cw.setFocus()

    def _count(self):
        limit = getattr(self.win.ctx.view.caps, "max_characters", None) or 500
        n = len(self.text.toPlainText())
        self.count.setText(f"{n}/{limit}")
        self.send_btn.setEnabled(0 < n <= limit and
                                 self.text.toPlainText().strip() != self._prefill.strip())

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        if obj is self.text and e.type() == QEvent.Type.KeyPress and \
                e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and \
                e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.send()
            return True
        return super().eventFilter(obj, e)

    # ---- sending ---------------------------------------------------------------------
    def send(self):
        text = self.text.toPlainText()
        if not text.strip() or not self.send_btn.isEnabled():
            return
        target = self.target
        warning = self.cw.text().strip() if self.cw_btn.isChecked() else ""
        self.send_btn.setEnabled(False)
        log.info("dock: %s", "reply to " + target.id if target else "new post")

        def sent(st):
            self.text.clear()
            self._prefill = ""
            self.cw.clear()
            self.cw_btn.setChecked(False)
            self.target = None
            self.win.after_post(st, target)
            self.follow(self.win.tabs.currentWidget())

        def failed(err):
            self._count()
            self.win.error(err)

        self.win.bridge.call(self.win.ctx.view.post(text, self.visibility, target, warning),
                             ok=sent, fail=failed)

    def open_full(self):
        """The same words in the full Compose window; the line here is emptied."""
        text = self.text.toPlainText()
        if text.strip() == self._prefill.strip():
            text = ""
        target = self.target
        self.text.clear()
        self._prefill = ""
        self.target = None
        self.win.compose(target, (), text)
        self.follow(self.win.tabs.currentWidget())
