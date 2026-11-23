"""The config's [keys] (core/keys.py) in Qt's words: a key event as a Key, and an
action's shortcuts made on a widget."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut

from ...core import keys

log = logging.getLogger(__name__)


def key_of(event):
    """A QKeyEvent → core.keys.Key (the keypad's Enter is Enter)."""
    mods = event.modifiers()
    return keys.from_qt(QKeySequence(event.key()).toString(),
                        bool(mods & Qt.KeyboardModifier.ControlModifier),
                        bool(mods & Qt.KeyboardModifier.AltModifier),
                        bool(mods & Qt.KeyboardModifier.ShiftModifier))


def bind(widget, cfg, action, fn, context=None):
    """A QShortcut on widget for every key the config gives the action → [QShortcut].
    Two owners of one key make Qt run neither: said in the log, and ours run anyway."""
    made = []
    for key in keys.of(cfg, action):
        seqs = [key.qt()]
        if key.name == "enter":  # the keypad's too
            seqs.append(key.qt().replace("Return", "Enter"))
        for seq in seqs:
            sc = QShortcut(QKeySequence(seq), widget)
            if context is not None:
                sc.setContext(context)
            sc.activated.connect(fn)
            sc.activatedAmbiguously.connect(
                lambda f=fn, k=seq: (log.warning("ambiguous shortcut %s", k), f()))
            made.append(sc)
    return made
