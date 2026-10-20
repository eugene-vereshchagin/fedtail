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

FACE = 64  # a face beside the messages, as in QIP: as tall as the input line
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
        self.text.setMinimumHeight(FACE)
        self.text.textChanged.connect(self._count)
        self.text.installEventFilter(self)
        row.addWidget(self.text, 1)
        # whom I write to, as in QIP: their face beside the line (mine isn't needed)
        from .card import ClickLabel
        self.face = ClickLabel()
        self.face.setFixedSize(FACE, FACE)
        self.face.setCursor(Qt.CursorShape.PointingHandCursor)
        self.face.clicked.connect(lambda: self._to is not None and
                                  self.win.open_account(self._to.id))
        self.face.hide()
        self._to = self._face_url = None
        row.addWidget(self.face, 0, Qt.AlignmentFlag.AlignTop)
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
        self.show_whom(account)
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
        self.show_whom(post.author if post else None)
        self._about = _("dock_reply", name=post.author.username) if post \
            else _("dock_new")
        self.about.setText(self._about)

    def show_whom(self, account):
        """Their face beside the line: whom this goes to (None: nobody in particular)."""
        me = self.win.ctx.view.me if self.win.core.me else None
        if account is not None and me is not None and account.id == me.id:
            account = None
        self._to = account
        self.face.setVisible(account is not None and self.win.cfg["ui"].get("faces", True))
        self.face.setToolTip("@" + account.handle if account else "")
        set_face(self.win, self.face, account.avatar_static if account else "", self,
                 "_face_url")

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


def other_side(win, me):
    """The account on the other side, or None: whose post the cursor is on (else the
    post on top of the screen); my own post there — whom I answer."""
    from ...model import real
    view = win.current_view()
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
    dock = win.dock
    if (post is None or (me and post.author.id == me.id)) and dock is not None \
            and dock.target is not None:
        post = dock.target
    if post is None or (me and post.author.id == me.id):
        return None
    return post.author


class AuthorBar(QWidget):
    """Over a lane's posts (ui.faces): who wrote the post under the cursor — the face on
    the right, changing as the cursor goes; on the left the name, the @address, how we
    stand, and what to do: follow or unfollow, the lists, a private message, the
    profile. Looked at twice a second: cheap, and no signal to miss."""

    def __init__(self, win):
        super().__init__()
        from .card import ClickLabel
        self.win = win
        self.who = None
        self._asked = set()
        self._url = None
        self.setObjectName("authorBar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 4, 10, 4)
        h.setSpacing(10)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.name = QLabel()
        self.name.setObjectName("faceName")
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        col.addWidget(self.name)
        self.about = QLabel()
        self.about.setObjectName("muted")
        self.about.setTextFormat(Qt.TextFormat.PlainText)
        col.addWidget(self.about)
        row = QHBoxLayout()
        row.setSpacing(4)
        self.follow_btn = QPushButton()
        self.follow_btn.setObjectName("tool")
        self.follow_btn.clicked.connect(self._follow)
        row.addWidget(self.follow_btn)
        self.lists_btn = QPushButton(_("add_to_list") + " ▾")
        self.lists_btn.setObjectName("tool")
        menu = QMenu(self.lists_btn)
        menu.aboutToShow.connect(lambda: self.who is not None and
                                 self.win.fill_list_menu(menu, self.who))
        self.lists_btn.setMenu(menu)
        row.addWidget(self.lists_btn)
        for text, tip, fn in (("✉", _("faces_private"), self._write),
                              ("👤", _("faces_profile"), self._profile)):
            b = QPushButton(text)
            b.setObjectName("tool")
            b.setToolTip(tip)
            b.clicked.connect(fn)
            row.addWidget(b)
        row.addStretch(1)
        col.addLayout(row)
        h.addLayout(col, 1)
        self.face = ClickLabel()
        self.face.setFixedSize(FACE, FACE)
        self.face.setCursor(Qt.CursorShape.PointingHandCursor)
        self.face.clicked.connect(self._profile)
        h.addWidget(self.face)
        self.hide()
        self._timer = QTimer(self, interval=500)
        self._timer.timeout.connect(self.update_bar)
        self._timer.start()

    def update_bar(self):
        from .feed import ThreadWidget
        win = self.win
        if not win.isVisible():
            return
        try:
            me = win.ctx.view.me if win.core.me else None
        except Exception:  # noqa: BLE001 — the core going away
            return
        # a thread or a talk has whom I answer by the input line; this is for lanes
        who = None if isinstance(win.tabs.currentWidget(), ThreadWidget) \
            else other_side(win, me)
        self.setVisible(who is not None)
        if who is None:
            self.who = None
            return
        changed = self.who is None or self.who.id != who.id
        self.who = who
        if changed:
            self.name.setText(who.name or who.username)
            set_face(win, self.face, who.avatar_static, self, "_url")
        self._show_relation()

    def _show_relation(self):
        who, view = self.who, self.win.ctx.view
        rel = view.relation_known(who.id)
        if rel is None and who.id not in self._asked:
            self._asked.add(who.id)
            self.win.bridge.call(view.relationship(who.id), ok=lambda _r: None,
                                 fail=lambda e: log.debug("relation: %s", e))
        bits = ["@" + who.handle]
        if rel is not None:
            if rel.following and rel.followed_by:
                bits.append(_("faces_mutual"))
            elif rel.followed_by:
                bits.append(_("faces_follows_me"))
            elif rel.requested:
                bits.append(_("faces_requested"))
        self.about.setText(" · ".join(bits))
        on = bool(rel and (rel.following or rel.requested))
        self.follow_btn.setText(_("unfollow") if on else _("follow"))
        self.follow_btn.setEnabled(rel is not None)

    def _follow(self):
        who, view = self.who, self.win.ctx.view
        if who is None:
            return
        rel = view.relation_known(who.id)
        on = not (rel and (rel.following or rel.requested))
        self.follow_btn.setEnabled(False)
        self.win.bridge.call(view.follow(who.id, on), ok=lambda _r: self._show_relation(),
                             fail=self.win.error)

    def _write(self):
        if self.who is not None:
            self.win.write_to(self.who)

    def _profile(self):
        if self.who is not None:
            self.win.open_account(self.who.id)


def set_face(win, lab, url, owner, attr):
    """A face into a label, round, once the picture comes (and only if it's still the
    one wanted: owner.<attr> keeps the url asked last)."""
    if getattr(owner, attr, None) == url:
        return
    setattr(owner, attr, url)
    lab.clear()
    if url:
        from .card import _round
        win.images.get(url, lambda pm: getattr(owner, attr, None) == url and
                       lab.setPixmap(_round(pm, lab.width())))


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
