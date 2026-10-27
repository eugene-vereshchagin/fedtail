"""Events no server tells a client, derived by comparing snapshots (docs/en/dev/feeds.md
§2.4): who stopped following me. Every activity.unfollows_minutes the whole list of my
followers is taken; who is gone from it — an Activity row of fedtail's own ("@x stopped
following you"), written so that it doesn't lie:

* a snapshot counts only when it came whole: every page without an error, and as many as
  the server's followers_count says (within a little); else it is thrown away;
* the first snapshot is where it starts: no events;
* one gone must be missing from two snapshots in a row, and `relationships` must say
  followed_by = false (a server's list has holes sometimes); an account the server no
  longer has (404/410) — "gone", not an unfollow;
* the ones I removed or blocked myself (Core records it: mark_mine) aren't events;
* many from one server at once (more than activity.unfollows_mass) — that server is down or
  cut us off: one row "lost x.org", not a hundred;
* someone I follow too who stopped — "unfollowed_back" as well (event atoms).

Runs in the background pool; the poll only asks whether it is due.
"""

from __future__ import annotations

import logging
import time
from collections import Counter

from .store import LOCAL_EVENT

log = logging.getLogger(__name__)

PAGE = 80
TYPE_UNFOLLOW = "fedtail.unfollow"
TYPE_GONE = "fedtail.gone"
TYPE_LOST = "fedtail.lost_domain"
TYPE_MOVED = "fedtail.moved"
TYPE_UNLIKED = "fedtail.unliked"
MOVED_ASK = 20  # the ones gone asked one by one whether they moved, at most
KEEP_ACC = ("id", "acct", "username", "display_name", "url", "avatar", "avatar_static", "bot")
MINE_KEEP_S = 7 * 86400  # my own removals remembered this long


def _small(acc):
    return {k: acc.get(k) for k in KEEP_ACC if acc.get(k) is not None}


def _domain(acct):
    return (acct or "").partition("@")[2].lower()


