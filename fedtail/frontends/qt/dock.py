"""The input line at the bottom of the messages window (``ui.layout = "split"``), as in
QIP or the Mail.ru Agent: always there, under whatever tab is in front. In a thread's
tab it answers the thread (its newest post — a private talk stays private); in a lane's
tab it writes a new post. Small buttons around it: who sees it, a content warning, and
⤢ — the same words in the full Compose window (pictures, polls, language, drafts,
schedule)."""

import logging
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QTabBar,
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
        self._about = _("dock_new")  # what it says it will do, above the line
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
        if self._typed():
            return  # words of mine on their way: they keep whom they answer
        self.set_target(post)

    def _typed(self):
        return self.text.toPlainText().strip() != self._prefill.strip()

    def reply_to(self, post):
        """Reply (the card's button, R): this post answered here, not in a window."""
        self.target = None
        self.set_target(post, fresh=not self._typed())
        self.text.setFocus()

    def write_to(self, account):
        """A private message to someone (a person in the roster): "@them ", direct."""
        self.target = None
        self.set_target(None)
        self._prefill = "@" + account.handle + " "
        self.text.setPlainText(self._prefill)
        self.text.moveCursor(QTextCursor.MoveOperation.End)
        self.set_visibility("direct")
        self._about = _("dock_private", name=account.username or account.handle)
        self.about.setText(self._about)
        self.text.setFocus()

    def start_with(self, text):
        """A new post beginning with these words ("Mention" on a profile)."""
        self.target = None
        self.set_target(None, fresh=True)
        self.text.setPlainText(text)
        self.text.moveCursor(QTextCursor.MoveOperation.End)
        self.text.setFocus()

    def set_target(self, post, fresh=None):
        if post is not None and self.target is not None and post.id == self.target.id:
            return
        self.target = post
        view = self.win.ctx.view
        if fresh is None:
            fresh = not self._typed()
        if fresh:  # nothing of mine yet: start anew
            me = view.me if self.win.core.me else None
            self._prefill = reply_mentions(post, me.handle if me else "") if post else ""
            self.text.setPlainText(self._prefill)
            self.text.moveCursor(QTextCursor.MoveOperation.End)
            self.visibility = view.reply_visibility(post)
            self._show_visibility()
        self._about = _("dock_reply", name=post.author.username) if post \
            else _("dock_new")
        self.about.setText(self._about)

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

    def command(self):
        """The text, when it is a Point-style command (ui.dock_commands): "#a3f",
        "#a3f text", "! #a3f", "S #a3f", "?" — one line; "@user …" stays a post here
        (a reply begins with it)."""
        text = self.text.toPlainText().strip()
        if not self.win.cfg["ui"].get("dock_commands", True) or "\n" in text or \
                text == self._prefill.strip():
            return None
        if re.match(r"^(#[a-z][0-9a-z]{2,}|[!~?]|[SUD]\s+[#@])", text):
            return text
        return None

    def put_alias(self, alias):
        """A click on a post's #abc: "#abc " at the start, the cursor at the end."""
        text = self.text.toPlainText()
        if text.strip() == self._prefill.strip():
            text = ""
        rest = re.sub(r"^\s*#[0-9a-z]+(/\d+)?\s*", "", text)
        self.text.setPlainText(f"#{alias} " + rest.lstrip())
        self.text.moveCursor(QTextCursor.MoveOperation.End)
        self.text.setFocus()

    def _count(self):
        cmd = self.command()
        if cmd is not None:  # what Enter will do, as the command line says it
            bar = self.win.cmdline
            bar._preview(cmd)
            self.about.setText(bar.hint.text() or _("dock_command"))
            self.count.setText("")
            self.send_btn.setEnabled(True)
            return
        self.about.setText(self._about)
        limit = getattr(self.win.ctx.view.caps, "max_characters", None) or 500
        n = len(self.text.toPlainText())
        self.count.setText(f"{n}/{limit}")
        self.send_btn.setEnabled(0 < n <= limit and
                                 self.text.toPlainText().strip() != self._prefill.strip())

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        if obj is self.text and e.type() == QEvent.Type.KeyPress and \
                e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and \
                (e.modifiers() & Qt.KeyboardModifier.ControlModifier or
                 self.command() is not None):  # a command: plain Enter, as on Point
            self.send()
            return True
        return super().eventFilter(obj, e)

    # ---- sending ---------------------------------------------------------------------
    def send(self):
        cmd = self.command()
        if cmd is not None:  # run by the command line, as typed there
            bar = self.win.cmdline
            bar.edit.setText(cmd)
            bar.run()
            self.text.clear()
            self._prefill = ""
            self.follow(self.win.tabs.currentWidget())
            return
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
        self.win.compose_window(target, (), text)
        self.follow(self.win.tabs.currentWidget())


