"""The counts of the posts on screen kept fresh: replies, boosts, likes and my own marks.

A lane holds each post as it came — its counts of that moment, mostly none — and only an
opened thread asked again (29.10: "why no number of replies under the posts?"). Now every
interface says which posts it shows (`on_screen`), as it says what is read; every
`feed.counts_minutes` the round asks my server again for those seen lately, in one batch
(`GET /api/v1/statuses?id[]=…`; one by one where the server can't), and with
`feed.honest_counters` the authors' servers too (origin.py). A post whose numbers changed
is stored and said (`status_updated`): the windows redo only its row of buttons, and the
lanes counting new comments (a thread's news) see the replies grow."""

import logging
import threading
import time

from .model import real
from .proto import Error as ApiError

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts

BATCH = 40        # ids in one request (Mastodon takes up to 40)
ONE_BY_ONE = 20   # at most so many single requests a round where batches aren't served
SEEN_FOR = 1800   # s: a post shown this long ago is no longer "on screen"
COUNTED = ("replies_count", "reblogs_count", "favourites_count", "quotes_count",
           "favourited", "reblogged", "bookmarked", "muted", "pinned")


def changed(old, new):
    """Whether what the row of buttons shows differs between two copies of a post."""
    return any(old.get(k) != new.get(k) for k in COUNTED if k in new)


class CountsMixin:
    """A part of Core (core/app.py): see the module's words."""

    def on_screen(self, ids):
        """These posts (ids, a boost's or its post's) are on screen now: their counts
        are asked again at the next round that is due (feed.counts_minutes)."""
        now = time.monotonic()
        with self._screen_lock():
            seen = self.__dict__.setdefault("_on_screen", {})
            for i in ids or ():
                if i and not str(i).startswith(("event:", "__")):
                    seen[str(i)] = now

    def _screen_lock(self):
        lock = self.__dict__.get("_counts_lock")
        if lock is None:
            lock = self.__dict__.setdefault("_counts_lock", threading.Lock())
        return lock

    def refresh_counts(self, force=False):
        """The round's step: the posts seen on screen lately asked again, if the time
        has come (or force). → the posts that changed (their raw statuses)."""
        every = int(self.cfg["feed"].get("counts_minutes", 5) or 0) * 60
        if self.api is None or (every <= 0 and not force):
            return []
        now = time.monotonic()
        if not force and now - self.__dict__.get("_counts_at", -1e9) < every:
            return []
        self._counts_at = now
        with self._screen_lock():
            seen = self.__dict__.get("_on_screen", {})
            for i in [i for i, t in seen.items() if now - t > SEEN_FOR]:
                del seen[i]
            ids = sorted(seen, key=seen.get, reverse=True)[:BATCH * 3]
        if not ids:
            return []
        have = self.store.get_statuses(set(ids))
        # a boost on screen: its post is what has the counts
        posts = {}
        for i in ids:
            st = have.get(i)
            if st is not None:
                p = real(st)
                posts.setdefault(p["id"], p)
        fresh = self._statuses_again(list(posts))
        out = [st for st in fresh if st.get("id") in posts and changed(posts[st["id"]], st)]
        if out:
            self._wake_threads(posts, out)
            self.store.put_statuses(out)
            for st in out:  # each its own: the windows redo only its buttons
                self.emit("status_updated", st)
        log.debug("counts: %d on screen asked, %d changed", len(posts), len(out))
        if self.cfg["feed"].get("honest_counters"):
            self._honest_counts([fresh_one for fresh_one in fresh
                                 if fresh_one.get("visibility") in ("public", "unlisted")])
        return out

    def _wake_threads(self, before, now):
        """Posts with more replies than before: a followed thread among them is asked
        about at the next round — the lanes of threads with new comments ("Commented
        posts") learn of them then, not when its quiet turn comes."""
        from .store import now_iso
        for st in now:
            old = before.get(st["id"]) or {}
            if (st.get("replies_count") or 0) > (old.get("replies_count") or 0):
                root = self.store.sub_root_of(st["id"])
                if root:
                    self.store.sub_wake(root, now_iso())
                    log.info("counts: thread %s has new replies: asked next round", root)

    def _statuses_again(self, ids):
        """The posts as my server has them now: in batches, or one by one (a few) where
        the server doesn't serve batches."""
        out = []
        batches = getattr(self.api, "statuses", None)
        if batches is not None and not self.__dict__.get("_no_batches"):
            try:
                for at in range(0, len(ids), BATCH):
                    out += batches(ids[at:at + BATCH]) or []
                return out
            except ApiError as e:
                if getattr(e, "status", 0) not in (400, 404, 405, 422, 501):
                    log.debug("counts: %s", e)
                    return out
                self._no_batches = True  # older servers: one by one from now on
                log.info("counts: the server serves no batches (%s): one by one", e)
        for sid in ids[:ONE_BY_ONE]:
            try:
                st = self.api.status(sid)
            except Exception as e:  # noqa: BLE001 — gone, refused: the next time
                log.debug("counts %s: %s", sid, e)
                continue
            if st:
                out.append(st)
        return out
