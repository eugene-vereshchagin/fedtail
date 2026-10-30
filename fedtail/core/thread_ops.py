"""Threads, the Core's side (core/threads.py builds the trees): one fetched and completed
— the replies the server didn't give asked of their own servers, the progress said —
the parents a round needs, and the threads I follow."""

import logging
import time
from concurrent.futures import ThreadPoolExecutor

from . import (
    sources,
    subs,
    threads,
)
from .model import real
from .proto import Error as ApiError  # the protocol's error answer (core/proto.py)

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts


class ThreadsMixin:
    """A part of Core (core/app.py): see the module's words."""

    def subscribed(self, status):
        """Is the thread this post is in followed? (Knows only threads it has seen.)"""
        return self._sub_root(status) is not None

    def subscribe(self, status):
        def job():
            root = subs.subscribe(self.store, self.api, status)
            if self.sync:
                self.sync.record_thread(root, "sub")
            self.emit("subs_changed", root)
            return root
        return self.submit(job)

    def _sub_root(self, status):
        st = real(status)
        return self.store.sub_root_of(st["id"]) or self.followed_root(st["id"])

    SUB_CHAIN = 40  # how far up a reply's stored parents are followed to find its thread

    def followed_root(self, status_id):
        """The followed thread a post is in, known at once: its own membership, else up
        its stored parents to a post of a followed thread — and then it is a member from
        now on. A comment that came as a mention (to me, unlisted in a public thread…)
        used to be one only after the thread's own next check, and so went to "To me"
        and never brought its thread up in "Commented posts" (28.10's report)."""
        store = self.store
        root = store.sub_root_of(status_id)
        if root is not None:
            return root
        seen, cur = {status_id}, status_id
        for _ in range(self.SUB_CHAIN):
            st = store.get_status(cur)
            parent = real(st).get("in_reply_to_id") if st else None
            if not parent or parent in seen:
                return None
            root = store.sub_root_of(parent)
            if root is not None:
                store.sub_add_members(root, list(seen))
                return root
            seen.add(parent)
            cur = parent
        return None

    def unsubscribe(self, status):
        """Leave the thread: no more "Subscriptions" from it — and, with
        subs.leave_mutes, no more mentions either (replies there tag everyone)."""
        def job():
            quiet = self.cfg["subs"]["leave_mutes"]
            root = subs.leave(self.store, self.api, status, quiet=quiet)
            if self.sync:
                self.sync.record_thread(root, "muted" if quiet else "left")
            self._silence_seen = {}  # what was let through before may be muted now
            self.emit("subs_changed", root)
            self.redraw("subs", *(["mentions"] if quiet else []))
            return root
        return self.submit(job)

    def thread_quiet(self, status):
        """Is this post's thread muted here? (Knows only the posts it has seen there.)"""
        return subs.quiet_root(self.store, status) is not None

    def _mention_entry(self, n):
        """The mentions source's entry: drops mentions from threads muted here."""
        e = sources.notification_entry(n)
        if e is None:
            return None
        sid = e[1].get("id")
        if sid in self._silence_seen:
            return None if self._silence_seen[sid] else e
        try:
            root = subs.silenced(self.store, self.api, e[1], False)
        except Exception as ex:  # noqa: BLE001 — a mention must never be lost to this
            log.warning("muted thread check %s: %s", sid, ex)
            root = None
        if len(self._silence_seen) > 2000:
            self._silence_seen.clear()
        self._silence_seen[sid] = root
        if root:
            log.info("mention %s dropped: thread %s is muted here", sid, root)
            return None
        return e

    def _follows_threads(self):
        """Is a lane shown that the followed threads feed — "subs", or a lane of rules
        taking from them ("commented", view = "threads")?"""
        return "subs" in self.lane_by_name or any(
            "subs" in (lane.feeds or ()) or lane.source == "subs" for lane in self.lanes)

    def _auto_subscribe(self, my_statuses):
        """My new posts and comments: follow their threads (flags subs.auto)."""
        if not self._follows_threads():
            return
        want = set(self.cfg["subs"]["auto"])
        for st in my_statuses:
            st = real(st)
            kind = "comments" if st.get("in_reply_to_id") else "posts"
            if kind not in want or self.subscribed(st):
                continue
            try:
                if subs.subscribe(self.store, self.api, st, auto=True):
                    self.emit("subs_changed", None)
            except Exception as e:
                log.warning("auto-subscribe %s: %s", st.get("id"), e)

    def parent_of(self, status):
        """Parent status, 'missing', or None when it isn't known (yet)."""
        pid = real(status).get("in_reply_to_id")
        if not pid:
            return None
        p = self.store.get_status(pid)
        if p:
            return p
        if self.store.is_missing(pid):
            return "missing"
        return None

    def parents_for(self, statuses):
        """{status id: parent status | 'missing' | None} in two queries."""
        pids = {st["id"]: real(st).get("in_reply_to_id") for st in statuses}
        wanted = {p for p in pids.values() if p}
        found = self.store.get_statuses(wanted)
        missing = self.store.missing_set(wanted - set(found))
        out = {}
        for sid, pid in pids.items():
            if not pid:
                out[sid] = None
            elif pid in found:
                out[sid] = found[pid]
            elif pid in missing:
                out[sid] = "missing"
            else:
                out[sid] = None
        return out

    def ensure_parents(self, statuses):
        self.bg.submit(self._fetch_parents, list(statuses))

    def _fetch_parents(self, statuses):
        want = []
        for st in statuses:
            pid = real(st).get("in_reply_to_id")
            if pid and pid not in self._parent_inflight and not self.store.get_status(pid) \
                    and not self.store.is_missing(pid):
                self._parent_inflight.add(pid)
                want.append(pid)
        got = False
        for pid in want:
            try:
                self.store.put_statuses([self.api.status(pid)])
                got = True
            except ApiError as e:
                if e.status in (403, 404, 410):
                    self.store.mark_missing(pid)
                    got = True
            except Exception:
                pass  # network hiccup: try again next time
            finally:
                self._parent_inflight.discard(pid)
        if got:
            self.emit("parents")

    def thread(self, sid):
        return self.submit(self._thread_nodes, sid)

    def _status_again(self, sid):
        """A post fetched again: gone from its server (404/410) — marked deleted here
        (feeds.md §2.4), then the error goes on."""
        try:
            return self.api.status(sid)
        except ApiError as e:
            if e.status in (404, 410) and self.store.get_status(sid) is not None:
                if self.store.mark_deleted(sid):
                    log.info("post %s: gone from its server, marked deleted", sid)
                    self._world_version += 1
                    # not "status_deleted" (that takes the card away): drawn anew, marked
                    self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})
            raise

    def deleted_ids(self):
        """Posts their server no longer has (marked when fetched again)."""
        return self.store.deleted_set()

    def _thread_nodes(self, sid):
        """The whole conversation, the same from whichever post it is opened: a
        server's context of a post holds its ancestors and *its* descendants only —
        not the sibling branches — so the tree is read from the top post."""
        focus = real(self._status_again(sid))
        ctx = self.api.context(focus["id"])
        ancestors = ctx.get("ancestors", [])
        root = ancestors[0] if ancestors else focus
        roots = self.__dict__.setdefault("_thread_root_of", {})
        if len(roots) > 5000:
            roots.clear()
        roots[str(sid)] = roots[str(focus["id"])] = str(root["id"])  # thread_progress(any)
        below = list(ctx.get("descendants", []))
        refresh = self._async_refresh_hint()
        if ancestors:
            below = self.api.context(root["id"]).get("descendants", []) + below + \
                ancestors[1:] + [focus]
            refresh = self._async_refresh_hint() or refresh
        seen, rest = {root["id"]}, []
        for st in below:
            if st["id"] not in seen:
                seen.add(st["id"])
                rest.append(st)
        everything = [root] + rest
        # every post shown knows its thread: an answer to any of them grows it
        # (_answers_in_open_threads), whichever interface has it open
        roots.update((str(st["id"]), str(root["id"])) for st in everything)
        self.store.put_statuses(everything)
        if self.cfg["feed"]["honest_counters"]:
            self.bg.submit(self._honest_counts, everything)
        mode = self.cfg["feed"].get("thread_from", "mixed")
        if self.cfg["feed"]["complete_threads"] and mode != "local":
            known = {s.get("uri") for s in everything}
            if mode == "remote":
                # the author's server first: its replies are in the tree as it opens
                seen = {s["id"] for s in everything}
                rest += [st for st in self._complete_thread(root, known, emit=False)
                         if st["id"] not in seen]
            else:
                self.bg.submit(self._complete_thread, root, known)
            if refresh:
                self.bg.submit(self._await_refresh, root["id"], *refresh)
        self._opened_threads[root["id"]] = time.monotonic()
        if self.cfg["feed"].get("thread_followed_only"):
            rest = self._followed_only(root, rest)
        return threads.build(root, {"ancestors": [], "descendants": rest})

    def _followed_only(self, root, rest):
        """feed.thread_followed_only: of the replies, those of people I follow and mine —
        and the posts they answer, up to the top, so each still hangs where it did."""
        self._refresh_following()
        mine = (self.me or {}).get("id")
        keep_authors = set(self._following or ()) | {mine}
        by_id = {st["id"]: st for st in rest}
        keep = set()
        for st in rest:
            if st["account"]["id"] in keep_authors:
                cur = st
                while cur is not None and cur["id"] not in keep:
                    keep.add(cur["id"])
                    cur = by_id.get(cur.get("in_reply_to_id"))
        return [st for st in rest if st["id"] in keep]

    def recheck_threads(self):
        """feed.thread_recheck_minutes: threads opened lately (within
        feed.thread_recheck_for_minutes) asked again for new replies every so many
        minutes; what came — the open thread grows
        (thread_grew), as with replies from other servers."""
        every = int(self.cfg["feed"].get("thread_recheck_minutes", 0) or 0) * 60
        if every <= 0 or self.api is None:
            return []
        now = time.monotonic()
        grew = []
        for root_id, opened in list(self._opened_threads.items()):
            if now - opened > 60 * int(self.cfg["feed"].get("thread_recheck_for_minutes", 30)):
                self._opened_threads.pop(root_id, None)
                continue
            if now - self._rechecked.get(root_id, opened) < every:
                continue
            self._rechecked[root_id] = now
            try:
                desc = self.api.context(root_id).get("descendants", [])
            except Exception as e:  # noqa: BLE001 — the next time
                log.debug("recheck %s: %s", root_id, e)
                continue
            have = self.store.get_statuses({st["id"] for st in desc})
            fresh = [st for st in desc if st["id"] not in have]
            if fresh:
                self.store.put_statuses(fresh)
                log.info("thread %s: %d new replies on recheck", root_id, len(fresh))
                self.emit("thread_grew", root_id)
                grew.append(root_id)
        return grew

    def _answers_in_open_threads(self, pairs):
        """[(id, in_reply_to_id)] of posts just stored — a round's, my own sent — →
        thread_grew for each opened thread one of them answers. Decided here once, for
        every interface: each only reloads the thread it shows on thread_grew (my answer
        showed only on opening anew; a round's news in Qt alone, by its own rule)."""
        roots = self.__dict__.get("_thread_root_of") or {}
        grew = []
        for sid, parent in pairs:
            root = roots.get(str(parent)) if parent else None
            if root is not None:
                roots[str(sid)] = root  # an answer to it is the thread's too
                if root not in grew:
                    grew.append(root)
        for root in grew:
            self.emit("thread_grew", root)
        return grew

    def _async_refresh_hint(self):
        hint = getattr(self.api, "last_async_refresh", None)
        return hint() if hint else None

    def _await_refresh(self, root_id, refresh_id, retry, budget=60):
        """Mastodon 4.5+ said it is fetching the rest of this thread from other
        servers: ask how it goes, and when done, the open thread grows."""
        waited = 0
        while waited < budget and not self._stop.is_set():
            pause = max(1, min(retry, 10))
            self._stop.wait(pause)
            waited += pause
            try:
                status = self.api.async_refresh(refresh_id)
            except Exception as e:  # noqa: BLE001 — experimental endpoint: give up quietly
                log.debug("async refresh %s: %s", refresh_id, e)
                return
            if status == "finished":
                log.info("thread %s: the server finished fetching replies (%d s)",
                         root_id, waited)
                self.emit("thread_grew", root_id)
                return

    def _complete_thread(self, root, known, emit=True):
        """Replies the post's own server lists and mine hasn't got: mine fetches them
        by address. Then the open thread grows (event thread_grew) — or, emit=False
        (feed.thread_from = "remote": the thread waits for them), [the posts fetched]."""
        if root.get("visibility") not in ("public", "unlisted") or not root.get("uri"):
            return []
        now = time.monotonic()
        if now - self._completed.get(root["id"], -1e9) < 300:
            return []
        self._completed[root["id"]] = now
        from . import replies
        t = time.monotonic()
        rid = root["id"]
        self._thread_step(rid, "asking")
        # the whole conversation in one list where the server keeps one; else walk
        # the replies of replies
        try:
            uris = replies.context_uris(self._origin_json, root["uri"])
            how = "context"
            if not uris:
                uris, how = replies.reply_uris(self._origin_json, root["uri"]), "replies"
        except Exception:
            self._thread_step(rid, "failed")
            raise
        missing = [u for u in uris if u not in known]
        wanted = missing[:30]
        self._thread_step(rid, "fetching", 0, len(wanted))

        def resolve(uri):
            try:
                found = self.api.search(uri, kind="statuses", resolve=True, limit=1)
            except Exception as e:  # not reachable, not public, gone: skip it
                log.debug("resolve %s: %s", uri, e)
                return []
            return (found or {}).get("statuses") or []
        # my server fetches each from its home: a few at once, not one after another
        from concurrent.futures import as_completed
        got = []
        with ThreadPoolExecutor(max_workers=4, thread_name_prefix="fedtail-resolve") as ex:
            for i, fut in enumerate(as_completed([ex.submit(resolve, u) for u in wanted])):
                got += fut.result()
                self._thread_step(rid, "fetching", i + 1, len(wanted))
        self._thread_step(rid, "done", len(got), len(wanted))
        log.info("thread %s: origin lists %d posts (%s), %d missing here, %d fetched "
                 "(%.1f s)", root["id"], len(uris), how, len(missing), len(got),
                 time.monotonic() - t)
        if got:
            self.store.put_statuses(got)
            if emit:
                self.emit("thread_grew", root["id"])
        return got

    THREAD_DONE_SHOWN = 8  # seconds "fetched N" stays said

    def _thread_step(self, root_id, stage, done=0, total=0):
        """threads.thread_progress: where fetching a thread's replies from its author's
        server stands — "asking" the server, "fetching" done of total, "done", "failed".
        The open thread says so (event thread_progress); thread_progress() reads it."""
        if not self.cfg["feed"].get("thread_progress"):
            return
        steps = self.__dict__.setdefault("_thread_steps", {})
        steps[str(root_id)] = {"stage": stage, "done": done, "total": total,
                               "at": time.monotonic()}
        self.emit("thread_progress", str(root_id))

    def thread_progress(self, root_id):
        """{"stage", "done", "total"} of the thread's fetching now, or None (none going,
        or its "done" said long enough ago)."""
        steps = self.__dict__.get("_thread_steps", {})
        got = steps.get(str(root_id)) or \
            steps.get(self.__dict__.get("_thread_root_of", {}).get(str(root_id), ""))
        if got is None:
            return None
        if got["stage"] in ("done", "failed") and \
                time.monotonic() - got["at"] > self.THREAD_DONE_SHOWN:
            return None
        return {k: got[k] for k in ("stage", "done", "total")}
