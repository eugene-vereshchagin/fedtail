"""The command line at the bottom of the window, Point-style. What it says while you
type and what Enter does are common/commands.py's (the terminal and the web page share
them); this is the Qt widget around it."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QMessageBox, QWidget

from ...core.commands import parse
from ...i18n import _
from ..common import compose as rules
from ..common.commands import Commands, Failed, History, preview


class CommandBar(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win, self.core = win, win.ctx.view
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
        self.history = History()
        self.cmds = Commands(self.core)

    def focus(self):
        self.edit.setFocus()
        self.edit.selectAll()

    def _hint(self, text):
        self.hint.setText(text)
        self.hint.setVisible(bool(text))

    def put_alias(self, alias):
        """A click on a post's #abc: it goes to the start of the line (instead of the
        #number already there, if any), the cursor to the end, ready for the text."""
        dock = getattr(self.win, "dock", None)
        if dock is not None and not self.isVisible():
            dock.put_alias(alias)  # the split layout: the input line takes commands too
            return
        self.show()
        self.edit.setText(rules.put_alias(self.edit.text(), alias))
        self.edit.setFocus()
        self.edit.end(False)

    # ---- what Enter would do ------------------------------------------------------
    def _preview(self, text):
        self._hint(preview(self.core, text))

    # ---- doing it -------------------------------------------------------------------
    def run(self):
        line = self.edit.text()
        c = parse(line)
        if c.kind == "error":
            self._hint(_("cmd_unknown"))
            return
        self.history.add(line)
        if c.kind == "help":
            QMessageBox.information(self, _("cmd_help_title"), _("cmd_help"))
            return
        fut, msg = self.cmds.run(line, unknown_as_post=True)
        if fut is None:
            self._hint(msg or _("cmd_unknown"))
            return
        self.edit.setEnabled(False)

        def ok(result):
            self.edit.setEnabled(True)
            self.edit.setFocus()
            if isinstance(result, Failed):
                self._hint(result)  # the line stays, to mend
                return
            self.edit.clear()
            if isinstance(result, tuple):
                what, x = result
                if what == "thread":
                    self.win.open_thread(x)
                elif what == "profile":
                    self.win.open_account(x.id)
                elif what == "delete":
                    self.win.on_link(f"fedtail:delete/{x.id}")
            elif isinstance(result, str):
                self.win.statusBar().showMessage(result, 4000)
            else:  # the post made
                self.win.statusBar().showMessage(msg or _("sent"), 4000)

        def fail(e):
            self.edit.setEnabled(True)
            self.win.error(_("send_failed_text", err=e))
        self.win.bridge.call(fut, ok=ok, fail=fail)

    # ---- ↑ ↓ through what you typed before ------------------------------------------
    def eventFilter(self, obj, e):
        if e.type() == e.Type.KeyPress and e.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            line = self.history.up() if e.key() == Qt.Key.Key_Up else self.history.down()
            if line is not None:
                self.edit.setText(line)
                return True
        return super().eventFilter(obj, e)
