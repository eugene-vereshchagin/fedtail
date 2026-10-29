"""Wider than my server knows (docs/en/dev/feeds.md §11, 1): Federated and the lanes of
tags also take what other servers show anyone — their public lane (lanes.federated_extra),
a tag's public lane (lanes.tags_extra). Read without an account and without my token
(core/remote.py), each new post is fetched into my server by its address (a search with
resolve), so it is an ordinary post here: liked, answered, opened like any other — and my
server knows it from then on (its own Federated and tag lanes show it too).

Gently: a server at most every lanes.extra_minutes, a few posts each time
(PER_ROUND), the addresses already fetched remembered; a server whose lanes are closed to
strangers (GoToSocial's are, many Mastodons') is left alone for a while. In the
background pool; the poll only asks whether something is due.
"""

from __future__ import annotations

import logging
import time

from ..protocols.mastodon.api import public_url as _public_url
from ..protocols.mastodon.api import tag_url
from . import taggroups

log = logging.getLogger(__name__)

PER_ROUND = 20      # posts fetched into my server from one server's lane, a round
SEEN_KEEP = 5000    # addresses already fetched, remembered
CLOSED_S = 6 * 3600  # a lane closed to strangers: asked again after this


def public_url(host, limit=40):
    """Their public lane: their own people's posts, as anyone sees it."""
    return _public_url(host, local=True, limit=limit)


class Wider:
    def __init__(self, core):
        self.core = core
        self.store = core.store
        self.running = False

    @property
    def cfg(self):
        return self.core.cfg["lanes"]

    def _hosts(self, key):
        mine = {h.lower() for h in self.core._own_hosts()}
        out = []
        for h in self.cfg.get(key) or ():
            h = self.core.server_host(str(h)) or ""
            if h and h.lower() not in mine and h not in out:
                out.append(h)
        return out

    # ---- when ----------------------------------------------------------------------------
    def _due(self, what):
        every = max(1, int(self.cfg.get("extra_minutes", 10))) * 60
        at = (self.store.kv_get("wider.at", {}) or {}).get(what, 0)
        return time.time() - float(at or 0) >= every

    def _done(self, what):
        at = dict(self.store.kv_get("wider.at", {}) or {})
        at[what] = time.time()
        self.store.kv_set("wider.at", at)

    def work(self, federated_open):
        """[(what, host, stream, tag)] due now: the federated stream's while a lane on it is
        open (it is browsed),
        the lanes of tags' always (they are read through)."""
        out = []
        if federated_open:  # a lane on the federated source is open (whatever its name)
            out += [("fed", h, "federated", "") for h in self._hosts("federated_extra")]
        tag_hosts = self._hosts("tags_extra")
        for g in getattr(self.core, "tag_groups", None) or ():
            lane = taggroups.lane_name(g)
            if lane not in self.core.lane_by_name:
                continue
            for tag in list(g.get("any") or ()) + list(g.get("all") or ())[:1]:
                out += [("tag", h, lane, tag) for h in tag_hosts]
        closed = self.store.kv_get("wider.closed", {}) or {}
        now = time.time()
        return [w for w in out if self._due(self._what(w))
                and now - float(closed.get(f"{w[0]}:{w[1]}", 0)) >= CLOSED_S]

    @staticmethod
    def _what(w):
        kind, host, lane, tag = w
        return f"{kind}:{host}:{tag}" if tag else f"{kind}:{host}"

    def due(self, federated_open):
        return not self.running and bool(self.core.me) and bool(self.work(federated_open))

    # ---- doing ---------------------------------------------------------------------------
    def run(self, federated_open):
        """One round over what is due. → {lane: [new item ids]} (also said: lanes_updated)."""
        if self.running:
            return {}
        self.running = True
        got = {}
        try:
            for w in self.work(federated_open):
                self._done(self._what(w))
                try:
                    ids = self._one(*w)
                except LookupError:
                    closed = dict(self.store.kv_get("wider.closed", {}) or {})
                    closed[f"{w[0]}:{w[1]}"] = time.time()
                    self.store.kv_set("wider.closed", closed)
                    log.info("wider: %s keeps its %s lane closed to strangers", w[1],
                             "tag" if w[0] == "tag" else "public")
                    continue
                except Exception as e:  # noqa: BLE001 — their server: anything goes
                    log.info("wider: %s %s: %s", w[1], w[3] or "public", e)
                    continue
                if ids:
                    got.setdefault(w[2], []).extend(ids)
        finally:
            self.running = False
        if got:  # by stream: to the lanes those streams fill (lanes_fed_by), not by name
            self.core.emit("lanes_updated", {
                n: ids for stream, ids in got.items()
                for n in (self.core.lanes_fed_by(stream) or [stream])})
        return got

    def remote_lane(self, host):
        """A lane of rules' source remote:<host>: that server's public lane, its new
        posts fetched into mine (a few a round) — [statuses], or [] when it's closed."""
        h = self.core.server_host(host) or ""
        if not h or not self._due(f"src:{h}"):  # gently: lanes.extra_minutes
            return []
        self._done(f"src:{h}")
        page = self.core._origin_get(public_url(h))
        if not isinstance(page, list):
            return []
        seen = list(self.store.kv_get("wider.seen", []) or ())
        known = set(seen)
        uris = [s["uri"] for s in page if isinstance(s, dict) and s.get("uri")
                and s.get("visibility") in ("public", None) and s["uri"] not in known]
        uris = uris[:PER_ROUND]
        if not uris:
            return []
        got = self.core._resolve_statuses(uris)
        self.store.kv_set("wider.seen", (seen + uris)[-SEEN_KEEP:])
        return got

    def rss_feed(self, url):
        """A lane of rules' source rss:<address>: the feed's items as posts (core/rss.py),
        asked gently — at most every lanes.extra_minutes; [] in between."""
        if not self._due(f"rss:{url}"):
            return []
        self._done(f"rss:{url}")
        from . import rss
        return rss.fetch(url, own_hosts=self.core._own_hosts())

    def _one(self, kind, host, lane, tag):
        url = tag_url(host, tag) if kind == "tag" else public_url(host)
        page = self.core._origin_get(url)
        if not isinstance(page, list):
            raise LookupError(host)
        seen = list(self.store.kv_get("wider.seen", []) or ())
        known = set(seen)
        uris = [s["uri"] for s in page if isinstance(s, dict) and s.get("uri")
                and s.get("visibility") in ("public", None) and s["uri"] not in known]
        uris = uris[:PER_ROUND]
        if not uris:
            return []
        statuses = self.core._resolve_statuses(uris)
        seen = (seen + uris)[-SEEN_KEEP:]
        self.store.kv_set("wider.seen", seen)
        if kind == "tag":
            spec = taggroups.spec_of(lane) or {}
            statuses = [st for st in statuses if taggroups.matches(st, spec)]
        from .sources import _status_entry
        entries = [e for e in (_status_entry(st) for st in statuses) if e]
        new = self.store.put_items(lane, entries)
        log.info("wider: %s %s: %d listed new, %d fetched, %d into %s", host,
                 f"#{tag}" if tag else "public", len(uris), len(statuses), len(new), lane)
        return new


__all__ = ["Wider", "public_url", "tag_url"]
