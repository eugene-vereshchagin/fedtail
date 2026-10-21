"""#tags, @names and :emoji: completed while typing, in any Qt text box: the Compose
window and the split layout's input line. What fits is common/compose.py's (the GTK
editor asks there too); this is the popup list under the cursor."""

from PySide6.QtCore import QEvent, QObject, QStringListModel, Qt, QTimer
from PySide6.QtWidgets import QCompleter

from ..common import compose as rules


class Completer(QObject):
    """text: a QPlainTextEdit or QTextEdit; core: the View; bridge: for the server's
    answer about people (asked a moment after typing stops)."""

    KEYS = (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab, Qt.Key.Key_Escape,
            Qt.Key.Key_Backtab)

    def __init__(self, owner, text, core, bridge):
        super().__init__(owner)
        self.text, self.core, self.bridge = text, core, bridge
        self.model = QStringListModel(self)
        self.completer = QCompleter(self.model, owner)
        self.completer.setWidget(text)
        self.completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self.completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.completer.activated.connect(self.put)
        text.textChanged.connect(self.suggest)
        text.installEventFilter(self)
        self.inserts = {}
        self.people_query = ""
        self.people_timer = QTimer(self, singleShot=True, interval=350)
        self.people_timer.timeout.connect(self.ask_server_people)
        core.prepare_tags()
        core.prepare_people()
        if core.cfg["post"].get("complete_emoji", True):
            core.prepare_emoji()

    def token(self):
        """("#", "@" or ":", the word typed right before the cursor) — or (None, None)."""
        cur = self.text.textCursor()
        return rules.token_at_end(cur.block().text()[:cur.positionInBlock()])

    def suggest(self):
        """Offer what fits (post.complete_tags / complete_mentions / complete_emoji); for
        a name, the server is asked too, a moment later."""
        sigil, word = self.token()
        items = rules.suggestions(self.core, sigil, word) if sigil else []
        if sigil == "@" and self.core.cfg["post"].get("complete_mentions", True) and \
                len(word) >= 2:
            self.people_query = word
            self.people_timer.start()
        self.offer(items, sigil, word)

    def ask_server_people(self):
        word = self.people_query

        def got(found):
            sigil, now = self.token()
            if sigil != "@" or now != word:
                return  # typed on meanwhile
            self.offer(rules.more_people(self.core.mention_suggestions(word), found), "@", word)
        self.bridge.call(self.core.search_people(word), ok=got, fail=lambda _e: None)

    def offer(self, items, sigil, word):
        popup = self.completer.popup()
        if not rules.worth_offering(items, word):
            popup.hide()
            return
        self.inserts = {label: insert for insert, label in items}
        self.model.setStringList([label for _i, label in items])
        rect = self.text.cursorRect()
        rect.setWidth(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width()
                      + 16)
        self.completer.complete(rect)
        popup.setCurrentIndex(self.model.index(0))

    def put(self, label):
        _sigil, word = self.token()
        if word is None:
            return
        cur = self.text.textCursor()
        cur.movePosition(cur.MoveOperation.Left, cur.MoveMode.KeepAnchor, len(word) + 1)
        cur.insertText(self.inserts.get(label, label) + " ")
        self.text.setTextCursor(cur)
        self.completer.popup().hide()

    def busy(self):
        """The list is open: Enter, Tab, Esc are its, not the text box's."""
        return self.completer.popup().isVisible()

    def eventFilter(self, obj, e):
        if obj is self.text and e.type() == QEvent.Type.KeyPress and self.busy() and \
                e.key() in self.KEYS:
            return True  # the list takes these
        return super().eventFilter(obj, e)
