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
        note = QLabel(_("issue_check"))
        note.setWordWrap(True)
        lay.addWidget(note)
        d = issue.draft(win.core.paths, win.cfg, known=self.mine, toolkit="qt")
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
        self.win.open_url(self.url())
        self.win.statusBar().showMessage(_("issue_opened"), 8000)
        self.accept()


__all__ = ["IssueDialog"]
