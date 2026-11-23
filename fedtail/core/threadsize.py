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
import time

from .model import real
from .proto import raw
from .state import CoreState

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts

AT_ONCE = 8         # threads asked for in one go
PER_MINUTE = 30     # requests a minute at most, whatever scrolls by
SHARE = 4           # …and of what the server still allows this window, a quarter at most
FAILED_S = 600      # a thread the server didn't give is left alone this long (or
#                     thread_size_minutes, when that is shorter)
KEEP = 5000         # posts whose thread is remembered; the oldest go first
KEY = "fedtail_thread_size"  # the raw status's key the adapter reads (Counts.thread)


class ThreadSizeMixin(CoreState):
    """A part of Core (core/app.py): see the module's words."""

    def _ts(self):
        """The lock of everything here (the state itself: core/state.py, _ts_*)."""
        return self._ts_lock

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
        if isinstance(raw.boosted(st), dict):
            return raw.with_boosted(st, dict(raw.boosted(st), **{KEY: n}))
        return dict(st, **{KEY: n})

    def size_threads(self, ids):
        """These posts are on screen (CountsMixin.on_screen): the threads among them not
        known lately are asked for, in the background, a few at a time. Nothing is read
        here — the caller is a window's own thread, scrolling: the ids are only noted,
        the store is asked in the background (one look at a time)."""
        if self._ts_every() <= 0 or self.api is None or not ids:
            return
        with self._ts():
            self._ts_wanted.update(str(i) for i in ids if i)
            if self._ts_looking:
                return
            self._ts_looking = True
        try:
            self.bg.submit(self._size_wanted)
        except Exception:  # the pool is shut: the program is leaving
            with self._ts():
                self._ts_looking = False
            raise

    def _size_wanted(self):
        """The posts noted by size_threads, looked through: which threads to ask about."""
        try:
            while True:
                with self._ts():
                    ids, self._ts_wanted = self._ts_wanted, set()
                    if not ids:  # said under the lock: none noted meanwhile is left waiting
                        self._ts_looking = False
                        return
                want = self._pick(ids)
                if want:
                    self._size_threads(want)
        except BaseException:
            with self._ts():
                self._ts_looking = False
            raise

    def _pick(self, ids):
        every = self._ts_every()
        have = self.store.get_statuses(ids)
        now = time.monotonic()
        want = []
        with self._ts():
            quiet = min(every, FAILED_S)
            for k in [k for k, t in self._ts_failed.items() if now - t >= quiet]:
                del self._ts_failed[k]
            for st in have.values():
                p = real(st)
                sid = str(p.get("id") or "")
                if not sid or not (raw.reply_to(p) or raw.replies(p)):
                    continue  # a post alone: nothing to count
                root = self._ts_root.get(sid)
                got = self._ts_size.get(root) if root else None
                if got and now - got[1] < every:
                    continue
                key = root or sid
                if key in self._ts_busy or key in self._ts_failed or sid in self._ts_failed:
                    continue
                self._ts_busy.add(key)
                want.append((sid, root))
                if len(want) >= AT_ONCE:
                    break
        return want

    def _spend(self):
        """One more request, if this minute allows it — and the server's own limit: of
        what it still allows this window, a quarter at most goes here (subs.py's share:
        the lanes keep theirs)."""
        now = time.monotonic()
        b = getattr(self.api, "budget", None)
        if b is not None and b.limit and time.time() < b.reset and \
                b.remaining // SHARE <= 0:
            return False
        with self._ts():
            self._ts_spent[:] = [t for t in self._ts_spent if now - t < 60]
            if len(self._ts_spent) >= PER_MINUTE:
                return False
            self._ts_spent.append(now)
            return True

    def _size_threads(self, want):
        for sid, root in want:
            key = root or sid
            try:
                self._size_one(sid, root)
            except Exception as e:  # noqa: BLE001 — gone, refused: asked again later
                log.debug("thread size %s: %s", sid, e)
                with self._ts():  # later: not at every scroll while it stays on screen
                    self._ts_failed[key] = time.monotonic()
            finally:
                with self._ts():
                    self._ts_busy.discard(key)

    def _size_one(self, sid, root):
        desc = None
        if root is None:
            with self._ts():  # a post asked just before was of the same thread
                root = self._ts_root.get(sid)
                got = self._ts_size.get(root) if root else None
            if got and time.monotonic() - got[1] < self._ts_every():
                return
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
            if len(self._ts_root) > KEEP:  # the oldest half goes, and sizes left alone
                for k in list(self._ts_root)[:len(self._ts_root) - KEEP // 2]:
                    del self._ts_root[k]
                held = set(self._ts_root.values())
                for k in [k for k in self._ts_size if k not in held]:
                    del self._ts_size[k]
                self._ts_root[root] = root
            if before and before[0] == n:
                return
            mine = {s for s, r in self._ts_root.items() if r == root}
        with self._screen_lock():
            shown = set(self._on_screen)
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
            up = raw.reply_to(st)
            if not up:
                return str(at)
            at = str(up)
        return None
