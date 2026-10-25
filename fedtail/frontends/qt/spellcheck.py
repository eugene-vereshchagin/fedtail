"""Spell checking in the post editor (core/spell.py): words with mistakes underlined
with a red wave, and on a right click over one — what to put instead, and "Add to
dictionary". The checker follows the post's language picked in the editor."""

import logging

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QColor, QSyntaxHighlighter, QTextCharFormat, QTextCursor

from ...core import spell
from ...i18n import _, current_language

log = logging.getLogger(__name__)
SUGGESTIONS = 8


class SpellHighlighter(QSyntaxHighlighter):
    """Marks the words the checker doesn't know, block by block (a line each)."""

    def __init__(self, document, checker=None):
        super().__init__(document)
        self.checker = checker
        self.fmt = QTextCharFormat()
        self.fmt.setUnderlineStyle(QTextCharFormat.UnderlineStyle.SpellCheckUnderline)
        self.fmt.setUnderlineColor(QColor("#d32f2f"))

    def set_checker(self, checker):
        if checker is not self.checker:
            self.checker = checker
            self.rehighlight()

    def highlightBlock(self, text):  # noqa: N802 — Qt's name
        if self.checker is None or not text:
            return
        try:
            wrong = self.checker.wrong(text)
        except Exception as e:  # noqa: BLE001 — a dictionary failing: no marks, typing goes on
            log.debug("spell: %s", e)
            return
        for start, end, _w in wrong:
            self.setFormat(start, end - start, self.fmt)


def config_dir(view):
    """Where my own dictionary lives: next to the config (spelling.txt)."""
    try:
        from ..common import settings
        return settings.config_file(view).parent
    except Exception:  # noqa: BLE001 — a view without paths (tests): no own words file
        return None


class Spell:
    """The editor's spell checking: the highlighter and the right-click menu."""

    def __init__(self, compose, edit):
        self.compose, self.edit = compose, edit
        self.view = compose.core
        self.on = bool((self.view.cfg.get("post") or {}).get("spellcheck", True))
        self.highlighter = SpellHighlighter(edit.document()) if self.on else None
        self.said_unavailable = False
        edit.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        edit.customContextMenuRequested.connect(self.menu)
        self.repick()

    @property
    def checker(self):
        return self.highlighter.checker if self.highlighter is not None else None

    def repick(self, *_a):
        """The checker for the language picked now (the editor's language list)."""
        if not self.on:
            return
        lang = ""
        try:
            lang = self.compose._language() or ""
        except Exception:  # noqa: BLE001 — called before the list is filled
            pass
        checker = spell.for_post(self.view.cfg, config_dir(self.view), lang,
                                 current_language())
        self.highlighter.set_checker(checker)
        if checker is None and not spell.available() and not self.said_unavailable:
            self.said_unavailable = True
            self.edit.setToolTip(_("spell_unavailable"))

    def word_at(self, pos):
        """(cursor selecting the word under pos, the word) — or (None, "")."""
        cur = self.edit.cursorForPosition(pos)
        block = cur.block()
        text, at = block.text(), cur.positionInBlock()
        for start, end, word in spell.words(text):
            if start <= at <= end:
                c = QTextCursor(block)
                c.setPosition(block.position() + start)
                c.setPosition(block.position() + end, QTextCursor.MoveMode.KeepAnchor)
                return c, word
        return None, ""

    def actions_for(self, pos):
        """[(label, fn)] for the word under pos when it's marked: suggestions (or "none")
        and "Add to dictionary"; [] for a good word or none at all."""
        checker = self.checker
        if checker is None:
            return []
        cur, word = self.word_at(pos)
        if cur is None or checker.ok(word):
            return []
        out = []
        for s in checker.suggest(word, SUGGESTIONS):
            out.append((s, lambda _c=False, s=s, cur=cur: self.replace(cur, s)))
        if not out:
            out.append((_("spell_none"), None))
        out.append((_("spell_add"), lambda _c=False, w=word: self.add(w)))
        return out

    def replace(self, cur, word):
        cur.beginEditBlock()
        cur.insertText(word)
        cur.endEditBlock()

    def add(self, word):
        if self.checker is not None:
            self.checker.add(word)
            self.highlighter.rehighlight()

    def menu(self, pos):
        """The editor's own menu, the spelling's on top for a marked word (pos: in
        the viewport, as the edit's customContextMenuRequested gives it)."""
        m = self.edit.createStandardContextMenu(pos)
        self.fill(m, pos)
        m.exec(self.edit.viewport().mapToGlobal(QPoint(pos)))
        m.deleteLater()

    def fill(self, m, pos):
        """The spelling's actions put on top of the menu m."""
        acts = self.actions_for(pos)
        if not acts:
            return []
        first = m.actions()[0] if m.actions() else None
        made = []
        for label, fn in acts:
            a = QAction(label, m)
            m.insertAction(first, a)
            if fn is None:
                a.setEnabled(False)
            else:
                a.triggered.connect(fn)
            made.append(a)
        if first is not None:
            m.insertSeparator(first)
        return made

__all__ = ["Spell", "SpellHighlighter", "config_dir"]
