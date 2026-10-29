"""Events — likes, boosts, follows, follow requests…: fetched (notifications), put into
the lanes whose rules take them, counted and seen."""

import logging

from .store import now_iso, sort_key

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts


class ActivityMixin:
    """A part of Core (core/app.py): see the module's words."""

    def _poll_activity(self):
        """New notifications of the chosen kinds. The very first fetch is history,
        not news: it is stored as already seen."""
        types = list(self.cfg["activity"]["types"])
        if self.cfg["activity"].get("approvals", True):  # GoToSocial: waiting for my yes
            types += ["pending.reply", "pending.favourite", "pending.reblog"]
        if self.cfg["activity"].get("server_notices", True):  # Mastodon 4.3+
            types += ["severed_relationships", "moderation_warning"]
        fc = self.cfg["feed"]
        newest, _sort = self.store.activity_newest(server=True)
        if newest is None:
            self.store.activity_put(self._notifications(types, limit=fc["page_size"]))
            self.store.kv_set("activity_seen", self.store.activity_newest()[1])
            return []
        new, cursor = [], newest
        while True:
            page = self._notifications(types, limit=fc["page_size"], min_id=cursor)
            if not page:
                break
            new += self.store.activity_put(page)
            nxt = max(page, key=lambda n: sort_key(n.get("created_at"), n["id"]))["id"]
            if nxt == cursor or len(page) < fc["page_size"] or len(new) >= fc["catch_up_limit"]:
                break
            cursor = nxt
        return new

    def _notifications(self, types, **page):
        """A page of notifications: the server's own groups where it has them
        (activity.server_groups, Mastodon 4.3+), else one by one (GoToSocial, older
        Mastodon, Akkoma) — the first "no such thing" answer settles it for the run."""
        if self.cfg["activity"].get("server_groups", True) and self.supports("grouped") \
                and hasattr(self.api, "notification_groups"):
            from .social import NotSupported
            try:
                return self._api("grouped", self.api.notification_groups, types, **page)
            except NotSupported:
                log.info("no grouped notifications on this server: one by one")
        return self.api.notifications(types, **page)

    def activity_entries(self, limit=300):
        """Activity newest first: what Activity (the lane of that name) takes — every
        event, follow requests among them while no lane of their own is shown."""
        if "activity" in self.lane_by_name:
            return self.lane_events("activity", limit, which="all")
        return self.event_items(limit)

    def event_items(self, limit=300):
        """Every event fedtail has, newest first, as notifications: the stored activity
        and — when some lane takes them — the follow requests waiting, on top (their
        ids social.FOLLOW_REQUEST + the account's, answered by the buttons)."""
        got = self.store.activity_recent(limit)
        if self._wants_event("follow_request"):
            got = self._request_events(self.follow_requests or ()) + list(got)
        return got

    REQUESTS_SEEN = "requests.seen"  # account id → when its request came (or was seen)

    def _request_events(self, accounts):
        """The follow requests waiting, as events — in time among the others, when each
        came — when fedtail first saw it (note_requests; the API gives no time of it).
        Not the account's creation date ("asks to follow you · 9 Oct 2024") nor "newest
        of all": a request stood on top of a lane read oldest first, its "followed you"
        at the bottom (29.10)."""
        from .social import FOLLOW_REQUEST
        seen = self.store.kv_get(self.REQUESTS_SEEN) or {}
        out = []
        for a in accounts:
            at = seen.get(a["id"]) or now_iso()
            rid = FOLLOW_REQUEST + a["id"]
            out.append({"id": rid, "type": "follow_request", "account": a,
                        "created_at": at, "sort": sort_key(at, rid)})
        return out

    def note_requests(self, accounts):
        """When each waiting request came, kept (the poll, on every list of them)."""
        seen = self.store.kv_get(self.REQUESTS_SEEN) or {}
        ids = {a["id"] for a in accounts}
        kept = {i: t for i, t in seen.items() if i in ids}
        for i in ids - set(kept):
            kept[i] = now_iso()
        if kept != seen:
            self.store.kv_set(self.REQUESTS_SEEN, kept)

    def _events_by_lane(self, new_requests=(), new_activity=()):
        """{lane: [notification]}: which shown lanes take which of the new events."""
        events = self._request_events(new_requests or ()) + \
            [n for n in new_activity or () if isinstance(n, dict)]
        if not events:
            return {}
        world, quiet = self._world(), self.muted | self.blocked
        events = [n for n in events if (n.get("account") or {}).get("id") not in quiet]
        out = {}
        for c in self._event_lanes():
            took = [n for n in events if c.takes_event(n, world)]
            if took:
                out[c.name] = took
        return out

    def _event_lanes(self):
        """The lanes shown that take events too (a condition with `event`)."""
        return [c for c in self.customs if c.event_conds and c.name in self.lane_by_name]

    def _events_only(self, name):
        """A lane of events only (Activity, Requests): no posts, its rows are events."""
        c = next((c for c in self.customs if c.name == name), None)
        return bool(c is not None and c.events_only and name in self.lane_by_name)

    def _wants_event(self, word):
        """Does a shown lane take events of this word ("follow_request"…)? The server
        is asked for them only then."""
        return any(c.wants_event(word) for c in self._event_lanes())

    def lane_events(self, name, limit=200, which=None):
        """[notification] newest first: the events (likes, boosts, follows…) a lane of
        rules shows among its posts (feeds.md §2.3) — from what Activity has stored."""
        c = next((c for c in self.customs if c.event_conds and c.name == name), None)
        if c is None or name not in self.lane_by_name:
            return []
        which = self.lane_filter(name) if which is None else which
        reqs = tuple(a.get("id") for a in self.follow_requests or ())
        key = (self.store.activity_newest(), self.store.activity_count_after(""),
               self._world_version, self._lists_version, limit, which, reqs,
               self._silence_version)
        cache = self.__dict__.setdefault("_events_cache", {})
        hit = cache.get((name, which))
        if hit and hit[0] == key:
            return hit[1]
        world, quiet = self._world(), self.muted | self.blocked
        got = [n for n in self.event_items(max(limit * 3, 300))
               if (n.get("account") or {}).get("id") not in quiet
               and c.takes_event(n, world, which)][:limit]
        cache[(name, which)] = (key, got)
        return got

    def activity_seen_mark(self):
        return self.store.kv_get("activity_seen", "")

    def activity_unread(self):
        """Activity's events not seen yet (follow requests: while they wait)."""
        if "activity" in self.lane_by_name:
            return self.events_unread("activity")
        return self.store.activity_count_after(self.activity_seen_mark())

    def events_unread(self, name):
        """A lane's events not seen yet: newer than the seen mark (common to every
        lane — an event seen in one is seen everywhere); follow requests count while
        they wait."""
        from .social import FOLLOW_REQUEST
        from .store import MINE_EVENT
        seen = self.activity_seen_mark()
        return sum(1 for n in self.lane_events(name, 1000, which="all")
                   if (str(n.get("sort") or "") > seen  # what I did myself isn't news
                       or str(n.get("id") or "").startswith(FOLLOW_REQUEST))  # waiting
                   and not str(n.get("id") or "").startswith(MINE_EVENT))

    def mark_activity_seen(self, upto=None):
        """Seen up to this entry's sort (what came on screen), or everything (None: the
        "all read" button). The mark only goes forward."""
        newest = self.store.activity_newest()[1]
        if upto is not None:
            newest = min(newest, upto) if newest else ""
        if newest and newest > self.activity_seen_mark():
            self.store.kv_set("activity_seen", newest)
            if self.sync is not None:  # seen here, seen on the account's other devices
                self.sync.record_activity_seen(newest)
            self.emit("activity_seen", newest)
