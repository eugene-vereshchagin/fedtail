"""The input line at the bottom of the messages window (``ui.layout = "split"``), as in
QIP or the Mail.ru Agent: always there, under whatever tab is in front. In a thread's
tab it answers the thread (its newest post — a private talk stays private); in a lane's
tab it writes a new post. Small buttons around it: who sees it, a content warning, and
⤢ — the same words in the full Compose window (pictures, polls, language, drafts,
schedule)."""

import logging
import re

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QFrame,
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

FACE = 64  # a face beside the messages, as in QIP: as tall as the input line
BAR_FACE = 36  # the author's, in the one-line bar over a lane
AGENT_FACE = 88  # the Agent's, in the column beside the posts


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
        self.attach_btn = self._mini(_("dock_attach_word"), _("dock_attach"))
        self.attach_btn.clicked.connect(self._attach)
        bar.addWidget(self.attach_btn)
        self.media = []         # [(path, description)] going with the next post
        self.lang_btn = self._mini("", _("dock_language"))
        self.lang_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.lang_btn.setMenu(QMenu(self.lang_btn))
        self.lang_btn.menu().aboutToShow.connect(self._fill_languages)
        self.language = None    # None: post.language
        bar.addWidget(self.lang_btn)
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
        HoverCard(win, self.face, lambda: self._to)
        # a column on the right: the face in its middle, Send at its foot
        side = QVBoxLayout()
        side.setSpacing(4)
        side.addStretch(1)
        side.addWidget(self.face, 0, Qt.AlignmentFlag.AlignHCenter)
        side.addStretch(1)
        self.send_btn = QPushButton(_("dock_send"))
        self.send_btn.setObjectName("compose")
        self.send_btn.setToolTip(_("dock_send") + " (Ctrl+Enter)")
        self.send_btn.clicked.connect(self.send)
        side.addWidget(self.send_btn, 0, Qt.AlignmentFlag.AlignHCenter)
        row.addLayout(side)
        v.addLayout(row)
        self.visibility = win.ctx.view.reply_visibility(None)
        self.dress()
        self._count()

    def dress(self):
        """Pictures on the buttons, or words (ui.button_icons); again after a theme."""
        from . import icons
        t = self.win.theme
        icons.dress(self.cw_btn, "warning", t, glyph="CW")
        n = f" {len(self.media)}" if self.media else ""
        icons.dress(self.attach_btn, "attach", t, words=n.strip(),
                    glyph=_("dock_attach_word") + n)
        self.lang_btn.setText((self.language or _("dock_lang_default")) + " ▾")
        icons.dress(self.send_btn, "send", t, words=_("dock_send"))
        self._show_visibility()

    def _attach(self):
        """Pictures or a video for the next post; again: what was chosen goes."""
        from PySide6.QtWidgets import QFileDialog
        if self.media:
            self.media = []
        else:
            paths, _f = QFileDialog.getOpenFileNames(self, _("dock_attach"))
            self.media = [(p, "") for p in paths[:4]]
        self.attach_btn.setToolTip("\n".join(p for p, _d in self.media) or _("dock_attach"))
        self.dress()

    def _fill_languages(self):
        m = self.lang_btn.menu()
        m.clear()
        m.addAction(_("dock_lang_default"), lambda: self._set_language(None))
        for code in self.win.cfg["post"].get("languages") or ("ru", "en"):
            m.addAction(code, lambda c=code: self._set_language(c))

    def _set_language(self, code):
        self.language = code
        self.dress()

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
        if isinstance(widget, TalkWidget):
            self.write_to(widget.who, focus=False)  # a talk: privately to them
            return
        self.set_target(post)

    def _typed(self):
        return self.text.toPlainText().strip() != self._prefill.strip()

    def reply_to(self, post):
        """Reply (the card's button, R): this post answered here, not in a window."""
        self.target = None
        self.set_target(post, fresh=not self._typed())
        self.text.setFocus()

    def write_to(self, account, focus=True):
        """A private message to someone (a person in the roster): "@them ", direct."""
        self.target = None
        self.set_target(None, fresh=True)
        self._prefill = "@" + account.handle + " "
        self.text.setPlainText(self._prefill)
        self.text.moveCursor(QTextCursor.MoveOperation.End)
        self.set_visibility("direct")
        self.show_whom(account)
        self._about = _("dock_private", name=account.username or account.handle)
        self.about.setText(self._about)
        if focus:
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
        """The face beside the line: whom this goes to (None: nobody in particular) —
        or, as the Agent had it (shape.faces = "agent"), mine whoever it goes to."""
        me = self.win.ctx.view.me if self.win.core.me else None
        mode = faces_mode(self.win)
        if mode == "agent":
            account = me
        elif mode == "none":
            account = None
        elif account is not None and me is not None and account.id == me.id:
            account = None
        self._to = account
        self.face.setVisible(account is not None)
        self.face.setToolTip("@" + account.handle if account else "")
        set_face(self.win, self.face, account.avatar_static if account else "", self,
                 "_face_url")

    def set_visibility(self, vis):
        self.visibility = vis
        self._show_visibility()

    def _show_visibility(self):
        from . import icons
        vis = self.visibility
        icons.dress(self.vis_btn, vis, self.win.theme, words="▾",
                    glyph=_("vis_short_" + VIS_KEY.get(vis, vis)) + " ▾")
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
            self.media = []
            self.dress()
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

        kw = {"language": self.language} if self.language else {}
        if self.media:
            kw["media"] = list(self.media)
        self.win.bridge.call(self.win.ctx.view.post(text, self.visibility, target, warning,
                                                    **kw), ok=sent, fail=failed)


