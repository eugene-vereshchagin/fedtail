"""The "What's this?" mode: point the mouse at a button and get the longer story.

While the mode is on, an application-wide event filter takes every tooltip request. The
widget under the mouse (or the menu action under it) says what it is by its usual
tooltip; `helpdocs.hint_for` finds the interface string behind that text and its hint in
``hints.toml``. Found — a rich tooltip: the button's own words, the hint, the config key
and the help page; not found — the usual tooltip, untouched. So no widget needs to be
marked by hand; one may still name its hint with ``setProperty("fedtail_hint", key)``.

On for the session from ≡ → What's this?, or from the start with ``ui.whats_this``.
There is no shortcut on purpose (Shift+F1 sits next to Esc too).
"""

import logging

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import QApplication, QLabel, QMenu, QToolTip, QWidget

from ...i18n import _
from .. import helpdocs

log = logging.getLogger(__name__)


class HintMode(QObject):
    def __init__(self, win, on=False):
        super().__init__(win)
        self.win = win
        self.on = False
        self.badge = None
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
            QToolTip.hideText()
        self._badge(on)
        if on and not quiet:
            self.win.statusBar().showMessage(_("whats_this_on"), 8000)
        log.info("what's this: %s", "on" if on else "off")

    def _badge(self, on):
        """A "?" at the right end of the status bar while the mode is on."""
        bar = self.win.statusBar()
        if on and self.badge is None:
            self.badge = QLabel("?")
            self.badge.setObjectName("muted")
            self.badge.setToolTip(_("whats_this_tip"))
            bar.addPermanentWidget(self.badge)
        elif not on and self.badge is not None:
            bar.removeWidget(self.badge)
            self.badge.deleteLater()
            self.badge = None

    def _what(self, obj, e):
        """(tooltip, own key) of what is under the mouse: a menu's action, or the widget
        or the nearest parent that has a tooltip or names a hint."""
        if isinstance(obj, QMenu):
            act = obj.actionAt(e.pos())
            if act is not None:
                return act.toolTip() or act.text().split("\t")[0], act.property("fedtail_hint")
            return "", None
        w = obj
        while isinstance(w, QWidget):
            tip, key = w.toolTip(), w.property("fedtail_hint")
            if tip or key:
                return tip, key
            w = w.parentWidget()
        return "", None

    def eventFilter(self, obj, e):  # noqa: N802 — Qt's name
        if not self.on or e.type() != QEvent.Type.ToolTip or not isinstance(obj, QWidget):
            return False
        tip, key = self._what(obj, e)
        found = helpdocs.hint_for(tip, key)
        if not found:
            return False  # the usual tooltip
        QToolTip.showText(e.globalPos(), helpdocs.hint_html(tip, found[1]), obj)
        return True

    def hint_text(self, widget):
        """The hint a widget would show now, as plain text (for tests and the log)."""
        found = helpdocs.hint_for(widget.toolTip(), widget.property("fedtail_hint"))
        return found[1]["text"] if found else None
