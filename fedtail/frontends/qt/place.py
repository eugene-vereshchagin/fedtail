"""A place of common/places.py in a window of its own — any of them, drawn as the web page,
the terminal and the phone draw it: the hint, the tabs, the rows with their buttons, the
form and its button, "more". What a button does is the place's (Places.act); what it
answers is done here the window's way: a question, a line to type, the status bar, a
thread or a profile in a tab, the browser. Collections (Mastodon 4.6) live here — and
any place the windows have no widget of their own for."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ...i18n import _
from ...model import real
from ..common.places import PLACES, Places


def _clear(layout):
    while layout.count():
        item = layout.takeAt(0)
        w = item.widget()
        if w is not None:
            w.deleteLater()
        elif item.layout() is not None:
            _clear(item.layout())


class PlaceDialog(QDialog):
    """One place; a button that opens another place of it goes on in the same window."""

    def __init__(self, win, name, arg="", tab=""):
        super().__init__(win)
        self.win = win
        self.view = win.ctx.view
        self.places = Places(self.view)
        self.name, self.arg, self.tab, self.cursor = name, arg, tab, ""
        self.page = None
        self.fields = {}  # name -> (kind, widget(s))
        self.setWindowTitle(_(PLACES.get(name, name)))
        self.resize(640, 640)
        lay = QVBoxLayout(self)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        self.hint.setObjectName("muted")
        lay.addWidget(self.hint)
        self.tabs = QHBoxLayout()
        lay.addLayout(self.tabs)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        self.rows = QVBoxLayout(body)
        self.rows.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(body)
        lay.addWidget(scroll, 1)
        self.form = QVBoxLayout()
        lay.addLayout(self.form)
        self.load()

    # ---- the page, built off the GUI thread (the place asks the server) ----------------
    def load(self):
        name, arg, tab, cursor = self.name, self.arg, self.tab, self.cursor
        fut = self.view.bg.submit(lambda: self.places.page(name, arg, tab, cursor))
        self.win.bridge.call(fut, ok=self.draw, fail=self.win.error)

    def draw(self, page):
        self.page = page
        self.setWindowTitle(page.title)
        self.hint.setText(page.hint)
        self.hint.setVisible(bool(page.hint))
        _clear(self.tabs)
        for key, words in page.tabs:
            b = QPushButton(words)
            b.setObjectName("primary" if key == page.tab else "tool")
            b.clicked.connect(lambda _c=False, k=key: self.go(self.name, self.arg, k))
            self.tabs.addWidget(b)
        if page.tabs:
            self.tabs.addStretch(1)
        if not self.cursor:
            _clear(self.rows)
        for row in page.rows:
            self.rows.addWidget(self.row(row))
        if not page.rows and not self.cursor:
            empty = QLabel(page.empty or "—")
            empty.setObjectName("muted")
            self.rows.addWidget(empty)
        _clear(self.form)
        self.fields = {}
        for f in page.form:
            self.field(f)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        for b in (page.more, page.submit):
            if b is not None:
                w = QPushButton(b.label)
                w.setObjectName("primary" if b.primary else "tool")
                if b.tip:
                    w.setToolTip(b.tip)
                w.clicked.connect(lambda _c=False, btn=b: self.press(btn))
                buttons.addWidget(w)
        self.form.addLayout(buttons)

    def row(self, r):
        box = QWidget()
        box.setObjectName("card")
        lay = QVBoxLayout(box)
        lay.setContentsMargins(10, 8, 10, 8)
        if r.kind == "html":
            text = QLabel(r.title)
            text.setTextFormat(Qt.TextFormat.RichText)
            text.setOpenExternalLinks(False)
            text.linkActivated.connect(self.win.on_link)
        elif r.kind == "pre":
            text = QLabel(r.title)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        elif r.kind == "post" and r.data is not None:
            from ...model.text import snippet
            p = real(r.data)
            text = QLabel(f"<b>{_esc(p.author.name or p.author.handle)}</b> "
                          f"@{_esc(p.author.handle)}<br>{_esc(snippet(p, 400))}")
            text.setTextFormat(Qt.TextFormat.RichText)
        elif r.kind == "heading":
            text = QLabel(f"<b>{_esc(r.title)}</b>")
        else:
            words = f"<b>{_esc(r.title)}</b>" if r.title else ""
            if r.line:
                words += ("<br>" if words else "") + _esc(r.line)
            text = QLabel(words)
            text.setTextFormat(Qt.TextFormat.RichText)
        text.setWordWrap(True)
        lay.addWidget(text)
        btns = list(r.buttons)
        if r.kind == "post" and r.data is not None:
            sid = real(r.data).id
            open_it = QPushButton(_("thread"))
            open_it.setObjectName("tool")
            open_it.clicked.connect(lambda _c=False: self.win.open_thread(sid))
            btns_row = [open_it]
        else:
            btns_row = []
        if btns or btns_row:
            row = QHBoxLayout()
            row.addStretch(1)
            for w in btns_row:
                row.addWidget(w)
            for b in btns:
                w = QPushButton(b.label)
                w.setObjectName("primary" if b.primary else "tool")
                if b.tip:
                    w.setToolTip(b.tip)
                w.clicked.connect(lambda _c=False, btn=b: self.press(btn))
                row.addWidget(w)
            lay.addLayout(row)
        return box

    def field(self, f):
        if f.kind == "check":
            w = QCheckBox(f.label)
            w.setChecked(bool(f.value))
            self.form.addWidget(w)
            self.fields[f.name] = ("check", w)
        elif f.kind == "choice":
            if f.label:
                self.form.addWidget(QLabel(f.label))
            w = QComboBox()
            for value, words in f.choices:
                w.addItem(words, value)
            i = w.findData(f.value)
            if i < 0:
                i = w.findData(str(f.value))
            w.setCurrentIndex(max(i, 0))
            self.form.addWidget(w)
            self.fields[f.name] = ("choice", w)
        elif f.kind == "checks":
            if f.label:
                self.form.addWidget(QLabel(f.label))
            row = QHBoxLayout()
            boxes = []
            for value, words in f.choices:
                c = QCheckBox(words)
                c.setChecked(value in (f.value or ()))
                row.addWidget(c)
                boxes.append((value, c))
            row.addStretch(1)
            self.form.addLayout(row)
            self.fields[f.name] = ("checks", boxes)
        elif f.kind == "file":
            w = QPushButton(f.label)
            w.setObjectName("tool")
            picked = {"path": ""}

            def choose(_c=False, w=w, picked=picked):
                path, _flt = QFileDialog.getOpenFileName(self, f.label)
                if path:
                    picked["path"] = path
                    w.setText(f.label + " ✓")
            w.clicked.connect(choose)
            self.form.addWidget(w)
            self.fields[f.name] = ("file", picked)
        elif f.kind == "text":
            if f.label:
                self.form.addWidget(QLabel(f.label))
            w = QPlainTextEdit(str(f.value or ""))
            w.setMaximumHeight(110)
            self.form.addWidget(w)
            self.fields[f.name] = ("text", w)
        else:
            w = QLineEdit(str(f.value or ""))
            w.setPlaceholderText(f.label)
            self.form.addWidget(w)
            self.fields[f.name] = ("line", w)
        if f.tip:
            tip = QLabel(f.tip)
            tip.setObjectName("muted")
            tip.setWordWrap(True)
            self.form.addWidget(tip)

    def values(self):
        out = {}
        for name, (kind, w) in self.fields.items():
            if kind == "check":
                out[name] = w.isChecked()
            elif kind == "choice":
                out[name] = w.currentData()
            elif kind == "checks":
                out[name] = [value for value, c in w if c.isChecked()]
            elif kind == "file":
                if w["path"]:
                    out[name] = w["path"]
            elif kind == "text":
                out[name] = w.toPlainText()
            else:
                out[name] = w.text()
        return out

    # ---- a button: the place does it; what it says is done here ------------------------
    def press(self, btn, confirmed=False, answer=None):
        values = self.values()
        fut = self.view.bg.submit(lambda: self.places.act(
            *btn.act, values=values, confirmed=confirmed, answer=answer))
        self.win.bridge.call(fut, ok=lambda out: self.done(btn, out, answer),
                             fail=self.win.error)

    def done(self, btn, out, answer):
        if out.error:
            self.win.error(out.error)
            return
        if out.confirm:
            if QMessageBox.question(self, self.windowTitle(), _plain(out.confirm)) == \
                    QMessageBox.StandardButton.Yes:
                self.press(btn, True, answer)
            return
        if out.ask:
            title, question, text = out.ask
            got, ok = QInputDialog.getText(self, title, question, text=text)
            if ok:
                self.press(btn, False, got)
            return
        if out.copy:
            QApplication.clipboard().setText(out.copy)
        if out.message:
            self.win.statusBar().showMessage(_plain(out.message), 8000)
        if out.compose:
            self.win.compose(text=str(out.compose.get("text") or ""))
        o = out.open or {}
        if o.get("thread"):
            self.win.open_thread(o["thread"])
        elif o.get("account"):
            self.win.open_account(o["account"])
        elif o.get("url"):
            self.win.open_url(o["url"])
        elif o.get("back"):
            self.close()
            return
        elif o.get("page"):
            page = o["page"]
            if isinstance(page, (tuple, list)):
                self.go(page[0], page[1] if len(page) > 1 else "")
            else:
                self.go(page, o.get("arg", ""), o.get("tab", ""), o.get("cursor", ""))
            return
        if out.refresh:
            self.cursor = ""
            self.load()

    def go(self, name, arg="", tab="", cursor=""):
        """Another place (or this one's tab, or its next rows) in this window."""
        same = (name, arg) == (self.name, self.arg)
        self.name, self.arg, self.tab = name, arg, tab
        self.cursor = cursor if same else ""
        self.load()


def _esc(text):
    from html import escape
    return escape(str(text or ""))


def _plain(text):
    import re
    from html import unescape
    return unescape(re.sub(r"<br\s*/?>", "\n", re.sub(r"<(?!br)[^>]+>", "", str(text or ""))))


__all__ = ["PlaceDialog"]
