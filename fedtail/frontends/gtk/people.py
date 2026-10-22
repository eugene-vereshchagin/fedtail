"""Tabs of people, tags and finds in the GTK window, as the Qt window has them:
whom my server suggests, the profile directory (all, or my server's), what's
trending, a search for people, tags and posts, a tag's posts. A person is a row with
their face, name and Follow; a tag a row with Follow; posts are cards."""

from __future__ import annotations

import logging

from ...i18n import _
from ...model import Account, Tag, real
from .card import Avatar, Card, link_markup, name_of
from .gi_setup import GLib, Gtk, Pango, tip

log = logging.getLogger(__name__)


class AccountRow(Gtk.Box):
    """A person: face, name and @address (open the profile), Follow / Unfollow;
    dismiss: a × that drops them from the list (suggestions)."""

    def __init__(self, win, acc, rel=None, dismiss=None):
        super().__init__(spacing=10)
        self.win, self.acc = win, acc
        self.add_css_class("ft-card")
        self.append(Avatar(win.ctx, acc, 40))
        names = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=True)
        name = Gtk.Label(xalign=0)
        name.set_markup(link_markup(f"fedtail:account/{acc.id}", name_of(acc)))
        name.add_css_class("ft-name")
        name.set_ellipsize(Pango.EllipsizeMode.END)
        name.connect("activate-link", lambda _l, u: (win.on_link(u), True)[1])
        names.append(name)
        handle = Gtk.Label(label="@" + acc.handle, xalign=0)
        handle.add_css_class("ft-muted")
        handle.set_ellipsize(Pango.EllipsizeMode.END)
        names.append(handle)
        if acc.note:
            from ...model.text import html_to_text
            bio = Gtk.Label(label=html_to_text(acc.note)[:220], xalign=0, wrap=True)
            bio.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            bio.set_lines(2)
            bio.set_ellipsize(Pango.EllipsizeMode.END)
            names.append(bio)
        self.append(names)
        me = win.view.me
        if me is None or me.id != acc.id:
            self.follow = Gtk.Button(valign=Gtk.Align.START)
            self.follow.connect("clicked", self._toggle)
            self.append(self.follow)
            self._show(rel)
            if rel is None:
                win.call(win.view.relationship(acc.id), self._show, lambda _e: None)
        if dismiss is not None:
            x = Gtk.Button(icon_name="window-close-symbolic", valign=Gtk.Align.START)
            x.add_css_class("flat")
            tip(x, _("dismiss_suggestion"))
            x.connect("clicked", lambda _b: (dismiss(acc.id), self.set_visible(False)))
            self.append(x)

    def _show(self, rel):
        on = bool(rel and (rel.following or rel.requested))
        self.following = on
        self.follow.set_label(_("unfollow") if on else _("follow"))
        self.follow.set_sensitive(True)

    def _toggle(self, _b):
        self.follow.set_sensitive(False)
        self.win.call(self.win.view.follow(self.acc.id, not self.following), self._show,
                      lambda e: (self.follow.set_sensitive(True), self.win.error(e)))