FACE = 88  # the faces beside the messages, as in the Mail.ru Agent


class FaceColumn(QWidget):
    """Beside the messages, as in the Mail.ru Agent: the other side's face on top (whose
    post the cursor is on, else the one answered, else the post on top of the screen),
    its name, @address and small buttons — the profile, a private message; mine at the
    bottom, beside the input line, with my name. A click on a face: the profile.
    Looked at twice a second: cheap, and no signal to miss."""

    def __init__(self, win):
        super().__init__()
        from .card import ClickLabel
        self.win = win
        self.who = None
        self.setObjectName("faceColumn")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(FACE + 20)
        v = QVBoxLayout(self)
        v.setContentsMargins(10, 8, 10, 8)
        v.setSpacing(3)
        self.them = ClickLabel()
        self.them.setFixedSize(FACE, FACE)
        self.them.setCursor(Qt.CursorShape.PointingHandCursor)
        self.them.clicked.connect(self._their_profile)
        v.addWidget(self.them, 0, Qt.AlignmentFlag.AlignHCenter)
        self.them_name = self._caption("faceName")
        v.addWidget(self.them_name)
        self.them_handle = self._caption("muted")
        v.addWidget(self.them_handle)
        row = QHBoxLayout()
        row.setSpacing(2)
        self.buttons = []
        for mark, tip, fn in (("👤", _("faces_profile"), self._their_profile),
                              ("✉", _("faces_private"), self._write)):
            b = QToolButton()
            b.setObjectName("menu")
            b.setText(mark)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(fn)
            row.addWidget(b)
            self.buttons.append(b)
        row.addStretch(1)
        v.addLayout(row)
        v.addStretch(1)
        self.me = ClickLabel()
        self.me.setFixedSize(FACE, FACE)
        self.me.setCursor(Qt.CursorShape.PointingHandCursor)
        self.me.clicked.connect(win.open_my_profile)
        v.addWidget(self.me, 0, Qt.AlignmentFlag.AlignHCenter)
        self.me_name = self._caption("faceName")
        v.addWidget(self.me_name)
        self._urls = {}
        self._timer = QTimer(self, interval=500)
        self._timer.timeout.connect(self.update_faces)
        self._timer.start()

    def _caption(self, name):
        lab = QLabel()
        lab.setObjectName(name)
        lab.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        lab.setTextFormat(Qt.TextFormat.PlainText)
        lab.setMaximumWidth(FACE + 4)
        return lab

    def _elided(self, lab, text):
        lab.setText(lab.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight,
                                                 FACE + 4))
        lab.setToolTip(text)

    def _set(self, lab, url, tip=""):
        lab.setToolTip(tip)
        if self._urls.get(id(lab)) == url:
            return
        self._urls[id(lab)] = url
        lab.clear()
        if url:
            from .card import _round
            self.win.images.get(url, lambda pm, w=lab, u=url: (
                self._urls.get(id(w)) == u and w.setPixmap(_round(pm, FACE))))

    def update_faces(self):
        if not self.isVisible():
            return
        try:
            me = self.win.ctx.view.me if self.win.core.me else None
        except Exception:  # noqa: BLE001 — the core going away
            return
        self._set(self.me, me.avatar_static if me else "", "@" + me.handle if me else "")
        self._elided(self.me_name, (me.name or me.username) if me else "")
        who = self.who = self._other(me)
        self._set(self.them, who.avatar_static if who else "",
                  "@" + who.handle if who else "")
        self._elided(self.them_name, (who.name or who.username) if who else "")
        self._elided(self.them_handle, "@" + who.handle if who else "")
        for b in self.buttons:
            b.setVisible(who is not None)

    def _their_profile(self):
        if self.who is not None:
            self.win.open_account(self.who.id)

    def _write(self):
        if self.who is not None:
            self.win.write_to(self.who)

    def _other(self, me):
        """The account on the other side, or None."""
        from ...model import real
        view = self.win.current_view()
        post = None
        if view is not None:
            key = view.cursor_key
            if key not in view.rows:
                anchor = view._reading_anchor()
                key = anchor[0] if anchor else None
            row = view.rows.get(key)
            spec = getattr(row, "spec", None)
            if spec is not None and spec.entry is not None:
                post = real(spec.entry)
        dock = self.win.dock
        if (post is None or (me and post.author.id == me.id)) and dock is not None \
                and dock.target is not None:
            post = dock.target  # my own post under the cursor: whom I answer
        if post is None or (me and post.author.id == me.id):
            return None
        return post.author


