"""The places of fedtail other than lanes, without a toolkit: what each one holds and
what its buttons do. Silence, lists, search, follow requests, the activity, a hashtag,
whom someone follows, who liked a post, its quotes and versions, a report, scheduled
posts, trends, suggestions, the directory, my server, held-back notifications, my
profile's editor, the help and what's new.

The web page and the terminal draw these as they are (a list of rows with buttons, a
form); so what a place offers and does is decided here once, for both, and the Qt and
GTK windows' own dialogs can be held against it (tests/test_places.py,
tools/behaviour.py).

A place is asked for by name and argument: ``Places(view).page("silence", tab="muted")``
→ :class:`Page`. A button is a :class:`Btn` whose ``act`` is ``(place, key, data)``;
``Places.act(place, key, data, values, confirmed, answer)`` does it and returns an
:class:`Out` — what's left for the interface: a message, "sure?" first, a line to type,
a place, a thread, a profile or an address to open, the editor, "draw it again".

Everything here blocks (it waits for the core's futures): call it from a worker
thread (the web server's request threads, the terminal's workers).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace

from ...i18n import _
from ...model import Account, Post, Share, real
from . import timed
from .placesmore import AccountPlaces, MorePlaces

log = logging.getLogger(__name__)

WAIT = 60  # seconds a server call may take before the place says it failed
POLICY_CHOICES = ("accept", "filter", "drop")  # the server's notification policy


@dataclass(frozen=True)
class Btn:
    """A button: its words, and what it does — ``act = (place, key, data)``."""
    label: str
    act: tuple
    primary: bool = False
    tip: str = ""


@dataclass(frozen=True)
class Row:
    """One row of a place. kind: "post" (data: the Post), "account" (data: the Account),
    "tag" (data: the Tag), "text" (title, line), "heading" (title), "html" (title: HTML
    made safe already — help pages, the server's about), "item" (title, line: a filter,
    a list, a server, a scheduled post…)."""
    kind: str              # also "pre": title is text to keep as it is (monospace)
    title: str = ""
    line: str = ""
    data: object = None
    buttons: tuple = ()
    key: str = ""  # a row's own id (what its buttons act on)


@dataclass(frozen=True)
class Field:
    """A form's field. kind: "line", "text" (several lines), "check", "choice"
    (choices: [(value, words)]), "checks" (several of choices; value: [values])."""
    name: str
    label: str
    value: object = ""
    kind: str = "line"
    choices: tuple = ()
    tip: str = ""  # what it means: under the field, or on hover


@dataclass
class Page:
    """A place as the interface draws it, top to bottom: the hint, the tabs, the rows,
    the form and its button. more: a button for the next page of rows."""
    name: str
    title: str
    arg: str = ""
    hint: str = ""
    tabs: tuple = ()          # ((key, words), …)
    tab: str = ""
    rows: list = field(default_factory=list)
    form: tuple = ()          # (Field, …)
    submit: Btn | None = None
    more: Btn | None = None
    empty: str = ""           # what to say when there are no rows


@dataclass
class Out:
    """What an action leaves to the interface."""
    message: str = ""
    error: str = ""
    confirm: str = ""          # ask "sure?" with these words, then act again confirmed
    ask: tuple = ()            # (title, question, text): a line to type, then act with it
    open: dict | None = None   # {"thread": id} {"account": id} {"url": u} {"back": True}
    #                            {"page": name, "arg": a, "tab": t, "cursor": c, "anchor": x}
    compose: dict | None = None
    refresh: bool = False      # draw the place again
    copy: str = ""             # put this text on the clipboard (with message said)


# the places, in the order of the ≡ menu (title words)
PLACES = {
    "silence": "silence_title", "lists": "lists_header", "search": "search_title",
    "requests": "lane_requests", "activity": "lane_activity", "tags": "followed_tags",
    "scheduled": "scheduled_title", "trends": "trends_title",
    "suggestions": "suggestions_title", "directory": "directory_title",
    "server": "server_info", "filtered": "filtered_title", "profile_edit": "edit_profile",
    "help": "help_title", "news": "help_news", "about": "about",
    "federation": "fed_title", "settings": "settings_title", "issue": "issue_title",
    # opened from somewhere: a post, a person, a tag
    "tag": "tag_info", "people": "people_following", "list_of": "add_to_list",
    "list_people": "list_people_title", "reactions": "who_favourited_by",
    "quotes": "quotes_title", "history": "history_title", "report": "report_title",
    "long_form": "long_form_title", "translate": "translate", "taglanes": "tags_lanes_menu",
    "probe": "probe_tab", "announcements": "announce_title", "profile_info": "profile_title",
    "filter": "filter_edit", "link": "link_posts", "remote": "remote_public",
    "accounts": "accounts", "login": "login_step2",
}
MENU = ("search", "lists", "tags", "silence", "filtered", "scheduled", "requests",
        "activity", "trends", "suggestions", "directory", "remote", "server", "probe",
        "announcements", "profile_edit", "accounts",
        "settings", "help", "news", "about", "issue", "federation")


def _wait(fut):
    return fut.result(timeout=WAIT)


def acc_line(a):
    return f"{a.name or a.username} @{a.handle}" if a else ""


def _acc_id(a):
    return a.id if isinstance(a, Account) else str(a)


class Places(MorePlaces, AccountPlaces):
    """The places on one View.

    Args:
        view: the core's View.
        date: date words (datetime → text); the windows' own format by default.
    """

    def __init__(self, view, date=None):
        self.view = view
        self.date = date or (lambda d: d.astimezone().strftime("%d.%m.%Y %H:%M") if d else "")

    # ---- asking for a place ----------------------------------------------------------
    def page(self, name, arg="", tab="", cursor=""):
        fn = getattr(self, "_p_" + name, None)
        if fn is None or name not in PLACES:
            raise KeyError(name)
        return fn(str(arg or ""), str(tab or ""), str(cursor or ""))

    def menu(self):
        """[(place, words)] for the ≡ menu: those the server can have."""
        sup = self.view.supports
        out = []
        for n in MENU:
            if n == "filtered" and not sup("filtered"):
                continue
            if n == "trends" and not sup("trends"):
                continue
            if n in ("suggestions", "directory") and not sup(n):
                continue
            if n == "announcements" and \
                    (self.view.cfg.get("ui") or {}).get("announcements") == "off":
                continue
            out.append((n, _(PLACES[n])))
        return out

    # ---- doing what a button says ------------------------------------------------------
    def act(self, place, key, data="", values=None, confirmed=False, answer=None):
        fn = getattr(self, f"_a_{place}_{key}", None)
        if fn is None:
            raise KeyError(f"{place}.{key}")
        try:
            return fn(str(data or ""), dict(values or {}), bool(confirmed), answer) or Out()
        except Exception as e:  # noqa: BLE001 — the interface shows what failed
            log.info("place %s.%s: %s", place, key, e.__class__.__name__)
            return Out(error=str(e) or e.__class__.__name__)

    @staticmethod
    def _btn(label, place, key, data="", primary=False, tip=""):
        return Btn(label, (place, key, str(data)), primary, tip)

    # ---- silence: filters, muted, blocked, servers ---------------------------------
    def _p_silence(self, arg, tab, cur):
        page = self._silence(arg, tab, cur)
        if self.view.cfg["ui"].get("arts_mode"):  # as the windows' menu says it
            page.hint = _("tender_arts") + (" · " + page.hint if page.hint else "")
        return page

    def _silence(self, _arg, tab, _cur):
        v = self.view
        tab = tab or "filters"
        tabs = (("filters", _("silence_filters")), ("muted", _("silence_muted")),
                ("blocked", _("silence_blocked")), ("domains", _("tender_domains")))
        page = Page("silence", _("silence_title"), tabs=tabs, tab=tab)
        if tab == "filters":
            page.hint = _("filters_hint")
            for f in _wait(v.filters()):
                words = ", ".join(f.words)
                how = _("filter_hide") if f.action == "hide" else _("filter_warn")
                line = " · ".join(x for x in (how, words, *timed.filter_bits(f)) if x)
                page.rows.append(Row("item", f.title or words, line, key=f.id, buttons=(
                    self._btn(_("filter_edit"), "silence", "filter_edit", f.id),
                    self._btn(_("filter_delete"), "silence", "filter_delete", f.id))))
            ctx = self._filter_contexts()
            page.form = (Field("words", _("filter_words")),
                         Field("action", _("filter_new"), "warn", "choice",
                               (("warn", _("filter_warn")), ("hide", _("filter_hide")))),
                         Field("contexts", "", ["home", "public", "thread", "account"],
                               "checks", ctx),
                         Field("expires", _("filter_for"), "0", "choice",
                               tuple((str(s), label) for s, label in timed.spans()),
                               tip=_("filter_for_q")))
            page.submit = self._btn(_("filter_add"), "silence", "filter_add", primary=True)
            return page
        s = _wait(v.silenced_people())
        if tab == "domains":
            page.hint = _("silence_domains_hint")
            for d in s.domains:
                page.rows.append(Row("item", d, key=d, buttons=(
                    self._btn(_("unblock"), "silence", "undo_domain", d),)))
            return page
        people = s.muted if tab == "muted" else s.blocked
        undo = "unmute" if tab == "muted" else "unblock"
        for a in people:
            page.rows.append(Row("account", acc_line(a), data=a, key=a.id, buttons=(
                self._btn(_(undo), "silence", undo, a.id),)))
        return page

    def _a_silence_filter_add(self, _d, values, _c, _ans):
        words = [x.strip() for x in str(values.get("words", "")).split(",") if x.strip()]
        if not words:
            return Out(error=_("filter_words"))
        how = "hide" if values.get("action") == "hide" else "warn"
        ctx = [c for c in values.get("contexts") or () if isinstance(c, str)] or ["home"]
        try:
            secs = int(str(values.get("expires") or "0"))
        except ValueError:
            secs = 0
        _wait(self.view.add_filter(", ".join(words), words, how, ctx,
                                   expires_in=secs if secs > 0 else None))
        return Out(refresh=True)

    @staticmethod
    def _filter_contexts():
        return tuple((c, _("filter_ctx_" + c)) for c in
                     ("home", "notifications", "public", "thread", "account"))

    def _a_silence_filter_edit(self, fid, _v, _c, _ans):
        return Out(open={"page": "filter", "arg": fid})

    def _filter(self, fid):
        f = next((x for x in _wait(self.view.filters()) if x.id == fid), None)
        if f is None:
            raise LookupError(fid)
        return f

    def _p_filter(self, fid, _tab, _cur):
        """One filter of mine as a form — the windows' "Edit…": its title, words, what it
        does, where, how long from now ("—" keeps the end it has)."""
        f = self._filter(fid)
        page = Page("filter", _("filter_edit_title", title=f.title or ", ".join(f.words)),
                    arg=fid, hint=" · ".join(timed.filter_bits(f)))
        page.form = (
            Field("title", _("filter_title_label"), f.title),
            Field("words", _("filter_words"), ", ".join(f.words)),
            Field("action", _("filter_new").rstrip(":"), f.action, "choice",
                  (("warn", _("filter_warn")), ("hide", _("filter_hide")))),
            Field("contexts", _("filter_where"), list(f.contexts) or ["home"], "checks",
                  self._filter_contexts()),
            Field("expires", _("filter_for"), "", "choice",
                  (("", "—"),) + tuple((str(s), label) for s, label in timed.spans()),
                  tip=_("filter_for_q")))
        page.submit = self._btn(_("save"), "filter", "save", fid, primary=True)
        return page

    def _a_filter_save(self, fid, values, _c, _ans):
        words = [x.strip() for x in str(values.get("words", "")).split(",") if x.strip()]
        if not words and not self._filter(fid).posts:  # a filter of single posts has none
            return Out(error=_("filter_words"))
        ctx = [c for c in values.get("contexts") or () if isinstance(c, str)] or ["home"]
        raw = str(values.get("expires") or "")
        try:
            secs = int(raw) if raw else None  # "" — the end it has stays
        except ValueError:
            secs = None
        title = str(values.get("title") or "").strip() or ", ".join(words)
        _wait(self.view.edit_filter(fid, title=title, words=words,
                                    action="hide" if values.get("action") == "hide" else "warn",
                                    contexts=ctx, expires_in=secs))
        return Out(message=_("filter_saved"), open={"page": "silence", "tab": "filters"})

    def _a_silence_filter_delete(self, fid, _v, _c, _ans):
        _wait(self.view.delete_filter(fid))
        return Out(refresh=True)

    def _a_silence_unmute(self, acc_id, _v, _c, _ans):
        _wait(self.view.mute(acc_id, False))
        return Out(refresh=True)

    def _a_silence_unblock(self, acc_id, _v, _c, _ans):
        _wait(self.view.block(acc_id, False))
        return Out(refresh=True)

    def _a_silence_undo_domain(self, domain, _v, _c, _ans):
        _wait(self.view.block_domain(domain, False))
        return Out(refresh=True)

    # ---- lists ------------------------------------------------------------------------
    def _p_lists(self, _arg, _tab, _cur):
        page = Page("lists", _("lists_header"), empty="—")
        policies = dict(timed.replies_policies())
        for x in self.view.lists:
            line = " · ".join(b for b in (_("list_exclusive") if x.exclusive else "",
                                          policies.get(x.replies, "")) if b)
            page.rows.append(Row("item", x.title, line,
                                 key=x.id, buttons=(
                self._btn(_("list_people"), "lists", "people", x.id),
                self._btn(_("list_rename"), "lists", "rename", x.id),
                self._btn(_("list_exclusive"), "lists", "exclusive", x.id,
                          tip=_("list_exclusive_tip")),
                # whose replies its lane shows: list → followed → none → list
                self._btn(_("replies_policy"), "lists", "replies", x.id,
                          tip=_("replies_policy_tip")),
                self._btn(_("list_delete"), "lists", "delete", x.id),
                # the order of the lists, as the windows' sidebar moves them (shared)
                self._btn("↑ " + _("list_up"), "lists", "move", f"{x.id} -1"),
                self._btn("↓ " + _("list_down"), "lists", "move", f"{x.id} 1"))))
        page.form = (Field("title", _("list_name_q")),
                     Field("exclusive", _("list_exclusive"), False, "check"),
                     Field("replies", _("replies_policy"), "list", "choice",
                           tuple(timed.replies_policies()), tip=_("replies_policy_tip")))
        page.submit = self._btn(_("list_new"), "lists", "new", primary=True)
        return page

    def _a_lists_move(self, data, _v, _c, _ans):
        list_id, _s, step = data.rpartition(" ")
        self.view.move_list(list_id, int(step))
        return Out(refresh=True)

    def _list(self, list_id):
        for x in self.view.lists:
            if x.id == list_id:
                return x
        raise KeyError(list_id)

    def _a_lists_new(self, _d, values, _c, _ans):
        title = str(values.get("title") or "").strip()
        if not title:
            return Out(error=_("list_name_q"))
        policy = str(values.get("replies") or "")
        _wait(self.view.create_list(title, bool(values.get("exclusive")),
                                    replies_policy=policy if policy in
                                    dict(timed.REPLIES_POLICIES) else None))
        return Out(refresh=True, message=_("list_created", title=title))

    def _a_lists_rename(self, list_id, _v, _c, answer):
        x = self._list(list_id)
        if answer is None or not str(answer).strip():
            return Out(ask=(_("list_rename"), _("list_name_q"), x.title))
        _wait(self.view.update_list(list_id, str(answer).strip(), x.exclusive))
        return Out(refresh=True)

    def _a_lists_exclusive(self, list_id, _v, _c, _ans):
        x = self._list(list_id)
        _wait(self.view.update_list(list_id, x.title, not x.exclusive))
        return Out(refresh=True)

    def _a_lists_replies(self, list_id, _v, _c, _ans):
        """The next of whose replies the list shows: list → followed → none."""
        x = self._list(list_id)
        keys = [k for k, _label in timed.REPLIES_POLICIES]
        now = keys.index(x.replies) if x.replies in keys else 0
        nxt = keys[(now + 1) % len(keys)]
        _wait(self.view.update_list(list_id, x.title, x.exclusive, replies_policy=nxt))
        return Out(refresh=True, message=_("replies_policy") + ": " +
                   dict(timed.replies_policies())[nxt])

    def _a_lists_delete(self, list_id, _v, confirmed, _ans):
        x = self._list(list_id)
        if not confirmed:
            return Out(confirm=_("list_delete_q", title=x.title))
        _wait(self.view.delete_list(list_id))
        return Out(refresh=True)

    def _a_lists_people(self, list_id, _v, _c, _ans):
        return Out(open={"page": "list_people", "arg": list_id})

    def _p_list_people(self, list_id, _tab, _cur):
        x = self._list(list_id)
        page = Page("list_people", _("list_people_title", title=x.title), arg=list_id,
                    empty="—")
        got, _next = _wait(self.view.list_people(list_id))
        for a in got.get("accounts") or ():
            page.rows.append(Row("account", acc_line(a), data=a, key=a.id, buttons=(
                self._btn(_("list_take_out"), "list_people", "out", f"{list_id} {a.id}"),)))
        return page

    def _a_list_people_out(self, data, _v, _c, _ans):
        list_id, _s, acc_id = data.partition(" ")
        _wait(self.view.set_in_list(list_id, acc_id, False))
        return Out(refresh=True, message=_("list_removed"))

    def _p_list_of(self, acc_id, _tab, _cur):
        """"Add to list" for someone: every list, ticked where they are."""
        v = self.view
        acc = _wait(v.account(acc_id))
        page = Page("list_of", _("add_to_list"), arg=acc_id, hint=acc_line(acc), empty="—")
        try:  # a server takes into lists only those I follow: said first, as the windows
            rel = _wait(v.relationship(acc_id))
            if rel is not None and not rel.following:
                page.hint += " · " + _("list_follow_first")
        except Exception:  # noqa: BLE001 — not known: said so, the lists all the same
            page.hint += " · " + _("list_checking")
        inside = set(v.lists_of(acc_id) or ())
        for x in v.lists:
            on = x.id in inside
            page.rows.append(Row("item", ("☑ " if on else "☐ ") + x.title, key=x.id,
                                 buttons=(self._btn(_("list_take_out") if on else
                                                    _("add_to_list"), "list_of",
                                                    "toggle", f"{x.id} {acc_id} {int(on)}"),)))
        page.form = (Field("title", _("list_name_q")),)
        page.submit = self._btn(_("list_new"), "list_of", "new", acc_id, primary=True)
        return page

    def _a_list_of_toggle(self, data, _v, _c, _ans):
        list_id, acc_id, on = data.split(" ")
        got = _wait(self.view.set_in_list(list_id, acc_id, on != "1"))
        if got == "pending":  # not followed yet: it goes in once the server lets it
            return Out(refresh=True, message=_("list_pending"))
        return Out(refresh=True, message=_("list_removed" if on == "1" else "list_added"))

    def _a_list_of_new(self, acc_id, values, _c, _ans):
        title = str(values.get("title") or "").strip()
        if not title:
            return Out(error=_("list_name_q"))
        _wait(self.view.create_list(title, False, add=acc_id))
        return Out(refresh=True, message=_("list_created", title=title))

    # ---- search -----------------------------------------------------------------------
    def _p_search(self, q, tab, _cur):
        page = Page("search", _("search_title"), arg=q, hint=_("search_hint"))
        page.form = (Field("q", _("search_placeholder"), q),)
        page.submit = self._btn(_("search_title"), "search", "go", primary=True)
        if not q.strip():
            return page
        got = _wait(self.view.search(q))
        page.empty = _("search_none")
        accounts = got.get("accounts") or []
        tags = got.get("hashtags") or []
        posts = got.get("statuses") or []
        if accounts:
            page.rows.append(Row("heading", _("search_people")))
            rel = got.get("relations") or {}
            for a in accounts:
                page.rows.append(self._person(a, rel.get(a.id)))
        if tags:
            page.rows.append(Row("heading", _("search_tags")))
            for t in tags:
                page.rows.append(self._tag_row(t))
        if posts:
            page.rows.append(Row("heading", _("search_posts")))
            page.rows += [Row("post", data=p, key=p.id) for p in posts]
        return page

    def _a_search_go(self, _d, values, _c, _ans):
        return Out(open={"page": "search", "arg": str(values.get("q") or "").strip()})

    def _person(self, a, rel=None, extra=()):
        """A person's row: open, follow or unfollow."""
        following = bool(rel and (getattr(rel, "following", False) or
                                  getattr(rel, "requested", False)))
        me = self.view.me
        btns = [self._btn(_("tui_profile"), "person", "open", a.id)]
        if not (me and a.id == me.id):
            btns.append(self._btn(_("unfollow") if following else _("follow"), "person",
                                  "unfollow" if following else "follow", a.id,
                                  primary=not following))
        return Row("account", acc_line(a), data=a, key=a.id, buttons=tuple(btns) + tuple(extra))

    def _a_person_open(self, acc_id, _v, _c, _ans):
        return Out(open={"account": acc_id})

    def _a_person_follow(self, acc_id, _v, _c, _ans):
        rel = _wait(self.view.follow(acc_id, True))
        acc = _wait(self.view.account(acc_id))
        return Out(refresh=True, message=_("followed_now", acct="@" + acc.handle)
                   if rel is not None and rel.following else _("follow_asked_list"))

    def _a_person_unfollow(self, acc_id, _v, _c, _ans):
        _wait(self.view.follow(acc_id, False))
        return Out(refresh=True)

    # ---- tags -------------------------------------------------------------------------
    def _tag_row(self, t):
        line = _("tag_people", n=t.people) if getattr(t, "people", 0) else ""
        return Row("tag", "#" + t.name, line, data=t, key=t.name, buttons=(
            self._btn(_("tag_info"), "tag", "open", t.name),
            self._btn(_("tag_unfollow") if t.following else _("tag_follow"), "tag",
                      "unfollow" if t.following else "follow", t.name,
                      tip=_("tag_follow_tip")),
            self._btn(_("tags_lanes_menu"), "tag", "lanes", t.name, tip=_("tags_lanes_tip"))))

    def _p_tags(self, _arg, _tab, _cur):
        page = Page("tags", _("followed_tags"), empty="—")
        for t in _wait(self.view.followed_tags()):
            page.rows.append(self._tag_row(t))
        return page

    def _p_tag(self, name, _tab, cursor):
        name = name.lstrip("#")
        v = self.view
        page = Page("tag", "#" + name, arg=name)
        try:
            t = _wait(v.tag_info(name))
            if t is not None:
                row = self._tag_row(t)
                feature = self._feature_button(name)
                if feature is not None:
                    row = replace(row, buttons=row.buttons + (feature,))
                page.rows.append(row)
        except Exception as e:  # noqa: BLE001 — the posts still show
            log.info("tag info: %s", e.__class__.__name__)
        posts = _wait(v.tag_timeline(name, cursor or None)) or []
        page.rows += [Row("post", data=p, key=p.id) for p in posts]
        if posts and len(posts) >= v.cfg["feed"]["page_size"]:
            page.more = self._btn(_("more"), "tag", "more", f"{name} {real(posts[-1]).id}")
        page.empty = "—"
        return page

    def _a_tag_open(self, name, _v, _c, _ans):
        return Out(open={"page": "tag", "arg": name})

    def _a_tag_more(self, data, _v, _c, _ans):
        name, _s, cursor = data.partition(" ")
        return Out(open={"page": "tag", "arg": name, "cursor": cursor})

    def _feature_button(self, name):
        """"On my profile" ("often writes about") for a tag, or None (no such thing on
        the server, or it didn't say)."""
        if not self.view.supports("featured_tags"):
            return None
        try:
            on = name.lower() in (_wait(self.view.featured_tag_names()) or ())
        except Exception as e:  # noqa: BLE001 — the tag still shows
            log.info("featured tags: %s", e.__class__.__name__)
            return None
        return self._btn(_("tag_unfeature") if on else _("tag_feature"), "tag", "feature",
                         f"{int(not on)} {name}", tip=_("tag_feature_tip"))

    def _a_tag_feature(self, data, _v, _c, _ans):
        on, _s, name = data.partition(" ")
        _wait(self.view.feature_tag(name, on == "1"))
        return Out(refresh=True)

    def _a_tag_lanes(self, name, _v, _c, _ans):
        return Out(open={"page": "taglanes", "arg": name})

    # ---- "Report a bug on GitHub…": a draft to read, then the tracker in the browser --
    def _p_issue(self, _arg, _tab, _cur):
        """The public issue's text (fedtail/issue.py), already scrubbed, to read and
        edit; the button opens GitHub's new-issue page with it — sending is the
        person's own click there."""
        from ... import issue
        page = Page("issue", _("issue_title"), hint=_("issue_check"))
        d = issue.draft(self.view.paths, self.view.cfg, known=self._mine())
        page.form = (Field("body", _("issue_title"), d.body, "text"),)
        page.submit = self._btn(_("issue_open"), "issue", "open", primary=True)
        return page

    def _mine(self):
        """Words that say who this is — the @name and the server — for scrub()."""
        from ...core.merged import full_handle
        name, _s, host = full_handle(getattr(self.view, "_core", self.view)).lstrip(
            "@").partition("@")
        me = getattr(self.view, "me", None)
        return [host, name, str(getattr(me, "name", "") or "")]

    def _a_issue_open(self, _d, values, _c, _ans):
        from ... import issue
        body = issue.scrub(str(values.get("body", "")), self._mine())  # what was typed too
        return Out(open={"url": issue.issue_url(self.view.cfg, "", body)},
                   message=_("issue_opened"))

    # ---- settings: the lines of config.toml (common/settings.py) ---------------------
    def _p_settings(self, query, tab, _cur):
        """A chapter of the settings as a form (tabs: the chapters), or what matches
        `query` in all of them; rows: what differs from the defaults there, each with
        "Default" (the line commented out)."""
        from . import settings
        chapters = settings.model(self.view)
        name = settings.config_file(self.view).name
        page = Page("settings", _("settings_title"), arg=query,
                    hint=_("settings_hint", file=name),
                    tabs=tuple((c.key, f"{c.number}. {c.title}") for c in chapters))
        # the windows' search box and "Open the file", as buttons
        page.rows.append(Row("item", f"🔍 {query}" if query else _("settings_search"), name,
                             key="_tools", buttons=(
                                 self._btn(_("settings_search"), "settings", "find", query),
                                 self._btn(_("settings_open_file"), "settings", "file"))))
        if query:
            options = [o for _c, hits in settings.find(chapters, query) for o in hits]
            page.empty = _("settings_none")
        else:
            ch = next((c for c in chapters if c.key == tab), chapters[0])
            page.tab = ch.key
            options = ch.options
        for o in options:
            if o.changed:
                page.rows.append(Row("item", o.title, f"{o.name} = {o.shown()}", key=o.name,
                                     buttons=(self._btn(
                                         _("settings_reset"), "settings", "reset", o.name,
                                         tip=_("settings_reset_tip",
                                               value=o.default_shown())),)))
        page.form = tuple(self._setting_field(o) for o in options)
        page.submit = self._btn(_("settings_save"), "settings", "save", query, primary=True)
        return page

    @staticmethod
    def _setting_field(o):
        tip = (o.about + "\n" if o.about else "") + o.name
        if not o.changed:  # as the windows say it under the name
            tip += "  ·  " + _("settings_default", value=o.default_shown())
        if o.kind == "bool":
            return Field(o.name, o.title, bool(o.value), "check", tip=tip)
        if o.kind in ("choice", "checks"):
            def words(v, w):
                w = w if len(w) <= 60 else w[:57].rsplit(" ", 1)[0] + "…"
                return w if o.kind == "checks" or w == str(v) else f"{v} — {w}"
            return Field(o.name, o.title, o.value, o.kind,
                         tuple((v, words(v, w)) for v, w in o.choices), tip=tip)
        return Field(o.name, o.title, o.line(), "line", tip=tip)

    def _a_settings_save(self, _query, values, _c, _ans):
        from . import settings
        try:
            changes = settings.changes_of(settings.model(self.view), values)
            if not changes:
                return Out(refresh=True)
            return Out(message=settings.save(self.view, changes), refresh=True)
        except (ValueError, settings.SaveError) as e:
            return Out(error=str(e))

    def _a_settings_find(self, query, _v, _c, answer):
        """Find a setting: by words of its name, title or explanation (common/settings)."""
        if answer is None:
            return Out(ask=(_("settings_title"), _("settings_search"), query))
        return Out(open={"page": "settings", "arg": str(answer).strip()})

    def _a_settings_file(self, _d, _v, _c, _ans):
        """The config itself: the terminal opens it in $EDITOR; the web page copies its
        path (the file is on the machine fedtail runs on)."""
        from . import settings
        return Out(open={"file": str(settings.config_file(self.view))})

    def _a_settings_reset(self, name, _v, _c, _ans):
        from . import settings
        section, _s, key = name.partition(".")
        try:
            return Out(message=settings.save(self.view, {(section, key): settings.UNSET}),
                       refresh=True)
        except settings.SaveError as e:
            return Out(error=str(e))

    def _p_taglanes(self, name, _tab, _cur):
        """"＋ to lanes": the tag as a lane of its own, or into a lane of tags kept in
        the sidebar — the windows' menu (common/taglanes.py), as rows."""
        from ...core import taggroups
        from . import taglanes
        name = name.lstrip("#")
        page = Page("taglanes", "#" + name + " — " + _("tags_lanes_menu").rstrip(" ▾"),
                    arg=name, hint=_("tags_lanes_tip"))
        for key, words, on in taglanes.choices(self.view, name):
            page.rows.append(Row("item", words, "" if on else "✓", key=key, buttons=(
                self._btn(_("tags_save"), "taglane", "add", f"{key} {name}",
                          tip=_("tags_save_tip")),) if on else ()))
        # the lanes of tags there are: saved ones go away from here, the config's — there
        page.rows.append(Row("heading", _("tags_info")))
        for g in getattr(self.view, "tag_groups", None) or []:
            lane = taggroups.lane_name(g)
            title = g.get("name") or taggroups.title(g)
            page.rows.append(Row("item", title, "" if g.get("saved") else _("tags_in_config"),
                                 key="lane:" + lane, buttons=(
                self._btn(_("tags_drop"), "taglane", "drop", lane),) if g.get("saved")
                else ()))
        return page

    def _a_taglane_drop(self, lane, _v, _c, _ans):
        _wait(self.view.drop_tag_group(lane))
        return Out(refresh=True)

    def _a_taglane_add(self, data, _v, _c, _ans):
        from . import taglanes
        key, _s, name = data.partition(" ")
        lane = _wait(taglanes.apply(self.view, key, name))
        title = self.view.lane_title(lane) or lane
        return Out(message=_("tags_saved", tags="#" + name) if key == taglanes.OWN
                   else _("tags_added", tag=name, lane=title), refresh=True)

    def _a_tag_follow(self, name, _v, _c, _ans):
        _wait(self.view.follow_tag(name, True))
        return Out(refresh=True)

    def _a_tag_unfollow(self, name, _v, _c, _ans):
        _wait(self.view.follow_tag(name, False))
        return Out(refresh=True)

    # ---- follow requests, activity -------------------------------------------------------
    def _p_requests(self, _arg, _tab, _cur):
        page = Page("requests", _("lane_requests"), empty=_("no_requests"))
        for a in self.view.follow_requests():
            page.rows.append(Row("account", acc_line(a), data=a, key=a.id, buttons=(
                self._btn(_("approve"), "requests", "yes", a.id, primary=True,
                          tip=_("approve_tip")),
                self._btn(_("reject"), "requests", "no", a.id, tip=_("reject_tip")),
                self._btn(_("tui_profile"), "person", "open", a.id))))
        return page

    def _a_requests_yes(self, acc_id, _v, _c, _ans):
        _wait(self.view.answer_follow(acc_id, True))
        return Out(refresh=True, message=_("approved"))

    def _a_requests_no(self, acc_id, _v, _c, _ans):
        _wait(self.view.answer_follow(acc_id, False))
        return Out(refresh=True, message=_("rejected"))

    def _p_activity(self, _arg, _tab, _cur):
        """Who liked, boosted, followed…: the rows the windows' Activity lane draws
        (common/activity.py), with the same buttons — answer a request, hide a row."""
        from ...model.text import snippet
        from . import activity as act
        v = self.view
        page = Page("activity", _("lane_activity"), empty=_("activity_none"))
        entries = v.activity()
        oldest_first = v.cfg["feed"]["order"] == "oldest_first"
        for r in act.rows(entries, v.activity_seen(), self.date, oldest_first):
            if r.notice:
                who = "⚠ " + r.notice
            else:
                who = ", ".join(a.name or a.username for a in r.people)
                if r.more:
                    who += " " + _("act_more", n=r.more)
            line = r.what + (" · " + r.when if r.when else "")
            if r.post is not None:
                line += " · «" + snippet(r.post, 160) + "»"
            btns = []
            if r.request:
                for e in r.entries:
                    btns.append(self._btn(_("ok_interaction"), "activity", "approve",
                                          e.id, primary=True, tip=_("approve_tip")))
                    btns.append(self._btn(_("no_interaction"), "activity", "refuse",
                                          e.id, tip=_("reject_tip")))
            if r.post is not None:
                btns.append(self._btn(_("thread"), "post", "thread", r.post.id))
            if r.people:
                btns.append(self._btn(_("tui_profile"), "person", "open", r.people[0].id))
            btns.append(self._btn("×", "activity", "dismiss",
                                  " ".join(e.id for e in r.entries),
                                  tip=_("activity_dismiss_tip" if v.can_dismiss_one()
                                        else "activity_hide_tip")))
            page.rows.append(Row("item", ("● " if r.unread else "") + who, line,
                                 key=r.newest_sort, buttons=tuple(btns)))
        if entries:
            page.submit = self._btn(_("activity_clear"), "activity", "clear",
                                    tip=_("activity_clear_tip"))
            page.more = self._btn(_("mark_all_read"), "activity", "seen")
        return page

    def _activity(self, aid):
        for e in self.view.activity():
            if e.id == aid:
                return e
        raise KeyError(aid)

    def _a_activity_seen(self, _d, _v, _c, _ans):
        self.view.mark_activity_seen()
        return Out(refresh=True)

    def _a_activity_approve(self, aid, _v, _c, _ans):
        found = _wait(self.view.answer_interaction(self._activity(aid), True))
        return Out(refresh=True, message=_("approved" if found else "approval_gone"))

    def _a_activity_refuse(self, aid, _v, _c, _ans):
        found = _wait(self.view.answer_interaction(self._activity(aid), False))
        return Out(refresh=True, message=_("rejected" if found else "approval_gone"))

    def _a_activity_dismiss(self, ids, _v, _c, _ans):
        for nid in ids.split():
            _wait(self.view.dismiss_activity(nid))
        return Out(refresh=True)

    def _a_activity_clear(self, _d, _v, confirmed, _ans):
        if not confirmed:
            return Out(confirm=_("activity_clear_q"))
        _wait(self.view.clear_activity())
        return Out(refresh=True)

    def _a_post_thread(self, sid, _v, _c, _ans):
        return Out(open={"thread": sid})

    # ---- people around someone or something -------------------------------------------
    def _p_people(self, arg, tab, cursor):
        acc_id = arg
        tab = tab or "following"
        page = Page("people", _("people_" + tab), arg=acc_id, tab=tab, tabs=(
            ("following", _("people_following")), ("followers", _("people_followers"))),
            empty="—")
        if cursor == "origin":  # the rest, as their own server lists them (feed.remote_people)
            acc = _wait(self.view.account(acc_id))
            got, nxt = _wait(self.view.people_from_origin(acc, tab))
            if got.get("total") is not None:
                page.hint = _("people_origin_total", n=got["total"])
        else:
            got, nxt = _wait(self.view.people(acc_id, tab, cursor or None))
        rel = got.get("relations") or {}
        page.rows += [self._person(a, rel.get(a.id)) for a in got.get("accounts") or ()]
        if nxt:
            page.more = self._btn(_("more"), "people", "more", f"{acc_id} {tab} {nxt}")
        elif cursor != "origin":
            host = self._origin_host(acc_id)
            if host:  # my server knows only part of them: the rest is on theirs
                page.more = self._btn(_("people_more_from", host=host), "people", "more",
                                      f"{acc_id} {tab} origin")
        return page

    def _origin_host(self, acc_id):
        """Someone of another server, whose lists theirs may know better ("" — no)."""
        if not self.view.cfg["feed"].get("remote_people", True):
            return ""
        try:
            acc = _wait(self.view.account(acc_id))
        except Exception:  # noqa: BLE001 — no button then
            return ""
        handle = acc.handle if acc else ""
        return handle.split("@", 1)[1] if "@" in handle else ""

    def _a_people_more(self, data, _v, _c, _ans):
        acc_id, tab, cursor = data.split(" ", 2)
        return Out(open={"page": "people", "arg": acc_id, "tab": tab, "cursor": cursor})

    def _post(self, sid):
        p = self.view.by_id(sid)
        if p is None:
            raise KeyError(sid)
        return p

    def _p_reactions(self, sid, tab, _cur):
        tab = tab or "favourited_by"
        page = Page("reactions", _("who_" + tab), arg=sid, tab=tab, tabs=(
            ("favourited_by", _("who_favourited_by")), ("reblogged_by", _("who_reblogged_by"))),
            empty="—")
        got, _next = _wait(self.view.who_reacted(self._post(sid), tab))
        rel = got.get("relations") or {}
        page.rows += [self._person(a, rel.get(a.id)) for a in got.get("accounts") or ()]
        return page

    def _p_quotes(self, sid, _tab, _cur):
        page = Page("quotes", _("quotes_title"), arg=sid, hint=_("quotes_info"), empty="—")
        posts, _next = _wait(self.view.quotes_of(self._post(sid)))
        page.rows += [Row("post", data=p, key=p.id) for p in posts or ()]
        return page

    def _p_history(self, sid, _tab, _cur):
        page = Page("history", _("history_title"), arg=sid, empty=_("history_none"))
        versions = _wait(self.view.history(self._post(sid)))
        for i, p in enumerate(versions, 1):
            page.rows.append(Row("heading", _("history_version", n=i, when=self.date(p.edited
                                 or p.created))))
            page.rows.append(Row("post", data=p, key=p.id))
        return page

    def _p_long_form(self, sid, _tab, _cur):
        page = Page("long_form", _("long_form_title"), arg=sid, empty=_("long_form_none"))
        from ..richtext import clean
        got = _wait(self.view.long_form(self._post(sid)))
        if isinstance(got, dict):
            if got.get("name"):
                page.rows.append(Row("heading", str(got["name"])))
            when = " — ".join(str(got[k]) for k in ("start", "end") if got.get(k))
            if when or got.get("location"):
                page.rows.append(Row("text", when, str(got.get("location") or "")))
            for key in ("summary", "content"):
                if got.get(key):
                    page.rows.append(Row("html", clean(str(got[key]))))
            if got.get("url"):
                page.rows.append(Row("item", str(got["url"]), key="url", buttons=(
                    self._btn(_("open_browser"), "url", "open", got["url"]),)))
        return page

    def _p_translate(self, sid, _tab, _cur):
        page = Page("translate", _("translate"), arg=sid, empty=_("translate_none"))
        tr = _wait(self.view.translate(self._post(sid)))
        if tr and tr.html:
            page.hint = _("translated_from", lang=tr.lang or "?", provider=tr.provider or "")
            page.rows.append(Row("html", tr.html))
        return page

    # ---- report -----------------------------------------------------------------------
    REASONS = ("spam", "legal", "violation", "other")

    def _p_report(self, sid, _tab, _cur):
        p = self._post(sid)
        page = Page("report", _("report_title", acct=real(p).author.handle), arg=sid)
        page.rows.append(Row("post", data=p, key=p.id))
        form = [Field("category", _("report_why"), "other", "choice",
                      tuple((r, _("report_" + r)) for r in self.REASONS))]
        rules = self._rules()
        if rules:  # "Breaks the server's rules": which (Mastodon asks for at least one)
            form.append(Field("rules", _("report_rules"), [], "checks", rules,
                              tip=_("report_violation")))
        form += [Field("comment", _("report_why"), "", "text"),
                 Field("forward", _("report_forward"), False, "check")]
        page.form = tuple(form)
        page.submit = self._btn(_("report_send"), "report", "send", sid, primary=True)
        return page

    def _rules(self):
        """((rule id, its words), …) of my server ((): it doesn't say)."""
        try:
            info = _wait(self.view.server_info())
        except Exception as e:  # noqa: BLE001 — a report still goes without them
            log.info("report: rules: %s", e.__class__.__name__)
            return ()
        return tuple((rid, text) for rid, (text, _hint)
                     in zip(info.rule_ids, info.rules, strict=False) if rid)

    def _a_report_send(self, sid, values, _c, _ans):
        cat = values.get("category") if values.get("category") in self.REASONS else "other"
        rules = [str(r) for r in values.get("rules") or () if r] if cat == "violation" else []
        if cat == "violation" and not rules and self._rules():
            return Out(error=_("report_rules_need"))
        extra = {"rule_ids": rules} if rules else {}
        _wait(self.view.report(self._post(sid), str(values.get("comment") or ""),
                               bool(values.get("forward")), cat, **extra))
        return Out(message=_("report_sent"), open={"back": True})

    # ---- scheduled, trends, suggestions, directory -------------------------------------
    def _p_scheduled(self, _arg, _tab, _cur):
        page = Page("scheduled", _("scheduled_title"), empty=_("scheduled_none"))
        for s in _wait(self.view.scheduled()):
            page.rows.append(Row("item", self.date(s.at), s.text, key=s.id, buttons=(
                self._btn(_("scheduled_cancel"), "scheduled", "cancel", s.id),)))
        return page

    def _a_scheduled_cancel(self, sid, _v, confirmed, _ans):
        _wait(self.view.cancel_scheduled(sid))
        return Out(refresh=True)

    def _p_trends(self, _arg, tab, _cur):
        tab = tab or "tags"
        page = Page("trends", _("trends_title"), tab=tab, empty=_("trends_none"), tabs=(
            ("tags", _("trends_tags")), ("posts", _("trends_posts")),
            ("links", _("trends_links"))))
        got = _wait(self.view.trends()) or {}
        items = got.get({"posts": "statuses"}.get(tab, tab)) or []
        for x in items:
            if tab == "tags":
                page.rows.append(self._tag_row(x))
            elif tab == "posts":
                page.rows.append(Row("post", data=x, key=x.id))
            else:
                url = x.get("url") if isinstance(x, dict) else getattr(x, "url", "")
                title = x.get("title") if isinstance(x, dict) else getattr(x, "title", "")
                page.rows.append(Row("item", title or url, url, key=url, buttons=(
                    self._btn(_("open_browser"), "url", "open", url),)))
        return page

    def _a_url_open(self, url, _v, _c, _ans):
        return Out(open={"url": url})

    def _p_suggestions(self, _arg, _tab, _cur):
        page = Page("suggestions", _("suggestions_title"), empty="—")
        got, _next = _wait(self.view.suggestions())
        rel = got.get("relations") or {}
        for a in got.get("accounts") or ():
            page.rows.append(self._person(a, rel.get(a.id), extra=(
                self._btn(_("dismiss_suggestion"), "suggestions", "dismiss", a.id),)))
        return page

    def _a_suggestions_dismiss(self, acc_id, _v, _c, _ans):
        _wait(self.view.dismiss_suggestion(acc_id))
        return Out(refresh=True)

    def _p_directory(self, _arg, tab, cursor):
        tab = tab or "all"
        page = Page("directory", _("directory_title"), tab=tab, empty="—", tabs=(
            ("all", _("directory_title")), ("local", _("directory_local"))))
        got = _wait(self.view.directory(int(cursor) if cursor.isdigit() else None,
                                        local=tab == "local"))
        people, nxt = got
        rel = people.get("relations") or {}
        page.rows += [self._person(a, rel.get(a.id)) for a in people.get("accounts") or ()]
        if nxt:
            page.more = self._btn(_("more"), "directory", "more", f"{tab} {nxt}")
        return page

    def _a_directory_more(self, data, _v, _c, _ans):
        tab, _s, cursor = data.partition(" ")
        return Out(open={"page": "directory", "tab": tab, "cursor": cursor})

    # ---- my server, held-back notifications ------------------------------------------
    def _p_server(self, _arg, _tab, _cur):
        from ..richtext import clean
        info = _wait(self.view.server_info())
        page = Page("server", info.title or info.domain or _("server_info"))
        if info.description:
            page.rows.append(Row("html", clean(info.description)))
        if info.contact or info.email:
            page.rows.append(Row("text", _("server_contact"),
                                 " · ".join(x for x in (acc_line(info.contact)
                                                        if info.contact else "", info.email) if x)))
        if info.rules:
            page.rows.append(Row("heading", _("server_rules")))
            for i, r in enumerate(info.rules, 1):
                page.rows.append(Row("text", f"{i}. {r}"))
        if info.about:
            page.rows.append(Row("heading", _("server_about_tab")))
            page.rows.append(Row("html", clean(info.about)))
        if info.privacy:
            page.rows.append(Row("heading", _("server_privacy")))
            page.rows.append(Row("html", clean(info.privacy)))
        if info.terms:
            page.rows.append(Row("heading", _("server_terms")))
            page.rows.append(Row("html", clean(info.terms)))
        page.rows.append(Row("heading", _("server_blocks")))
        if info.blocks:
            for domain, severity, why in info.blocks:
                word = _("server_block_" + severity) if severity in ("suspend", "silence") \
                    else severity
                page.rows.append(Row("text", domain, " · ".join(x for x in (word, why) if x)))
        else:
            page.rows.append(Row("text", _("server_blocks_none")))
        langs = "; ".join(f"{src} → {', '.join(into)}" for src, into in info.translates)
        page.rows.append(Row("text", _("server_translates", langs=langs) if langs
                             else _("server_translates_none")))
        return page

    def _p_filtered(self, _arg, _tab, _cur):
        page = Page("filtered", _("filtered_title"), hint=_("filtered_note"),
                    empty=_("filtered_waiting"))
        got = _wait(self.view.filtered())
        if got is None:
            page.hint = _("filtered_unsupported")
            return page
        policy = got.get("policy") or {}
        if policy:  # what the server holds back — the windows' "What to hold back"
            page.form = tuple(
                Field(key, _("filtered_" + key), policy[key], "choice",
                      tuple((c, _("policy_" + c)) for c in POLICY_CHOICES))
                for key in self.view.FILTER_POLICY if key in policy)
            page.submit = self._btn(_("save") + " · " + _("filtered_policy"), "filtered",
                                    "policy")
        for r in got.get("requests") or ():
            page.rows.append(Row("account", acc_line(r.who),
                                 _("filtered_count", n=r.count) if r.count else "",
                                 data=r.who, key=r.id, buttons=(
                self._btn(_("filtered_accept"), "filtered", "yes", r.id, primary=True),
                self._btn(_("filtered_dismiss"), "filtered", "no", r.id),
                self._btn(_("filtered_profile"), "person", "open", r.who.id))))
        return page

    def _a_filtered_policy(self, _d, values, _c, _ans):
        changes = {k: v for k, v in values.items()
                   if k in self.view.FILTER_POLICY and v in POLICY_CHOICES}
        if changes:
            _wait(self.view.set_filter_policy(**changes))
        return Out(refresh=True, message=_("profile_saved") if changes else "")

    def _a_filtered_yes(self, rid, _v, _c, _ans):
        _wait(self.view.answer_filtered(rid, True))
        return Out(refresh=True)

    def _a_filtered_no(self, rid, _v, _c, _ans):
        _wait(self.view.answer_filtered(rid, False))
        return Out(refresh=True)

    # ---- my profile -------------------------------------------------------------------
    FIELDS = 4

    def _p_profile_edit(self, _arg, _tab, _cur):
        mp = _wait(self.view.my_profile())
        a = mp.account
        fields = list(mp.fields) + [("", "")] * self.FIELDS
        form = [Field("name", _("profile_name"), a.name if a else ""),
                Field("bio", _("profile_bio"), mp.bio or "", "text")]
        for i, (k, val) in enumerate(fields[:self.FIELDS]):
            form.append(Field(f"field{i}_name", _("field_name"), k))
            form.append(Field(f"field{i}_value", _("field_value"), val))
        # new pictures: a file's path in the terminal, a file picked on the web page
        form += [Field("avatar", _("change_avatar"), "", "file"),
                 Field("header", _("change_header") +
                       ("" if a and a.header_static else " (" + _("no_header") + ")"),
                       "", "file")]
        form += [Field("locked", _("profile_locked"), bool(a and a.locked), "check"),
                 Field("bot", _("profile_bot"), bool(a and a.bot), "check"),
                 Field("discoverable", _("profile_discoverable"),
                       bool(a and a.discoverable), "check"),
                 Field("hide_collections", _("profile_hide_collections"),
                       bool(mp.hide_collections), "check"),
                 Field("indexable", _("profile_indexable"), bool(mp.indexable), "check"),
                 Field("attribution_domains", _("profile_attribution"),
                       ", ".join(mp.attribution_domains), tip=_("profile_attribution_tip"))]
        page = Page("profile_edit", _("edit_profile"), hint=_("profile_fields"))
        page.form = tuple(form)
        page.submit = self._btn(_("save"), "profile_edit", "save", primary=True)
        self._tag_suggestions(page)
        return page

    def _tag_suggestions(self, page):
        """The tags I write about most and don't put forward yet: one click each to put
        them on my profile ("Often writes about")."""
        if not self.view.supports("featured_tags"):
            return
        try:
            tags = _wait(self.view.featured_tag_suggestions()) or []
        except Exception as e:  # noqa: BLE001 — a nicety (Mastodon 4.x)
            log.info("featured tag suggestions: %s", e.__class__.__name__)
            return
        if tags:
            page.rows.append(Row("heading", _("featured_suggest")))
        for t in tags:
            page.rows.append(Row("item", "#" + t.name, key=t.name, buttons=(
                self._btn(_("tag_feature"), "tag", "feature", f"1 {t.name}",
                          tip=_("tag_feature_tip")),)))

    def _a_profile_edit_save(self, _d, values, _c, _ans):
        fields = []
        for i in range(self.FIELDS):
            k = str(values.get(f"field{i}_name") or "").strip()
            val = str(values.get(f"field{i}_value") or "").strip()
            if k or val:
                fields.append((k, val))
        pictures = {}
        for key in ("avatar", "header"):
            got = picture_file(values.get(key))
            if got:
                pictures[key] = got
        flags = self._profile_flags(values)
        _wait(self.view.update_profile(
            name=str(values.get("name") or ""), bio=str(values.get("bio") or ""),
            fields=fields, locked=bool(values.get("locked")),
            bot=bool(values.get("bot")), discoverable=bool(values.get("discoverable")),
            **pictures, **flags))
        return Out(message=_("profile_saved"), open={"back": True})

    def _profile_flags(self, values):
        """hide_collections, indexable, attribution_domains — only those changed (a server
        that doesn't know one is never sent it)."""
        try:
            mp = _wait(self.view.my_profile())
        except Exception as e:  # noqa: BLE001 — the rest is saved anyway
            log.info("profile flags: %s", e.__class__.__name__)
            return {}
        out = {}
        for key in ("hide_collections", "indexable"):
            if key in values and bool(values[key]) != bool(getattr(mp, key)):
                out[key] = bool(values[key])
        if "attribution_domains" in values:
            sites = [x.strip() for x in str(values["attribution_domains"] or "")
                     .replace(" ", ",").split(",") if x.strip()]
            if tuple(sites) != tuple(mp.attribution_domains):
                out["attribution_domains"] = sites
        return out

    # ---- who else shared a link (Mastodon 4.3: trending links only) --------------------
    def _p_link(self, url, _tab, cursor):
        from urllib.parse import urlsplit
        host = urlsplit(url).hostname or url
        page = Page("link", _("link_posts_title", host=host), arg=url,
                    empty=_("link_posts_none"))
        posts = _wait(self.view.link_timeline(url, cursor or None)) or []
        page.rows += [Row("post", data=p, key=p.id) for p in posts]
        if posts and len(posts) >= self.view.cfg["feed"]["page_size"]:
            page.more = self._btn(_("more"), "link", "more", f"{real(posts[-1]).id} {url}")
        return page

    # ---- another server's public lane (core.remote_public) ------------------------------
    def _p_remote(self, host, _tab, cursor):
        """The lane of the server named (arg), or the box to name one."""
        page = Page("remote", _("remote_public").rstrip("…"), arg=host,
                    hint=_("remote_public_tip"))
        page.form = (Field("host", _("remote_public_q"), host or ""),)
        page.submit = self._btn(_("remote_public").rstrip("…"), "remote", "open",
                                primary=True)
        if not host:
            return page
        page.title = _("remote_public_title", host=host)
        try:
            got, nxt = _wait(self.view.remote_public(host, cursor or None))
        except LookupError:
            page.empty = _("remote_public_closed", host=host)
            return page
        except ValueError:
            page.empty = _("remote_public_bad", text=host)
            return page
        page.rows += [Row("post", data=p, key=p.id) for p in got or ()]
        if nxt:
            page.more = self._btn(_("more"), "remote", "more", f"{nxt} {host}")
        return page

    def _a_remote_open(self, _d, values, _c, _ans):
        from ...core.remote import server_host
        text = str(values.get("host") or "").strip()
        host = server_host(text)
        if not host:
            return Out(error=_("remote_public_bad", text=text))
        return Out(open={"page": "remote", "arg": host})

    def _a_remote_more(self, data, _v, _c, _ans):
        cursor, _s, host = data.partition(" ")
        return Out(open={"page": "remote", "arg": host, "cursor": cursor})

    def _a_link_more(self, data, _v, _c, _ans):
        cursor, _s, url = data.partition(" ")
        return Out(open={"page": "link", "arg": url, "cursor": cursor})

    # ---- the help, what's new ---------------------------------------------------------
    def _p_help(self, name, _tab, _cur):
        from .. import helpdocs
        from ..mdhtml import markdown_html
        name = name or "index"
        if name.startswith("?"):  # a search through every page (the windows' field)
            return self._help_found(name[1:])
        md = helpdocs.page(None, name)
        page = Page("help", _("help_title"), arg=name)
        page.form = (Field("q", _("help_search")),)
        page.submit = self._btn(_("help_search").rstrip("…"), "help", "search")
        if md is None:
            page.empty = _("help_missing")
            return page
        page.rows.append(Row("html", markdown_html(md, lambda link: help_href(link, name)),
                             data=help_markdown(md, name)))
        return page

    def _help_found(self, query):
        from .. import helpdocs
        hits = helpdocs.search(None, query)
        page = Page("help", _("help_title"), arg="?" + query,
                    hint=_("help_found", n=len(hits)) if hits else _("help_none"))
        page.form = (Field("q", _("help_search"), query),)
        page.submit = self._btn(_("help_search").rstrip("…"), "help", "search")
        deep = False
        for p, _n in hits:
            if p.deep and not deep:  # the deep dive (ref/) under its own heading
                deep = True
                page.rows.append(Row("heading", _("help_deep")))
            page.rows.append(Row("item", p.title, p.about, key=p.name, buttons=(
                self._btn(_("open_action"), "help", "open", p.name),)))
        return page

    def _a_help_search(self, _d, values, _c, _ans):
        q = str(values.get("q") or "").strip()
        return Out(open={"page": "help", "arg": "?" + q if q else "index"})

    def _a_help_open(self, name, _v, _c, _ans):
        return Out(open={"page": "help", "arg": name})

    def _p_news(self, _arg, _tab, _cur):
        return self._p_help("news", "", "")

    def _p_about(self, _arg, _tab, _cur):
        """What fedtail is, which build, on what — the windows' About cards
        (common/about.py), as rows."""
        from ... import version
        from . import about
        a = about.facts(self.view, getattr(self, "toolkit", ""),
                        getattr(self, "toolkit_version", ""))
        page = Page("about", _("about"))
        page.rows.append(Row("heading", "fedtail " + a.version))
        page.rows.append(Row("text", a.tagline))
        for label, value in a.tiles + a.rows:
            page.rows.append(Row("item", value, label, key="about:" + label))
        page.rows.append(Row("text", a.made_by))
        page.rows.append(Row("item", version.HOMEPAGE, key="repo", buttons=(
            self._btn(_("open_browser"), "url", "open", version.HOMEPAGE),)))
        page.rows.append(Row("item", version.AUTHOR, version.AUTHOR_URL, key="author",
                             buttons=(self._btn(_("open_browser"), "url", "open",
                                                version.AUTHOR_URL),)))
        page.rows.append(Row("html", _("made_by")))
        page.rows.append(Row("pre", a.text(), key="facts", buttons=(  # for a bug report
            self._btn(_("about_copy"), "about", "copy", primary=True),)))
        return page

    def _a_about_copy(self, _d, _v, _c, _ans):
        from . import about
        a = about.facts(self.view, getattr(self, "toolkit", ""),
                        getattr(self, "toolkit_version", ""))
        return Out(copy=a.text(), message=_("about_copied"))

    def _p_federation(self, _arg, _tab, _cur):
        """Debug → Federation status: what failed where in this run (fedstatus.py)."""
        from .. import fedstatus
        data = _wait(self.view.federation_status())
        page = Page("federation", _("fed_title"), hint=_("info_head"))
        page.rows.append(Row("pre", fedstatus.text(data), key="status", buttons=(
            self._btn(_("fed_refresh"), "federation", "refresh"),
            self._btn(_("fed_copy"), "federation", "copy"),
            self._btn(_("fed_reset"), "federation", "reset"))))
        return page

    def _a_federation_refresh(self, _d, _v, _c, _ans):
        return Out(refresh=True)

    def _a_federation_copy(self, _d, _v, _c, _ans):
        from .. import fedstatus
        return Out(copy=fedstatus.text(_wait(self.view.federation_status())),
                   message=_("fed_copied"))

    def _a_federation_reset(self, _d, _v, _c, _ans):
        from ...core import health
        health.REC.clear()  # count anew from now, as the windows' button
        log.info("federation status: counting anew")
        return Out(refresh=True)

    def help_target(self, link, current="index"):
        """Where a help page's link goes: Out(open={"page": ("help", name)}) or {"url"}."""
        from .. import helpdocs
        t = helpdocs.resolve(link, None, current)
        if t.page:
            return Out(open={"page": "help", "arg": t.page, "anchor": t.anchor})
        return Out(open={"url": t.url})


