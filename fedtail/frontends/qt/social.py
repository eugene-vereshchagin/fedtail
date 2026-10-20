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


class ServerInfoDialog(QDialog):
    """My server about itself (a ServerInfo): description, contact, rules, privacy."""

    def __init__(self, win, info):
        super().__init__(win)
        self.setWindowTitle(_("server_info") + " — " + (info.title or info.domain))
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        css = win.theme.css("link")
        parts = [f"<h2>{esc(info.title or info.domain)}</h2>"]
        desc = info.description
        if desc:
            # HTML on GoToSocial and older Mastodon, plain text on Mastodon 4
            parts.append(clean(desc, css) if "<" in desc else f"<p>{esc(desc)}</p>")
        who = ", ".join(x for x in ("@" + info.contact.handle if info.contact else "",
                                    info.email) if x)
        if who:
            parts.append(f"<p>{esc(_('server_contact', who=who))}</p>")
        if info.about:
            parts.append(clean(info.about, css))
        if info.rules:
            parts.append(f"<h3>{esc(_('server_rules'))}</h3><ol>" +
                         "".join(f"<li>{esc(text)}"
                                 + (f"<br><small>{esc(hint)}</small>" if hint else "")
                                 + "</li>" for text, hint in info.rules)
                         + "</ol>")
        if info.privacy:
            parts.append(f"<h3>{esc(_('server_privacy'))}</h3>" + clean(info.privacy, css))
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setHtml("".join(parts))
        self.tabs = QTabWidget()
        self.tabs.addTab(view, _("server_about_tab"))
        self.tabs.addTab(self._can_tab(win), _("probe_tab"))
        lay.addWidget(self.tabs, 1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        lay.addWidget(box)

    # ---- what it can do: asked by a button, a few seconds, in the background --------
    def _can_tab(self, win):
        self.win = win
        tab = QWidget()
        v = QVBoxLayout(tab)
        v.setContentsMargins(0, 8, 0, 0)
        top = QHBoxLayout()
        self.probe_note = QLabel()
        self.probe_note.setObjectName("muted")
        self.probe_note.setWordWrap(True)
        top.addWidget(self.probe_note, 1)
        self.probe_btn = _button(_("probe_run"), self._probe, icon="view-refresh",
                                 tip=_("probe_tip"))
        top.addWidget(self.probe_btn, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(top)
        self.probe_table = QTreeWidget()
        self.probe_table.setRootIsDecorated(False)
        self.probe_table.setHeaderLabels([_("probe_what"), _("probe_answer")])
        self.probe_table.setAlternatingRowColors(True)
        v.addWidget(self.probe_table, 1)
        self._show_probe(win.ctx.view.last_probe())
        return tab

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

    def _show_probe(self, probe):
        self.probe_table.clear()
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


PROBE_MARKS = {"yes": "✓", "no": "✗", "closed": "🔒", "error": "⚠", "self": "◐", "info": "·"}


def _has(key):
    return _(key) != key