def faces_mode(win):
    """How the split layout shows faces: the theme's shape.faces ("qip", "agent",
    "none"), "none" with ui.faces = false."""
    if not win.cfg["ui"].get("faces", True):
        return "none"
    return win.theme.shape.get("faces", "qip")


class AgentFace(QWidget):
    """The Mail.ru Agent's column beside the posts (shape.faces = "agent"): the other
    side's face, big, in a frame, the name under it, a click — the profile. In a thread
    whom I answer, in a talk whom I talk to, over a lane the author under the cursor."""

    def __init__(self, win):
        super().__init__()
        from .card import ClickLabel
        self.win, self.who = win, None
        self._url = None
        self.setObjectName("agentFace")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(AGENT_FACE + 16)
        v = QVBoxLayout(self)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(3)
        self.face = ClickLabel()
        self.face.setObjectName("faceFrame")
        self.face.setFixedSize(AGENT_FACE, AGENT_FACE)
        self.face.setCursor(Qt.CursorShape.PointingHandCursor)
        self.face.clicked.connect(self._profile)
        v.addWidget(self.face, 0, Qt.AlignmentFlag.AlignHCenter)
        self.name = QLabel()
        self.name.setObjectName("faceName")
        self.name.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        v.addWidget(self.name)
        self.link = QLabel()
        self.link.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.link.linkActivated.connect(lambda _u: self._profile())
        v.addWidget(self.link)
        v.addStretch(1)
        HoverCard(win, self.face, lambda: self.who)
        self._timer = QTimer(self, interval=500)
        self._timer.timeout.connect(self.update_face)
        self._timer.start()

    def update_face(self):
        win = self.win
        if not win.isVisible():
            return
        try:
            me = win.ctx.view.me if win.core.me else None
        except Exception:  # noqa: BLE001 — the core going away
            return
        if win.dock is not None and me is not None and win.dock._to is None:
            win.dock.show_whom(None)  # mine by the input line, once I'm known
        front = win.tabs.currentWidget()
        who = front.who if isinstance(front, TalkWidget) else other_side(win, me)
        if who is not None and self.who is not None and who.id == self.who.id:
            return
        self.who = who
        set_face(win, self.face, who.avatar_static if who else "", self, "_url")
        name = (who.name or who.username) if who else ""
        self.name.setText(self.name.fontMetrics().elidedText(
            name, Qt.TextElideMode.ElideRight, AGENT_FACE + 8))
        link = win.theme.css("link")
        self.link.setText(f'<a href="#" style="color:{link}">{_("faces_profile")}</a>'
                          if who else "")

    def _profile(self):
        if self.who is not None:
            self.win.open_account(self.who.id)


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
        if key not in view.rows:  # not scrolled yet: the first card on screen
            top = view.verticalScrollBar().value()
            key = next((k for k in view.order if k in view.rows and
                        view.rows[k].y() + view.rows[k].height() > top), None)
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
        # one line: name @address · how we stand ……… [Follow] [List ▾] [✉] [profile] face
        self.setFixedHeight(BAR_FACE + 8)  # one height whoever it shows: nothing jumps
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 3, 6, 3)
        h.setSpacing(6)
        self.name = QLabel()
        self.name.setObjectName("faceName")
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        h.addWidget(self.name)
        self.about = QLabel()
        self.about.setObjectName("muted")
        self.about.setTextFormat(Qt.TextFormat.PlainText)
        self.about.setMinimumWidth(40)
        from PySide6.QtWidgets import QSizePolicy
        self.about.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        h.addWidget(self.about, 1)
        self.follow_btn = QPushButton()
        self.follow_btn.setObjectName("tool")
        self.follow_btn.clicked.connect(self._follow)
        h.addWidget(self.follow_btn)
        self.lists_btn = QPushButton(_("add_to_list") + " ▾")
        self.lists_btn.setObjectName("tool")
        menu = QMenu(self.lists_btn)
        menu.aboutToShow.connect(lambda: self.who is not None and
                                 self.win.fill_list_menu(menu, self.who))
        self.lists_btn.setMenu(menu)
        h.addWidget(self.lists_btn)
        self.glyph_btns = []
        # without pictures: ✉ (in every font) and a word for the profile (👤 is not)
        for glyph, pic, tip, fn in (("✉", "direct", _("faces_private"), self._write),
                                    (_("faces_profile"), "profile", _("faces_profile"),
                                     self._profile)):
            b = QPushButton(glyph)
            b.setObjectName("tool")
            b.setToolTip(tip)
            b.clicked.connect(fn)
            h.addWidget(b)
            self.glyph_btns.append((b, pic, glyph))
        self.face = ClickLabel()
        self.face.setFixedSize(BAR_FACE, BAR_FACE)
        self.face.setCursor(Qt.CursorShape.PointingHandCursor)
        self.face.clicked.connect(self._profile)
        h.addWidget(self.face)
        for w in (self.face, self.name):
            HoverCard(win, w, lambda: self.who)
        self.hide()
        self.dress()
        self._timer = QTimer(self, interval=500)
        self._timer.timeout.connect(self.update_bar)
        self._timer.start()

    def dress(self):
        from . import icons
        t = self.win.theme
        self._shown = None  # the follow button dressed anew with the rest
        icons.dress(self.lists_btn, "list", t, words=_("add_to_list") + " ▾")
        for b, pic, glyph in self.glyph_btns:
            icons.dress(b, pic, t, glyph=glyph)

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
        lane = not isinstance(win.tabs.currentWidget(), (ThreadWidget, TalkWidget))
        # over a lane it stays, even empty, so the posts under it never jump
        self.setVisible(lane)
        who = other_side(win, me) if lane else None
        for b in [self.follow_btn, self.lists_btn] + [b for b, _p, _g in self.glyph_btns]:
            b.setEnabled(who is not None)
        if who is None:
            if self.who is not None:
                self.who = None
                self.name.setText("")
                self.about.setText("")
                set_face(win, self.face, "", self, "_url")
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
        text = " · ".join(bits)
        on = bool(rel and (rel.following or rel.requested))
        # asked twice a second: change nothing that's the same — a button's picture or
        # words set anew lays the whole window out again (300 ms with a full lane)
        now = (text, self.about.width(), on, rel is not None)
        if now == getattr(self, "_shown", None):
            return
        self._shown = now
        self.about.setText(self.about.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, max(40, self.about.width())))
        self.about.setToolTip(text)
        from . import icons
        icons.dress(self.follow_btn, "unfollow" if on else "follow", self.win.theme,
                    words=_("unfollow") if on else _("follow"))
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


