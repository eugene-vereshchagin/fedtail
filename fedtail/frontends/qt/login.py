"""First login: register the app, open the browser, paste the code."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QPushButton, QVBoxLayout

from ...i18n import _


class LoginDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        self.win, self.core = win, win.core
        self.setWindowTitle(_("login_title", profile=self.core.paths.profile))
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(_("login_server")))
        self.server = QLineEdit()
        self.server.setPlaceholderText("example.social")
        lay.addWidget(self.server)
        self.b1 = QPushButton(_("login_step1"))
        self.b1.clicked.connect(self.step1)
        lay.addWidget(self.b1)
        hint = QLabel(_("login_hint"))
        hint.setWordWrap(True)
        lay.addWidget(hint)
        self.code = QLineEdit()
        self.code.setEnabled(False)
        lay.addWidget(self.code)
        self.b2 = QPushButton(_("login_step2"))
        self.b2.setEnabled(False)
        self.b2.clicked.connect(self.step2)
        lay.addWidget(self.b2)
        self.msg = QLabel()
        self.msg.setWordWrap(True)
        self.msg.setObjectName("muted")
        lay.addWidget(self.msg)
        self.url = None
        self.resize(480, 260)

    def step1(self):
        if not self.server.text().strip():
            return
        self.b1.setEnabled(False)
        self.msg.setText(_("loading"))
        self.win.bridge.call(self.core.begin_login(self.server.text()), ok=self._opened,
                             fail=self._fail)

    def _opened(self, url):
        self.url = url
        from .opener import open_link
        open_link(url)
        self.code.setEnabled(True)
        self.b2.setEnabled(True)
        self.b1.setEnabled(True)
        self.code.setFocus()
        self.msg.setText(_("login_browser_opened", url=url))
        self.msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def step2(self):
        if not self.code.text().strip():
            return
        self.b2.setEnabled(False)
        self.win.bridge.call(self.core.finish_login(self.code.text()),
                             ok=lambda _me: self.accept(), fail=self._fail)

    def _fail(self, err):
        self.msg.setText(_("error", err=err))
        self.b1.setEnabled(True)
        self.b2.setEnabled(self.url is not None)