class TagRow(Gtk.Box):
    """#tag (its posts in a tab), how much it's used, Follow / Unfollow."""

    def __init__(self, win, tag, header=False):
        super().__init__(spacing=10)
        self.win, self.tag = win, tag
        self.header = header
        self.add_css_class("ft-card")
        lab = Gtk.Label(xalign=0, hexpand=True)
        used = f"  ·  {tag.uses} / {tag.people}" if tag.uses or tag.people else ""
        lab.set_markup(link_markup(f"fedtail:tag/{tag.name}", "#" + tag.name)
                       + GLib.markup_escape_text(used))
        lab.connect("activate-link", lambda _l, u: (win.on_link(u), True)[1])
        self.append(lab)
        self.follow = Gtk.Button()
        self.following = bool(tag.following)
        self.follow.connect("clicked", self._toggle)
        self._words()
        self.append(self.follow)
        self.feature = None
        if header and win.view.supports("featured_tags"):
            # on my profile (featured tags), as Qt's tag tab; not known yet: dead
            self.featured = None
            self.feature = Gtk.Button(label=_("tag_feature"))
            tip(self.feature, _("tag_feature_tip"))
            self.feature.set_sensitive(False)
            self.feature.connect("clicked", self._toggle_feature)
            self.append(self.feature)
            win.call(win.view.featured_tag_names(), self._featured,
                     lambda _e: self.feature.set_visible(False))

    def _words(self):
        if self.header:
            self.follow.set_label(_("tag_unfollow") if self.following else _("tag_follow"))
            tip(self.follow, _("tag_follow_tip"))
        else:
            self.follow.set_label(_("unfollow") if self.following else _("follow"))

    def _featured(self, names):
        self.featured = self.tag.name.lower() in (names or set())
        self.feature.set_label(_("tag_unfeature") if self.featured else _("tag_feature"))
        self.feature.set_sensitive(True)

    def _toggle_feature(self, _b):
        on = not self.featured
        self.feature.set_sensitive(False)
        self.win.call(self.win.view.feature_tag(self.tag.name, on),
                      lambda _r: self._featured({self.tag.name.lower()} if on else set()),
                      lambda e: (self.feature.set_sensitive(True), self.win.error(e)))

    def _toggle(self, _b):
        on = not self.following
        self.follow.set_sensitive(False)

        def done(_r):
            self.following = on
            self._words()
            self.follow.set_sensitive(True)
        self.win.call(self.win.view.follow_tag(self.tag.name, on), done,
                      lambda e: (self.follow.set_sensitive(True), self.win.error(e)))


def _section(text):
    lab = Gtk.Label(label=text, xalign=0)
    lab.add_css_class("ft-account")
    lab.add_css_class("caption-heading")
    lab.set_margin_top(10)
    return lab


class Pager:
    """A list of people fetched a page at a time: fetch(cursor) → future of
    ({accounts, relations}, next cursor); "More" for the next page."""

    def __init__(self, win, box, fetch, dismiss=None):
        self.win, self.box, self.fetch, self.dismiss = win, box, fetch, dismiss
        self.more = Gtk.Button(label=_("more"))
        self.more.add_css_class("flat")
        self.more.connect("clicked", lambda _b: self.load())
        self.cursor = None
        self.load()

    def load(self):
        self.more.set_sensitive(False)
        self.win.call(self.fetch(self.cursor), self._got,
                      lambda e: (self.more.set_sensitive(True), self.win.error(e)))

    def _got(self, got):
        page, nxt = got
        if self.more.get_parent() is not None:
            self.box.remove(self.more.get_parent())
        rel = page.get("relations") or {}
        accounts = [a for a in page.get("accounts") or () if isinstance(a, Account)]
        for a in accounts:
            self.box.append(AccountRow(self.win, a, rel.get(a.id), self.dismiss))
        if not accounts and self.cursor is None:
            self.box.append(Gtk.Label(label=_("search_none")))
        self.cursor = nxt
        if nxt:
            self.more.set_sensitive(True)
            self.box.append(self.more)


def open_people(win, key, title, fetch, dismiss=None):
    """A tab of people (suggestions, the directory…); asked again: to the front."""
    page = win.extra_tabs.get(key)
    if page is not None:
        win.tabs.set_current_page(win.tabs.page_num(page))
        return page
    page, box, _title = win._new_tab(title, lambda: win.close_extra(key))
    win.extra_tabs[key] = page
    Pager(win, box, fetch, dismiss)
    return page


