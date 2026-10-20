"""The help, as a panel inside the main window (like the compose panel).

Pages are Markdown from ``fedtail/data/help/<lang>/`` (`fedtail.frontends.helpdocs` reads
them, resolves links and searches); this module only shows them: the contents on the
left — the short pages, then the deep dive under "In detail" — the page on the right,
Back / Forward / Contents and a search field in the title strip, ✕ or Esc to close.

There is no shortcut on purpose: F1 sits next to Esc, and a missed Esc should not open a
window. The help comes from ≡ → Help only.
"""

import logging

from PySide6.QtCore import QEvent, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QTextCursor, QTextTable
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...i18n import _
from .. import helpdocs

log = logging.getLogger(__name__)

PCT = 90  # of the main window, as the compose panel's big size
# the app's own pages below the help's: (name, title word, icon)
APP_PAGES = [("app:server", "server_info", "network-server"),
             ("app:probe", "probe_tab", "dialog-information"),
             ("app:federation", "fed_title", "network-workgroup")]
NAME_ROLE = Qt.ItemDataRole.UserRole


class StickyHeader(QWidget):
    """A long table's header row stays at the top while its rows scroll under it (the
    comparison matrix: without its header row the ✓ say nothing). Drawn from the very
    document, so it looks exactly like the row it repeats; clicks go through."""

    MIN_ROWS = 6  # a short table is seen whole anyway

    def __init__(self, view):
        super().__init__(view.viewport())
        self.view, self.tables, self.shown = view, [], None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.hide()
        for bar in (view.verticalScrollBar(), view.horizontalScrollBar()):
            bar.valueChanged.connect(self.place)
        view.viewport().installEventFilter(self)

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Type.Resize:
            self.place()
        return False

    def reload(self):
        """The page changed: find its tables anew."""
        self.tables = []

        def walk(frame):
            for child in frame.childFrames():
                if isinstance(child, QTextTable) and child.rows() >= self.MIN_ROWS:
                    self.tables.append(child)
                walk(child)
        walk(self.view.document().rootFrame())
        self.place()

    def _header(self, table):
        """(the table's rect, the header row's height) in the document."""
        lay = self.view.document().documentLayout()
        box = lay.frameBoundingRect(table)
        second = lay.blockBoundingRect(table.cellAt(1, 0).firstCursorPosition().block())
        return box, max(0.0, second.top() - box.top())

    def place(self, *_a):
        y = self.view.verticalScrollBar().value()
        for t in self.tables:
            box, h = self._header(t)
            # its header gone above the top, and rows of it still on screen below
            if h and box.top() < y and box.bottom() - 2 * h > y:
                self.shown = (box, h)
                self.setGeometry(0, 0, self.view.viewport().width(), int(h) + 1)
                self.show()
                self.raise_()
                self.update()
                return
        self.shown = None
        self.hide()

    def paintEvent(self, _e):
        if not self.shown:
            return
        box, h = self.shown
        x = self.view.horizontalScrollBar().value()
        p = QPainter(self)
        p.fillRect(self.rect(), self.view.palette().base())
        p.translate(-x, -box.top())
        self.view.document().drawContents(p, QRectF(x, box.top(), self.width(), h))
        p.resetTransform()
        p.setPen(self.view.palette().mid().color())
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class HelpPanel(QDialog):
    """One help panel per window; `win.open_help()` brings it back with a page."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.lang = helpdocs.language()
        self.history, self.at = [], -1  # [(page, anchor)], the index shown
        self.current = None
        self.setWindowFlags(Qt.WindowType.Widget)  # a panel, not a window of its own
        self.setObjectName("composePanel")  # the compose panel's frame and colours
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(_("help_title"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        head_box = QWidget(self)
        head_box.setObjectName("composeHead")
        head_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        top = QHBoxLayout(head_box)
        top.setContentsMargins(10, 6, 6, 6)
        self.back_btn = self._tool("←", _("help_back"), self.back)
        self.fwd_btn = self._tool("→", _("help_forward"), self.forward)
        self.home_btn = self._tool("☰", _("help_home"), lambda: self.show_page("index"))
        for b in (self.back_btn, self.fwd_btn, self.home_btn):
            top.addWidget(b)
        title = QLabel(_("help_title"))
        title.setObjectName("laneTitle")
        top.addWidget(title, 1)
        self.search = QLineEdit()
        self.search.setPlaceholderText(_("help_search"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(220)
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self.find_next)
        top.addWidget(self.search)
        top.addWidget(self._tool("✕", _("help_close_tip") + " (Esc)", self.reject))
        lay.addWidget(head_box)

        split = QSplitter(Qt.Orientation.Horizontal)
        side = QWidget()
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 0)
        self.toc = QListWidget()
        self.toc.setObjectName("helpToc")
        self.toc.itemActivated.connect(self._picked)
        self.toc.itemClicked.connect(self._picked)
        sv.addWidget(self.toc, 1)
        self.found = QLabel("")
        self.found.setObjectName("muted")
        self.found.setVisible(False)
        sv.addWidget(self.found)
        split.addWidget(side)
        self.view = QTextBrowser()
        self.view.setObjectName("helpView")
        self.view.setOpenLinks(False)
        self.view.anchorClicked.connect(lambda url: self.follow(url.toString()))
        self.sticky = StickyHeader(self.view)
        # the right side: a help page, or one of the app's own (APP_PAGES)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.view)
        self.app_pages = {}
        split.addWidget(self.pages)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([240, 760])
        lay.addWidget(split, 1)

        self._fill_toc()
        win.installEventFilter(self)

    def _tool(self, glyph, tip, slot):
        b = QPushButton(glyph)
        b.setObjectName("tool")
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    # ---- the contents ---------------------------------------------------------------
    def _fill_toc(self, only=None):
        """The pages, in the index's order; `only` — {page: matches} of a search."""
        self.toc.clear()
        deep_head = False
        for p in helpdocs.pages(self.lang):
            if only is not None and p.name not in only:
                continue
            if p.deep and not deep_head:
                head = QListWidgetItem(_("help_deep"))
                head.setFlags(Qt.ItemFlag.NoItemFlags)
                f = head.font()
                f.setBold(True)
                head.setFont(f)
                self.toc.addItem(head)
                deep_head = True
            label = p.title if only is None else f"{p.title}  ({only[p.name]})"
            it = QListWidgetItem(("    " if p.deep else "") + label)
            it.setData(NAME_ROLE, p.name)
            if p.about:
                it.setToolTip(p.about)
            self.toc.addItem(it)
        if only is None:  # what the app itself knows: my server, the federation
            head = QListWidgetItem(_("info_head"))
            head.setFlags(Qt.ItemFlag.NoItemFlags)
            f = head.font()
            f.setBold(True)
            head.setFont(f)
            self.toc.addItem(head)
            for name, word, icon in APP_PAGES:
                it = QListWidgetItem("    " + _(word))
                it.setData(NAME_ROLE, name)
                ic = QIcon.fromTheme(icon)
                if not ic.isNull():
                    it.setIcon(ic)
                self.toc.addItem(it)
        self._mark_current()

    def _app_page(self, name):
        """The widget of one of the app's pages, made the first time it's asked for."""
        page = self.app_pages.get(name)
        if page is not None:
            return page
        from .social import FederationWidget, ProbeWidget, server_html
        win = self.win
        if name == "app:server":
            page = QTextBrowser()
            page.setOpenExternalLinks(True)
            page.setPlainText(_("loading"))
            win.bridge.call(win.ctx.view.server_info(),
                            ok=lambda info, p=page: p.setHtml(server_html(win, info)),
                            fail=lambda e, p=page: p.setPlainText(_("load_failed", err=e)))
        elif name == "app:probe":
            from urllib.parse import urlparse
            host = urlparse((win.core.auth or {}).get("server", "")).hostname or ""
            page = ProbeWidget(win, host)
        else:
            page = FederationWidget(win)
        self.pages.addWidget(page)
        self.app_pages[name] = page
        return page

    def _mark_current(self):
        for i in range(self.toc.count()):
            it = self.toc.item(i)
            if it.data(NAME_ROLE) == self.current:
                self.toc.setCurrentItem(it)
                return

    def _picked(self, it):
        name = it.data(NAME_ROLE)
        if name and name != self.current:
            self.show_page(name)
            if self.search.text().strip():
                self.find_next(from_top=True)

    # ---- pages ----------------------------------------------------------------------
    def show_page(self, name, anchor="", record=True):
        if name.startswith("app:"):
            if name not in {n for n, _w, _i in APP_PAGES}:
                return False
            self.pages.setCurrentWidget(self._app_page(name))
            self.current = name
            self._record(name, anchor, record)
            return True
        self.pages.setCurrentIndex(0)
        text = helpdocs.page(self.lang, name)
        if text is None:
            log.info("help: no page %s", name)
            self.win.statusBar().showMessage(_("help_missing", name=name), 5000)
            return False
        if name != self.current:
            self.view.setMarkdown(text)
            self.current = name
            self.sticky.reload()
        self._scroll_to(anchor)
        self._record(name, anchor, record)
        return True

    def _record(self, name, anchor, record):
        if record:
            del self.history[self.at + 1:]
            self.history.append((name, anchor))
            self.at = len(self.history) - 1
        self._mark_current()
        self.back_btn.setEnabled(self.at > 0)
        self.fwd_btn.setEnabled(self.at < len(self.history) - 1)
        log.info("help: %s%s", name, f"#{anchor}" if anchor else "")

    def _scroll_to(self, anchor):
        bar = self.view.verticalScrollBar()
        if not anchor:
            bar.setValue(0)
            return
        block = self.view.document().begin()
        while block.isValid():
            if block.blockFormat().headingLevel() and helpdocs.slug(block.text()) == anchor:
                self.view.setTextCursor(QTextCursor(block))
                rect = self.view.document().documentLayout().blockBoundingRect(block)
                bar.setValue(int(rect.top()))
                return
            block = block.next()
        bar.setValue(0)

    def follow(self, link):
        """A link on the page: another help page (and the place on it), or the browser."""
        target = helpdocs.resolve(link, self.lang, self.current or "index")
        if target.url:
            self.win.open_url(target.url)
        else:
            self.show_page(target.page, target.anchor)

    def back(self):
        if self.at > 0:
            self.at -= 1
            self.show_page(*self.history[self.at], record=False)

    def forward(self):
        if self.at < len(self.history) - 1:
            self.at += 1
            self.show_page(*self.history[self.at], record=False)

    # ---- search ---------------------------------------------------------------------
    def _filter(self, text):
        query = text.strip()
        if not query:
            self.found.setVisible(False)
            self._fill_toc()
            return
        hits = helpdocs.search(self.lang, query)
        self._fill_toc({p.name: n for p, n in hits})
        self.found.setText(_("help_found", n=len(hits)) if hits else _("help_none"))
        self.found.setVisible(True)

    def find_next(self, from_top=False):
        """Enter in the search field: the next place on the page with the first word of
        the query; past the end, the next page that has it."""
        words = self.search.text().split()
        if not words:
            return
        if from_top:
            self.view.moveCursor(QTextCursor.MoveOperation.Start)
        if self.view.find(words[0]):
            return
        names = [self.toc.item(i).data(NAME_ROLE) for i in range(self.toc.count())]
        names = [n for n in names if n]
        if not names:
            return
        i = names.index(self.current) if self.current in names else -1
        nxt = names[(i + 1) % len(names)]
        self.show_page(nxt)
        self.view.moveCursor(QTextCursor.MoveOperation.Start)
        self.view.find(words[0])

    # ---- the panel: over the lanes, following the window ----------------------------
    def _place(self):
        win = self.win
        w = max(480, int(win.width() * PCT / 100) - 20)
        h = max(360, int(win.height() * PCT / 100) - 20)
        self.setGeometry(max(10, (win.width() - w) // 2), max(10, (win.height() - h) // 2),
                         w, h)
        self.raise_()

    def showEvent(self, e):  # noqa: N802 — Qt's name
        super().showEvent(e)
        self._place()
        if self.current is None:
            self.show_page("index")
        self.view.setFocus()

    def eventFilter(self, obj, e):  # noqa: N802 — Qt's name
        if obj is self.win and e.type() == QEvent.Type.Resize and self.isVisible():
            self._place()
        return super().eventFilter(obj, e)

    def reject(self):
        """✕ or Esc: hidden, not destroyed — the next ≡ → Help is back where it was."""
        self.hide()