def picture_file(value):
    """A picture field's value — a file's path (typed in the terminal; the web page
    uploads the file picked and hands its path on) — checked; None when empty.
    ValueError when there's no such file."""
    import os
    from pathlib import Path
    if not value or not str(value).strip():
        return None
    path = Path(os.path.expanduser(str(value).strip()))
    if not path.is_file():
        raise ValueError(_("load_failed", err=str(path)))
    return str(path)




def help_markdown(md, current):
    """A help page's Markdown with its links made fedtail:help/… or web addresses — for
    a Markdown widget (the terminal's)."""
    import re
    return re.sub(r"\]\(([^)\s]+)\)",
                  lambda m: "](" + (help_href(m.group(1), current) or m.group(1)) + ")", md)


def help_href(link, current):
    """A help page's link as the page shows it: fedtail:help/<page>#anchor inside the
    help, the web address otherwise."""
    from .. import helpdocs
    t = helpdocs.resolve(link, None, current)
    if t.page:
        return f"fedtail:help/{t.page}" + (f"#{t.anchor}" if t.anchor else "")
    return t.url


def for_post(entry):
    """The places a post's ⋯ menu items open (links.py's host methods) by link action."""
    p = real(entry) if isinstance(entry, (Post, Share)) else entry
    return {"history": ("history", p.id), "report": ("report", p.id),
            "quotes": ("quotes", p.id), "favourited_by": ("reactions", p.id),
            "reblogged_by": ("reactions", p.id)}
