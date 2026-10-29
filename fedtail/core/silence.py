"""Silence: muted and blocked people and servers, the server's filters (a hashtag muted
in one click among them), the posts I hid — what keeps the lanes clear of what I
don't want to read."""

import copy
import logging
import time

from .model import real
from .proto import Error as ApiError  # the protocol's error answer (core/proto.py)

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts


class SilenceMixin:
    """A part of Core (core/app.py): see the module's words."""

    def _refresh_silence(self):
        try:  # the server's filters, by their words (a lane's filter_context)
            got = [f for f in self.api.filters() or () if isinstance(f, dict)]
        except Exception as e:  # noqa: BLE001 — what we had stays
            log.debug("filters: %s", e)
            got = self._server_filters
        filters_changed = got != self._server_filters
        if filters_changed:
            # a copy: an API handing back objects it keeps (a cache, the tests' fake)
            # mustn't change ours under us, or the next change would look like none
            self._server_filters = copy.deepcopy(got)
            self._silence_version += 1
        muted = {a["id"] for a in self.api.mutes()}
        blocked = {a["id"] for a in self.api.blocks()}
        domains = self._domain_blocks()
        self._silence_checked = time.monotonic()
        people_changed = (muted, blocked, domains) != (self.muted, self.blocked,
                                                       self.blocked_domains)
        if people_changed:
            self.muted, self.blocked, self.blocked_domains = muted, blocked, domains
            self._silence_version += 1
        if people_changed or filters_changed and self._muted_tags_of(got) != \
                self.__dict__.get("_tags_seen_muted"):
            self._tags_seen_muted = self._muted_tags_of(got)
            self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})

    TAG_MUTE_CONTEXTS = ("home", "public", "notifications", "thread", "account")

    @staticmethod
    def _muted_tags_of(filters):
        """The tags my "hide" filters name as "#tag" — muted, whoever made the filter."""
        out = set()
        for f in filters or ():
            if (f.get("filter_action") or "warn") != "hide":
                continue
            for k in f.get("keywords") or ():
                word = str(k.get("keyword") or "").strip()
                if word.startswith("#") and len(word) > 1 and " " not in word:
                    out.add(word[1:].lower())
        return out

    def muted_tags(self):
        return self._muted_tags_of(self._server_filters)

    def tag_muted(self, name):
        return str(name or "").lstrip("#").lower() in self.muted_tags()

    TAG_FILTER = "fedtail: hashtags"  # the one filter muted tags gather in (its title)

    def mute_tag(self, name, on=True):
        """Mute a hashtag (on): "#tag" added to one filter of muted hashtags (made the
        first time, hiding in every context — as Fedilab does it); or take it off again,
        from whichever filter of mine names it (an emptied one goes). Its posts leave the
        lanes at once, those stored before too (silenced). → future of on."""
        name = str(name or "").lstrip("#").lower()
        word = "#" + name

        def job():
            filters = [f for f in self.api.filters() or () if isinstance(f, dict)]
            if on:
                if name not in self._muted_tags_of(filters):
                    mine = next((f for f in filters if f.get("title") == self.TAG_FILTER), None)
                    if mine is None:
                        self.api.create_filter(self.TAG_FILTER, [word], "hide",
                                               self.TAG_MUTE_CONTEXTS)
                    else:
                        self.api.update_filter(mine["id"], action="hide", add=(word,))
            else:
                for f in filters:
                    kws = [k for k in f.get("keywords") or ()
                           if str(k.get("keyword") or "").strip().lower() == word]
                    if not kws:
                        continue
                    if len(kws) == len(f.get("keywords") or ()):
                        self.api.delete_filter(f["id"])
                    else:
                        self.api.update_filter(f["id"], remove=tuple(k["id"] for k in kws))
            self._refresh_silence()
            return on
        return self.submit(job)

    def _domain_blocks(self):
        """My blocked servers; a server without the endpoint (GoToSocial for users) is
        asked once a run, not on every silence refresh."""
        if not self.supports("domain_blocks"):
            return self.blocked_domains
        try:
            return {d.lower() for d in self._api("domain_blocks", self.api.domain_blocks)}
        except Exception as e:  # noqa: BLE001 — not there, or down: what we had
            log.debug("domain blocks: %s", e)
            return self.blocked_domains

    def silenced(self, status):
        """Is this post hidden: its author or booster muted/blocked, or a server
        filter says "hide"?"""
        quiet = self.muted | self.blocked
        s = real(status)
        if self.hidden_posts and (s.get("id") in self.hidden_posts
                                  or status.get("id") in self.hidden_posts):
            return True
        if s["account"]["id"] in quiet or status["account"]["id"] in quiet:
            return True
        if self.blocked_domains and any(
                (a.get("acct") or "").partition("@")[2].lower() in self.blocked_domains
                for a in (s["account"], status["account"])):
            return True
        muted_tags = self.muted_tags()
        if muted_tags and any(str(t.get("name") or "").lower() in muted_tags
                              for t in s.get("tags") or () if isinstance(t, dict)):
            return True  # a tag muted by hand: hidden in arts mode too, posts stored before too
        if self.cfg["ui"]["arts_mode"]:
            return False  # server filters don't hide anything in arts mode
        return any((f.get("filter") or {}).get("filter_action") == "hide"
                   for f in s.get("filtered") or [])

    def mute(self, acc_id, on=True, duration=0, notifications=True):
        """duration: seconds until the mute ends by itself (0 — for good); notifications:
        theirs muted too, or still coming (a mute of their posts only)."""
        if not on or (not duration and notifications):
            return self._silence(self.api.mute, self.muted, acc_id, on)
        return self._silence(lambda a, o: self.api.mute(a, o, duration=duration,
                                                         notifications=notifications),
                             self.muted, acc_id, on)

    def block(self, acc_id, on=True):
        if on:
            self.derived.mark_mine(acc_id)  # a block ends their follow: my doing
        return self._silence(self.api.block, self.blocked, acc_id, on)

    def _silence(self, call, bucket, acc_id, on):
        def job():
            rel = call(acc_id, on)
            (bucket.add if on else bucket.discard)(acc_id)
            self._silence_version += 1
            self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})
            return rel
        return self.submit(job)

    def block_domain(self, domain, on=True):
        """Hide a whole server: nobody from there in any lane, no follows across."""
        domain = domain.lower()

        def job():
            self.api.block_domain(domain, on)
            (self.blocked_domains.add if on else self.blocked_domains.discard)(domain)
            self._silence_version += 1
            self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})
            return domain
        return self.submit(job)

    FILTER_POLICY = ("for_not_following", "for_not_followers", "for_new_accounts",
                     "for_private_mentions", "for_limited_accounts")

    def filtered(self):
        """Notifications my server holds back (Mastodon 4.3+). Future:
        {"policy": {key: "accept"|"filter"|"drop"} or None, "requests": [...]};
        None when the server has no such thing (GoToSocial, older Mastodon)."""
        def job():
            if not self.supports("notification_policy"):
                return None
            try:
                policy = self._api("notification_policy", self.api.notification_policy) or {}
                requests = self.api.notification_requests()
            except ApiError as e:
                log.debug("filtered notifications: %s", e)
                return None
            return {"policy": {k: policy[k] for k in self.FILTER_POLICY if k in policy},
                    "pending": (policy.get("summary") or {}).get("pending_requests_count",
                                                                 len(requests)),
                    "requests": requests}
        return self.submit(job)

    def answer_filtered(self, rid, accept):
        """Let one held-back sender through (their notifications arrive) or drop them."""
        def job():
            self.api.answer_notification_request(rid, accept)
            if accept:
                self.poll_now()
        return self.submit(job)

    def set_filter_policy(self, **changes):
        bad = {k: v for k, v in changes.items()
               if k not in self.FILTER_POLICY or v not in ("accept", "filter", "drop")}
        if bad:
            raise ValueError(f"filter policy: {bad}")
        return self.call_api("set_notification_policy", **changes)

    def filters(self):
        return self.call_api("filters")

    def silenced_people(self):
        """{"muted": [accounts], "blocked": [accounts]} for the Silence dialog."""
        def job():
            muted, blocked = self.api.mutes(), self.api.blocks()
            self.muted = {a["id"] for a in muted}
            self.blocked = {a["id"] for a in blocked}
            self.blocked_domains = self._domain_blocks()
            return {"muted": muted, "blocked": blocked,
                    "domains": sorted(self.blocked_domains)}
        return self.submit(job)

    def add_filter(self, title, keywords, action="warn", contexts=None, expires_in=None):
        """expires_in: seconds until the filter ends by itself (None — never)."""
        args = (title, keywords, action) + ((tuple(contexts),) if contexts else ())
        if expires_in:
            return self.call_api("create_filter", *args, expires_in=int(expires_in))
        return self.call_api("create_filter", *args)

    def delete_filter(self, filter_id):
        return self.call_api("delete_filter", filter_id)

    def edit_filter(self, filter_id, title=None, words=None, action=None, contexts=None,
                    expires_in=None):
        """Change a filter of mine: words — the whole list it should have now (those gone
        are dropped, the new added); expires_in: seconds from now, 0 — for good, None —
        as it was."""
        def job():
            remove, add = (), ()
            if words is not None:
                have = next((f for f in self.api.filters() or []
                             if str(f.get("id")) == str(filter_id)), None)
                if have is None:
                    raise LookupError(filter_id)
                old = {k.get("keyword"): k.get("id") for k in have.get("keywords") or ()}
                want = [w for w in dict.fromkeys(x.strip() for x in words) if w]
                remove = tuple(kid for kw, kid in old.items() if kw not in want)
                add = tuple(w for w in want if w not in old)
            return self.api.update_filter(filter_id, title=title, action=action,
                                          contexts=tuple(contexts) if contexts else None,
                                          expires_in=expires_in, add=add, remove=remove)
        return self.submit(job)

    def _hidden_authors(self):
        """Who the lanes in lists.hide_in leave out: everyone in a list
        (lists.hide_members = "all"), only in exclusive ones, or nobody."""
        which = self.cfg["lists"]["hide_members"]
        if which == "off":
            return frozenset()
        return frozenset(a for x in self.lists if which == "all" or x.get("exclusive")
                         for a in self.list_members.get(x["id"], ()))

    HIDDEN_POSTS = "fedtail: hidden posts"  # the filter "Hide this post" keeps them in

    def _hidden_filter(self, make=False):
        mine = next((f for f in self.api.filters() or []
                     if f.get("title") == self.HIDDEN_POSTS), None)
        if mine is None and make:
            mine = self.api.create_filter(self.HIDDEN_POSTS, [], "hide",
                                          ("home", "public", "thread", "account",
                                           "notifications"))
        return mine

    def _hidden_changed(self, sid, on):
        (self.hidden_posts.add if on else self.hidden_posts.discard)(sid)
        self._silence_version += 1
        self.emit("lanes_updated", {lane.name: [] for lane in self.lanes})

    def hide_post(self, status):
        """This very post out of sight everywhere (and in every client): put into a
        filter of the server's, made the first time, that hides posts one by one."""
        sid = status["id"] if isinstance(status, dict) else status

        def job():
            got = self._api("filter_status", self.api.filter_status,
                            self._hidden_filter(make=True)["id"], sid)
            self._hidden_changed(sid, True)
            return got
        return self.submit(job)

    def unhide_post(self, status):
        """The post back: out of the hidden posts' filter. True when it was there."""
        sid = status["id"] if isinstance(status, dict) else status

        def job():
            self._hidden_changed(sid, False)
            mine = self._hidden_filter()
            if mine is None:
                return False
            for fs in self.api.filter_statuses(mine["id"]) or []:
                if str(fs.get("status_id")) == str(sid):
                    self.api.unfilter_status(fs["id"])
                    return True
            return False
        return self.submit(job)
