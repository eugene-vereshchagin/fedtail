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
from dataclasses import dataclass, field

from ...i18n import _
from ...model import Account, Post, Share, real

log = logging.getLogger(__name__)

WAIT = 60  # seconds a server call may take before the place says it failed


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


# the places, in the order of the ≡ menu (title words)
PLACES = {
    "silence": "silence_title", "lists": "lists_header", "search": "search_title",
    "requests": "lane_requests", "activity": "lane_activity", "tags": "followed_tags",
    "scheduled": "scheduled_title", "trends": "trends_title",
    "suggestions": "suggestions_title", "directory": "directory_title",
    "server": "server_info", "filtered": "filtered_title", "profile_edit": "edit_profile",
    "help": "help_title", "news": "help_news", "about": "about",
    "federation": "fed_title",
    # opened from somewhere: a post, a person, a tag
    "tag": "tag_info", "people": "people_following", "list_of": "add_to_list",
    "list_people": "list_people_title", "reactions": "who_favourited_by",
    "quotes": "quotes_title", "history": "history_title", "report": "report_title",
    "long_form": "long_form_title", "translate": "translate",
}
MENU = ("search", "lists", "tags", "silence", "filtered", "scheduled", "requests",
        "activity", "trends", "suggestions", "directory", "server", "profile_edit",
        "help", "news", "about", "federation")


def _wait(fut):
    return fut.result(timeout=WAIT)


def acc_line(a):
    return f"{a.name or a.username} @{a.handle}" if a else ""


def _acc_id(a):
    return a.id if isinstance(a, Account) else str(a)


