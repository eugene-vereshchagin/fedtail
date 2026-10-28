"""The formatting buttons over a Qt editor (post.format_bar): a row of small buttons and
their shortcuts; what each one does to the text is frontends/common/markup.py's."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QKeySequence, QShortcut, QTextCursor
from PySide6.QtWidgets import QHBoxLayout, QToolButton, QWidget

from ...i18n import _
from ..common import markup


def apply(edit, name):
    """Format `name` on a QPlainTextEdit's selection — one step of undo."""
    text = edit.toPlainText()
    c = edit.textCursor()
    s = markup.from_utf16(text, c.selectionStart())
    e = markup.from_utf16(text, c.selectionEnd())
    got = markup.apply(name, text, s, e)
    c.beginEditBlock()
    c.select(QTextCursor.SelectionType.Document)
    c.insertText(got.text)
    c.endEditBlock()
    c.setPosition(markup.utf16(got.text, got.start))
    c.setPosition(markup.utf16(got.text, got.end), QTextCursor.MoveMode.KeepAnchor)
    edit.setTextCursor(c)
    edit.setFocus()


def bar(edit, cfg, markdown):
    """The row of buttons for `edit` (its shortcuts work while it has the focus) — or None
    when post.format_bar says there are none here."""
    if not markup.shown(cfg, markdown):
        return None
    w = QWidget()
    w.setObjectName("formatBar")
    row = QHBoxLayout(w)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(2)
    w.buttons = {}
    for f in markup.FORMATS:
        b = QToolButton()
        b.setObjectName("tool")
        b.setText(f.face)
        b.setAutoRaise(True)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # the selection stays in the text
        b.setToolTip(markup.tip(f, _(f.tip)))
        font = QFont(b.font())
        font.setBold(f.name == "bold")
        font.setItalic(f.name == "italic")
        font.setStrikeOut(f.name == "strike")
        b.setFont(font)
        b.clicked.connect(lambda _c=False, n=f.name: apply(edit, n))
        row.addWidget(b)
        w.buttons[f.name] = b
        if f.keys:
            sc = QShortcut(QKeySequence(f.keys), edit)
            sc.setContext(Qt.ShortcutContext.WidgetShortcut)
            sc.activated.connect(lambda n=f.name: apply(edit, n))
    row.addStretch(1)
    return w