class _TabChip(QFrame):
    """One tab of MessageTabs: its picture, its title, its ×."""

    def __init__(self, bar, text):
        super().__init__()
        self.bar, self.data = bar, None
        self.setObjectName("msgTab")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        h = QHBoxLayout(self)
        h.setContentsMargins(8, 3, 3, 3)
        h.setSpacing(5)
        self.icon = QLabel()
        self.icon.hide()
        h.addWidget(self.icon)
        self.label = QLabel(text)
        self.label.setObjectName("msgTabText")
        self.label.setTextFormat(Qt.TextFormat.PlainText)
        self.label.setMaximumWidth(220)
        h.addWidget(self.label)
        self.close_btn = QToolButton()
        self.close_btn.setObjectName("msgTabClose")
        self.close_btn.setText("×")
        self.close_btn.setToolTip(_("close_tab"))
        self.close_btn.clicked.connect(lambda: bar._close_chip(self))
        h.addWidget(self.close_btn)

    def set_text(self, text):
        if text == getattr(self, "full", None):
            return
        self.full = text
        self.label.setText(self.label.fontMetrics().elidedText(
            text, Qt.TextElideMode.ElideRight, 220))

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.bar.setCurrentIndex(self.bar.chips.index(self))
        elif e.button() == Qt.MouseButton.MiddleButton:
            self.bar._close_chip(self)
        e.accept()