class Places:
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
    def _p_silence(self, _arg, tab, _cur):
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
                page.rows.append(Row("item", f.title or words, f"{how} · {words}", key=f.id,
                                     buttons=(self._btn(_("filter_delete"), "silence",
                                                        "filter_delete", f.id),)))
            ctx = tuple((c, _("filter_ctx_" + c)) for c in
                        ("home", "notifications", "public", "thread", "account"))
            page.form = (Field("words", _("filter_words")),
                         Field("action", _("filter_new"), "warn", "choice",
                               (("warn", _("filter_warn")), ("hide", _("filter_hide")))),
                         Field("contexts", "", ["home", "public", "thread", "account"],
                               "checks", ctx))
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
        _wait(self.view.add_filter(", ".join(words), words, how, ctx))
        return Out(refresh=True)

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
        for x in self.view.lists:
            page.rows.append(Row("item", x.title, _("list_exclusive") if x.exclusive else "",
                                 key=x.id, buttons=(
                self._btn(_("list_people"), "lists", "people", x.id),
                self._btn(_("list_rename"), "lists", "rename", x.id),
                self._btn(_("list_exclusive"), "lists", "exclusive", x.id,
                          tip=_("list_exclusive_tip")),
                self._btn(_("list_delete"), "lists", "delete", x.id))))
        page.form = (Field("title", _("list_name_q")),
                     Field("exclusive", _("list_exclusive"), False, "check"))
        page.submit = self._btn(_("list_new"), "lists", "new", primary=True)
        return page

    def _list(self, list_id):
        for x in self.view.lists:
            if x.id == list_id:
                return x
        raise KeyError(list_id)

    def _a_lists_new(self, _d, values, _c, _ans):
        title = str(values.get("title") or "").strip()
        if not title:
            return Out(error=_("list_name_q"))
        _wait(self.view.create_list(title, bool(values.get("exclusive"))))
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
        _wait(self.view.set_in_list(list_id, acc_id, on != "1"))
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
                      tip=_("tag_follow_tip"))))

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
                page.rows.append(self._tag_row(t))
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
        got, nxt = _wait(self.view.people(acc_id, tab, cursor or None))
        rel = got.get("relations") or {}
        page.rows += [self._person(a, rel.get(a.id)) for a in got.get("accounts") or ()]
        if nxt:
            page.more = self._btn(_("more"), "people", "more", f"{acc_id} {tab} {nxt}")
        return page

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
        page.form = (Field("category", _("report_why"), "other", "choice",
                           tuple((r, _("report_" + r)) for r in self.REASONS)),
                     Field("comment", _("report_why"), "", "text"),
                     Field("forward", _("report_forward"), False, "check"))
        page.submit = self._btn(_("report_send"), "report", "send", sid, primary=True)
        return page

    def _a_report_send(self, sid, values, _c, _ans):
        cat = values.get("category") if values.get("category") in self.REASONS else "other"
        _wait(self.view.report(self._post(sid), str(values.get("comment") or ""),
                               bool(values.get("forward")), cat))
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
        return page

    def _p_filtered(self, _arg, _tab, _cur):
        page = Page("filtered", _("filtered_title"), hint=_("filtered_note"),
                    empty=_("filtered_waiting"))
        got = _wait(self.view.filtered())
        if got is None:
            page.hint = _("filtered_unsupported")
            return page
        for r in got.get("requests") or ():
            page.rows.append(Row("account", acc_line(r.who),
                                 _("filtered_count", n=r.count) if r.count else "",
                                 data=r.who, key=r.id, buttons=(
                self._btn(_("filtered_accept"), "filtered", "yes", r.id, primary=True),
                self._btn(_("filtered_dismiss"), "filtered", "no", r.id),
                self._btn(_("filtered_profile"), "person", "open", r.who.id))))
        return page

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
        form += [Field("locked", _("profile_locked"), bool(a and a.locked), "check"),
                 Field("bot", _("profile_bot"), bool(a and a.bot), "check"),
                 Field("discoverable", _("profile_discoverable"),
                       bool(a and a.discoverable), "check")]
        page = Page("profile_edit", _("edit_profile"), hint=_("profile_fields"))
        page.form = tuple(form)
        page.submit = self._btn(_("save"), "profile_edit", "save", primary=True)
        return page

    def _a_profile_edit_save(self, _d, values, _c, _ans):
        fields = []
        for i in range(self.FIELDS):
            k = str(values.get(f"field{i}_name") or "").strip()
            val = str(values.get(f"field{i}_value") or "").strip()
            if k or val:
                fields.append((k, val))
        _wait(self.view.update_profile(
            name=str(values.get("name") or ""), bio=str(values.get("bio") or ""),
            fields=fields, locked=bool(values.get("locked")), bot=bool(values.get("bot")),
            discoverable=bool(values.get("discoverable"))))
        return Out(message=_("profile_saved"), open={"back": True})

    # ---- the help, what's new ---------------------------------------------------------
    def _p_help(self, name, _tab, _cur):
        from .. import helpdocs
        from ..mdhtml import markdown_html
        name = name or "index"
        md = helpdocs.page(None, name)
        page = Page("help", _("help_title"), arg=name)
        if md is None:
            page.empty = _("help_missing")
            return page
        page.rows.append(Row("html", markdown_html(md, lambda link: help_href(link, name)),
                             data=help_markdown(md, name)))
        return page

    def _p_news(self, _arg, _tab, _cur):
        return self._p_help("news", "", "")

    def _p_about(self, _arg, _tab, _cur):
        """What fedtail is, which build, who made it — the windows' About, in words."""
        import platform

        from ... import version
        from ...model.text import html_to_text
        info = version.info()
        page = Page("about", _("about"))
        page.rows.append(Row("heading", "fedtail " + info["version"]))
        tagline = html_to_text(_("about_text", version=info["version"])).split("\n")[-1]
        page.rows.append(Row("text", tagline.strip()))
        if info.get("commit"):
            page.rows.append(Row("text", _("about_build", commit=info["commit"],
                                           date=info["date"])))
        page.rows.append(Row("text", "Python " + platform.python_version()))
        page.rows.append(Row("text", _("made_by_long")))
        page.rows.append(Row("item", version.HOMEPAGE, key="repo", buttons=(
            self._btn(_("open_browser"), "url", "open", version.HOMEPAGE),)))
        page.rows.append(Row("item", version.AUTHOR, version.AUTHOR_URL, key="author",
                             buttons=(self._btn(_("open_browser"), "url", "open",
                                                version.AUTHOR_URL),)))
        return page

    def _p_federation(self, _arg, _tab, _cur):
        """Debug → Federation status: what failed where in this run (fedstatus.py)."""
        from .. import fedstatus
        data = _wait(self.view.federation_status())
        page = Page("federation", _("fed_title"))
        page.rows.append(Row("pre", fedstatus.text(data)))
        return page

    def help_target(self, link, current="index"):
        """Where a help page's link goes: Out(open={"page": ("help", name)}) or {"url"}."""
        from .. import helpdocs
        t = helpdocs.resolve(link, None, current)
        if t.page:
            return Out(open={"page": "help", "arg": t.page, "anchor": t.anchor})
        return Out(open={"url": t.url})


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