class MessageTabs(QTabBar):
    """The messages window's tabs (the split layout): every lane opened from the roster
    and every thread, profile or search a tab of its own, as contacts are in a
    messenger. The window's own QTabWidget keeps holding the widgets (a lane lives in
    its stack, the rest in tabs) — this bar only says which is in front; closing its
    last tab closes the window."""

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("messageTabs")
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setExpanding(False)
        self.setElideMode(Qt.TextElideMode.ElideRight)
        self.setUsesScrollButtons(True)
        self._busy = False
        self.currentChanged.connect(self._picked)
        self.tabCloseRequested.connect(self._close)
        self._timer = QTimer(self, interval=1000)
        self._timer.timeout.connect(self.sync)
        self._timer.start()

    def _find(self, data):
        for i in range(self.count()):
            d = self.tabData(i)
            if not d:
                continue
            if data[0] == "w":
                if d[0] == "w" and d[1] is data[1]:
                    return i
            elif d[0] == data[0] and d[1] == data[1]:
                return i
        return -1

    def lane_opened(self, name):
        """A lane in front (from the roster, Alt+N, a link): its tab, added if new."""
        self._busy = True
        try:
            i = self._find(("lane", name))
            if i < 0:
                i = self.addTab(self.win.lane_title(name))
                self.setTabData(i, ("lane", name))
            self.setCurrentIndex(i)
        finally:
            self._busy = False
        self.sync()

    def sync(self):
        """The bar made to agree with the window: tabs for widgets that came, none for
        those gone, titles as they are now, the one in front chosen."""
        tabs, stack = self.win.tabs, self.win.stack
        widgets = [tabs.widget(i) for i in range(tabs.count()) if tabs.widget(i) is not stack]
        self._busy = True
        try:
            for i in reversed(range(self.count())):
                d = self.tabData(i)
                if d and d[0] == "w" and d[1] not in widgets:
                    self.removeTab(i)
            for w in widgets:
                i = self._find(("w", w))
                if i < 0:
                    i = self.addTab(tabs.tabText(tabs.indexOf(w)))
                    self.setTabData(i, ("w", w))
            for i in range(self.count()):
                kind, what = self.tabData(i)
                if kind == "w":
                    j = tabs.indexOf(what)
                    text, icon = tabs.tabText(j), tabs.tabIcon(j)
                else:
                    text, icon = self.win.lane_title(what), None
                    try:
                        n = self.win.core.unread_count(what)
                    except Exception:  # noqa: BLE001 — a lane not drawn yet
                        n = 0
                    if n:
                        text = f"{text} ({n})"
                if self.tabText(i) != text:
                    self.setTabText(i, text)
                    self.setTabToolTip(i, text)
                if icon is not None:
                    self.setTabIcon(i, icon)
            front = tabs.currentWidget()
            if front is stack:
                i = self._find(("lane", getattr(self.win, "lane_now", None)))
            else:
                i = self._find(("w", front))
            if i >= 0 and i != self.currentIndex():
                self.setCurrentIndex(i)
        finally:
            self._busy = False

    def _picked(self, i):
        if self._busy or i < 0:
            return
        kind, what = self.tabData(i)
        if kind == "lane":
            self.win.select_lane(what)
        else:
            self.win.tabs.setCurrentWidget(what)

    def _close(self, i):
        kind, what = self.tabData(i)
        if kind == "lane":
            self.removeTab(i)  # the lane stays in the stack, only its tab goes
        else:
            self.win.close_tab(self.win.tabs.indexOf(what))
        self.after_close()

    def close_current(self):
        if self.currentIndex() >= 0:
            self._close(self.currentIndex())

    def after_close(self):
        self.sync()
        if self.count() == 0:
            self.win.hide()  # the last conversation closed: the messages window goes too