class MessageTabs(QWidget):
    """The messages window's tabs (the split layout): every lane opened from the roster
    and every thread, profile, talk or search a tab of its own, as contacts are in a
    messenger — in more rows when they don't fit (shape.tab_rows = "wrap", the Agent).
    The window's own QTabWidget keeps holding the widgets (a lane lives in its stack,
    the rest in tabs) — this bar only says which is in front; closing its last tab
    closes the window. It speaks QTabBar's few words the window uses."""

    currentChanged = Signal(int)
    tabCloseRequested = Signal(int)

    def __init__(self, win):
        super().__init__()
        from .flow import FlowLayout
        self.win = win
        self.setObjectName("messageTabs")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        if win.theme.shape.get("tab_rows", "wrap") == "wrap":
            self.lay = FlowLayout(self, spacing=2, justify=True)
            self.lay.setContentsMargins(4, 3, 4, 0)
        else:
            self.lay = QHBoxLayout(self)
            self.lay.setContentsMargins(4, 3, 4, 0)
            self.lay.setSpacing(2)
            self.lay.addStretch(1)
        self.chips = []
        self._current = -1
        self._busy = False
        self.currentChanged.connect(self._picked)
        self.tabCloseRequested.connect(self._close)
        self._timer = QTimer(self, interval=1000)
        self._timer.timeout.connect(self.sync)
        self._timer.start()

    # ---- QTabBar's words -------------------------------------------------------------
    def count(self):
        return len(self.chips)

    def addTab(self, text):  # noqa: N802 — QTabBar's name
        chip = _TabChip(self, text)
        chip.set_text(text)
        self.chips.append(chip)
        if isinstance(self.lay, QHBoxLayout):
            self.lay.insertWidget(self.lay.count() - 1, chip)
        else:
            self.lay.addWidget(chip)
        if self._current < 0:
            self.setCurrentIndex(len(self.chips) - 1)
        return len(self.chips) - 1

    def removeTab(self, i):  # noqa: N802
        if not 0 <= i < len(self.chips):
            return
        chip = self.chips.pop(i)
        self.lay.removeWidget(chip)
        chip.deleteLater()
        if not self.chips:
            self._current = -1
            self.currentChanged.emit(-1)
        elif i < self._current:
            self._current -= 1  # the same one in front, one place to the left
        elif i == self._current:
            self._current = -1  # a neighbour comes in front, as in QTabBar
            self.setCurrentIndex(min(i, len(self.chips) - 1))

    def tabData(self, i):  # noqa: N802
        return self.chips[i].data if 0 <= i < len(self.chips) else None

    def setTabData(self, i, data):  # noqa: N802
        self.chips[i].data = data

    def tabText(self, i):  # noqa: N802
        return getattr(self.chips[i], "full", self.chips[i].label.text())

    def setTabText(self, i, text):  # noqa: N802
        self.chips[i].set_text(text)

    def setTabToolTip(self, i, text):  # noqa: N802
        self.chips[i].setToolTip(text)

    def setTabIcon(self, i, icon):  # noqa: N802
        chip = self.chips[i]
        key = None if icon is None or icon.isNull() else icon.cacheKey()
        if key == getattr(chip, "icon_key", None):
            return  # the same: a picture set anew lays the window out again
        chip.icon_key = key
        if key is None:
            chip.icon.hide()
        else:
            chip.icon.setPixmap(icon.pixmap(16, 16))
            chip.icon.show()

    def currentIndex(self):  # noqa: N802
        return self._current

    def setCurrentIndex(self, i):  # noqa: N802
        if i == self._current or not 0 <= i < len(self.chips):
            return
        self._current = i
        for n, chip in enumerate(self.chips):
            chip.setProperty("current", "true" if n == i else "false")
            chip.style().unpolish(chip)
            chip.style().polish(chip)
        self.currentChanged.emit(i)

    def _close_chip(self, chip):
        if chip in self.chips:
            self.tabCloseRequested.emit(self.chips.index(chip))

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


