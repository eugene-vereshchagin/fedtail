"""Other servers, asked without my token: a post's honest counts from its own server (or
my other accounts' servers), someone's posts and pinned ones from their server, a
server's public lane, an outbox."""

import logging
import time

import requests

from ..version import USER_AGENT
from . import auth, proto, remote
from .model import real
from .proto import Error as ApiError  # the protocol's error answer (core/proto.py)

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts


class OriginMixin:
    """A part of Core (core/app.py): see the module's words."""

    def _origin_get(self, url):
        """GET from someone else's server: no token, short timeout (see remote)."""
        return remote.get_json(url, headers={"User-Agent": USER_AGENT},
                               own_hosts=self._own_hosts())

    def _honest_counts(self, statuses):
        now = time.monotonic()
        fresh = []
        for st in statuses[:40]:
            sid = real(st)["id"]
            if now - self._honest_checked.get(sid, -1e9) < 600:
                continue
            url = proto.counters.origin_api_url(st, self.auth["server"])
            if not url:
                continue
            self._honest_checked[sid] = now
            try:
                origin = self._origin_get(url)
            except Exception as e:  # their server, their problems
                log.debug("honest counters %s: %s", url, e)
                origin = None
            if origin is None and self.cfg["feed"].get("counters_via_accounts", True):
                # their server won't tell a stranger: ask as one of my other accounts
                origin = self._counts_via_accounts(st, url)
            better = proto.counters.merge(st, origin)
            if better:
                fresh.append(better)
        if fresh:
            self.store.put_statuses(fresh)
            for st in fresh:  # each its own: the window redoes only the cards of each
                self.emit("status_updated", st)

    def _other_accounts(self):
        """[(server, token)] of my other logged-in profiles (not this one), looked up
        once in ten minutes."""
        now = time.monotonic()
        cached = getattr(self, "_others_cache", None)
        if cached and now - cached[0] < 600:
            return cached[1]
        from . import paths as paths_module
        from . import profiles
        out = []
        try:
            for prof in profiles.listing():
                if prof["name"] == self.paths.profile or not prof["logged_in"]:
                    continue
                a = auth.load(paths_module.resolve(prof["name"]).auth_file)
                if a and a.get("server") and a.get("token"):
                    out.append((a["server"].rstrip("/"), a["token"]))
        except Exception as e:  # noqa: BLE001 — a nicety
            log.debug("other accounts: %s", e)
        self._others_cache = (now, out)
        return out

    def _counts_via_accounts(self, status, origin_url):
        """The post as my other accounts' servers see it — the post's own server when
        one of my accounts lives there (it knows every like), or another server that
        already has the post. Each token goes only to its own server."""
        from urllib.parse import urlparse
        st = real(status)
        host = urlparse(origin_url).hostname
        best = None
        for server, token in self._other_accounts():
            # the protocol's own client for that account: its token to its server alone,
            # the answer capped and counted as every call to my servers is
            client = self.api_class(server, token)
            try:
                if urlparse(server).hostname == host:  # my account on the post's server
                    got = client.status(origin_url.rstrip("/").rsplit("/", 1)[-1])
                else:  # another server: only if it has the post already (no fetching)
                    found = client.search_statuses(st.get("uri"), limit=1)
                    got = found[0] if found else None
            except (requests.RequestException, ValueError, ApiError) as e:
                log.debug("counters via %s: %s", urlparse(server).hostname, e)
                continue
            if not isinstance(got, dict) or got.get("uri") != st.get("uri"):
                continue
            if best is None or sum(got.get(k) or 0 for k in ("favourites_count",
                                                             "reblogs_count")) > \
                    sum(best.get(k) or 0 for k in ("favourites_count", "reblogs_count")):
                best = got
        return best

    def posts_from_origin(self, acc, have_uris=()):
        """Someone from another server my server knows little about: their newest public
        posts, read from their own server's outbox (ActivityPub, without my token),
        fetched into my server by address so they are ordinary posts here — answerable,
        likeable. A future of those statuses (feed.remote_profiles)."""
        def job():
            fc = self.cfg["feed"]
            if not fc.get("remote_profiles", True) or "@" not in (acc.get("acct") or ""):
                return []
            from . import replies
            t = time.monotonic()
            outbox = self._outbox_of(acc)
            limit = min(40, int(fc.get("remote_posts", 20)))
            uris = []
            try:
                if outbox:
                    uris = replies.outbox_post_uris(self._origin_json, outbox, limit)
            except Exception as e:  # noqa: BLE001 — their server, anything goes
                log.info("profile %s: outbox: %s", acc.get("id"), e)
            have = set(have_uris)
            if not uris:  # no outbox for strangers: their public API, maybe
                uris = self._older_via_api(acc, None, have, limit, pages=1)[0]
            got = self._resolve_statuses([u for u in uris if u not in have])
            log.info("profile %s: outbox lists %d posts, %d new here, fetched in %.1f s",
                     acc.get("id"), len(uris), len(got), time.monotonic() - t)
            return got
        return self.bg.submit(job)

    def older_from_origin(self, acc, cursor=None, have_uris=(), resolve=True):
        """Further back in someone's posts than my server has (it knows only what reached
        it, mostly since someone here followed them): page by page from their own
        server's outbox, fetched into mine by address. A future of (statuses, cursor
        for the next call or None) — cursor None to start from their newest."""
        def job():
            if not self.cfg["feed"].get("remote_profiles", True) or \
                    "@" not in (acc.get("acct") or ""):
                return [], None
            from . import replies
            t = time.monotonic()
            limit = min(40, int(self.cfg["feed"].get("remote_posts", 20)))
            uris, nxt, how = [], None, "outbox"
            if not (cursor or "").startswith("api:"):
                where = cursor or self._outbox_of(acc)
                try:
                    if where:
                        uris, nxt = replies.outbox_page(self._origin_json, where, limit,
                                                        pages=5, skip=have_uris)
                except Exception as e:  # noqa: BLE001 — their server, anything goes
                    log.info("profile %s: outbox page: %s", acc.get("id"), e)
            if not uris and not nxt and (cursor is None or cursor.startswith("api:")):
                # no outbox for strangers (GoToSocial, Mastodon with authorized fetch):
                # their server's public API, if it answers without a token
                how = "api"
                uris, nxt = self._older_via_api(acc, cursor, set(have_uris), limit)
            log.info("profile %s: older from origin via %s: %d listed", acc.get("id"), how,
                     len(uris))
            if not resolve:  # the frontend fetches them a few at a time (resolve_statuses)
                return uris, nxt
            got = self._resolve_statuses(uris)
            log.info("profile %s: older from origin: %d listed, %d fetched in %.1f s, %s",
                     acc.get("id"), len(uris), len(got), time.monotonic() - t,
                     "more there" if nxt else "that's all")
            return got, nxt
        return self.bg.submit(job)

    def _older_via_api(self, acc, cursor, have, limit, pages=5):
        """Someone's public posts from their server's Mastodon API, without my token:
        (addresses, cursor "api:<their id>:<max id>" or None)."""
        from urllib.parse import urlparse
        host = next((urlparse(u).netloc for u in (acc.get("url"), acc.get("uri")) if u), "")
        if not host:
            return [], None
        try:
            if cursor:
                _api, their_id, max_id = cursor.split(":", 2)
            else:
                found = self._origin_get(proto.urls.lookup(host, acc.get("username")))
                their_id, max_id = (found or {}).get("id"), ""
                if not their_id:
                    log.info("profile %s: %s won't look them up", acc.get("id"), host)
                    return [], None
            uris = []
            for _ in range(pages):
                page = self._origin_get(proto.urls.statuses(host, their_id, max_id))
                if not isinstance(page, list) or not page:
                    log.info("profile %s: %s gave %s", acc.get("id"), host,
                             "nothing more" if page == [] else "no posts to a stranger")
                    return uris, None
                max_id = str(page[-1].get("id") or "")
                uris += [s["uri"] for s in page if s.get("uri") and s["uri"] not in have
                         and s.get("visibility") in ("public", "unlisted")]
                if len(uris) >= limit or not max_id:
                    break
            return uris, (f"api:{their_id}:{max_id}" if max_id else None)
        except Exception as e:  # noqa: BLE001 — their server, anything goes
            log.info("profile %s: %s api: %s", acc.get("id"), host, e)
            return [], None

    @staticmethod
    def server_host(text):
        from .remote import server_host
        return server_host(text)

    def remote_public(self, host, cursor=None):
        """Another server's public lane (its own people), read without an account and
        fetched into mine page by page, so each post can be liked, answered, opened as
        any other. A future of (statuses, cursor of the next page or None); LookupError
        when that server keeps its lane closed to strangers (many do; GoToSocial
        always) or isn't a server that has one."""
        def job():
            h = self.server_host(host)
            if not h:
                raise ValueError(host)
            mine = {x.lower() for x in self._own_hosts()}
            if h in mine:  # my own server: its Local, with my token
                page = self.api.local(limit=20, max_id=cursor) or []
                self.store.put_statuses(page)
                return page, (page[-1]["id"] if len(page) >= 20 else None)
            page = self._origin_get(proto.urls.public(h, cursor or ""))
            if not isinstance(page, list):
                raise LookupError(h)
            uris = [s["uri"] for s in page if isinstance(s, dict) and s.get("uri")
                    and s.get("visibility") in ("public", None)]
            nxt = str(page[-1].get("id") or "") if len(page) >= 20 else ""
            got = self._resolve_statuses(uris)
            log.info("server %s: public lane: %d listed, %d fetched", h, len(uris),
                     len(got))
            return got, (nxt or None)
        return self.bg.submit(job)

    def _outbox_of(self, acc):
        for url in (acc.get("uri"), acc.get("url")):
            if not url:
                continue
            try:
                actor = self._origin_json(url)
            except Exception as e:  # noqa: BLE001
                log.debug("actor %s: %s", url, e)
                continue
            if isinstance(actor, dict) and actor.get("outbox"):
                return actor["outbox"]
        log.info("profile %s: no outbox to read", acc.get("id"))
        return None

    def _pinned_from_origin(self, acc_id, limit=10):
        from . import replies
        try:
            acc = self.api.account(acc_id) or {}
        except ApiError:
            return []
        if "@" not in (acc.get("acct") or "") or not acc.get("uri"):
            return []  # one of my server's own: it knows their pins
        try:
            actor = self._origin_json(acc["uri"])
            featured = actor.get("featured") if isinstance(actor, dict) else None
            uris = replies.collection_items(self._origin_json, featured, pages=1) \
                if featured else []
        except Exception as e:  # noqa: BLE001 — someone else's server
            log.debug("pins of %s at their server: %s", acc_id, e)
            return []
        got = []
        for uri in uris[:limit]:
            try:
                found = self.api.search(uri, kind="statuses", resolve=True, limit=1)
            except ApiError as e:
                log.debug("resolve pin %s: %s", uri, e)
                continue
            got += [dict(st, pinned=True) for st in (found or {}).get("statuses") or []]
        log.info("pins of %s: %d at their server, %d found here", acc_id, len(uris), len(got))
        return got
