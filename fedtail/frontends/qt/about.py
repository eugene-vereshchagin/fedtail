"""About fedtail, as cards: the opossum and the name on top, a grid of tiles (version,
platform, build…), rows (Python, Qt, the accounts, the server…), who made it, the
links, and "Copy the information" for a bug report. What it says is
common/about.py's; the GTK window draws the same."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from ...i18n import _
from ..common import about as facts_of


def _card(name):
    f = QFrame()
    f.setObjectName(name)
    return f


class AboutDialog(QDialog):
    def __init__(self, win):
        super().__init__(win)
        from PySide6 import __version__ as pyside

        from .notify import mascot_path
        self.win = win
        self.setWindowTitle(_("about"))
        self.facts = facts_of.facts(win.ctx.view, "Qt", pyside)
        t = win.theme
        k = t.css
        self.setStyleSheet(f"""
QFrame#aboutHead, QFrame#aboutTile, QFrame#aboutRow {{
    background: {k('card')}; border: 1px solid {k('card_border')}; border-radius: 8px; }}
QFrame#aboutHead QLabel, QFrame#aboutTile QLabel, QFrame#aboutRow QLabel {{
    background: transparent; border: 0; }}
QLabel#aboutName {{ color: {k('accent')}; font-size: 24pt; }}
QLabel#aboutMuted {{ color: {k('muted')}; }}
QLabel#aboutSmall {{ color: {k('muted')}; font-size: 8.5pt; }}
""")
        a = self.facts
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 14)
        lay.setSpacing(10)

        head = _card("aboutHead")
        h = QHBoxLayout(head)
        h.setContentsMargins(16, 14, 16, 14)
        h.setSpacing(18)
        pic = QLabel()
        pic.setPixmap(QIcon(mascot_path()).pixmap(96, 96))
        h.addWidget(pic, 0, Qt.AlignmentFlag.AlignTop)
        words = QVBoxLayout()
        words.setSpacing(2)
        name = QLabel("fedtail")
        name.setObjectName("aboutName")
        words.addWidget(name)
        tag = QLabel(a.tagline)
        tag.setObjectName("aboutMuted")
        tag.setWordWrap(True)
        words.addWidget(tag)
        words.addWidget(QLabel(a.version))
        words.addStretch(1)
        h.addLayout(words, 1)
        lay.addWidget(head)

        grid = QGridLayout()
        grid.setSpacing(10)
        for i, (label, value) in enumerate(a.tiles):
            tile = _card("aboutTile")
            v = QVBoxLayout(tile)
            v.setContentsMargins(12, 8, 12, 10)
            v.setSpacing(4)
            small = QLabel(label)
            small.setObjectName("aboutSmall")
            v.addWidget(small)
            big = QLabel(value)
            big.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            v.addWidget(big)
            grid.addWidget(tile, i // 3, i % 3)
        lay.addLayout(grid)

        for label, value in a.rows:
            row = _card("aboutRow")
            r = QHBoxLayout(row)
            r.setContentsMargins(12, 7, 12, 7)
            left = QLabel(label)
            left.setObjectName("aboutMuted")
            left.setMinimumWidth(130)
            r.addWidget(left)
            right = QLabel(value)
            right.setWordWrap(True)
            right.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            r.addWidget(right, 1)
            lay.addWidget(row)

        if a.update[0]:  # what the website said last, "Check now", the release's page
            row = _card("aboutRow")
            r = QHBoxLayout(row)
            r.setContentsMargins(12, 7, 12, 7)
            left = QLabel(_("about_updates"))
            left.setObjectName("aboutMuted")
            left.setMinimumWidth(130)
            r.addWidget(left)
            self.update_words = QLabel(a.update[0])
            self.update_words.setWordWrap(True)
            r.addWidget(self.update_words, 1)
            self.release = QPushButton(_("open_browser"))
            self.release.setObjectName("primary")
            self.release.clicked.connect(self._release)
            r.addWidget(self.release)
            self.check = QPushButton(_("about_check"))
            self.check.setObjectName("tool")
            self.check.clicked.connect(self.check_now)
            r.addWidget(self.check)
            self._show_update(a.update)
            lay.addWidget(row)

        made = QLabel(a.made_by)
        made.setObjectName("aboutMuted")
        made.setWordWrap(True)
        lay.addWidget(made)
        from urllib.parse import quote
        links = []
        for words_, url in a.links:
            # the author opens here (fedtail:resolve), with Follow on the page; the code
            # in the browser
            href = url if "github" in url else "fedtail:resolve/" + quote(url, safe="")
            links.append(f'<a href="{href}">{words_}</a>')
        link_line = QLabel(" · ".join(links))
        link_line.setTextFormat(Qt.TextFormat.RichText)
        link_line.setOpenExternalLinks(False)
        link_line.linkActivated.connect(self._link)
        lay.addWidget(link_line)

        buttons = QHBoxLayout()
        self.copied = QLabel("")
        self.copied.setObjectName("aboutMuted")
        buttons.addWidget(self.copied, 1)
        copy = QPushButton(_("about_copy"))
        copy.setObjectName("primary")
        copy.clicked.connect(self.copy)
        buttons.addWidget(copy)
        close = QPushButton(_("close"))
        close.setObjectName("tool")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        lay.addLayout(buttons)
        self.setMinimumWidth(620)

    def copy(self):
        QGuiApplication.clipboard().setText(self.facts.text())
        self.copied.setText(_("about_copied"))

    def _show_update(self, update):
        self.facts.update = update
        self.update_words.setText(update[0])
        self.release.setVisible(bool(update[1]))

    def _release(self):
        from ...core.updates import release_page
        self._link(release_page(self.facts.update[1]))

    def check_now(self):
        """The website asked at once (a worker), the row redrawn with its answer."""
        view = self.win.ctx.view
        self.check.setEnabled(False)

        def done(_st):
            self.check.setEnabled(True)
            self._show_update(facts_of.update_line(view))
        self.win.bridge.call(self.win.core.submit(view.check_updates_now), ok=done,
                             fail=lambda _e: done(None))

    def _link(self, url):
        self.accept()
        if url.startswith("fedtail:"):
            self.win.on_link(url)
        else:
            self.win.open_url(url)