def talk_with(view, entries, handle):
    """The entries of a private lane that are between me and this one person only:
    written by them to me alone, or by me to them alone."""
    from ...model import real
    from ...model.text import norm_handle
    me = norm_handle(view.me.handle) if view.me else ""
    them = norm_handle(handle)
    out = []
    for item, e in entries:
        p = real(e)
        people = {norm_handle(p.author.handle)} | {norm_handle(m.handle) for m in p.mentions}
        people.discard(me)
        if people == {them}:
            out.append((item, e))
    return out


class TalkWidget(QWidget):
    """A private talk with one person, as a messenger has it: their private messages
    with me, and mine with them, nobody else's (the Direct lane holds everyone's).
    Its tab is theirs; the input line writes to them, privately."""

    def __init__(self, win, account):
        super().__init__()
        from .feed import FeedView
        self.win, self.who = win, account
        self.title = account.name or account.username or account.handle
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.view = FeedView(win.ctx)
        self.view.seen.connect(self._seen)
        v.addWidget(self.view, 1)
        self.empty = QLabel(_("talk_empty", name=self.title))
        self.empty.setObjectName("muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.addWidget(self.empty)
        self._key = None
        self._timer = QTimer(self, interval=2000)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self.refresh()

    def refresh(self):
        from .card import make_spec
        view = self.win.ctx.view
        if "direct" not in self.win.core.lane_by_name:
            return
        mine = talk_with(view, view.entries("direct"), self.who.handle)
        unread = view.unread([e for _i, e in mine])
        key = (tuple(e.id for _i, e in mine), tuple(sorted(unread)))
        if key == self._key:
            return
        self._key = key
        specs = [make_spec(view, e.id, e, unread=e.id in unread) for _i, e in mine]
        self.view.set_specs(specs, keep_position=True)
        self.empty.setVisible(not specs)
        if specs and self._key is not None and not getattr(self, "_placed", False):
            self._placed = True
            QTimer.singleShot(0, lambda: self.view.scroll_to_end(True))

    def _seen(self, ids):
        if self.win.cfg["read"]["mark_read"] != "manual":
            self.win.ctx.view.mark_read(ids)

    def apply_read(self, ids):
        self.view.set_unread(ids, False)


class ContactCard(QWidget):
    """Who this is, as QIP showed a contact on hover: a card of its own beside the
    pointer — the face, the name, the @address, how we stand, the bio's first lines, how
    much they post and since when, a link to the whole profile. One for the window."""

    def __init__(self, win):
        super().__init__(None, Qt.WindowType.ToolTip)
        from .card import ClickLabel
        self.win, self.who = win, None
        self.setObjectName("contactCard")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedWidth(340)
        h = QHBoxLayout(self)
        h.setContentsMargins(10, 8, 10, 8)
        v = QVBoxLayout()
        v.setSpacing(2)
        self.name = QLabel()
        self.name.setObjectName("faceName")
        self.name.setTextFormat(Qt.TextFormat.PlainText)
        v.addWidget(self.name)
        self.lines = QLabel()
        self.lines.setWordWrap(True)
        self.lines.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self.lines)
        v.addStretch(1)
        h.addLayout(v, 1)
        self.face = ClickLabel()
        self.face.setFixedSize(FACE + 16, FACE + 16)
        h.addWidget(self.face, 0, Qt.AlignmentFlag.AlignTop)
        self._url = None
        self._timer = QTimer(self, singleShot=True, interval=600)
        self._timer.timeout.connect(self._show_now)
        self._at = None

    def soon(self, account, pos):
        """Shown a moment after the pointer stays (pos: global, where to put it)."""
        self.who, self._at = account, pos
        self._timer.start()

    def away(self):
        self._timer.stop()
        self.hide()

    def _show_now(self):
        from PySide6.QtGui import QTextDocumentFragment

        from .text import esc
        who, win = self.who, self.win
        if who is None:
            return
        self.name.setText(who.name or who.username)
        rel = win.ctx.view.relation_known(who.id)
        stand = ""
        if rel is not None:
            stand = _("faces_mutual") if rel.following and rel.followed_by else \
                _("faces_follows_me") if rel.followed_by else \
                _("following_them") if rel.following else ""
        bio = QTextDocumentFragment.fromHtml(who.note or "").toPlainText().strip()
        bio = bio[:220] + ("…" if len(bio) > 220 else "")
        muted = win.theme.css("muted")
        rows = [f"<span style='color:{muted}'>@{esc(who.handle)}</span>"]
        if stand:
            rows.append(f"<b>{esc(stand)}</b>")
        if bio:
            rows.append(esc(bio).replace("\n", "<br>"))
        if who.posts or who.followers:
            rows.append(esc(_("card_counts", posts=who.posts, followers=who.followers,
                              following=who.following)))
        if who.created:
            rows.append(esc(_("card_since", when=win.theme.date(who.created.isoformat()))))
        if who.bot:
            rows.append(esc(_("bot")))
        self.lines.setText("<br>".join(rows))
        set_face(win, self.face, who.avatar_static, self, "_url")
        self.adjustSize()
        x, y = self._at.x() + 16, self._at.y() + 8
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen is not None:
            if x + self.width() > screen.right():
                x = self._at.x() - self.width() - 16
            y = min(y, screen.bottom() - self.height())
        self.move(x, y)
        self.show()


def card_for(win):
    if getattr(win, "contact_card", None) is None:
        win.contact_card = ContactCard(win)
    return win.contact_card


class HoverCard:
    """An event filter: hovering a widget shows the contact card of who(), leaving it
    hides it."""

    def __init__(self, win, widget, who):
        from PySide6.QtCore import QObject

        class _F(QObject):
            def eventFilter(_s, obj, e):
                from PySide6.QtCore import QEvent
                t = e.type()
                if t == QEvent.Type.Enter:
                    acc = who()
                    if acc is not None:
                        from PySide6.QtGui import QCursor
                        card_for(win).soon(acc, QCursor.pos())
                elif t in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress, QEvent.Type.Hide):
                    card_for(win).away()
                return False
        self.f = _F(widget)
        widget.installEventFilter(self.f)