def open_trends(win):
    key = "trends"
    page = win.extra_tabs.get(key)
    if page is not None:
        win.tabs.set_current_page(win.tabs.page_num(page))
        return page
    page, box, _title = win._new_tab(_("trends_title"), lambda: win.close_extra(key))
    win.extra_tabs[key] = page

    def got(t):
        if t.get("tags"):
            box.append(_section(_("trends_tags")))
            for tag in t["tags"][:10]:
                if isinstance(tag, Tag):
                    box.append(TagRow(win, tag))
        if t.get("links"):
            box.append(_section(_("trends_links")))
            for ln in t["links"][:10]:  # links: as the server gives them (no model yet)
                get = ln.get if isinstance(ln, dict) else (lambda k, d="", o=ln: getattr(o, k, d))
                lab = Gtk.Label(xalign=0, wrap=True)
                lab.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
                lab.set_markup(
                    "<b>" + link_markup(get("url", "") or "", get("title", "") or "") + "</b>\n"
                    + GLib.markup_escape_text(f"{get('provider_name', '') or ''} · "
                                              f"{(get('description', '') or '')[:200]}"))
                lab.add_css_class("ft-card")
                lab.connect("activate-link", lambda _l, u: (win.on_link(u), True)[1])
                box.append(lab)
        if t.get("statuses"):
            box.append(_section(_("trends_posts")))
            short = win.view.short_ids(t["statuses"])
            for p in t["statuses"]:
                box.append(Card(win.ctx, p.id, p, short_id=short.get(real(p).id)))
        if not any(t.values()):
            box.append(Gtk.Label(label=_("trends_none")))
    win.call(win.view.trends(), got)
    return page


def open_search(win, query):
    """People, tags and posts for what's typed in the sidebar's box; addresses are
    fetched from their home server by mine."""
    query = (query or "").strip()
    if not query:
        return None
    key = "search"
    old = win.extra_tabs.pop(key, None)
    if old is not None:
        win.tabs.remove_page(win.tabs.page_num(old))
    page, box, title = win._new_tab(_("search_title") + ": " + query,
                                    lambda: win.close_extra(key))
    win.extra_tabs[key] = page
    box.append(Gtk.Label(label=_("loading")))

    def got(res):
        while (c := box.get_first_child()) is not None:
            box.remove(c)
        accs = [a for a in res.get("accounts") or () if isinstance(a, Account)]
        tags = [t for t in res.get("hashtags") or () if isinstance(t, Tag)]
        sts = list(res.get("statuses") or ())
        rel = res.get("relations") or {}
        if accs:
            box.append(_section(_("search_people")))
            for a in accs:
                box.append(AccountRow(win, a, rel.get(a.id)))
        if tags:
            box.append(_section(_("trends_tags")))
            for t in tags:
                box.append(TagRow(win, t))
        if sts:
            box.append(_section(_("trends_posts")))
            short = win.view.short_ids(sts)
            for p in sts:
                box.append(Card(win.ctx, p.id, p, short_id=short.get(real(p).id)))
        if not (accs or tags or sts):
            box.append(Gtk.Label(label=_("search_none")))
    win.call(win.view.search(query), got,
             lambda e: title.set_text(_("load_failed", err=e)))
    return page


def open_tag(win, tag):
    """A tag's posts in a tab, newest first, Follow on top, "older" below."""
    tag = tag.lstrip("#")
    key = "tag:" + tag.lower()
    page = win.extra_tabs.get(key)
    if page is not None:
        win.tabs.set_current_page(win.tabs.page_num(page))
        return page
    page, box, _title = win._new_tab("#" + tag, lambda: win.close_extra(key))
    win.extra_tabs[key] = page

    def info(t):
        if isinstance(t, Tag):
            note = Gtk.Label(label=_("tag_info"), xalign=0, wrap=True)
            note.add_css_class("ft-muted")
            box.prepend(note)
            box.prepend(TagRow(win, t, header=True))
    win.call(win.view.tag_info(tag), info, lambda _e: None)
    older = Gtk.Button(label=_("older_down"))
    older.add_css_class("flat")
    last = [None]

    def got(posts):
        if older.get_parent() is not None:
            box.remove(older.get_parent())
        short = win.view.short_ids(posts)
        for p in posts:
            box.append(Card(win.ctx, p.id, p, short_id=short.get(real(p).id)))
        if posts:
            last[0] = posts[-1].id
            older.set_sensitive(True)
            box.append(older)

    def more(_b=None):
        older.set_sensitive(False)
        win.call(win.view.tag_timeline(tag, last[0]), got)
    older.connect("clicked", more)
    more()
    return page