class Derived:
    def __init__(self, core):
        self.core = core
        self.store = core.store
        self.running = False

    @property
    def cfg(self):
        return self.core.cfg["activity"]

    # ---- my own doings: not unfollows -------------------------------------------------
    def mark_mine(self, acc_id):
        """I removed or blocked them myself: their leaving isn't news."""
        mine = dict(self.store.kv_get("derived.mine", {}) or {})
        now = time.time()
        mine = {k: v for k, v in mine.items() if now - v < MINE_KEEP_S}
        mine[str(acc_id)] = now
        self.store.kv_set("derived.mine", mine)

    # ---- when ----------------------------------------------------------------------------
    def due(self):
        if not self.cfg.get("unfollows", True) or self.running or not self.core.me:
            return False
        every = max(10, int(self.cfg.get("unfollows_minutes", 60))) * 60
        return time.time() - float(self.store.kv_get("derived.at", 0) or 0) >= every

    def run(self):
        """One snapshot and what it says. → the rows written (notifications)."""
        if self.running:
            return []
        self.running = True
        try:
            self.store.kv_set("derived.at", time.time())
            return self._run()
        except Exception as e:  # noqa: BLE001 — next time; nothing claimed
            log.info("derived: %s", e)
            return []
        finally:
            self.running = False

    # ---- the snapshot --------------------------------------------------------------------
    def snapshot(self):
        """{id: account} of every follower, or None when the list didn't come whole."""
        api, me = self.core.api, self.core.me
        try:
            count = int((api.account(me["id"]) or {}).get("followers_count") or 0)
        except Exception as e:  # noqa: BLE001
            log.info("derived: my count: %s", e)
            return None
        most = int(self.cfg.get("unfollows_max", 5000))
        if count > most:
            log.info("derived: %d followers, over activity.unfollows_max (%d): skipped",
                     count, most)
            return None
        got, max_id = {}, None
        for _ in range(most // PAGE + 2):
            page, max_id = api.followers(me["id"], max_id, limit=PAGE)
            for a in page or ():
                if isinstance(a, dict) and a.get("id"):
                    got[a["id"]] = _small(a)
            if not max_id or not page:
                break
        slack = max(2, count // 100)
        if abs(len(got) - count) > slack:
            log.info("derived: %d followers came, the server counts %d: not whole, thrown "
                     "away", len(got), count)
            return None
        return got

    def _run(self):
        now = self.snapshot()
        if now is None:
            return []
        before = self.store.kv_get("derived.followers")
        self.store.kv_set("derived.followers", now)
        if not isinstance(before, dict):
            log.info("derived: first snapshot of %d followers: the start, no events", len(now))
            self.store.kv_set("derived.pending", {})
            return []
        # missing from the last snapshot and still missing now: twice in a row
        pending = self.store.kv_get("derived.pending", {}) or {}
        pending = pending if isinstance(pending, dict) else {}
        confirmed = {i: a for i, a in pending.items() if i not in now}
        fresh = {i: before[i] for i in set(before) - set(now) if i not in pending}
        self.store.kv_set("derived.pending", fresh)
        mine = set((self.store.kv_get("derived.mine", {}) or {}).keys())
        confirmed = {i: a for i, a in confirmed.items() if i not in mine}
        if not confirmed:
            return []
        rows = self._check(sorted(confirmed), confirmed)
        new = self.store.activity_put(rows) if rows else []
        if new:
            self.core.emit("activity_updated", len(new))
            lanes_in = {c.name: [] for c in self.core._event_lanes()}
            if lanes_in:
                self.core.emit("lanes_updated", lanes_in)
        return new

    def _moved(self, ids):
        """{id: the new account's acct} of the ones gone that moved (their account says
        `moved`): one request each, a few at most."""
        out = {}
        for i in ids[:MOVED_ASK]:
            try:
                acc = self.core.api.account(i) or {}
            except Exception as e:  # noqa: BLE001 — unsure: an unfollow as it looks
                log.debug("derived: %s moved?: %s", i, e)
                continue
            new = acc.get("moved")
            if isinstance(new, dict) and new.get("acct"):
                out[i] = new["acct"]
        return out

    # ---- likes taken back (activity.unlikes, off by default: a request a post) ----------
    def likes_due(self):
        if not self.cfg.get("unlikes", False) or self.running or not self.core.me:
            return False
        every = max(10, int(self.cfg.get("unfollows_minutes", 60))) * 60
        return time.time() - float(self.store.kv_get("derived.likes_at", 0) or 0) >= every

    def run_likes(self):
        """Who liked my recent posts, compared with last time: a like taken back — a row
        "took the like back" (the first look at a post is the start)."""
        self.store.kv_set("derived.likes_at", time.time())
        api, me = self.core.api, self.core.me
        days = max(1, int(self.cfg.get("unlikes_days", 3)))
        most = max(1, int(self.cfg.get("unlikes_posts", 20)))
        since = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - days * 86400))
        posts = [st for _i, st in self.store.items("mine", most * 2)
                 if not st.get("reblog") and (st.get("created_at") or "") >= since
                 and (st.get("account") or {}).get("id") == me["id"]][:most]
        before = self.store.kv_get("derived.likes", {}) or {}
        now, rows = {}, []
        day = time.strftime("%Y-%m-%d", time.gmtime())
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        for st in posts:
            try:
                page, _next = api.favourited_by(st["id"])
            except Exception as e:  # noqa: BLE001 — this post next time
                log.debug("derived: likes of %s: %s", st["id"], e)
                if st["id"] in before:
                    now[st["id"]] = before[st["id"]]
                continue
            who = {a["id"]: _small(a) for a in page or () if isinstance(a, dict) and a.get("id")}
            now[st["id"]] = who
            was = before.get(st["id"])
            if not isinstance(was, dict) or len(page or ()) >= 80:
                continue  # the start for this post, or more than a page: not sure
            for aid in set(was) - set(who):
                rows.append({"id": f"{LOCAL_EVENT}unliked:{st['id']}:{aid}:{day}",
                             "type": TYPE_UNLIKED, "account": was[aid], "status": st,
                             "created_at": stamp})
        self.store.kv_set("derived.likes", now)
        new = self.store.activity_put(rows) if rows else []
        if new:
            self.core.emit("activity_updated", len(new))
        return new

    def _check(self, ids, before):
        """The ones missing twice, asked once more: still not following → rows."""
        api = self.core.api
        rels = {}
        for i in range(0, len(ids), 40):
            try:
                for r in api.relationships(ids[i:i + 40]) or ():
                    rels[str(r.get("id"))] = r
            except Exception as e:  # noqa: BLE001 — unsure: nothing said this time
                log.info("derived: relationships: %s", e)
                return []
        day = time.strftime("%Y-%m-%d", time.gmtime())
        stamp = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
        following = getattr(self.core, "_following", None) or set()
        left, gone = [], []
        for i in ids:
            r = rels.get(i)
            if r is None:  # the server knows them no more: deleted, suspended
                gone.append(i)
            elif not r.get("followed_by"):
                left.append(i)
        rows = []
        by_domain = Counter(_domain(before[i].get("acct")) for i in left)
        mass = int(self.cfg.get("unfollows_mass", 10))
        lost = {d for d, n in by_domain.items() if d and n > mass}
        for d in sorted(lost):
            n = by_domain[d]
            rows.append({"id": f"{LOCAL_EVENT}lost:{d}:{day}", "type": TYPE_LOST,
                         "account": {"id": f"domain:{d}", "acct": d, "username": d,
                                     "display_name": f"{d} ({n})"},
                         "created_at": stamp})
        moved = self._moved([i for i in left if _domain(before[i].get("acct")) not in lost])
        for i in left:
            acc = before[i]
            if _domain(acc.get("acct")) in lost:
                continue
            if i in moved:  # not an unfollow: the new account follows by itself
                rows.append({"id": f"{LOCAL_EVENT}moved:{i}:{day}", "type": TYPE_MOVED,
                             "account": dict(acc, _moved_to=moved[i]), "created_at": stamp})
                continue
            rows.append({"id": f"{LOCAL_EVENT}unfollow:{i}:{day}", "type": TYPE_UNFOLLOW,
                         "account": dict(acc, _back=i in following), "created_at": stamp})
        for i in gone:
            rows.append({"id": f"{LOCAL_EVENT}gone:{i}:{day}", "type": TYPE_GONE,
                         "account": before[i], "created_at": stamp})
        log.info("derived: %d stopped following, %d gone, %d servers lost",
                 len([r for r in rows if r["type"] == TYPE_UNFOLLOW]), len(gone), len(lost))
        return rows


__all__ = ["Derived", "TYPE_GONE", "TYPE_LOST", "TYPE_UNFOLLOW"]
