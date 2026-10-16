"""The command line at the bottom of the window, Point-style (core/commands.py
has the grammar). While you type it says what Enter will do — which post a
reply goes to, who will see a new post — so nothing is sent by surprise."""

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMessageBox, QWidget

from ...core.commands import parse
from ...core.model import real, reply_mentions, snippet
from ...i18n import _


class CommandBar(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.core = win, win.core
        self.setObjectName("findBar")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        self.edit = QLineEdit()
        self.edit.setObjectName("cmdline")
        self.edit.setPlaceholderText(_("cmd_placeholder"))
        self.edit.setToolTip(_("cmd_tip"))
        self.edit.textChanged.connect(self._preview)
        self.edit.returnPressed.connect(self.run)
        self.edit.installEventFilter(self)
        lay.addWidget(self.edit, 3)
        self.hint = QLabel()
        self.hint.setObjectName("counter")
        self.hint.setTextFormat(Qt.TextFormat.PlainText)
        self.hint.hide()  # the line takes the whole width until there's a hint
        lay.addWidget(self.hint, 2)
        self.history, self.pos = [], 0

    def focus(self):
        self.edit.setFocus()
        self.edit.selectAll()

    def _hint(self, text):
        self.hint.setText(text)
        self.hint.setVisible(bool(text))

    def put_alias(self, alias):
        """A click on a post's #abc: it goes to the start of the line (instead of the
        #number already there, if any), the cursor to the end, ready for the text."""
        self.show()
        text = self.edit.text()
        rest = re.sub(r"^\s*#[0-9a-z]+(/\d+)?\s*", "", text) if text.lstrip().startswith("#") \
            else text
        self.edit.setText(f"#{alias} " + rest.lstrip())
        self.edit.setFocus()
        self.edit.end(False)

    # ---- what Enter would do ------------------------------------------------------
    def _who_sees(self, vis):
        return _("vis_" + vis)

    def _preview(self, text):
        c = parse(text)
        if not text.strip():
            self._hint("")
            return
        if c.kind in ("open", "reply", "sub", "unsub", "boost", "bookmark", "delete"):
            st = self.core.by_alias(c.alias)
            if st is None:
                self._hint(_("cmd_no_post", alias=c.alias) +
                                  (" " + _("cmd_as_post") if c.kind == "reply" and
                                   self.core.cfg["post"]["plain_posts"] else ""))
                return
            who = real(st)["account"].get("acct", "")
            where = f"#{c.alias}" + (f"/{c.number}" if c.number else "")
            self._hint(_("cmd_do_" + c.kind, where=where, who=who,
                                text=snippet(st, 50),
                                vis=self._who_sees(self.core.reply_visibility(real(st)))))
        elif c.kind in ("follow", "unfollow", "profile", "direct"):
            self._hint(_("cmd_do_" + c.kind, who=c.user))
        elif c.kind == "post":
            self._hint(_("cmd_do_post", vis=self._who_sees(
                self.core.cfg["post"]["default_visibility"]))
                if self.core.cfg["post"]["plain_posts"] else _("cmd_unknown"))
        elif c.kind == "help":
            self._hint(_("cmd_do_help"))
        else:
            self._hint(_("cmd_unknown"))

    # ---- doing it -------------------------------------------------------------------
    def run(self):
        line = self.edit.text()
        c = parse(line)
        if c.kind == "error":
            self._hint(_("cmd_unknown"))
            return
        if line.strip() and (not self.history or self.history[-1] != line):
            self.history.append(line)
        self.pos = len(self.history)
        if c.kind == "help":
            QMessageBox.information(self, _("cmd_help_title"), _("cmd_help"))
            return
        if c.kind == "post":
            if not self.core.cfg["post"]["plain_posts"]:
                self._hint(_("cmd_unknown"))
                return
            self._send(c.text, self.core.cfg["post"]["default_visibility"])
            return
        if c.kind in ("follow", "unfollow", "profile", "direct"):
            self.win.bridge.call(self.core.find_user(c.user), ok=lambda acc: self._user(c, acc),
                                 fail=self.win.error)
            return
        if self.core.by_alias(c.alias) is None:
            if c.kind == "reply" and self.core.cfg["post"]["plain_posts"]:
                self._send(line.strip(), self.core.cfg["post"]["default_visibility"])
            else:
                self._hint(_("cmd_no_post", alias=c.alias))
            return
        self.win.bridge.call(self.core.target(c.alias, c.number),
                             ok=lambda st: self._post_cmd(c, st), fail=self.win.error)

    def _post_cmd(self, c, st):
        if st is None:
            self._hint(_("cmd_no_comment", where=f"#{c.alias}/{c.number}"))
            return
        s = real(st)
        done = lambda key: (self.edit.clear(), self.win.statusBar().showMessage(_(key), 4000))  # noqa: E731
        if c.kind == "open":
            self.win.open_thread(s["id"])
            self.edit.clear()
        elif c.kind == "reply":
            mentions = reply_mentions(s, self.core.me["acct"])
            self._send(mentions + c.text, self.core.reply_visibility(s), s["id"])
        elif c.kind in ("sub", "unsub"):
            call = self.core.subscribe if c.kind == "sub" else self.core.unsubscribe
            self.win.bridge.call(call(s), ok=lambda _r: done("subbed" if c.kind == "sub"
                                                             else "unsubbed"))
        elif c.kind == "boost":
            self.win.bridge.call(self.core.boost(s), ok=lambda _r: done("cmd_boosted"))
        elif c.kind == "bookmark":
            on = not s.get("bookmarked")
            self.win.bridge.call(self.core.bookmark(s, on),
                                 ok=lambda _r: done("bookmarked" if on else "unbookmarked"))
        elif c.kind == "delete":
            self.edit.clear()
            self.win.on_link(f"fedtail:delete/{s['id']}")

    def _user(self, c, acc):
        if acc is None:
            self._hint(_("cmd_no_user", who=c.user))
            return
        if c.kind == "profile":
            self.win.open_account(acc["id"])
            self.edit.clear()
        elif c.kind in ("follow", "unfollow"):
            on = c.kind == "follow"
            self.win.bridge.call(self.core.follow(acc["id"], on), ok=lambda _r: (
                self.edit.clear(), self.win.statusBar().showMessage(
                    _("cmd_followed" if on else "cmd_unfollowed", who=acc["acct"]), 4000)))
        elif c.kind == "direct":
            self._send(c.text, "direct")

    def _send(self, text, visibility, reply_to=None):
        self.edit.setEnabled(False)

        def ok(_st):
            self.edit.setEnabled(True)
            self.edit.clear()
            self.win.statusBar().showMessage(_("sent"), 4000)
            self.edit.setFocus()

        def fail(e):
            self.edit.setEnabled(True)
            self.win.error(_("send_failed_text", err=e))
        self.win.bridge.call(self.core.post(text, visibility, reply_to), ok=ok, fail=fail)

    # ---- ↑ ↓ through what you typed before ------------------------------------------
    def eventFilter(self, obj, e):
        if e.type() == e.Type.KeyPress and self.history:
            if e.key() == Qt.Key.Key_Up:
                self.pos = max(0, self.pos - 1)
                self.edit.setText(self.history[self.pos])
                return True
            if e.key() == Qt.Key.Key_Down:
                self.pos = min(len(self.history), self.pos + 1)
                self.edit.setText(self.history[self.pos] if self.pos < len(self.history)
                                  else "")
                return True
        return super().eventFilter(obj, e)
