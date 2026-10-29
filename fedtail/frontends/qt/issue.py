""""Report a bug on GitHub…": the public issue's text (fedtail/issue.py — already
scrubbed of addresses, nicknames and paths) to read and edit, and "Open GitHub", which
opens the tracker's new-issue page with it. Nothing leaves from here: the person sends
it there, on GitHub, with their own click."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ...i18n import _


class IssueDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        from ... import issue
        from ..common.places import Places
        self.win = win
        self.mine = Places(win.ctx.view)._mine()
        self.setWindowTitle(_("issue_title"))
        lay = QVBoxLayout(self)
        note = self.note = QLabel(_("issue_check"))
        note.setWordWrap(True)
        lay.addWidget(note)
        d = issue.draft(win.core.paths, win.cfg, known=self.mine)
        self.text = QPlainTextEdit(d.body)
        lay.addWidget(self.text, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        go = QPushButton(_("issue_open"))
        go.setObjectName("primary")
        go.clicked.connect(self.go)
        row.addWidget(go)
        cancel = QPushButton(_("cancel"))
        cancel.setObjectName("tool")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        lay.addLayout(row)
        self.resize(720, 560)

    def url(self):
        from ... import issue
        return issue.issue_url(self.win.cfg, "",
                               issue.scrub(self.text.toPlainText(), self.mine))

    def go(self):
        """The whole text on the clipboard (the address holds only its start), the page
        in the browser; if no browser came, the address copied instead and the window
        stays, with the text in it."""
        from PySide6.QtWidgets import QApplication

        from ... import issue
        from .opener import open_link
        body = issue.scrub(self.text.toPlainText(), self.mine)
        url = self.url()
        QApplication.clipboard().setText(body)
        if not open_link(url):
            QApplication.clipboard().setText(url)
            self.note.setText(_("issue_not_opened"))
            return
        self.win.statusBar().showMessage(_("issue_opened"), 12000)
        self.accept()


__all__ = ["IssueDialog"]
