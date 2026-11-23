"""How many comments a whole thread has, for the posts on screen: the Thread button's
number. Mastodon counts only a post's direct replies (`replies_count`), so a boosted
comment deep in a busy thread showed none (23.11: "the replies to the comment, not the
thread's"). For a post on screen that is a reply, or has replies, the thread's root is
asked for its context once (`GET /api/v1/statuses/:id/context`, one or two requests a
thread), remembered `feed.thread_size_minutes` minutes, and the posts of that thread on
screen said again (`status_updated`) — the View puts the number into the model
(`Counts.thread`), every interface draws it. 0 — off: the button says the direct
replies."""

import logging
import threading
import time

from .model import real

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts

AT_ONCE = 8         # threads asked for at one call of on_screen
PER_MINUTE = 30     # requests a minute at most, whatever scrolls by
KEY = "fedtail_thread_size"  # the raw status's key the adapter reads (Counts.thread)


class ThreadSizeMixin:
    """A part of Core (core/app.py): see the module's words."""

    def _ts(self):
        d = self.__dict__
        if "_ts_lock" not in d:
            d.setdefault("_ts_lock", threading.Lock())
        with d["_ts_lock"]:
            d.setdefault("_ts_root", {})      # post id -> its thread's root id
            d.setdefault("_ts_size", {})      # root id -> (comments, monotonic time)
            d.setdefault("_ts_busy", set())   # roots (or posts) being asked now
            d.setdefault("_ts_spent", [])     # monotonic times of the requests made
        return d["_ts_lock"]

    def _ts_every(self):
        return int(self.cfg["feed"].get("thread_size_minutes", 60) or 0) * 60

    def thread_size(self, st):
        """The comments of the whole thread the post (a raw status, a boost's too) is
        in, as last asked; None — not known (or feed.thread_size_minutes is 0)."""
        if not isinstance(st, dict) or self._ts_every() <= 0:
            return None
        p = real(st)
        with self._ts():
            root = self._ts_root.get(str(p.get("id")))
            got = self._ts_size.get(root) if root else None
        return got[0] if got else None

    def thread_sized(self, st):
        """The raw status with its thread's size in it (KEY, the boosted post's for a
        boost) when known; None — as it is."""
        n = self.thread_size(st)
        if n is None:
            return None
        if isinstance(st.get("reblog"), dict):
            return dict(st, reblog=dict(st["reblog"], **{KEY: n}))
        return dict(st, **{KEY: n})

    def size_threads(self, ids):
        """These posts are on screen (CountsMixin.on_screen): the threads among them not
        known lately are asked for, in the background, a few at a time."""
        every = self._ts_every()
        if every <= 0 or self.api is None or not ids:
            return
        have = self.store.get_statuses({str(i) for i in ids if i})
        now = time.monotonic()
        want = []
        with self._ts():
            for st in have.values():
                p = real(st)
                sid = str(p.get("id") or "")
                if not sid or not (p.get("in_reply_to_id") or p.get("replies_count")):
                    continue  # a post alone: nothing to count
                root = self._ts_root.get(sid)
                got = self._ts_size.get(root) if root else None
                if got and now - got[1] < every:
                    continue
                if (root or sid) in self._ts_busy or sid in self._ts_busy:
                    continue
                self._ts_busy.add(root or sid)
                want.append((sid, root))
                if len(want) >= AT_ONCE:
                    break
        if want:
            self.bg.submit(self._size_threads, want)

    def _spend(self):
        """One more request, if this minute allows it."""
        now = time.monotonic()
        with self._ts():
            self._ts_spent[:] = [t for t in self._ts_spent if now - t < 60]
            if len(self._ts_spent) >= PER_MINUTE:
                return False
            self._ts_spent.append(now)
            return True

    def _size_threads(self, want):
        for sid, root in want:
            try:
                self._size_one(sid, root)
            except Exception as e:  # noqa: BLE001 — gone, refused: asked again later
                log.debug("thread size %s: %s", sid, e)
            finally:
                with self._ts():
                    self._ts_busy.discard(root or sid)

    def _size_one(self, sid, root):
        desc = None
        if root is None:
            root = self._local_root(sid)
        if root is None:
            if not self._spend():
                return
            ctx = self.api.context(sid) or {}
            anc = ctx.get("ancestors") or []
            root = str(anc[0]["id"]) if anc else sid
            if root == sid:
                desc = ctx.get("descendants") or []
        if desc is None:
            if not self._spend():
                with self._ts():
                    self._ts_root[sid] = root
                return
            desc = (self.api.context(root) or {}).get("descendants") or []
        self.learn_thread_size(root, [sid] + [str(d.get("id")) for d in desc], len(desc))

    def learn_thread_size(self, root, members, n):
        """The thread of root has n comments; members are posts in it. The posts of it
        on screen are said again when the number changed."""
        root = str(root)
        with self._ts():
            before = self._ts_size.get(root)
            self._ts_size[root] = (n, time.monotonic())
            for m in members:
                if m and m != "None":
                    self._ts_root[str(m)] = root
            self._ts_root[root] = root
            if before and before[0] == n:
                return
            mine = {s for s, r in self._ts_root.items() if r == root}
        with self._screen_lock():
            shown = set(self.__dict__.get("_on_screen", {}))
        said = 0
        for st in self.store.get_statuses(shown).values() if shown else ():
            if str(real(st).get("id")) in mine:  # a boost on screen: its post's
                self.emit("status_updated", st)
                said += 1
        log.debug("thread size: %s has %d comments (%d on screen)", root, n, said)

    def _local_root(self, sid):
        """The thread's root as the store knows it (walking up the replies), or None
        when a post on the way is missing."""
        at, seen = sid, set()
        while at and at not in seen:
            seen.add(at)
            st = self.store.get_statuses({at}).get(at)
            if st is None:
                return None
            up = st.get("in_reply_to_id")
            if not up:
                return str(at)
            at = str(up)
        return None
