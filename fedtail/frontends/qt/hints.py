"""The "What's this?" mode: point the mouse at a button and get the longer story.

While the mode is on, an application-wide event filter takes every tooltip request. The
widget under the mouse (or the menu action under it) says what it is by its usual
tooltip; `helpdocs.hint_for` finds the interface string behind that text and its hint in
``hints.toml``. Found — our own hint popup: the button's own words, the hint, the config
key and the help page; not found — the usual tooltip, untouched. So no widget needs to be
marked by hand; one may still name its hint with ``setProperty("fedtail_hint", key)``.

The popup is ours, not ``QToolTip``: a long rich-text tooltip that Qt word-wraps can land
right under the cursor, Qt hides it as the mouse "enters" it, the button asks for its
tooltip again — round and round until the window freezes or Qt aborts (it did, in
0.17.0.dev5). `HintPopup` has a fixed width, is placed beside the cursor and never over
it, lets the mouse through, and is shown once per widget until the mouse leaves it.

On for the session from ≡ → What's this?, or from the start with ``ui.whats_this``.
There is no shortcut on purpose (Shift+F1 sits next to Esc too).
"""

import logging

from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PySide6.QtGui import QCursor, QGuiApplication
from PySide6.QtWidgets import QApplication, QFrame, QLabel, QMenu, QVBoxLayout, QWidget

from ...i18n import _
from .. import helpdocs
from .gone import drop

log = logging.getLogger(__name__)

WIDTH = 420  # px: the hint's width, fixed — Qt never has to guess a wrap
GAP = 18  # px between the cursor and the hint

_HIDE_ON = (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonDblClick,
            QEvent.Type.KeyPress, QEvent.Type.Wheel, QEvent.Type.WindowDeactivate)


def place(cursor, size, area):
    """Where a hint of `size` goes for the mouse at `cursor` within the screen's `area`:
    right of and below the cursor; flipped left / up where it doesn't fit; never over the
    cursor itself (the loop that froze the window started there)."""
    w, h = size.width(), size.height()
    x = cursor.x() + GAP
    if x + w > area.right():
        x = cursor.x() - GAP - w
    x = max(area.left(), min(x, area.right() - w))
    y = cursor.y() + GAP
    if y + h > area.bottom():
        y = cursor.y() - GAP - h
    y = max(area.top(), min(y, area.bottom() - h))
    rect = QRect(x, y, w, h)
    if rect.contains(cursor):  # a screen too small for both: beside it, whatever it covers
        rect.moveLeft(cursor.x() + GAP if cursor.x() + GAP + w <= area.right()
                      else max(area.left(), cursor.x() - GAP - w))
    return rect


class HintPopup(QFrame):
    """The hint itself: a frameless tooltip-like window the mouse goes through."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("hintPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        self.label = QLabel()
        self.label.setObjectName("hintText")
        self.label.setTextFormat(Qt.TextFormat.RichText)
        self.label.setWordWrap(True)
        self.label.setFixedWidth(WIDTH - 20)
        lay.addWidget(self.label)
        self.target = None

    def show_for(self, widget, html, cursor):
        self.target = widget
        self.label.setText(html)
        self.label.setFixedHeight(self.label.heightForWidth(WIDTH - 20))
        self.adjustSize()
        screen = QGuiApplication.screenAt(cursor) or QGuiApplication.primaryScreen()
        self.setGeometry(place(cursor, self.size(), screen.availableGeometry()))
        self.show()
        self.raise_()

    def hide_hint(self):
        self.target = None
        self.hide()


class HintMode(QObject):
    def __init__(self, win, on=False):
        super().__init__(win)
        self.win = win
        self.on = False
        self.badge = None
        self.popup = None
        if on:
            self.set_on(True, quiet=True)

    def set_on(self, on, quiet=False):
        on = bool(on)
        if on == self.on:
            return
        self.on = on
        app = QApplication.instance()
        if on:
            app.installEventFilter(self)
        else:
            app.removeEventFilter(self)
            self.hide()
        self._badge(on)
        if on and not quiet:
            self.win.statusBar().showMessage(_("whats_this_on"), 8000)
        log.info("what's this: %s", "on" if on else "off")

    def hide(self):
        if self.popup is not None:
            self.popup.hide_hint()

    def _badge(self, on):
        """A "?" at the right end of the status bar while the mode is on."""
        bar = self.win.statusBar()
        if on and self.badge is None:
            self.badge = QLabel("?")
            self.badge.setObjectName("muted")
            self.badge.setToolTip(_("whats_this_tip"))
            bar.addPermanentWidget(self.badge)
        elif not on and self.badge is not None:
            drop(self.badge)
            self.badge = None

    def _what(self, obj, e):
        """(tooltip, own key, the thing it belongs to) under the mouse: a menu's action,
        or the widget or the nearest parent with a tooltip or a hint of its own."""
        if isinstance(obj, QMenu):
            act = obj.actionAt(e.pos())
            if act is not None:
                return (act.toolTip() or act.text().split("\t")[0],
                        act.property("fedtail_hint"), act)
            return "", None, None
        w = obj
        while isinstance(w, QWidget):
            tip, key = w.toolTip(), w.property("fedtail_hint")
            if tip or key:
                return tip, key, w
            w = w.parentWidget()
        return "", None, None

    def eventFilter(self, obj, e):  # noqa: N802 — Qt's name
        if not self.on:
            return False
        t = e.type()
        popup = self.popup
        if popup is not None and popup.isVisible():
            if t in _HIDE_ON or (t == QEvent.Type.Leave and obj is popup.target):
                popup.hide_hint()
        if t != QEvent.Type.ToolTip or not isinstance(obj, QWidget):
            return False
        if popup is not None and obj is popup:
            return True
        tip, key, owner = self._what(obj, e)
        found = helpdocs.hint_for(tip, key)
        if not found:
            return False  # the usual tooltip
        if self.popup is None:
            self.popup = HintPopup(self.win)
        if self.popup.isVisible() and self.popup.target is owner:
            return True  # already showing this one: nothing to redo
        cursor = e.globalPos() if hasattr(e, "globalPos") else QCursor.pos()
        self.popup.show_for(owner, helpdocs.hint_html(tip, found[1]), QPoint(cursor))
        return True

    def hint_text(self, widget):
        """The hint a widget would show now, as plain text (for tests and the log)."""
        found = helpdocs.hint_for(widget.toolTip(), widget.property("fedtail_hint"))
        return found[1]["text"] if found else None
