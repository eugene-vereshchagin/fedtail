"""Tabs and a dialog for the people and reactions around posts (core/social.py):
lists of people (who liked, who boosted, suggestions, the directory), quotes of a
post of mine, trends, and what my server says about itself."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QTabWidget,
    QTextBrowser,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...i18n import _
from ...model.text import snippet
from ..common import server
from .feed import AccountRow, FeedView, TagRow, _button, _Header, _PagedTab
from .text import clean, esc

log = logging.getLogger(__name__)


class AccountsWidget(QWidget):
    """A list of people read page by page: fetch(cursor) gives a future of
    ({accounts, relations}, next cursor). origin(have_ids): more from somewhere else
    (the post's own server) once the pages run out. dismiss(acc_id): a "don't
    suggest" button on each row."""

    def __init__(self, win, key, title, fetch, origin=None, origin_label="", dismiss=None,
                 dismiss_label=None):
        super().__init__()
        self.win, self.core, self.key = win, win.ctx.view, key
        self.title, self.fetch, self.origin = title, fetch, origin
        self.origin_label, self.dismiss = origin_label, dismiss
        self.dismiss_label = dismiss_label or _("dismiss_suggestion")
        self.next = None
        self.count = 0
        self.shown_ids = set()
        self.view = None  # Ctrl+F has nothing to find here
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.header = _Header(win.theme, title)
        lay.addWidget(self.header)
        self.feed = FeedView(win.ctx)
        lay.addWidget(self.feed, 1)
        self.box = QWidget()
        self.box_lay = QVBoxLayout(self.box)
        self.box_lay.setContentsMargins(0, 0, 0, 0)
        self.box_lay.setSpacing(8)
        self.feed.header.addWidget(self.box)
        self.btn_more = _button(_("older_down"), self.more, name="older")
        self.feed.footer.addWidget(self.btn_more)
        self.asked_origin = False
        self.more()

    def more(self):
        self.btn_more.setEnabled(False)
        if self.asked_origin:
            fut = self.origin(self.shown_ids)
        else:
            fut = self.fetch(self.next)
        # fetch and origin may be the window's calls on the core itself: what they give
        # is made the model here
        self.win.bridge.call(fut, ok=lambda got: self._page(self.core.model_of(got)),
                             fail=lambda e: (self.btn_more.setText(_("no_older")),
                                             self.win.error(e)))

    def _page(self, got):
        res, nxt = got
        for a in res["accounts"]:
            if a.id in self.shown_ids:
                continue
            row = AccountRow(self.win, a, res["relations"].get(a.id))
            if self.dismiss is not None:
                b = _button(self.dismiss_label, lambda _c=False, r=row: self._drop(r))
                row.layout().addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
            self.box_lay.addWidget(row)
            self.shown_ids.add(a.id)
            self.count += 1
        info = _("people_shown", n=self.count)
        if res.get("total") is not None:
            info += " · " + _("people_origin_total", n=res["total"])
        self.header.info.setText(info)
        self.next = nxt
        if nxt and not self.asked_origin:
            self.btn_more.setEnabled(True)
        elif self.origin is not None and not self.asked_origin:
            self.asked_origin = True  # mine has no more: the rest is on their server
            self.btn_more.setText(self.origin_label)
            self.btn_more.setEnabled(True)
        else:
            self.btn_more.setText(_("no_older"))

    def _drop(self, row):
        self.win.bridge.call(self.dismiss(row.acc.id), ok=lambda _r: row.deleteLater(),
                             fail=self.win.error)

    def apply_read(self, ids):
        pass


class QuotesWidget(_PagedTab):
    """Posts quoting a post of mine; each card's menu can take my post out of it."""

    def __init__(self, win, post):
        self.status = post  # a Post of mine
        super().__init__(win, _("quotes_title", text=snippet(post, 40)))
        self.cursor = None
        self.header.info.setText(_("quotes_info"))
        self.more()

    def more(self):
        self.btn_more.setEnabled(False)

        def got(r):
            page, self.cursor = r
            self._page(page)
            self.btn_more.setEnabled(bool(self.cursor))
            if not self.cursor:
                self.btn_more.setText(_("no_older"))
        self.win.bridge.call(self.core.quotes_of(self.status, self.cursor), ok=got,
                             fail=lambda e: (self.btn_more.setText(_("no_older")),
                                             self.win.error(e)))


class TrendsWidget(_PagedTab):
    """What's talked about on my server: tags, links, posts."""

    def __init__(self, win):
        super().__init__(win, _("trends_title"))
        self.top = QWidget()
        self.top_lay = QVBoxLayout(self.top)
        self.top_lay.setContentsMargins(0, 0, 0, 0)
        self.top_lay.setSpacing(8)
        self.view.header.addWidget(self.top)
        self.btn_more.hide()  # one page: what's trending now
        self.header.add(_button("", self.reload, icon="view-refresh", tip=_("refresh")))
        self.reload()

    def reload(self):
        self.win.bridge.call(self.core.trends(), ok=self._got, fail=self.win.error)

    def _got(self, t):
        while self.top_lay.count():
            item = self.top_lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        theme = self.win.theme
        if t["tags"]:
            self.top_lay.addWidget(_section(_("trends_tags")))
            for tag in t["tags"][:10]:
                self.top_lay.addWidget(TagRow(self.win, tag))
        if t["links"]:
            self.top_lay.addWidget(_section(_("trends_links")))
            for ln in t["links"][:10]:  # links: as the server gives them (no model yet)
                label = QLabel(f'<a href="{esc(ln.get("url", ""))}" style="color:'
                               f'{theme.c["link"].name()};"><b>{esc(ln.get("title") or "")}'
                               f'</b></a><br><span style="color:{theme.c["muted"].name()};">'
                               f'{esc(ln.get("provider_name") or "")} · '
                               f'{esc((ln.get("description") or "")[:200])}</span>')
                label.setTextFormat(Qt.TextFormat.RichText)
                label.setWordWrap(True)
                label.setObjectName("card")
                label.linkActivated.connect(self.win.on_link)
                self.top_lay.addWidget(label)
        if t["statuses"]:
            self.top_lay.addWidget(_section(_("trends_posts")))
        if not any(t.values()):
            self.top_lay.addWidget(QLabel(_("trends_none")))
        self.items = list(t["statuses"])
        self.render()


def _section(text):
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


def server_html(win, info):
    """What my server says about itself (a ServerInfo), as a page."""
    css = win.theme.css("link")
    return server.server_html(info, lambda html: clean(html, css))


class ServerInfoDialog(QDialog):
    """My server about itself (a ServerInfo): description, contact, rules, privacy;
    and what it can do (ProbeWidget)."""

    def __init__(self, win, info):
        super().__init__(win)
        self.setWindowTitle(_("server_info") + " — " + (info.title or info.domain))
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setHtml(server_html(win, info))
        self.probe = ProbeWidget(win, info.domain or info.title)
        for name in ("probe_table", "probe_btn", "copy_btn", "save_btn", "probe_note",
                     "probe_text"):
            setattr(self, name, getattr(self.probe, name))
        self.tabs = QTabWidget()
        self.tabs.addTab(view, _("server_about_tab"))
        self.tabs.addTab(self.probe, _("probe_tab"))
        lay.addWidget(self.tabs, 1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        lay.addWidget(box)


class ProbeWidget(QWidget):
    """What my server can do: asked by a button, a few seconds, in the background; the
    last round shown at once; copied or saved as a Markdown table."""

    def __init__(self, win, domain):
        super().__init__()
        self.win, self.domain = win, domain
        self._build(win)

    def _build(self, win):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 8, 0, 0)
        top = QHBoxLayout()
        self.probe_note = QLabel()
        self.probe_note.setObjectName("muted")
        self.probe_note.setWordWrap(True)
        top.addWidget(self.probe_note, 1)
        self.probe_btn = _button(_("probe_run"), self._probe, icon="view-refresh",
                                 tip=_("probe_tip"))
        self.copy_btn = _button(_("probe_copy"), self._copy, icon="edit-copy",
                                tip=_("probe_copy_tip"))
        self.save_btn = _button(_("probe_save"), self._save, icon="document-save",
                                tip=_("probe_save_tip"))
        for b in (self.copy_btn, self.save_btn, self.probe_btn):
            top.addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(top)
        self.probe_table = QTreeWidget()
        self.probe_table.setRootIsDecorated(False)
        self.probe_table.setHeaderLabels([_("probe_what"), _("probe_answer")])
        self.probe_table.setAlternatingRowColors(True)
        self.probe_table.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        from PySide6.QtGui import QKeySequence, QShortcut
        QShortcut(QKeySequence.StandardKey.Copy, self.probe_table,
                  context=Qt.ShortcutContext.WidgetShortcut,
                  activated=lambda: self._copy(selected=True))
        v.addWidget(self.probe_table, 1)
        self._show_probe(win.ctx.view.last_probe())

    def _probe(self):
        self.probe_btn.setEnabled(False)
        self.probe_note.setText(_("probe_running"))

        def done(got):
            try:
                self.probe_btn.setEnabled(True)
                self._show_probe(got)
            except RuntimeError:  # closed meanwhile: the result is kept for next time
                pass

        def failed(e):
            try:
                self.probe_btn.setEnabled(True)
                self.probe_note.setText(_("probe_failed", err=e))
            except RuntimeError:
                pass
        self.win.bridge.call(self.win.ctx.view.probe_server(), ok=done, fail=failed)

    def probe_text(self, selected=False):
        """The answers as a Markdown table (pasted into an issue, a chat, a note):
        the server, when it was checked, then a row per feature."""
        items = self.probe_table.selectedItems() if selected else []
        rows = [it for it in (items or [self.probe_table.topLevelItem(i) for i in
                                        range(self.probe_table.topLevelItemCount())])]
        rows = list(dict.fromkeys(rows))  # a selected row comes once per column
        return server.probe_markdown(self.domain, self.probe_note.text(),
                                     [(it.text(0), it.text(1)) for it in rows])

    def _copy(self, selected=False):
        from PySide6.QtGui import QGuiApplication
        if not self.probe_table.topLevelItemCount():
            return
        QGuiApplication.clipboard().setText(self.probe_text(selected))
        self.probe_note.setToolTip(_("probe_copied"))
        self.win.statusBar().showMessage(_("probe_copied"), 4000)

    def _save(self):
        from pathlib import Path

        from PySide6.QtWidgets import QFileDialog
        if not self.probe_table.topLevelItemCount():
            return
        name = f"fedtail-{self.domain or 'server'}-features.md"
        start = str(Path(self.win.core.get_state("last_save_dir", str(Path.home()))) / name)
        path, _f = QFileDialog.getSaveFileName(self, _("probe_save"), start,
                                               "Markdown (*.md);;Text (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(self.probe_text(), encoding="utf-8")
        except OSError as e:
            self.win.error(e)
            return
        self.win.core.set_state("last_save_dir", str(Path(path).parent))
        self.win.statusBar().showMessage(_("saved_to", path=path), 6000)

    def _show_probe(self, probe):
        self.probe_table.clear()
        has = probe is not None
        self.copy_btn.setEnabled(has)
        self.save_btn.setEnabled(has)
        if probe is None:
            self.probe_note.setText(_("probe_never"))
            return
        when = self.win.theme.date(probe.checked) if probe.checked else "?"
        self.probe_note.setText(_("probe_checked", when=when,
                                  software=" ".join(x for x in (probe.software,
                                                                probe.version) if x)))
        self.probe_btn.setText(_("probe_again"))
        order = {"no": 0, "closed": 1, "error": 2, "self": 3, "yes": 4, "info": 5}
        for f in sorted(probe.features, key=lambda f: order.get(f.state, 9)):
            mark = PROBE_MARKS.get(f.state, "?")
            answer = f.detail if f.state == "info" else \
                _("probe_" + f.state) + (f" ({f.detail})" if f.detail and
                                         f.detail != "known" else "")
            item = QTreeWidgetItem([_("probe_" + f.key) if _has("probe_" + f.key)
                                    else f.key, f"{mark} {answer}"])
            if f.detail == "known":
                item.setToolTip(1, _("probe_known_tip"))
            self.probe_table.addTopLevelItem(item)
        self.probe_table.resizeColumnToContents(0)


class FederationWidget(QWidget):
    """How my server is doing and what keeps failing, here and on other servers
    (core.health; fedstatus draws it): live while shown, copied as text, counted anew."""

    def __init__(self, win):
        super().__init__()
        from PySide6.QtCore import QTimer
        self.win, self.data = win, None
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.view = QTextBrowser()
        self.view.setOpenLinks(False)
        # someone waiting for a list: their profile opens in a tab here (Follow on it)
        self.view.anchorClicked.connect(lambda u: win.on_link(u.toString()))
        self.view.setPlainText(_("loading"))
        v.addWidget(self.view, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        for word, fn in (("fed_refresh", self.refresh), ("fed_copy", self.copy),
                         ("fed_reset", self.count_anew)):
            row.addWidget(_button(_(word), fn))
        v.addLayout(row)
        self.timer = QTimer(self)  # live while shown: the numbers move as polls come
        self.timer.timeout.connect(self.refresh)
        self.timer.setInterval(15000)

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()
        self.timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self.timer.stop()

    def refresh(self):
        def show(data):
            try:
                self.data = data
                from .. import fedstatus
                pos = self.view.verticalScrollBar().value()
                self.view.setHtml(fedstatus.html(data))
                self.view.verticalScrollBar().setValue(pos)  # a refresh keeps the place
            except RuntimeError:  # closed meanwhile
                pass
        self.win.bridge.call(self.win.core.federation_status(), ok=show,
                             fail=lambda e: self.view.setPlainText(_("load_failed", err=e)))

    def copy(self):
        from PySide6.QtGui import QGuiApplication

        from .. import fedstatus
        if self.data is not None:
            QGuiApplication.clipboard().setText(fedstatus.text(self.data))
            self.win.statusBar().showMessage(_("fed_copied"), 5000)

    def count_anew(self):
        from ...core import health
        health.REC.clear()
        log.info("federation status: counting anew")
        self.refresh()


PROBE_MARKS = {"yes": "✓", "no": "✗", "closed": "🔒", "error": "⚠", "self": "◐", "info": "·"}


def _has(key):
    return _(key) != key
