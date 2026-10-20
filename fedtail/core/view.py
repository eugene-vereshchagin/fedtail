"""The core as the frontends see it: fedtail.model in, fedtail.model out.

A thin layer over Core (or MergedCore — all accounts in one window): every method
here takes and returns model objects (Post, Share, Account, ThreadItem…), and the
server's JSON never leaves the core. Frontends use this and nothing else of the core
that carries posts or accounts (docs/PROTOCOLS.md, stage 2); a test checks that the
frontends moved to it read no protocol fields.

Lane entries are converted once per change of the lane (Core.lane_entries caches the
raw list; this caches what it made of that very list), so scrolling and badge counts
cost nothing extra.
"""

from __future__ import annotations

import threading
from concurrent.futures import Future

from ..model import Account, Post, Share, ThreadItem, real
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
    "load_older", "auth",
}


class View:
    """Model-only face of a Core. Unknown attributes are refused, so a frontend can't
    reach the raw core by accident; PASS lists what goes through unchanged."""

    def __init__(self, core):
        self._core = core
        self._cache = {}   # lane -> (the raw list it was made from, converted)
        self._lock = threading.Lock()

    def __getattr__(self, name):
        if name in PASS:
            return getattr(self._core, name)
        raise AttributeError(f"View has no {name!r} (a raw core attribute?)")

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
        return adapter.account(raw, self._prof(raw)) if isinstance(raw, dict) else None

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
        """{entry id: the Post it answers | "missing" | None (not known yet)}."""
        out = {}
        for e in self._only(entries):
            p = real(e)
            if not p.reply_to:
                out[e.id] = None
                continue
            got = self._core.parent_of({"id": p.id, "in_reply_to_id": p.reply_to})
            out[e.id] = got if got in (None, "missing") else real(self.entry(got))
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

    # ---- writing -------------------------------------------------------------------
    def default_visibility(self):
        return adapter.visibility_in(self._core.default_visibility())

    def reply_visibility(self, parent):
        raw = self._raw(real(parent)) if parent is not None else None
        return adapter.visibility_in(self._core.reply_visibility(raw))

    def post(self, text, visibility, reply_to=None, warning="", language=None, **kw):
        """A new post or a reply (reply_to: a Post or its id). Future: the Post made."""
        rid = None if reply_to is None else (reply_to if isinstance(reply_to, str)
                                             else real(reply_to).id)
        fut = self._core.post(text, adapter.visibility_out(visibility), rid, warning,
                              language=language, **kw)
        return _then(fut, lambda st: real(self.entry(st)) if isinstance(st, dict) else st)

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
