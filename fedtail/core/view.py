"""The core as the frontends see it: fedtail.model in, fedtail.model out.

A thin layer over Core (or MergedCore — all accounts in one window): every method
here takes and returns model objects (Post, Share, Account, ThreadItem…), and the
server's JSON never leaves the core. Frontends use this and nothing else of the core
that carries posts or accounts (docs/PROTOCOLS.md, stage 2); a test checks that the
frontends moved to it read no protocol fields.

Methods written out below have model-shaped signatures of their own. Any other method
of the core goes through as it is, its arguments and its answer converted on the way:
a Post, a Share, an Account, a Relationship going in becomes what the core takes, and
what comes back — statuses, accounts, relationships, notifications, thread nodes,
inside lists, tuples and dicts, now or in a future — comes back as the model. Shapes
the model has no type for yet (lists, tags, server info) pass as they are.

Lane entries are converted once per change of the lane (Core.lane_entries caches the
raw list; this caches what it made of that very list), so scrolling and badge counts
cost nothing extra.
"""

from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import fields, replace

from ..model import (
    Account,
    Activity,
    Feature,
    Post,
    Probe,
    Redraft,
    Relationship,
    Scheduled,
    Share,
    ThreadItem,
    real,
)
from ..protocols.mastodon import adapter
from . import links


def _then(fut, fn):
    """A future of fn(what fut gives)."""
    out = Future()

    def done(f):
        if f.cancelled():
            out.cancel()
        elif f.exception() is not None:
            out.set_exception(f.exception())
        else:
            try:
                out.set_result(fn(f.result()))
            except Exception as e:  # noqa: BLE001 — handed to the caller
                out.set_exception(e)
    fut.add_done_callback(done)
    return out


# Core attributes the frontends may use as they are: nothing in them is a server's JSON
PASS = {
    "cfg", "lanes", "lane_by_name", "lane_title", "set_active_lane", "set_state",
    "get_state", "poll_once", "poll_now", "start_polling", "shutdown", "connect",
    "logged_in", "begin_login", "finish_login", "bg", "paths", "posts_only",
    "load_older", "auth", "activity_unread", "mark_activity_seen", "answer_follow",
}
# what never goes through: the server's own data, unconverted
BLOCKED = {"store", "api", "events", "_core"}
RAW_KEEP = 4000  # accounts remembered as the core had them, to hand back unchanged

MEDIA_MAX = 20 * 1024 * 1024  # one picture fetched for a frontend (as Qt's previews)


