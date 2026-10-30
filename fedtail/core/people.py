"""People: their accounts and my relationship to them, following (and what changed
elsewhere), whom I follow for the rules, my own names and colours for them, "not in
Home", the bell, finding them."""

import logging
import time

from .proto import Error as ApiError  # the protocol's error answer (core/proto.py)
from .store import now_iso

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts


class PeopleMixin:
    """A part of Core (core/app.py): see the module's words."""

    FOLLOWING_EVERY_S = 6 * 3600


    def _refresh_following(self):
        """Whom I follow and which tags, for atoms like author = "followed" (every 6 hours;
        kept in the store between runs)."""
        if self._following is None:
            kept = self.store.kv_get("custom_following") or {}
            self._following = set(kept.get("ids") or ())
            self._following_at = float(kept.get("at") or 0)
            if kept.get("tags") is not None and \
                    getattr(self, "_followed_tag_names", None) is None:
                self._followed_tag_names = set(kept["tags"])
        if time.time() - self._following_at < self.FOLLOWING_EVERY_S:
            return
        self._following_at = time.time()
        ids, max_id, accounts = set(), None, {}
        try:
            # feed.following_max people, 40 a page (the server's most)
            pages = max(1, -(-int(self.cfg["feed"].get("following_max", 1000)) // 40))
            for _ in range(pages):
                page, max_id = self.api.following(self.me["id"], max_id)
                ids |= {a["id"] for a in page or ()}
                accounts.update({a["id"]: a for a in page or ()})
                if not max_id or not page:
                    break
            tags = {t["name"] for t in self.api.followed_tags() or () if t.get("name")}
        except Exception as e:  # noqa: BLE001 — the old sets stay; next time
            log.info("free lanes: whom I follow: %s", e)
            return
        if (ids, tags) != (self._following, getattr(self, "_followed_tag_names", None)):
            self._world_version += 1  # the lanes' rules see another world: drawn anew
        if self._following and ids - self._following:  # followed since (here or elsewhere)
            self._my_follows([accounts[i] for i in sorted(ids - self._following)][:50])
        self._following, self._followed_tag_names = ids, tags
        self.store.kv_set("custom_following", {"ids": sorted(ids), "tags": sorted(tags),
                                               "at": self._following_at})

    def find_user(self, handle):
        """@user or user@server → the account (fetched through my server), or None."""
        def job():
            got = self.api.search("@" + handle.lstrip("@"), kind="accounts", resolve=True,
                                  limit=1)
            return (got.get("accounts") or [None])[0]
        return self.submit(job)

    def account(self, acc_id):
        return self.call_api("account", acc_id)

    def relationship(self, acc_id):
        """following, followed_by, requested, … between me and an account (and kept a
        few minutes for relation_known)."""
        def job():
            rel = self.api.relationship(acc_id)
            self._relations[acc_id] = (time.monotonic(), rel)
            return rel
        return self.submit(job)

    RELATION_KEEP_S = 300

    def relation_known(self, acc_id):
        """The relationship asked for lately, or None — for menus that open at once."""
        got = getattr(self, "_relations", {}).get(acc_id)
        if got and time.monotonic() - got[0] < self.RELATION_KEEP_S:
            return got[1]
        return None

    def follow(self, acc_id, on=True):
        """Follow or not. The server doesn't say since when I follow someone, so the
        moment it happens through fedtail is written down here (followed_since)."""
        def job():
            rel = self.api.follow(acc_id, on)
            self._relations[acc_id] = (time.monotonic(), rel)
            since = dict(self.store.kv_get("followed_at", {}) or {})
            if on:
                since.setdefault(acc_id, now_iso())
            else:
                since.pop(acc_id, None)
            self.store.kv_set("followed_at", since)
            if not on and self.cfg["feed"].get("forget_unfollowed", True):
                self._forget_in_home(acc_id)
            if self.cfg["feed"].get("follow_date_note", True):
                rel = self._note_follow(acc_id, rel, since.get(acc_id) if on else None)
            if on:
                try:
                    self._my_follows([self.api.account(acc_id)])
                except Exception as e:  # noqa: BLE001 — the follow itself is done
                    log.debug("my follow event: %s", e)
            return rel
        return self.submit(job)

    MY_FOLLOW = "fedtail.followed"  # Activity's type for "I followed someone"

    def _my_follows(self, accounts):
        """I followed these (here, or elsewhere — seen in whom I follow): a row each in
        Activity, mine (activity.my_follows) — not news, no number. One a day for each."""
        if not self.cfg["activity"].get("my_follows", True):
            return []
        from .store import MINE_EVENT
        day = now_iso()[:10]
        rows = [{"id": f"{MINE_EVENT}followed:{a['id']}:{day}", "type": self.MY_FOLLOW,
                 "account": a, "created_at": now_iso()}
                for a in accounts if isinstance(a, dict) and a.get("id")]
        new = self.store.activity_put(rows) if rows else []
        if new:
            self.emit("activity_updated", 0)
            lanes_in = {c.name: [] for c in self._event_lanes()}
            if lanes_in:
                self.emit("lanes_updated", lanes_in)
        return new

    def _forget_in_home(self, acc_id):
        """Unfollowed: their posts and boosts leave Home as they leave the server's.
        Kept, they stayed there — and showed up anew when the unfollow also took them
        out of a list that had kept them out of Home (lists.hide_members, 27.10)."""
        n = self.store.drop_items_by("home", acc_id)
        if n:
            log.info("unfollowed: %d of their posts out of Home", n)
            self.emit("lanes_updated", {lane.name: [] for lane in self.lanes
                                        if lane.source == "home"})

    UNFOLLOW_CHECK_S = 6 * 3600

    def _forget_unfollowed_elsewhere(self):
        """Unfollowed in another client or on the server's page: fedtail hears of it
        only by asking. Every few hours the people whose posts Home holds are asked
        about; who was followed last time and isn't now leaves Home. Who was never
        followed (a followed tag's posts) is never taken out: only a follow that ended."""
        me = (self.me or {}).get("id")
        authors = [a for a in self.store.authors_in("home", 400) if a != me]
        if not authors:
            return 0
        now = set()
        for i in range(0, len(authors), 40):
            chunk = authors[i:i + 40]
            rel = self.api.relationships(chunk) or []
            now |= {r["id"] for r in rel if r.get("following") or r.get("requested")}
        before = set(self.store.kv_get("home_followed", []) or [])
        gone = [a for a in authors if a in before and a not in now]
        for a in gone:
            self._forget_in_home(a)
        self.store.kv_set("home_followed", sorted(now))
        if gone:
            log.info("unfollowed elsewhere: %d account(s) out of Home", len(gone))
        return len(gone)

    def _note_follow(self, acc_id, rel, when):
        """The follow date into (or out of) my private note on them, on the server — so
        every device and client of mine sees it. A server without notes: just here."""
        from .model import note_followed, note_with_followed
        rel = rel or {}
        old = rel.get("note")
        if old is None:
            try:
                old = self.api.relationship(acc_id).get("note") or ""
            except ApiError:
                return rel
        day = when[:10] if when else None
        if when and note_followed(old):
            return rel  # followed before, unfollowed elsewhere: the first date stays
        new = note_with_followed(old, day)
        if new == (old or "").rstrip():
            return rel
        try:
            self.api.set_note(acc_id, new)
            log.info("follow date %s in the note on %s", day or "taken out", acc_id)
            return dict(rel, note=new)
        except ApiError as e:
            log.info("note on %s: %s", acc_id, e)
            return rel

    def followed_since(self, acc_id, rel=None):
        """Since when I follow them — from my note on them (any client of mine wrote it
        there through fedtail) or from what this profile saw. ISO date or None."""
        from .model import note_followed
        return note_followed((rel or {}).get("note")) or \
            (self.store.kv_get("followed_at", {}) or {}).get(acc_id)

    def follow_options(self, acc_id, reblogs=None, languages=None):
        """Their boosts shown or not, the languages read (feed.per_person_follow)."""
        def job():
            rel = self.api.follow_options(acc_id, reblogs, languages)
            self._relations[acc_id] = (time.monotonic(), rel)
            log.info("follow %s: boosts %s, languages %s", acc_id,
                     (rel or {}).get("showing_reblogs"), (rel or {}).get("languages"))
            return rel
        return self.submit(job)

    def people_aliases(self):
        """{account id: my name for them}."""
        cached = getattr(self, "_aliases_cache", None)
        if cached is None:  # asked for every card drawn: read once, again when changed
            got = self.store.kv_get("people_aliases", {}) or {}
            cached = {str(k): str(v) for k, v in got.items() if v} \
                if isinstance(got, dict) else {}
            self._aliases_cache = cached
        return dict(cached)

    def set_alias(self, acc_id, name):
        """My own name for someone ("" — theirs again): shown wherever theirs was, here
        (and on my other devices with sync.people)."""
        def job():
            now = self.people_aliases()
            name_ = str(name or "").strip()[:60]
            if name_:
                now[str(acc_id)] = name_
            else:
                now.pop(str(acc_id), None)
            self.store.kv_set("people_aliases", now)
            if self.sync:
                self.sync.record_setting("people_aliases")
            self._people_changed()
            return name_
        return self.submit(job)

    NICK_COLORS = {"red": "#d32f2f", "orange": "#ef6c00", "yellow": "#c79a00",
                   "green": "#2e7d32", "teal": "#00897b", "blue": "#1565c0",
                   "purple": "#7b1fa2", "pink": "#c2185b", "brown": "#6d4c41",
                   "gray": "#616161"}

    def people_colors(self):
        """{account id: "#rrggbb"} — my colours for people's names (people.nick_colors)."""
        cached = getattr(self, "_colors_cache", None)
        if cached is None:
            got = self.store.kv_get("people_colors", {}) or {}
            cached = {str(k): str(v) for k, v in got.items() if v} \
                if isinstance(got, dict) else {}
            self._colors_cache = cached
        return dict(cached)

    def set_nick_color(self, acc_id, color):
        """A colour for someone's name: "#rrggbb", a name of NICK_COLORS (красный,
        red…), "" — none. ValueError for what isn't a colour."""
        import re as re_
        name = str(color or "").strip().lower()
        from ..i18n import _
        words = {_("color_" + k).lower(): v for k, v in self.NICK_COLORS.items()}
        value = self.NICK_COLORS.get(name) or words.get(name) or name
        if value and not re_.fullmatch(r"#[0-9a-f]{6}", value):
            raise ValueError(_("color_bad", color=color))

        def job():
            now = self.people_colors()
            if value:
                now[str(acc_id)] = value
            else:
                now.pop(str(acc_id), None)
            self.store.kv_set("people_colors", now)
            if self.sync:
                self.sync.record_setting("people_colors")
            self._people_changed()
            return value
        return self.submit(job)

    def _people_changed(self):
        """Names or Home's people changed (here or from another device): drawn anew."""
        self._aliases_cache = None
        self._colors_cache = None
        self._lane_cache.clear()
        self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})

    def hidden_home(self):
        return set(self.store.kv_get("people.hidden_home", []) or ())

    def hide_from_home(self, acc_id, on=True):
        """Take someone's posts out of Home (on) or back, still following them: the
        Home lanes of every set say none = { author = "hidden_home" }. Here only, as the
        follow stays (a Future, like the server's actions)."""
        def job():
            now = self.hidden_home()
            (now.add if on else now.discard)(str(acc_id))
            self.store.kv_set("people.hidden_home", sorted(now))
            if self.sync:
                self.sync.record_setting("people.hidden_home")
            self._people_changed()
            return on
        return self.submit(job)

    def notify_posts(self, acc_id, on=True):
        """The bell on someone I follow: their every new post comes as a notification
        (in Likes & boosts, with activity.types including "status")."""
        return self.call_api("notify_posts", acc_id, on)

    def followed_among(self, accounts):
        """Which of these accounts I follow — why a thread I'm not subscribed to still
        reaches my Home: the server puts there replies between people I follow.
        Future: [account] in the given order, me left out."""
        mine = (self.me or {}).get("id")
        uniq = list({a["id"]: a for a in accounts if a["id"] != mine}.values())

        def job():
            if not uniq:
                return []
            rel = {r["id"]: r for r in self.api.relationships([a["id"] for a in uniq[:40]])}
            return [a for a in uniq if rel.get(a["id"], {}).get("following")]
        return self.submit(job)

    def people(self, acc_id, which, max_id=None):
        """One page of whom an account follows (which="following") or who follows
        it ("followers"), with my relationship to each: ({accounts, relations}, next)."""
        def job():
            fetch = self.api.following if which == "following" else self.api.followers
            accounts, nxt = fetch(acc_id, max_id)
            rel = {r["id"]: r for r in self.api.relationships([a["id"] for a in accounts])} \
                if accounts else {}
            return {"accounts": accounts, "relations": rel}, nxt
        return self.submit(job)

    def people_from_origin(self, acc, which, have_ids=(), limit=40):
        """Whom someone from another server follows / who follows them, as their own
        server lists it (ActivityPub, without my token), each found through my server:
        ({accounts, relations, total}, None). Lists hidden by their owner give nothing."""
        def job():
            from . import replies
            actor = None
            for url in (acc.get("uri"), acc.get("url")):
                if url:
                    try:
                        actor = self._origin_json(url)
                    except Exception as e:  # noqa: BLE001
                        log.debug("actor %s: %s", url, e)
                    if isinstance(actor, dict) and actor.get(which):
                        break
            coll_url = actor.get(which) if isinstance(actor, dict) else None
            if not coll_url:
                return {"accounts": [], "relations": {}, "total": None}, None
            coll = self._origin_json(coll_url) if isinstance(coll_url, str) else coll_url
            total = coll.get("totalItems") if isinstance(coll, dict) else None
            try:
                uris = replies.collection_items(self._origin_json, coll or {}, pages=3)
            except Exception as e:  # noqa: BLE001
                log.info("%s of %s: %s", which, acc.get("id"), e)
                uris = []
            have, found = set(have_ids), []
            for uri in uris[:limit]:
                try:
                    got = self.api.search(uri, kind="accounts", resolve=True, limit=1)
                except Exception as e:  # noqa: BLE001
                    log.debug("resolve %s: %s", uri, e)
                    continue
                for a in (got or {}).get("accounts") or []:
                    if a["id"] not in have:
                        have.add(a["id"])
                        found.append(a)
            rel = {r["id"]: r for r in self.api.relationships([a["id"] for a in found])} \
                if found else {}
            log.info("%s of %s from their server: %s listed, %d found here", which,
                     acc.get("id"), total, len(found))
            return {"accounts": found, "relations": rel, "total": total}, None
        return self.bg.submit(job)

    def search_people(self, q, limit=8):
        """Ask the server for accounts matching q (no fetching from other servers):
        a future of [(acct, display name)]."""
        def job():
            got = self.api.search(q, "accounts", resolve=False, limit=limit)
            return [(a["acct"], a.get("display_name") or "") for a in got.get("accounts") or []]
        return self.submit(job)
