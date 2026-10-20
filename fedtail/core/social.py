"""People and reactions around posts — the parts of the Mastodon API added in 0.11:
who liked or boosted a post (also from its own server), quiet threads, direct
conversations kept read in step with the server, notifications dismissed or cleared,
removing a follower, recommending people and tags on my profile, people in common,
suggestions, the profile directory, trends, the server's rules and pages, its
preferences, reactions to announcements, quotes of my posts.

A mixin of Core (core/app.py): every method returns a future, like the rest of Core.
A server without some of this (GoToSocial lacks a good part) answers 404 and the
like: the feature is then remembered as unsupported (Core.supports) — frontends hide
it — and the future fails with NotSupported, a message for people.
"""

import logging
from urllib.parse import urlparse

import requests

from . import counters
from .api import ApiError
from .model import real

log = logging.getLogger(__name__)

UNSUPPORTED_STATUS = (404, 405, 410, 501)


class NotSupported(ApiError):
    """The server doesn't have this (feature: a short name, see Core.supports)."""

    def __init__(self, feature):
        from ..i18n import _
        super().__init__(501, _("server_cant"))
        self.feature = feature


class SocialMixin:
    # ---- what the server can do ----------------------------------------------------
    def supports(self, feature):
        """False once the server answered that it hasn't got this feature."""
        return feature not in self.unsupported

    def _api(self, feature, fn, *a, **kw):
        """Call the API; a "no such thing here" answer marks the feature unsupported."""
        try:
            return fn(*a, **kw)
        except ApiError as e:
            if e.status in UNSUPPORTED_STATUS and not isinstance(e, NotSupported):
                if feature not in self.unsupported:
                    log.info("server has no %s (%s)", feature, e.status)
                    self.unsupported.add(feature)
                    self.emit("unsupported", feature)
                raise NotSupported(feature) from e
            raise

    def _with_relations(self, accounts):
        rel = {}
        if accounts:
            try:
                rel = {r["id"]: r for r in self.api.relationships([a["id"] for a in accounts])}
            except ApiError as e:
                log.debug("relationships: %s", e)
        return {"accounts": accounts, "relations": rel}

    # ---- who liked, who boosted -----------------------------------------------------
    def who_reacted(self, status, kind, max_id=None):
        """Who liked (kind="favourited_by") or boosted ("reblogged_by") a post, as my
        server knows: ({accounts, relations}, cursor of the next page or None)."""
        s = real(status)
        fn = self.api.favourited_by if kind == "favourited_by" else self.api.reblogged_by

        def job():
            accounts, nxt = self._api(kind, fn, s["id"], max_id)
            return self._with_relations(accounts or []), nxt
        return self.submit(job)

    def who_reacted_from_origin(self, status, kind, have_ids=(), limit=40):
        """The same, as the post's own server knows it (it knows everyone; mine only
        those who reached me): read there without my token, each found through my
        server so the rows work like any other. ({accounts, relations, total}, None)."""
        s = real(status)

        def job():
            url = counters.origin_api_url(s, self.auth["server"])
            if not url:
                return {"accounts": [], "relations": {}, "total": None}, None
            theirs = self._origin_get(f"{url}/{kind}?limit=80") or []
            total = len(theirs)
            have, found = set(have_ids), []
            for a in theirs[:limit]:
                handle = a.get("acct") or ""
                if "@" not in handle:  # local to their server
                    handle = f"{handle}@{urlparse(url).hostname}"
                try:
                    got = self.api.search("@" + handle, kind="accounts", resolve=True,
                                          limit=1).get("accounts") or []
                except ApiError as e:
                    log.debug("who %s: %s: %s", kind, handle, e)
                    continue
                if got and got[0]["id"] not in have:
                    found.append(got[0])
                    have.add(got[0]["id"])
            out = self._with_relations(found)
            out["total"] = total
            return out, None
        return self.submit(job)

    # ---- quiet threads --------------------------------------------------------------
    def mute_thread(self, status, on=True):
        """No notifications from this thread any more (or again). Asked of the server
        when it can; fedtail mutes the thread itself as well (core/subs.py) — the only
        way on a server without it (GoToSocial), and it also leaves the thread's
        subscription. The status comes back with `muted` as it now is."""
        from . import subs
        s = real(status)

        def job():
            st = None
            if self.supports("mute_thread"):
                try:
                    st = self._api("mute_thread", self.api.mute_conversation, s["id"], on)
                except NotSupported:
                    pass  # remembered; muted here below
                except ApiError as e:  # not my thread, say: here it still works
                    log.info("mute thread %s on the server: %s", s["id"], e)
            if on:
                subs.leave(self.store, self.api, s, quiet=True)
            else:
                subs.unquiet(self.store, s)
            self._silence_seen = {}  # what was let through before may be muted now
            st = dict(st or s, muted=on)
            self.store.put_statuses([st])
            self.emit("status_updated", st)
            self.emit("subs_changed", None)
            if on:
                self.emit("lanes_updated", {"subs": [], "mentions": []})
            return st
        return self.submit(job)

    # ---- direct conversations: read here = read on the server -----------------------
    def sync_conversations(self):
        """What the server keeps as conversations: which of their last posts are unread.
        Called by the poll when the direct lane is on (one cheap request)."""
        if not self.supports("conversations"):
            return
        try:
            convs = self._api("conversations", self.api.conversations, 40)
        except (ApiError, requests.RequestException) as e:
            # a nicety: a slow answer here must not fail the whole poll (it did, with
            # "Read timed out" shown to the user, the lanes not fetched at all)
            log.info("conversations: %s", e.__class__.__name__)
            return
        for c in convs:
            last = c.get("last_status") or {}
            if last.get("id"):
                self._conv_of[last["id"]] = (c["id"], bool(c.get("unread")))

    def _read_conversations(self, status_ids):
        """Read here: the conversations they end are marked read on the server too."""
        todo = []
        for sid in status_ids:
            cid, unread = self._conv_of.get(sid, (None, False))
            if cid and unread:
                todo.append(cid)
                self._conv_of[sid] = (cid, False)
        if not todo or not self.supports("conversations"):
            return

        def job():
            for cid in todo:
                try:
                    self._api("conversations", self.api.read_conversation, cid)
                except ApiError as e:
                    log.debug("conversation %s read: %s", cid, e)
        self.bg.submit(job)

    # ---- notifications --------------------------------------------------------------
    def can_dismiss_one(self):
        """Can the server dismiss a single notification? GoToSocial can't (it only clears
        them all): there × hides it here only."""
        return self.supports("dismiss_one") and \
            getattr(getattr(self, "caps", None), "software", "") != "gotosocial"

    def dismiss_activity(self, nid):
        """One notification gone: from Activity always, from the server when it can."""
        def job():
            if self.can_dismiss_one():
                try:
                    self._api("dismiss_one", self.api.dismiss_notification, nid)
                except NotSupported:
                    pass  # hidden here all the same
            self.store.activity_hide([nid])
            self.emit("activity_updated", None)
        return self.submit(job)

    def answer_interaction(self, entry, approve):
        """A reply, like or boost waiting for my approval (GoToSocial's interaction
        policies): yes or no, on the server; the notification goes either way."""
        kind = entry["type"].split(".", 1)[-1]  # pending.reply -> reply
        st = entry.get("status") or {}
        who = (entry.get("account") or {}).get("id")

        def job():
            reqs = self._api("interactions", self.api.interaction_requests)
            # only the ones still waiting, and only the very one: same person, same post
            # (their reply, or my post they liked or boosted) — never "something similar"
            waiting = [r for r in reqs if not r.get("accepted_at") and not r.get("rejected_at")]
            match = next((r for r in waiting
                          if (r.get("account") or {}).get("id") == who
                          and st.get("id") in ((r.get("reply") or {}).get("id"),
                                               (r.get("status") or {}).get("id"))), None)
            found = False
            if match is None:
                log.info("interaction %s (%s by %s on %s): no request waiting; the server "
                         "lists %d, waiting %s", entry["id"], kind, who, st.get("id"),
                         len(reqs), [(r.get("type"), (r.get("account") or {}).get("id"),
                                      (r.get("status") or {}).get("id"),
                                      (r.get("reply") or {}).get("id")) for r in waiting][:10])
            else:
                try:
                    self.api.answer_interaction(match["id"], approve)
                    found = True
                    log.info("interaction %s %s: %s", match["id"], kind,
                             "approved" if approve else "rejected")
                except ApiError as e:
                    if e.status != 404:
                        raise
                    log.info("interaction %s: answered elsewhere already", match["id"])
            if self.can_dismiss_one():
                try:
                    self._api("dismiss_one", self.api.dismiss_notification, entry["id"])
                except ApiError as e:  # gone with the answer, or no such call here
                    log.debug("dismiss %s: %s", entry["id"], e)
            self.store.activity_hide([entry["id"]])
            self.emit("activity_updated", None)
            return found
        return self.submit(job)

    def clear_activity(self):
        """Every notification gone, here and on the server (for every app)."""
        def job():
            self._api("dismiss", self.api.clear_notifications)
            self.store.activity_delete()
            self.emit("activity_updated", None)
        return self.submit(job)

    # ---- people ---------------------------------------------------------------------
    def remove_follower(self, acc_id):
        """They stop following me; no block."""
        def job():
            rel = self._api("remove_follower", self.api.remove_from_followers, acc_id)
            self.emit("relation_changed", rel)
            return rel
        return self.submit(job)

    def endorse(self, acc_id, on=True):
        """Recommend someone on my profile, or stop."""
        def job():
            rel = self._api("endorse", self.api.endorse, acc_id, on)
            self.emit("relation_changed", rel)
            return rel
        return self.submit(job)

    def feature_tag(self, name, on=True):
        """A tag on my profile (featured tags), or off it."""
        name = name.lstrip("#")

        def job():
            if on:
                return self._api("featured_tags", self.api.feature_tag, name)
            mine = self._api("featured_tags", self.api.my_featured_tags)
            for t in mine:
                if (t.get("name") or "").lower() == name.lower():
                    self.api.unfeature_tag(t["id"])
            return None
        return self.submit(job)

    def featured_tag_names(self):
        """My featured tags' names, lowercase (a future of a set)."""
        def job():
            return {(t.get("name") or "").lower()
                    for t in self._api("featured_tags", self.api.my_featured_tags)}
        return self.submit(job)

    def familiar(self, acc_id):
        """Of the people I follow, who follows this account too (a future of a list)."""
        def job():
            got = self._api("familiar", self.api.familiar_followers, [acc_id])
            return next((x.get("accounts") or [] for x in got if x.get("id") == acc_id), [])
        return self.submit(job)

    def suggestions(self, _cursor=None):
        """Whom my server suggests following: ({accounts, relations}, None)."""
        def job():
            got = self._api("suggestions", self.api.suggestions, 40)
            return self._with_relations([x["account"] for x in got if x.get("account")]), None
        return self.submit(job)

    def dismiss_suggestion(self, acc_id):
        return self.submit(self._api, "suggestions", self.api.dismiss_suggestion, acc_id)

    def directory(self, offset=None, local=False):
        """The profile directory, a page at a time: ({accounts, relations}, next offset)."""
        offset = int(offset or 0)

        def job():
            got = self._api("directory", self.api.directory, offset, local)
            return self._with_relations(got), (offset + len(got) if got else None)
        return self.submit(job)

    # ---- trends ---------------------------------------------------------------------
    def trends(self):
        """{"statuses": [...], "tags": [...], "links": [...]} — what's talked about on my
        server; a kind it doesn't have is []."""
        def job():
            out = {}
            for kind in ("statuses", "tags", "links"):
                try:
                    out[kind] = self._api("trends_" + kind, self.api.trends, kind) or []
                except ApiError as e:
                    log.debug("trends %s: %s", kind, e)
                    out[kind] = []
            if not any(out.values()) and all(not self.supports("trends_" + k)
                                              for k in out):
                raise NotSupported("trends")
            self.store.put_statuses(out["statuses"])
            return out
        return self.submit(job)

    # ---- the server -----------------------------------------------------------------
    def server_info(self):
        """About my server: {instance, rules, about (HTML), privacy (HTML)}."""
        def job():
            out = {"instance": self.api.instance() or {}}
            for key, fn in (("rules", self.api.instance_rules),
                            ("about", lambda: self.api.instance_page("extended_description")),
                            ("privacy", lambda: self.api.instance_page("privacy_policy"))):
                try:
                    got = fn()
                    out[key] = got if key == "rules" else (got or {}).get("content") or ""
                except ApiError as e:
                    log.debug("server info %s: %s", key, e)
                    out[key] = [] if key == "rules" else ""
            return out
        return self.submit(job)

    def probe_server(self):
        """Ask my server what it can do (core/probe.py). Future: the round's result,
        kept for next time; the features it answered for are offered — or not — from now."""
        from . import probe

        def job():
            got = probe.run(self.api, self.caps)
            for feature, there in probe.features(got).items():
                if there:
                    self.unsupported.discard(feature)
                elif feature not in self.unsupported:
                    self.unsupported.add(feature)
                    self.emit("unsupported", feature)
            self.store.kv_set(probe.KV, got)
            return got
        return self.submit(job)

    def last_probe(self):
        """The last round of probe_server, or None (never checked)."""
        from . import probe
        return self.store.kv_get(probe.KV)

    def load_preferences(self):
        """The preferences I set on the server's web side, kept in self.server_prefs
        (default visibility for post.default_visibility = "server", and the like)."""
        try:
            self.server_prefs = self._api("preferences", self.api.preferences) or {}
        except Exception as e:  # noqa: BLE001 — a nicety: never in the way of connecting
            log.debug("preferences: %s", e)
            self.server_prefs = {}
        return self.server_prefs

    def react_announcement(self, aid, name, on=True):
        return self.submit(self._api, "announcement_reactions", self.api.react_announcement,
                           aid, name, on)

    # ---- quotes of my posts ---------------------------------------------------------
    def quotes_of(self, status, max_id=None):
        """Posts quoting this post of mine: (statuses, cursor or None)."""
        s = real(status)

        def job():
            got, nxt = self._api("quotes", self.api.quotes, s["id"], max_id)
            self.store.put_statuses(got or [])
            return got or [], nxt
        return self.submit(job)

    def revoke_quote(self, my_status, quoting):
        """My post out of someone's quote of it."""
        mine, theirs = real(my_status), real(quoting)

        def job():
            st = self._api("quotes", self.api.revoke_quote, mine["id"], theirs["id"])
            if st:
                self.store.put_statuses([st])
                self.emit("status_updated", st)
            return st
        return self.submit(job)