class View:
    """Model-only face of a Core: see the module's words. BLOCKED attributes are
    refused, so a frontend can't reach the server's data by accident."""

    def __init__(self, core):
        self._core = core
        self._cache = {}   # lane -> (the raw list it was made from, converted)
        self._lock = threading.Lock()
        self._media = None  # pictures' own workers, made when first needed
        self._raw_accounts = OrderedDict()  # (profile, id) -> the core's account dict
        self._raw_activity = OrderedDict()  # (profile, id) -> the core's activity entry

    def __getattr__(self, name):
        if name in PASS:
            return getattr(self._core, name)
        if name in BLOCKED or name.startswith("__"):
            raise AttributeError(f"View has no {name!r} (the server's data stays inside)")
        attr = getattr(self._core, name)
        if not callable(attr):
            return self._out(attr)

        def call(*args, **kw):
            res = attr(*[self._in(a) for a in args], **{k: self._in(v) for k, v in kw.items()})
            return _then(res, self._out) if isinstance(res, Future) else self._out(res)
        call.__name__ = name
        return call

    # ---- converting both ways ------------------------------------------------------
    def _in(self, x):
        """Model objects in what's handed to the core become what the core takes."""
        if isinstance(x, (Post, Share)):
            return self._raw(x)
        if isinstance(x, Account):
            return self._acc_raw(x)
        if isinstance(x, Activity):
            return self._raw_activity.get((x.ref.profile, x.id)) or {"id": x.id}
        if isinstance(x, Relationship):
            return _rel_raw(x)
        if isinstance(x, list):
            return [self._in(v) for v in x]
        if isinstance(x, tuple):
            return tuple(self._in(v) for v in x)
        return x

    def _out(self, x):
        """What the core gives, with every status, account, relationship, notification
        and thread node in it made the model."""
        if isinstance(x, dict):
            kind = _shape(x)
            if kind == "status":
                return self.entry(x)
            if kind == "account":
                return self.acc(x)
            if kind == "relationship":
                return adapter.relationship(x)
            if kind == "activity":
                return self._activity_of(x)
            if kind == "tag":
                return adapter.tag(x)
            return {k: self._out(v) for k, v in x.items()}
        if isinstance(x, list):
            return [self._out(v) for v in x]
        if isinstance(x, tuple):
            return tuple(self._out(v) for v in x)
        if type(x).__name__ == "Node" and hasattr(x, "status"):  # core.threads.Node
            return ThreadItem(real(self.entry(x.status)), x.depth, x.number)
        return x

    def model_of(self, x):
        """What a core call gave (a future's result), made the model — for answers of
        calls made on the core elsewhere (the window's fetchers of people lists)."""
        return self._out(x)

    def raw_account(self, a):
        """The core's account for an Account — for core calls not behind the View yet."""
        return self._acc_raw(a)

    def _acc_raw(self, a):
        """The core's account for a model one: as it came, else rebuilt from it."""
        got = self._raw_accounts.get((a.ref.profile, a.id))
        if got is not None:
            return got
        return {"id": a.id, "acct": a.handle, "username": a.username,
                "display_name": a.name, "url": a.url, "uri": a.uri,
                "avatar": a.avatar, "avatar_static": a.avatar_static, "bot": a.bot,
                "locked": a.locked, "note": a.note, "statuses_count": a.posts,
                "followers_count": a.followers, "following_count": a.following}

    def _activity_of(self, raw):
        """A notification (or a stored activity entry) → Activity; its order is the
        one the core keeps (activity marks "seen up to" by it)."""
        raw = dict(raw)
        acc = raw.get("account")
        if isinstance(acc, dict) and acc.get("_notice") is not None:
            # a server's notice, kept with the account in the store
            key = "moderation_warning" if raw.get("type") == "moderation_warning" else "event"
            raw.setdefault(key, acc["_notice"])
        a = adapter.activity(raw, self._prof(acc if isinstance(acc, dict) else raw))
        if raw.get("sort"):
            a = replace(a, sort=raw["sort"])
        key = (a.ref.profile, a.id)
        self._raw_activity[key] = raw
        self._raw_activity.move_to_end(key)
        while len(self._raw_activity) > RAW_KEEP:
            self._raw_activity.popitem(last=False)
        if isinstance(acc, dict) and acc.get("id"):
            self._remember(acc)
        return a

    def _remember(self, raw):
        key = (self._prof(raw), str(raw.get("id")))
        self._raw_accounts[key] = raw
        self._raw_accounts.move_to_end(key)
        while len(self._raw_accounts) > RAW_KEEP:
            self._raw_accounts.popitem(last=False)

    # ---- converting ----------------------------------------------------------------
    @property
    def profile(self):
        paths = getattr(self._core, "paths", None)
        return getattr(paths, "profile", "") or ""

    def _prof(self, raw):
        return (raw.get("_profile") if isinstance(raw, dict) else None) or self.profile

    def entry(self, raw):
        """A stored status → Post or Share."""
        return adapter.post(raw, self._prof(raw))

    def acc(self, raw):
        if not isinstance(raw, dict):
            return None
        self._remember(raw)
        return adapter.account(raw, self._prof(raw))

    def raw(self, x):
        """The core's own status for a model object or an id — for core methods not
        behind the View yet (docs/PROTOCOLS.md, stage 2). Frontends hand it on and never
        look inside."""
        return self._raw(x)

    def _raw(self, x):
        """The core's status for a model object or an id: from the store, else made up
        from the model (enough for the core's actions: the id and my flags)."""
        sid = x if isinstance(x, str) else x.id
        got = self._core.store.get_status(sid)
        if got is not None:
            return got
        if isinstance(x, str):
            return {"id": x}
        p = real(x)
        return {"id": p.id, "favourited": p.mine.liked, "reblogged": p.mine.shared,
                "bookmarked": p.mine.bookmarked,
                "visibility": adapter.visibility_out(p.visibility),
                "in_reply_to_id": p.reply_to, "account": {"id": p.author.id,
                                                          "acct": p.author.handle}}

    # ---- me ------------------------------------------------------------------------
    @property
    def me(self) -> Account | None:
        me = self._core.me
        return adapter.account(me, self.profile) if me else None

    # ---- lanes ---------------------------------------------------------------------
    def entries(self, lane):
        """[(item id, Post | Share)] oldest → newest, as Core.lane_entries."""
        raw = self._core.lane_entries(lane)
        with self._lock:
            hit = self._cache.get(lane)
            if hit and hit[0] is raw:
                return hit[1]
        out = [(item, self.entry(st)) for item, st in raw]
        with self._lock:
            self._cache[lane] = (raw, out)
        return out

    def unread(self, entries):
        """The ids of the unread among entries (a Share counts by its own id)."""
        return self._core.unread_ids([(None, {"id": e.id}) for e in self._only(entries)])

    @staticmethod
    def _only(entries):
        return [e[1] if isinstance(e, tuple) else e for e in entries]

    def unread_count(self, lane):
        return self._core.unread_count(lane)

    def mark_read(self, ids):
        self._core.mark_read([i if isinstance(i, str) else i.id for i in ids])

    def mark_lane_read(self, lane):
        ids = sorted(self.unread(self.entries(lane)))
        self.mark_read(ids)
        return ids

    def parents(self, entries):
        """{entry id: the Post it answers | "missing" | None (not known yet)}, in two
        queries for the lot."""
        es = self._only(entries)
        got = self._core.parents_for([{"id": e.id, "in_reply_to_id": real(e).reply_to}
                                      for e in es])
        return {k: v if v is None or v == "missing" else real(self.entry(v))
                for k, v in got.items()}

    def parent(self, entry):
        """The Post this one answers, "missing", or None (not known yet / no reply)."""
        return self.parents([entry]).get(entry.id)

    def read_ids(self, ids):
        """Which of these post ids are read."""
        ids = list(ids)
        return self._core.store.read_set(ids) if ids else set()

    def via(self, entry):
        """All accounts in one window: "@me@there" of the account of mine that got this
        post (and acts on it); "" for the main one."""
        tag = entry.ref.profile
        others = getattr(self._core, "others", None)
        return self._core.via(tag) if others and tag in others else ""

    def conversations(self, entries, unread):
        """One group per conversation among lane entries, as the lanes' conversation
        view shows them: [{"key", "top": Post | Share, "members": [ids], "unread": n,
        "last": Post}], the newest conversation last."""
        from .threads import conversations
        raw = [(item, self._raw(e)) for item, e in entries]
        out = []
        for g in conversations(raw, self._core.store.get_status, unread):
            out.append({"key": g["key"], "top": self.entry(g["top"]),
                        "members": [m["id"] for m in g["members"]],
                        "unread": g["unread"], "last": real(self.entry(g["last"]))})
        return out

    def short_ids(self, entries):
        """{post id: '#a3f' alias} (a Share: of the post inside)."""
        return self._core.short_ids([{"id": real(e).id} for e in self._only(entries)])

    def by_id(self, post_id):
        """A stored post by its id (a boost's id gives the post inside), or None."""
        st = self._core.store.get_status(post_id)
        return real(self.entry(st)) if st else None

    def by_alias(self, alias):
        st = self._core.by_alias(alias)
        return real(self.entry(st)) if st else None

    def target(self, alias, number=0):
        """#a3f → that post; #a3f/2 → comment /2 of its thread. Future: Post or None."""
        return _then(self._core.target(alias, number),
                     lambda st: real(self.entry(st)) if st else None)

    def thread(self, post_id):
        """Future: [ThreadItem] in reading order, the root first."""
        def made(nodes):
            return [ThreadItem(real(self.entry(n.status)), n.depth, n.number) for n in nodes]
        return _then(self._core.thread(post_id), made)

    def in_app_html(self, html):
        """HTML (a bio, a profile field) with fediverse links pointing into fedtail."""
        return links.in_app(html)

    def in_app(self, post):
        """The post's HTML with mentions, tags and fediverse links pointing into fedtail
        (fedtail:account/…, fedtail:tag/…, fedtail:resolve/…)."""
        p = real(post)
        return links.in_app(p.text, mentions={u: m.id for m in p.mentions
                                              for u in (m.url, m.uri) if u})

    # ---- people --------------------------------------------------------------------
    def account(self, acc_id):
        return _then(self._core.account(acc_id), self.acc)

    def account_posts(self, acc_id, max_id=None):
        return _then(self._core.account_statuses(acc_id, max_id=max_id),
                     lambda page: [self.entry(st) for st in page or ()])

    def relationship(self, acc_id):
        return _then(self._core.relationship(acc_id), adapter.relationship)

    def follow(self, acc_id, on=True):
        return _then(self._core.follow(acc_id, on), adapter.relationship)

    def find_user(self, handle):
        return _then(self._core.find_user(handle), self.acc)

    def resolve(self, url):
        """Future: the Post or Account behind a web address, or None."""
        def made(found):
            if not found:
                return None
            kind, what = found
            return real(self.entry(what)) if kind == "status" else self.acc(what)
        return _then(self._core.resolve(url), made)

    # ---- acting on posts -----------------------------------------------------------
    def _post_back(self, st):
        return real(self.entry(st)) if isinstance(st, dict) and st.get("id") else None

    def like(self, post):
        """Like or unlike (a toggle). Future: the post as it is now."""
        return _then(self._core.favourite(self._raw(real(post))), self._post_back)

    def share(self, post):
        """Boost or unboost (a toggle). Future: the post as it is now."""
        return _then(self._core.boost(self._raw(real(post))), self._post_back)

    def bookmark(self, post, on=None):
        return _then(self._core.bookmark(self._raw(real(post)), on), self._post_back)

    def vote(self, post, choices):
        """Vote in the post's poll (option indexes). Future: the post with the counts."""
        return _then(self._core.vote(self._raw(real(post)), list(choices)), self._post_back)

    def delete(self, post):
        return self._core.delete(self._raw(real(post)))

    def subscribe(self, post):
        return self._core.subscribe(self._raw(real(post)))

    def unsubscribe(self, post):
        return self._core.unsubscribe(self._raw(real(post)))

    def subscribed(self, post):
        """Is the thread this post is in followed (Point-style)? Not a future."""
        return bool(self._core.subscribed(self._raw(real(post))))

    def thread_quiet(self, post):
        """Is the thread this post is in muted (here, or on the server too)?"""
        quiet = getattr(self._core, "thread_quiet", None)
        return bool(quiet and quiet(self._raw(real(post))))

    def mute_thread(self, post, on=True):
        """Mute (or unmute) the post's thread: on the server when it can, here always.
        Future: the post as it is now."""
        return _then(self._core.mute_thread(self._raw(real(post)), on), self._post_back)

    # ---- activity and follow requests (lanes that are not posts) -------------------
    def activity(self, limit=300):
        """[Activity] newest first: who liked, shared, followed, mentioned…"""
        return [self._activity_of(n) for n in self._core.activity_entries(limit)]

    def activity_seen(self):
        """The sort key up to which activity is seen (Activity.sort above it: new)."""
        return self._core.activity_seen_mark()

    def follow_requests(self):
        """[Account] asking to follow me (as of the last poll)."""
        return [self.acc(a) for a in getattr(self._core, "follow_requests", None) or ()]

    # ---- pictures --------------------------------------------------------------------
    def media_bytes(self, url):
        """Future: a picture's bytes, from the shared disk cache (the Qt window's too) or
        downloaded — without the token, public addresses only (core.remote), at most
        MEDIA_MAX. A frontend that draws pictures itself (the terminal) uses this."""
        with self._lock:
            if self._media is None:
                self._media = ThreadPoolExecutor(max_workers=3,
                                                 thread_name_prefix="fedtail-media")
        return self._media.submit(self._fetch_media, url)

    def _fetch_media(self, url):
        import requests

        from . import remote
        from .api import USER_AGENT
        cache = self._core.paths.cache_dir
        path = cache / hashlib.sha1(url.encode()).hexdigest()
        if path.exists():
            try:
                os.utime(path)  # used now: the cache cleanup keeps it
            except OSError:
                pass
            return path.read_bytes()
        session = requests.Session()
        session.headers["User-Agent"] = USER_AGENT
        with remote.open_url(session, url, timeout=(6, 30), schemes=("https", "http"),
                             own_hosts=self._core._own_hosts()) as r:
            r.raise_for_status()
            kind = (r.headers.get("Content-Type") or "").split(";")[0].strip()
            data = remote.read(r, MEDIA_MAX)
        if kind.startswith("image/"):  # never keep an error page in the shared cache
            try:
                path.write_bytes(data)
            except OSError:
                pass
        return data

    def server_info(self):
        """Future: my server about itself (ServerInfo)."""
        return _then(self._core.server_info(), lambda r: adapter.server_info(r, self.profile))

    def probe_server(self):
        """Future: a Probe — my server asked what it can do (takes a few seconds)."""
        return _then(self._core.probe_server(), _probe)

    def last_probe(self):
        """The last Probe, or None: never asked."""
        got = self._core.last_probe()
        return _probe(got) if got else None

    # ---- writing -------------------------------------------------------------------
    def default_visibility(self):
        return adapter.visibility_in(self._core.default_visibility())

    def reply_visibility(self, parent):
        raw = self._raw(real(parent)) if parent is not None else None
        return adapter.visibility_in(self._core.reply_visibility(raw))

    def post(self, text, visibility, reply_to=None, warning="", language=None, quote=None,
             **kw):
        """A new post or a reply (reply_to, quote: a Post or its id). Future: the Post
        made, or a Scheduled one (scheduled_at given)."""
        def pid(x):
            return None if x is None else x if isinstance(x, str) else real(x).id
        fut = self._core.post(text, adapter.visibility_out(visibility), pid(reply_to), warning,
                              language=language, quote=pid(quote), **kw)

        def made(st):
            if isinstance(st, dict) and st.get("scheduled"):
                return Scheduled(st.get("id") or "", adapter.when(st.get("scheduled_at")))
            return real(self.entry(st)) if isinstance(st, dict) else st
        return _then(fut, made)

    def source(self, post):
        """Future: (text, warning) — what I typed for my post, to edit it."""
        return _then(self._core.source(self._raw(real(post))),
                     lambda d: ((d or {}).get("text") or "",
                                (d or {}).get("spoiler_text") or ""))

    def edit(self, post, text, warning="", **kw):
        """My post corrected. Future: the Post as it is now."""
        return _then(self._core.edit(self._raw(real(post)), text, warning, **kw),
                     self._post_back)

    def redraft(self, post):
        """Delete my post; Future: a Redraft — what it was made of, for a new draft."""
        def made(d):
            return Redraft(text=d.get("text") or "", warning=d.get("cw") or "",
                           visibility=adapter.visibility_in(d.get("visibility") or ""),
                           language=d.get("language") or "",
                           reply_to=d.get("in_reply_to_id"), media=int(d.get("media") or 0))
        return _then(self._core.redraft(self._raw(real(post))), made)

    # ---- events --------------------------------------------------------------------
    def on(self, name, fn):
        """Subscribe to a core event; payloads that carry server objects come as model
        ones: status_updated → Post, me_updated → Account, requests_updated →
        [Account]. Ids and lane maps pass as they are."""
        conv = {"status_updated": lambda st: self._post_back(st),
                "me_updated": lambda me: adapter.account(me, self.profile),
                "requests_updated": lambda accs: [self.acc(a) for a in accs or ()]}.get(name)
        if conv is None:
            self._core.events.on(name, fn)
        else:
            self._core.events.on(name, lambda n, p: fn(n, conv(p)))


