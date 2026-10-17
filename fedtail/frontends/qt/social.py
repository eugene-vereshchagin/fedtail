"""Tabs and a dialog for the people and reactions around posts (core/social.py):
lists of people (who liked, who boosted, suggestions, the directory), quotes of a
post of mine, trends, and what my server says about itself."""

import logging

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...core.model import real, snippet
from ...i18n import _
from .card import CardSpec
from .feed import AccountRow, FeedView, TagRow, _button, _Header, _PagedTab
from .text import clean, esc

log = logging.getLogger(__name__)


class AccountsWidget(QWidget):
    """A list of people read page by page: fetch(cursor) gives a future of
    ({accounts, relations}, next cursor). origin(have_ids): more from somewhere else
    (the post's own server) once the pages run out. dismiss(acc_id): a "don't
    suggest" button on each row."""

    def __init__(self, win, key, title, fetch, origin=None, origin_label="", dismiss=None):
        super().__init__()
        self.win, self.core, self.key = win, win.core, key
        self.title, self.fetch, self.origin = title, fetch, origin
        self.origin_label, self.dismiss = origin_label, dismiss
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
        self.win.bridge.call(fut, ok=self._page,
                             fail=lambda e: (self.btn_more.setText(_("no_older")),
                                             self.win.error(e)))

    def _page(self, got):
        res, nxt = got
        for a in res["accounts"]:
            if a["id"] in self.shown_ids:
                continue
            row = AccountRow(self.win, a, res["relations"].get(a["id"]))
            if self.dismiss is not None:
                b = _button(_("dismiss_suggestion"), lambda _c=False, r=row: self._drop(r))
                row.layout().addWidget(b, 0, Qt.AlignmentFlag.AlignTop)
            self.box_lay.addWidget(row)
            self.shown_ids.add(a["id"])
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
        self.win.bridge.call(self.dismiss(row.acc["id"]), ok=lambda _r: row.deleteLater(),
                             fail=self.win.error)

    def apply_read(self, ids):
        pass


class QuotesWidget(_PagedTab):
    """Posts quoting a post of mine; each card's menu can take my post out of it."""

    def __init__(self, win, status):
        self.status = real(status)
        super().__init__(win, _("quotes_title", text=snippet(status, 40)))
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
            for ln in t["links"][:10]:
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

    def render(self):
        short = self.core.short_ids(self.items)
        self.view.set_specs([CardSpec(key=st["id"], status=st, parent=self.core.parent_of(st),
                                      extra={"short_id": short.get(real(st)["id"])})
                             for st in self.items], keep_position=True)


def _section(text):
    label = QLabel(text)
    label.setObjectName("sectionTitle")
    return label


class ServerInfoDialog(QDialog):
    """My server about itself: description, contact, rules, privacy policy."""

    def __init__(self, win, info):
        super().__init__(win)
        inst = info.get("instance") or {}
        self.setWindowTitle(_("server_info") + " — " + (inst.get("title") or
                                                        inst.get("domain") or ""))
        self.resize(640, 560)
        lay = QVBoxLayout(self)
        css = win.theme.css("link")
        parts = [f"<h2>{esc(inst.get('title') or inst.get('domain') or '')}</h2>"]
        desc = inst.get("description") or inst.get("short_description") or ""
        if desc:
            # HTML on GoToSocial and older Mastodon, plain text on Mastodon 4
            parts.append(clean(desc, css) if "<" in desc else f"<p>{esc(desc)}</p>")
        contact = (inst.get("contact") or {}).get("account") or \
            inst.get("contact_account") or {}
        email = (inst.get("contact") or {}).get("email") or inst.get("email") or ""
        who = ", ".join(x for x in (("@" + contact["acct"]) if contact.get("acct") else "",
                                    email) if x)
        if who:
            parts.append(f"<p>{esc(_('server_contact', who=who))}</p>")
        if info.get("about"):
            parts.append(clean(info["about"], css))
        rules = info.get("rules") or []
        if rules:
            parts.append(f"<h3>{esc(_('server_rules'))}</h3><ol>" +
                         "".join(f"<li>{esc(r.get('text') or '')}"
                                 + (f"<br><small>{esc(r['hint'])}</small>"
                                    if r.get("hint") else "") + "</li>" for r in rules)
                         + "</ol>")
        if info.get("privacy"):
            parts.append(f"<h3>{esc(_('server_privacy'))}</h3>" + clean(info["privacy"], css))
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        view.setHtml("".join(parts))
        lay.addWidget(view, 1)
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        lay.addWidget(box)
