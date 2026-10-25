"""All accounts in one window: several Cores behind the face of one.

The window talks to a MergedCore exactly as to a Core. The main profile's posts
keep their ids; the other accounts' posts, accounts and lists get theirs prefixed
with the profile name ("work~01ABC"), so one id still says everything — which
account received the post, and so which account a reply, a like or a boost goes
from. Their posts also carry "_via" (the account's @handle) for the card to show.

Lanes of the same name are merged (Home of both accounts is one Home); lists of
the other accounts come as lanes of their own. Activity, follow requests, the
command line and new (not reply) posts belong to the main account.
"""

import logging
from concurrent.futures import Future

from . import lanes as lanes_module
from .events import Events
from .model import real
from .threads import Node

log = logging.getLogger(__name__)

SEP = "~"


def full_handle(core):
    """"@name@server" of a core's own account ("" before it has connected)."""
    me = getattr(core, "me", None)
    if not me:
        return ""
    acct = me.get("acct") or me.get("username") or ""
    if "@" not in acct:
        from urllib.parse import urlsplit
        server = (getattr(core, "auth", None) or {}).get("server") or me.get("url") or ""
        host = urlsplit(server if "//" in server else "https://" + server).hostname
        if host:
            acct += "@" + host
    return "@" + acct


class MergedCore:
    def __init__(self, primary, others):
        """others: {profile name: Core}, in the order they should be listed."""
        self.primary = primary
        self.others = dict(others)
        self.events = Events()
        self.store = _Store(self)
        primary.events.on("*", lambda n, p: self.events.emit(n, p))
        for tag, core in self.others.items():
            core.events.on("*", lambda n, p, t=tag: self._from_other(t, n, p))

    # anything not merged is the main account's
    def __getattr__(self, name):
        return getattr(self.primary, name)

    # ---- ids --------------------------------------------------------------------
    def via(self, tag):
        """An account of this window as "@name@server" — whole: the same name on two
        servers must not look like one account (23.10)."""
        return full_handle(self.others[tag]) or tag

    def handle(self, tag):
        """The same for the main account too (tag None or "")."""
        return full_handle(self.primary) if not tag else self.via(tag)

    def post_accounts(self, reply_to=None):
        """[(key, "@name@server")] the editor offers under "From": "" — the main
        account, a tag — another; and the one it starts with (the account that got the
        post replied to, the main one for a new post)."""
        out = [("", self.handle(None))] + [(t, self.via(t)) for t in self.others]
        first = ""
        if reply_to is not None:
            _core, tag, _sid = self.split(reply_to["id"] if isinstance(reply_to, dict)
                                          else reply_to)
            first = tag or ""
        return out, first

    def split(self, x):
        """A (possibly prefixed) id → (core, tag or None, the id on that core)."""
        if isinstance(x, str) and SEP in x:
            tag, _s, rest = x.partition(SEP)
            if tag in self.others:
                return self.others[tag], tag, rest
        return self.primary, None, x

    def _p(self, tag, x):
        return f"{tag}{SEP}{x}" if tag and x else x

    def wrap(self, tag, st):
        """Another account's status in this window's terms (ids prefixed)."""
        if not tag or not isinstance(st, dict):
            return st
        s = dict(st)
        s["id"] = self._p(tag, st.get("id"))
        for k in ("in_reply_to_id", "in_reply_to_account_id"):
            if s.get(k):
                s[k] = self._p(tag, s[k])
        if isinstance(s.get("account"), dict):
            s["account"] = dict(s["account"], id=self._p(tag, s["account"].get("id")))
        if s.get("mentions"):
            s["mentions"] = [dict(m, id=self._p(tag, m.get("id"))) for m in s["mentions"]]
        if isinstance(s.get("reblog"), dict):
            s["reblog"] = self.wrap(tag, s["reblog"])
        s["_via"] = self.via(tag)
        s["_profile"] = tag
        return s

    def own(self, status):
        """(core, tag, the status as that core knows it) for a status in window terms."""
        core, tag, sid = self.split(status["id"] if isinstance(status, dict) else status)
        if tag is None:
            return core, None, status
        got = core.store.get_status(sid)
        return core, tag, got if got is not None else self._unwrap(tag, status)

    def _unwrap(self, tag, st):
        if not isinstance(st, dict):
            return st
        s = {k: v for k, v in st.items() if k not in ("_via", "_profile")}
        cut = len(tag) + len(SEP)
        for k in ("id", "in_reply_to_id", "in_reply_to_account_id"):
            if isinstance(s.get(k), str) and s[k].startswith(tag + SEP):
                s[k] = s[k][cut:]
        if isinstance(s.get("account"), dict):
            a = s["account"].get("id", "")
            s["account"] = dict(s["account"], id=a[cut:] if a.startswith(tag + SEP) else a)
        if isinstance(s.get("reblog"), dict):
            s["reblog"] = self._unwrap(tag, s["reblog"])
        return s

    def _then(self, fut, fn):
        """A future whose result is fn(result of fut)."""
        out = Future()

        def done(f):
            if f.exception() is not None:
                out.set_exception(f.exception())
            else:
                try:
                    out.set_result(fn(f.result()))
                except Exception as e:  # noqa: BLE001 — handed to the caller
                    out.set_exception(e)
        fut.add_done_callback(done)
        return out

    def _wrapped(self, tag, fut):
        return fut if tag is None else self._then(fut, lambda r: self.wrap(tag, r))

    # ---- events from the other accounts -------------------------------------------
    def _from_other(self, tag, name, payload):
        if name == "lanes_updated":
            self.events.emit(name, {self._lane_name(tag, k): [self._p(tag, i) for i in v]
                                    for k, v in payload.items()})
        elif name in ("status_updated",):
            self.events.emit(name, self.wrap(tag, payload))
        elif name == "status_deleted":
            self.events.emit(name, self._p(tag, payload))
        elif name == "read_changed":
            self.events.emit(name, [self._p(tag, i) for i in payload])
        elif name == "arrived":
            self.events.emit(name, [(self._p(tag, a), self._p(tag, b)) for a, b in payload])
        elif name == "thread_grew":
            self.events.emit(name, self._p(tag, payload))
        elif name == "notify":
            items = [(self._lane_name(tag, lane), self.wrap(tag, x)) for lane, x in payload
                     if lane not in ("requests", "activity")]
            if items:
                self.events.emit(name, items)
        elif name in ("parents", "lists_changed", "subs_changed", "sound"):
            self.events.emit(name, payload)
        elif name == "ready":
            self.events.emit("lists_changed", self.lists)
            self.events.emit("lanes_updated", {lane.name: [] for lane in self.lanes})
        elif name == "error":
            self.events.emit(name, f"{self.via(tag)}: {payload}")
        # ready, me_updated, requests and activity of the others stay theirs

    @staticmethod
    def _lane_name(tag, name):
        if lanes_module.is_list(name):
            return lanes_module.LIST_PREFIX + tag + SEP + name[len(lanes_module.LIST_PREFIX):]
        return name

    def _own_lane(self, name):
        """A merged lane name → [(core, tag, its name there)]."""
        if lanes_module.is_list(name):
            core, tag, lid = self.split(name[len(lanes_module.LIST_PREFIX):])
            return [(core, tag, lanes_module.LIST_PREFIX + lid)]
        out = [(self.primary, None, name)]
        out += [(c, t, name) for t, c in self.others.items() if name in c.lane_by_name]
        return out

    # ---- lanes --------------------------------------------------------------------
    @property
    def lists(self):
        out = list(self.primary.lists)
        for tag, core in self.others.items():
            out += [dict(x, id=self._p(tag, x["id"]), title=f"{x['title']} · {self.via(tag)}")
                    for x in core.lists]
        return out

    @property
    def lanes(self):
        out = list(self.primary.lanes)
        for tag, core in self.others.items():
            for lane in core.lanes:
                if lanes_module.is_list(lane.name):
                    out.append(_renamed(lane, self._lane_name(tag, lane.name)))
        return out

    @property
    def lane_by_name(self):
        return {lane.name: lane for lane in self.lanes}

    def lane_title(self, name):
        if lanes_module.is_list(name):
            lid = name[len(lanes_module.LIST_PREFIX):]
            return next((x["title"] for x in self.lists if x["id"] == lid), "?")
        return None

    def lane_entries(self, name):
        parts = self._own_lane(name)
        out, seen = [], set()
        for core, tag, own in parts:
            if own not in core.lane_by_name:
                continue
            for item, st in core.lane_entries(own):
                uri = real(st).get("uri") or real(st).get("id")
                if uri in seen:  # the same post through two accounts: the first one
                    continue
                seen.add(uri)
                out.append((self._p(tag, item), self.wrap(tag, st)))
        if len(parts) > 1 and any(t for _c, t, _n in parts):
            by_time = getattr(self.primary.lane_by_name.get(name), "by_status_time", False)
            out.sort(key=lambda e: (real(e[1]) if by_time else e[1]).get("created_at", ""))
        return out

    def unread_ids(self, entries):
        groups = {}
        for item, st in entries:
            core, tag, sid = self.split(st["id"])
            groups.setdefault(tag, (core, []))[1].append((item, dict(st, id=sid)))
        out = set()
        for tag, (core, own) in groups.items():
            out |= {self._p(tag, i) for i in core.unread_ids(own)}
        return out

    def unread_count(self, name):
        return len(self.unread_ids(self.lane_entries(name)))

    def fresh_count(self, name):
        """"Of them new": every account's share of the lane's last update."""
        return sum(core.fresh_count(own) for core, _t, own in self._own_lane(name)
                   if own in core.lane_by_name or own in ("activity", "requests"))

    def calm(self, name):
        parts = self._own_lane(name)
        return parts[0][0].calm(parts[0][2]) if parts else 0

    def set_calm(self, name, minutes):
        for core, _t, own in self._own_lane(name):
            core.set_calm(own, minutes)

    def set_slow(self, minutes):
        """Slow mode for every account of the window: one pace for all."""
        for core in [self.primary, *self.others.values()]:
            core.set_slow(minutes)

    def mark_read(self, status_ids):
        groups = {}
        for x in status_ids:
            core, tag, sid = self.split(x)
            groups.setdefault(tag, (core, []))[1].append(sid)
        for _tag, (core, ids) in groups.items():
            core.mark_read(ids)

    def set_active_lane(self, name):
        for core, _tag, own in self._own_lane(name) if name else []:
            core.set_active_lane(own)
        if not name:
            for core in [self.primary, *self.others.values()]:
                core.set_active_lane(None)

    def set_active_lanes(self, names):
        per = {id(c): (c, []) for c in [self.primary, *self.others.values()]}
        for name in names or ():
            for core, _tag, own in self._own_lane(name):
                per[id(core)][1].append(own)
        for core, own in per.values():
            core.set_active_lanes(own)

    def load_older(self, name):
        futs = [core.load_older(own) for core, _t, own in self._own_lane(name)
                if own in core.lane_by_name]
        return self._then(futs[0], lambda n: n) if len(futs) == 1 else \
            self.primary.submit(lambda: sum(f.result() for f in futs))

    # ---- what cards need ----------------------------------------------------------
    def _by_core(self, statuses):
        groups = {}
        for st in statuses:
            core, tag, own = self.own(st)
            groups.setdefault(tag, (core, []))[1].append(own)
        return groups

    def parents_for(self, statuses):
        out = {}
        for tag, (core, own) in self._by_core(statuses).items():
            for k, v in core.parents_for(own).items():
                out[self._p(tag, k)] = self.wrap(tag, v) if isinstance(v, dict) else v
        return out

    def parent_of(self, status):
        core, tag, own = self.own(status)
        p = core.parent_of(own)
        return self.wrap(tag, p) if isinstance(p, dict) else p

    def ensure_parents(self, statuses):
        for _tag, (core, own) in self._by_core(statuses).items():
            core.ensure_parents(own)

    def my_replies(self, statuses):
        out = {}
        for tag, (core, own) in self._by_core(statuses).items():
            for k, v in core.my_replies(own).items():
                out[self._p(tag, k)] = [self.wrap(tag, x) for x in v]
        return out

    def check_my_replies(self, statuses):
        for _tag, (core, own) in self._by_core(statuses).items():
            core.check_my_replies(own)

    def short_ids(self, statuses):
        # #abc names posts of the main account only (the command line is its)
        return self.primary.short_ids([s for s in statuses if self.split(s["id"])[1] is None])

    # ---- actions on a post go from the account that received it ---------------------
    def _act(self, method, status, *a, **kw):
        core, tag, own = self.own(status)
        return self._wrapped(tag, getattr(core, method)(own, *a, **kw))

    def favourite(self, status):
        return self._act("favourite", status)

    def boost(self, status, *a, **kw):
        return self._act("boost", status, *a, **kw)

    def bookmark(self, status, on=None):
        return self._act("bookmark", status, on)

    def vote(self, status, choices):
        return self._act("vote", status, choices)

    def refresh_poll(self, status):
        return self._act("refresh_poll", status)

    def edit(self, status, *a, **kw):
        return self._act("edit", status, *a, **kw)

    def delete(self, status):
        core, _tag, own = self.own(status)
        return core.delete(own)

    def report(self, status, *a, **kw):
        """To the moderators of the server of the account that has the post."""
        core, _tag, own = self.own(status)
        return core.report(own, *a, **kw)

    def source(self, status):
        core, _tag, own = self.own(status)
        return core.source(own)

    def history(self, status):
        core, tag, own = self.own(status)
        return self._then(core.history(own), lambda v: [self.wrap(tag, x) for x in v or []])

    def subscribed(self, status):
        core, _tag, own = self.own(status)
        return core.subscribed(own)

    def subscribe(self, status):
        core, _tag, own = self.own(status)
        return core.subscribe(own)

    def thread_quiet(self, status):
        core, _tag, own = self.own(status)
        return core.thread_quiet(own)

    def unsubscribe(self, status):
        core, _tag, own = self.own(status)
        return core.unsubscribe(own)

    def reply_visibility(self, status):
        if status is None:
            return self.primary.reply_visibility(None)
        core, _tag, own = self.own(status)
        return core.reply_visibility(own)

    def post(self, text, visibility, reply_to=None, *a, account=None, **kw):
        """account: "" — the main one, a tag — another (the editor's "From"); None — the
        account that got the post replied to (the main one for a new post). From another
        account than that, the post replied to (and a quote) is looked up on its server
        first; the draft, kept by this window's main account, goes once it's out."""
        core, tag, rid = self.split(reply_to) if reply_to else (self.primary, None, None)
        if account is None or (account or None) == tag:
            return self._wrapped(tag, core.post(text, visibility, rid, *a, **kw))
        new_tag = account or None
        target = self.primary if new_tag is None else self.others[new_tag]
        draft = kw.pop("draft_key", None)
        quote = kw.pop("quote", None)

        def job():
            there = self._lookup(reply_to, target, self.handle(new_tag)) if reply_to else None
            q = self._lookup(quote, target, self.handle(new_tag)) if quote else None
            st = target.post(text, visibility, there["id"] if there else None, *a,
                             quote=q["id"] if q else None, **kw).result()
            if draft:
                self.primary.store.delete_draft(draft)
            return self.wrap(new_tag, st)
        return self.primary.bg.submit(job)

    def _lookup(self, status, target, who):
        """The post (an id or a dict in window terms) as target's server has it: by its
        ActivityPub id, then by its web address (GoToSocial and kin find a post by one
        and not the other). LookupError, said plainly, when neither finds it."""
        from ..i18n import _
        from .model import real
        if not isinstance(status, dict):
            core, tag, sid = self.split(status)
            got = core.store.get_status(sid)
            status = self.wrap(tag, got) if got is not None else {"id": status}
        _core, _mine, own = self.own(status)
        if _core is target and isinstance(own, dict) and own.get("id"):
            return own
        post = real(own) if isinstance(own, dict) else {}
        ways = list(dict.fromkeys(x for x in (post.get("uri"), post.get("url")) if x))
        for q in ways:
            try:
                found = target.api.search(q, kind="statuses", resolve=True, limit=5)
            except Exception as e:  # noqa: BLE001 — the next way, or "not found"
                log.info("as %s: %s: %s", who, q, e)
                continue
            st = next(iter((found or {}).get("statuses") or []), None)
            if st is not None:
                target.store.put_statuses([st])
                return st
        raise LookupError(_("act_as_none", acct=who))

    def hide_post(self, status):
        core, _tag, own = self.own(status)
        return core.hide_post(own)

    def unhide_post(self, status):
        core, _tag, own = self.own(status)
        return core.unhide_post(own)

    def thread(self, sid):
        core, tag, own = self.split(sid)
        if tag is None:
            return core.thread(own)
        return self._then(core.thread(own), lambda nodes: [
            Node(self.wrap(tag, n.status), n.depth, n.number) for n in nodes])

    # ---- the same post from another account (ui.act_as) ------------------------------
    def act_accounts(self, status):
        """[(tag, "@acct")]: the accounts that could act on this post besides the one that
        received it (tag None is this window's own account)."""
        _core, mine, _own = self.own(status)
        out = [] if mine is None else [(None, self.handle(None))]
        return out + [(t, self.via(t)) for t in self.others if t != mine]

    def act_as(self, status, tag, action):
        """Like ("fav"), boost ("boost") or find for a reply ("find") the post from
        another account: it is looked up on that account's server by its address, and
        the action goes from there. The result is the post in this window's terms."""
        from .model import real
        target = self.primary if tag is None else self.others[tag]
        who = self.handle(tag)

        def job():
            st = self._lookup(status, target, who)
            if action == "fav" and not real(st).get("favourited"):
                st = target.favourite(st).result()
            elif action == "boost" and not real(st).get("reblogged"):
                st = target.boost(st).result()
            return self.wrap(tag, st)
        return self.primary.bg.submit(job)

    # ---- people of another account: through that account ---------------------------
    def _acc(self, method, acc_id, *a, **kw):
        core, tag, own = self.split(acc_id)
        fut = getattr(core, method)(own, *a, **kw)
        if tag is None:
            return fut
        return self._then(fut, lambda r: self._wrap_any(tag, r))

    def _wrap_any(self, tag, r):
        if isinstance(r, list):
            return [self.wrap(tag, x) if isinstance(x, dict) and "content" in x else x
                    for x in r]
        if isinstance(r, dict) and "acct" in r and "id" in r:
            return dict(r, id=self._p(tag, r["id"]))
        return r

    # ---- 0.11 (core/social.py): each on the account the post or person came by ------
    def _people(self, tag, got):
        """({accounts, relations, …}, next) of another account, ids prefixed."""
        res, nxt = got
        if tag is None:
            return got
        res = dict(res, accounts=[dict(a, id=self._p(tag, a["id"])) for a in res["accounts"]],
                   relations={self._p(tag, k): v for k, v in res["relations"].items()})
        return res, nxt

    def who_reacted(self, status, kind, max_id=None):
        core, tag, own = self.own(status)
        return self._then(core.who_reacted(own, kind, max_id), lambda r: self._people(tag, r))

    def who_reacted_from_origin(self, status, kind, have_ids=(), limit=40):
        core, tag, own = self.own(status)
        have = [self.split(i)[2] for i in have_ids]
        return self._then(core.who_reacted_from_origin(own, kind, have, limit),
                          lambda r: self._people(tag, r))

    def mute_thread(self, status, on=True):
        return self._act("mute_thread", status, on)

    def quotes_of(self, status, max_id=None):
        core, tag, own = self.own(status)
        return self._then(core.quotes_of(own, max_id),
                          lambda r: ([self.wrap(tag, s) for s in r[0]], r[1]))

    def revoke_quote(self, my_status, quoting):
        core, tag, mine = self.own(my_status)
        _c, _t, theirs = self.own(quoting)
        return self._wrapped(tag, core.revoke_quote(mine, theirs))

    def remove_follower(self, acc_id):
        return self._acc("remove_follower", acc_id)

    def endorse(self, acc_id, on=True):
        return self._acc("endorse", acc_id, on)

    def familiar(self, acc_id):
        core, tag, own = self.split(acc_id)
        return self._then(core.familiar(own),
                          lambda r: [dict(a, id=self._p(tag, a["id"])) for a in r])

    def account(self, acc_id):
        return self._acc("account", acc_id)

    def relationship(self, acc_id):
        return self._acc("relationship", acc_id)

    def follow(self, acc_id, on=True):
        return self._acc("follow", acc_id, on)

    def mute(self, acc_id, on=True, **kw):
        return self._acc("mute", acc_id, on, **kw)

    def block(self, acc_id, on=True):
        return self._acc("block", acc_id, on)

    def account_statuses(self, acc_id, max_id=None, show="all"):
        core, tag, own = self.split(acc_id)
        _c, _t, mid = self.split(max_id) if max_id else (None, None, None)
        return self._then(core.account_statuses(own, mid, show=show),
                          lambda page: [self.wrap(tag, s) for s in page])

    def followed_among(self, accounts):
        if not accounts:
            return self.primary.followed_among([])
        core, tag, _x = self.split(accounts[0]["id"])
        own = [dict(a, id=self.split(a["id"])[2]) for a in accounts]
        return self._then(core.followed_among(own), lambda r: [
            dict(a, id=self._p(tag, a["id"])) for a in r])

    def lists_of(self, acc_id):
        core, tag, own = self.split(acc_id)
        return {self._p(tag, x) for x in core.lists_of(own)}

    def set_in_list(self, list_id, acc_id, on):
        core, _tag, lid = self.split(list_id)
        return core.set_in_list(lid, self.split(acc_id)[2], on)

    # ---- the whole family ------------------------------------------------------
    def connect(self):
        for tag, core in self.others.items():
            if core.logged_in:
                # each one polls once it's connected; one that can't stays quiet
                core.connect().add_done_callback(
                    lambda f, c=core, t=tag: c.start_polling() if f.exception() is None
                    else log.warning("merge: %s didn't connect: %s", t, f.exception()))
        return self.primary.connect()

    def start_polling(self):
        self.primary.start_polling()  # the others start when they've connected

    def poll_now(self):
        for core in [self.primary, *self.others.values()]:
            core.poll_now()

    def shutdown(self):
        for core in [*self.others.values(), self.primary]:
            core.shutdown()

    def pause_polling(self, on=True):
        """A phone's app out of sight: every account's rounds stop, and come back."""
        for core in [self.primary, *self.others.values()]:
            core.pause_polling(on)

    def poll_once(self):
        """One round of every connected account, here and now (a phone's round in the
        background, the poller paused); one that fails doesn't stop the rest."""
        for tag, core in self.others.items():
            if core.logged_in and core.me is not None:
                try:
                    core.poll_once()
                except Exception as e:  # noqa: BLE001 — the others still get their round
                    log.warning("merge: %s's round failed: %s", tag, e)
        return self.primary.poll_once()


class _Store:
    """The bits of the store the window reads, routed by id."""

    def __init__(self, merged):
        self.m = merged

    def get_status(self, sid):
        core, tag, own = self.m.split(sid)
        return self.m.wrap(tag, core.store.get_status(own))

    def read_set(self, ids):
        out = set()
        groups = {}
        for x in ids:
            core, tag, own = self.m.split(x)
            groups.setdefault(tag, (core, []))[1].append(own)
        for tag, (core, own) in groups.items():
            out |= {self.m._p(tag, i) for i in core.store.read_set(own)}
        return out

    def __getattr__(self, name):
        return getattr(self.m.primary.store, name)


def _renamed(lane, name):
    from dataclasses import replace
    return replace(lane, name=name)
