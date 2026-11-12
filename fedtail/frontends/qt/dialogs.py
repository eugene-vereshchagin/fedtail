"""Small windows of the window's own: one of a few choices (common/timed.py), a text
file attached to a post, read here."""

from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)


class Choose(QDialog):
    """One of options ([(key, label)]) by radio buttons, and a tick box when check (its
    label) is given; then(key, ticked) on OK — never on Cancel or close."""

    def __init__(self, parent, title, text, options, then, check=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.options, self.then = list(options), then
        lay = QVBoxLayout(self)
        lab = QLabel(text)
        lab.setWordWrap(True)
        lay.addWidget(lab)
        self.group = QButtonGroup(self)
        self.radios = []
        for i, (_key, label) in enumerate(self.options):
            r = QRadioButton(label)
            r.setChecked(i == 0)
            self.group.addButton(r, i)
            self.radios.append(r)
            lay.addWidget(r)
        self.tick = None
        if check:
            self.tick = QCheckBox(check)
            lay.addWidget(self.tick)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok
                               | QDialogButtonBox.StandardButton.Cancel)
        box.accepted.connect(self.accept)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
        self.accepted.connect(self._chosen)

    def picked(self):
        i = max(0, self.group.checkedId())
        return self.options[i][0]

    def _chosen(self):
        self.then(self.picked(), bool(self.tick is not None and self.tick.isChecked()))


def choose(parent, title, text, options, then, check=None):
    """Ask (window-modal, never blocking the loop); the dialog, for tests to answer."""
    dlg = Choose(parent, title, text, options, then, check)
    dlg.setModal(True)
    dlg.show()
    return dlg


class TextFile(QDialog):
    """A text file attached to a post (common/links.file_link): its words, read-only,
    loading until they come; "Open in browser" for the file itself."""

    def __init__(self, parent, name, url, open_url):
        super().__init__(parent)
        from ...i18n import _
        self.setWindowTitle(name)
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        self.text = QPlainTextEdit(_("image_loading"))
        self.text.setReadOnly(True)
        self.text.setObjectName("textFile")
        lay.addWidget(self.text)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        browser = QPushButton(_("open_browser"))
        box.addButton(browser, QDialogButtonBox.ButtonRole.ActionRole)
        browser.clicked.connect(lambda: open_url(url))
        box.rejected.connect(self.close)
        lay.addWidget(box)

    def fill(self, words):
        self.text.setPlainText(words)

    def failed(self, why):
        from ...i18n import _
        self.text.setPlainText(_("text_file_failed", why=why))