def is_entry(x):
    return isinstance(x, (Post, Share))


def _shape(d):
    """What a dict from the core is, by its keys: "status", "account", "relationship",
    "activity" (a notification or a stored activity entry), "tag", or None."""
    if "name" in d and not ("acct" in d or "count" in d or "shortcode" in d) and \
            ("url" in d or "history" in d or "statuses_count" in d or "following" in d):
        return "tag"  # (an emoji reaction has a count, an emoji a shortcode: not tags)
    if "id" not in d:
        return None
    if "account" in d and ("content" in d or "reblog" in d or "media_attachments" in d):
        return "status"
    if "acct" in d and "username" in d:
        return "account"
    if "following" in d and "followed_by" in d:
        return "relationship"
    if "type" in d and "account" in d and ("status" in d or "created_at" in d):
        return "activity"
    return None


def _probe(d):
    from datetime import UTC, datetime
    t = d.get("checked")
    return Probe(datetime.fromtimestamp(t, UTC) if isinstance(t, (int, float)) else None,
                 d.get("software") or "", d.get("version") or "",
                 tuple(Feature(str(k), str(s), str(x or "")) for k, s, x in d.get("items") or ()))


_REL_KEYS = {"showing_shares": "showing_reblogs"}


def _rel_raw(rel):
    """A Relationship as the core's dict (what it reads back: following, note…)."""
    out = {_REL_KEYS.get(f.name, f.name): getattr(rel, f.name) for f in fields(rel)}
    if rel.languages is not None:
        out["languages"] = list(rel.languages)
    return out
