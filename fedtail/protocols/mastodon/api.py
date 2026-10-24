"""Mastodon-compatible REST client (GoToSocial, Mastodon, Akkoma, Pleroma).

Plain blocking calls; the core runs them in worker threads.
"""

import logging
import mimetypes
import os
import re
import threading
import time
from urllib.parse import quote, urlencode, urlsplit

import requests

from ... import version
from ...core import health
from ..base import Budget, Capabilities, RateLimited, ServerError  # noqa: F401

OOB = "urn:ietf:wg:oauth:2.0:oob"
SCOPES = "read write"
USER_AGENT = version.USER_AGENT
MARKDOWN_SERVERS = ("gotosocial", "akkoma", "pleroma", "glitch")
SLOW_SECONDS = 5.0  # set from [debug] slow_request_seconds
log = logging.getLogger("fedtail.api")
# query keys that are fine in a log line (paging, kinds); anything else is left out
_SAFE_PARAMS = {"limit", "max_id", "min_id", "since_id", "local", "types[]"}


def error_text(r):
    """What went wrong, in a line: the server's own "error", or — for a page from a proxy
    in front of it (a 502 from Cloudflare when the server is down) — the reason, not the
    HTML of that page."""
    try:
        msg = r.json().get("error")
        if msg:
            return str(msg)[:300]
    except (ValueError, AttributeError):
        pass
    text = (r.text or "").strip()
    if text.startswith("<") or "<html" in text[:200].lower():
        reason = getattr(r, "reason", "") or ""
        hint = {502: "the server is down or not answering", 503: "the server is overloaded",
                504: "the server took too long"}.get(r.status_code, "")
        return " — ".join(x for x in (reason, hint) if x) or "an HTML page instead of JSON"
    return text[:300]


class ApiError(ServerError):
    """An error answer of the Mastodon API."""


# names a server's software goes by, looked for in what it says of itself
SOFTWARE = MARKDOWN_SERVERS + ("hometown", "iceshrimp", "sharkey", "firefish", "misskey")


def software_of(inst):
    """(name, sure) from the instance document. GoToSocial 0.22 says only "0.22.1+git…"
    in version: its source_url and its own keys give it away; a bare "4.3.0" is a
    guess of Mastodon (sure False: the core asks nodeinfo)."""
    inst = inst or {}
    version = str(inst.get("version", "")).lower()
    source = str(inst.get("source_url") or "").lower()
    for name in SOFTWARE:
        if name in version or name in source:
            return name, True
    conf = inst.get("configuration") or {}
    if "allow_custom_css" in (conf.get("accounts") or {}) or "account_domain" in inst:
        return "gotosocial", True
    if "mastodon" in source:
        return "mastodon", True
    return "mastodon", False


# what the server may fold into one group (the rest come one by one, as groups of one)
GROUPED_TYPES = ("favourite", "reblog", "follow")


def flatten_groups(resp):
    """/api/v2/notifications' answer ({accounts, statuses, notification_groups}) as
    v1-like notifications, one per group, newest first: its newest notification's id
    (paging goes on by notification ids), time and person, its post, and `_group`: the
    group's key, how many notifications it holds in all, and the people the server
    gave as a sample (the newest first)."""
    resp = resp if isinstance(resp, dict) else {}
    accounts = {str(a.get("id")): a for a in resp.get("accounts") or ()
                if isinstance(a, dict) and a.get("id")}
    statuses = {str(st.get("id")): st for st in resp.get("statuses") or ()
                if isinstance(st, dict) and st.get("id")}
    out = []
    for g in resp.get("notification_groups") or ():
        if not isinstance(g, dict) or not g.get("most_recent_notification_id"):
            continue
        sample = [accounts[str(i)] for i in g.get("sample_account_ids") or ()
                  if str(i) in accounts]
        n = {"id": str(g["most_recent_notification_id"]), "type": g.get("type") or "",
             "created_at": g.get("latest_page_notification_at") or "",
             "account": sample[0] if sample else {},
             "group_key": g.get("group_key") or "",
             "_group": {"key": g.get("group_key") or "",
                        "count": int(g.get("notifications_count") or 1),
                        "accounts": sample}}
        if g.get("status_id") and str(g["status_id"]) in statuses:
            n["status"] = statuses[str(g["status_id"])]
        for k in ("event", "relationship_severance_event", "moderation_warning", "report",
                  "emoji"):
            if g.get(k):
                n[k] = g[k]
        out.append(n)
    return out


def capabilities_from_instance(inst, v2=None):
    """inst: /api/v1/instance; v2: /api/v2/instance when the server has it — the v1
    document doesn't say whether it translates."""
    inst = dict(inst or {})
    v2 = v2 if isinstance(v2, dict) else {}
    if v2.get("source_url") and not inst.get("source_url"):
        inst["source_url"] = v2["source_url"]
    version = str(inst.get("version", "")).lower()
    conf = inst.get("configuration") or {}
    st = conf.get("statuses") or {}
    mimes = st.get("supported_mime_types") or []
    software, sure = software_of(inst)
    md = "text/markdown" in mimes or software in MARKDOWN_SERVERS or \
        any(s in version for s in MARKDOWN_SERVERS)
    return Capabilities(
        software=software,
        software_sure=sure,
        version=str(inst.get("version", ""))[:80],
        max_characters=int(st.get("max_characters") or inst.get("max_toot_chars") or 500),
        max_media=int(st.get("max_media_attachments") or 4),
        max_poll_options=int((conf.get("polls") or {}).get("max_options") or 4),
        translation=bool((conf.get("translation") or {}).get("enabled") or
                         ((v2.get("configuration") or {}).get("translation") or {})
                         .get("enabled")),
        markdown=md,
        streaming=str((inst.get("urls") or {}).get("streaming_api") or
                      ((conf.get("urls") or {}).get("streaming")) or ""),
        image_bytes=int((conf.get("media_attachments") or {}).get("image_size_limit") or 0),
        image_pixels=int((conf.get("media_attachments") or {}).get("image_matrix_limit") or 0),
    )


def _when_reset(value):
    """X-RateLimit-Reset as a unix time: an ISO time (Mastodon, GoToSocial), a unix time,
    or seconds from now."""
    if not value:
        return time.time() + 60
    value = str(value).strip()
    try:
        n = float(value)
        return n if n > 10**9 else time.time() + n
    except ValueError:
        pass
    try:
        from datetime import datetime
        return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return time.time() + 60


def _retry_after(headers):
    try:
        return max(5.0, float(headers.get("Retry-After") or 60))
    except ValueError:
        return 60.0


def seg(value):
    """An id as one segment of an API path: whatever it holds ("1/../../statuses/2/
    reblog", "?x", "#") can't become another path. Server ids (digits, ULIDs) pass as
    they are."""
    from urllib.parse import quote
    value = str(value)
    if value in ("", ".", ".."):
        raise ValueError(f"bad id {value!r}")
    return quote(value, safe="")


# ---- someone else's server, asked without my token (core: honest counters, profiles) ----
def search_url(server):
    """Another server of mine: the search there (for a post it already has)."""
    return server.rstrip("/") + "/api/v2/search"


def lookup_url(host, username):
    """A stranger's server: who is username there."""
    from urllib.parse import quote
    return f"https://{host}/api/v1/accounts/lookup?acct=" + quote(username or "")


def statuses_url(host, their_id, max_id=""):
    """A stranger's server: someone's public posts, own ones only, page after max_id."""
    from urllib.parse import quote
    return (f"https://{host}/api/v1/accounts/{quote(str(their_id))}/statuses"
            "?limit=40&exclude_reblogs=true" + (f"&max_id={quote(max_id)}" if max_id else ""))


def cleartext_ok(server):
    """May a token go to this server: https always; http only to a server here or at
    home — localhost, a loopback or private address, a .local/.lan/.home.arpa name."""
    import ipaddress
    from urllib.parse import urlsplit
    server = (server or "").strip()
    if not server.lower().startswith("http://"):
        return True  # https://, or no scheme: Api makes it https
    host = (urlsplit(server).hostname or "").rstrip(".").lower()
    if host == "localhost" or host.endswith((".localhost", ".local", ".lan", ".home.arpa",
                                             ".internal")):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_loopback or ip.is_private or ip.is_link_local


class Api:
    has_stream = True  # a live stream to connect to (core/stream.py); fakes say no
    def __init__(self, server, token=None, session=None):
        server = server.strip().rstrip("/")
        if not server.startswith(("http://", "https://")):
            server = "https://" + server
        self.base = server
        self.host = (urlsplit(server).hostname or "?").lower()  # for health.REC
        self._last = threading.local()  # the latest response's headers, per thread
        self.budget = Budget()  # the server's rate limit, as its latest answer said
        self.requests = 0       # made so far (the core paces its polls by it)
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"

    # ---- plumbing ---------------------------------------------------------
    def _req(self, method, path, **kw):
        kw.setdefault("timeout", 30)
        if self.budget.spent():  # it would only say 429: don't ask until the window ends
            raise RateLimited("rate limit reached (waiting for the server's window)",
                              self.budget.reset)
        self.requests += 1
        params = kw.get("params") or {}
        shown = " ".join(f"{k}={v}" for k, v in params.items() if k in _SAFE_PARAMS)
        t = time.monotonic()
        try:
            r = self.s.request(method, self.base + path, **kw)
        except requests.RequestException as e:
            log.warning("%s %s %s -> %s after %.2f s", method, path, shown,
                        e.__class__.__name__, time.monotonic() - t)
            health.REC.note(self.host, method, path, health.outcome_of(e))
            raise
        took = time.monotonic() - t
        health.REC.note(self.host, method, path, r.status_code, took)
        # path, paging and timing only: never the token, a body or a post's text
        log.log(logging.WARNING if took > SLOW_SECONDS or r.status_code >= 400
                else logging.DEBUG, "%s %s %s -> %s %.2f s %d B", method, path, shown,
                r.status_code, took, len(r.content or b""))
        self._last.headers = r.headers
        self._note_budget(r.headers)
        if r.status_code == 429:
            until = self.budget.reset if self.budget.reset > time.time() else \
                time.time() + _retry_after(r.headers)
            self.budget = Budget(self.budget.limit, 0, until)
            raise RateLimited(error_text(r), until)
        if r.status_code >= 400:
            raise ApiError(r.status_code, error_text(r))
        if not r.content:
            return None
        return r.json()

    def _note_budget(self, headers):
        """X-RateLimit-Limit / -Remaining / -Reset (Mastodon, GoToSocial, Akkoma)."""
        rem = headers.get("X-RateLimit-Remaining")
        if rem is None:
            return
        try:
            self.budget = Budget(int(headers.get("X-RateLimit-Limit") or 0), int(rem),
                                 _when_reset(headers.get("X-RateLimit-Reset")))
        except ValueError:
            pass

    def get(self, path, params=None, timeout=30):
        return self._req("GET", path, params=params, timeout=timeout)

    def post(self, path, json=None, data=None, files=None, headers=None, timeout=30):
        return self._req("POST", path, json=json, data=data, files=files, headers=headers,
                         timeout=timeout)

    def delete(self, path):
        return self._req("DELETE", path)

    def put(self, path, data=None):
        return self._req("PUT", path, data=data)

    def patch(self, path, data=None, files=None):
        return self._req("PATCH", path, data=data, files=files)

    @staticmethod
    def _page(limit, max_id=None, min_id=None, **extra):
        p = {"limit": limit}
        if max_id:
            p["max_id"] = max_id
        if min_id:
            p["min_id"] = min_id
        p.update({k: v for k, v in extra.items() if v is not None})
        return p

    # ---- auth ---------------------------------------------------------------
    def register_app(self, scopes=SCOPES, name="fedtail", redirect=OOB):
        """redirect: where the server sends the code — OOB (it shows it, the user pastes
        it) or an app's own address (fedtail://oauth on a phone)."""
        return self.post("/api/v1/apps", data={
            "client_name": name,
            "redirect_uris": redirect,
            "scopes": scopes,
            "website": version.HOMEPAGE,
        })

    def authorize_url(self, client_id, scopes=SCOPES, redirect=OOB):
        q = urlencode({"client_id": client_id, "redirect_uri": redirect,
                       "response_type": "code", "scope": scopes})
        return f"{self.base}/oauth/authorize?{q}"

    def get_token(self, client_id, client_secret, code, scopes=SCOPES, redirect=OOB):
        res = self.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect,
            "code": code.strip(),
            "scope": scopes,
        })
        return res["access_token"]

    def revoke(self, client_id, client_secret, token):
        """The token is no good any more, on the server too (logging out, logging in
        anew). Short: nobody waits on it."""
        return self._req("POST", "/oauth/revoke", timeout=(5, 5), data={
            "client_id": client_id, "client_secret": client_secret, "token": token})

    # ---- reading ------------------------------------------------------------
    def verify_credentials(self):
        """My account with `source`: the bio and fields as I typed them."""
        return self.get("/api/v1/accounts/verify_credentials")

    def update_credentials(self, display_name=None, note=None, fields=None, locked=None,
                           bot=None, discoverable=None, avatar=None, header=None,
                           hide_collections=None, indexable=None, attribution_domains=None):
        """Change my profile. fields: [(name, value)] up to the server's limit;
        avatar/header: paths of new pictures; hide_collections: whom I follow and who
        follows me hidden; indexable: my public posts found by a search of words;
        attribution_domains: sites that may name me the author of their articles
        (Mastodon 4.4). None leaves a thing as it is."""
        data = {}
        for key, val in (("display_name", display_name), ("note", note)):
            if val is not None:
                data[key] = val
        for key, val in (("locked", locked), ("bot", bot), ("discoverable", discoverable),
                         ("hide_collections", hide_collections), ("indexable", indexable)):
            if val is not None:
                data[key] = "true" if val else "false"
        if attribution_domains is not None:
            # an empty list clears it: a form sends nothing for an empty array
            data["attribution_domains[]"] = list(attribution_domains) or [""]
        if fields is not None:
            for i, (name, value) in enumerate(fields):
                data[f"fields_attributes[{i}][name]"] = name
                data[f"fields_attributes[{i}][value]"] = value
        files, opened = {}, []
        try:
            for key, path in (("avatar", avatar), ("header", header)):
                if path:
                    f = open(path, "rb")  # noqa: SIM115 — closed below
                    opened.append(f)
                    # its name only: never a folder of this machine (Windows paths have
                    # backslashes — split on "/" sent the whole of it to the server)
                    files[key] = (os.path.basename(path), f)
            return self.patch("/api/v1/accounts/update_credentials", data=data,
                              files=files or None)
        finally:
            for f in opened:
                f.close()

    def me(self):
        return self.get("/api/v1/accounts/verify_credentials")

    def instance(self):
        return self.get("/api/v1/instance")

    def instance_v2(self):
        """The newer instance document: says whether the server translates, and where its
        source lives (source_url: what software it is). None on servers without it."""
        try:
            return self.get("/api/v2/instance", timeout=15)
        except ApiError:
            return None

    def home(self, limit=40, max_id=None, min_id=None):
        return self.get("/api/v1/timelines/home", self._page(limit, max_id, min_id))

    def local(self, limit=40, max_id=None, min_id=None):
        return self.get("/api/v1/timelines/public",
                        self._page(limit, max_id, min_id, local="true"))

    def federated(self, limit=40, max_id=None, min_id=None):
        """The whole fediverse as this server knows it."""
        return self.get("/api/v1/timelines/public", self._page(limit, max_id, min_id))

    def account_statuses(self, acc_id, limit=40, max_id=None, min_id=None,
                         exclude_replies=False, only_media=False, tagged=None,
                         exclude_reblogs=False):
        """Someone's posts, newest first; the server filters: without replies (its own
        threads still come), only with pictures, only with a tag, without boosts."""
        extra = {"exclude_replies": "true" if exclude_replies else None,
                 "only_media": "true" if only_media else None,
                 "exclude_reblogs": "true" if exclude_reblogs else None,
                 "tagged": tagged.lstrip("#") if tagged else None}
        return self.get(f"/api/v1/accounts/{seg(acc_id)}/statuses",
                        self._page(limit, max_id, min_id, **extra))

    def notification_policy(self):
        return self.get("/api/v2/notifications/policy")

    def set_notification_policy(self, **fields):
        return self.patch("/api/v2/notifications/policy", data=fields)

    def notification_requests(self):
        return self.get("/api/v1/notifications/requests", {"limit": 40}) or []

    def answer_notification_request(self, rid, accept):
        return self.post(f"/api/v1/notifications/requests/{seg(rid)}/"
                         + ("accept" if accept else "dismiss"))

    def announcements(self):
        return self.get("/api/v1/announcements") or []

    def dismiss_announcement(self, aid):
        return self.post(f"/api/v1/announcements/{seg(aid)}/dismiss")

    def scheduled(self):
        return self.get("/api/v1/scheduled_statuses", {"limit": 40}) or []

    def cancel_scheduled(self, sid):
        return self.delete(f"/api/v1/scheduled_statuses/{seg(sid)}")

    def domain_blocks(self):
        return self.get("/api/v1/domain_blocks", {"limit": 200}) or []

    def block_domain(self, domain, on=True):
        return self._req("POST" if on else "DELETE", "/api/v1/domain_blocks",
                         params={"domain": domain})

    def set_note(self, acc_id, text):
        """My private note on someone (only I see it)."""
        return self.post(f"/api/v1/accounts/{seg(acc_id)}/note", json={"comment": text})

    def translate(self, sid, lang=None):
        """{content, spoiler_text, detected_source_language, provider} in my language."""
        return self.post(f"/api/v1/statuses/{seg(sid)}/translate",
                         json={"lang": lang} if lang else None)

    def report(self, acc_id, status_ids=(), comment="", forward=False, category="other",
               rule_ids=()):
        """category "violation" names the server's rules broken (rule_ids)."""
        body = {"account_id": acc_id, "status_ids": list(status_ids), "comment": comment,
                "forward": bool(forward), "category": category}
        if rule_ids:
            body["category"] = "violation"
            body["rule_ids"] = [str(r) for r in rule_ids]
        return self.post("/api/v1/reports", json=body)

    def pinned(self, acc_id):
        return self.get(f"/api/v1/accounts/{seg(acc_id)}/statuses", {"pinned": "true"}) or []

    def custom_emojis(self):
        return self.get("/api/v1/custom_emojis") or []

    def featured_tags(self, acc_id):
        return self.get(f"/api/v1/accounts/{seg(acc_id)}/featured_tags") or []

    def endorsements(self, acc_id):
        return self.get(f"/api/v1/accounts/{seg(acc_id)}/endorsements", {"limit": 40}) or []

    def pin(self, sid, on=True):
        return self.post(f"/api/v1/statuses/{seg(sid)}/{'pin' if on else 'unpin'}")

    def mentions(self, limit=40, max_id=None, min_id=None):
        p = self._page(limit, max_id, min_id)
        p["types[]"] = ["mention"]
        return self.get("/api/v1/notifications", p)

    def notifications(self, types, limit=40, max_id=None, min_id=None):
        p = self._page(limit, max_id, min_id)
        p["types[]"] = list(types)
        return self.get("/api/v1/notifications", p)

    def notification_groups(self, types, limit=40, max_id=None, min_id=None,
                            grouped=GROUPED_TYPES):
        """Mastodon 4.3+: the server's own groups (/api/v2/notifications) — 300 likes of
        one post are one group with its count and the latest few people, not 300
        notifications in eight pages. Returned flattened, one v1-like notification per
        group (flatten_groups), so the store and the rest take them as they are."""
        p = self._page(limit, max_id, min_id)
        p["types[]"] = list(types)
        p["grouped_types[]"] = list(grouped)
        return flatten_groups(self.get("/api/v2/notifications", p))

    def dismiss_notification_group(self, key):
        return self.post(f"/api/v2/notifications/{seg(key)}/dismiss")

    def status(self, sid):
        return self.get(f"/api/v1/statuses/{seg(sid)}")

    def context(self, sid):
        return self.get(f"/api/v1/statuses/{seg(sid)}/context")

    def last_async_refresh(self):
        """After a request in this thread: Mastodon 4.5+'s "I'm fetching more of this
        in the background" (Mastodon-Async-Refresh: id="…", retry=N) as (id, seconds),
        or None."""
        raw = (getattr(self._last, "headers", None) or {}).get("Mastodon-Async-Refresh")
        if not raw:
            return None
        m = re.search(r'id="([^"]+)"', raw)
        retry = re.search(r"retry=(\d+)", raw)
        return (m.group(1), int(retry.group(1)) if retry else 3) if m else None

    def async_refresh(self, refresh_id):
        """"running" or "finished" (an experimental Mastodon endpoint)."""
        got = self.get(f"/api/v1_alpha/async_refreshes/{refresh_id}") or {}
        return (got.get("async_refresh") or {}).get("status", "finished")

    def follow_requests(self):
        return self.get("/api/v1/follow_requests", {"limit": 80})

    # ---- people, tags, search -------------------------------------------------
    def relationship(self, acc_id):
        got = self.get("/api/v1/accounts/relationships", {"id[]": [acc_id]}) or []
        return got[0] if got else {}

    def follow(self, acc_id, on=True):
        return self.post(f"/api/v1/accounts/{seg(acc_id)}/{'follow' if on else 'unfollow'}")

    def tag_timeline(self, tag, limit=40, max_id=None, min_id=None):
        return self.get(f"/api/v1/timelines/tag/{quote(tag, safe='')}",
                        self._page(limit, max_id, min_id))

    def get_page(self, path, params=None):
        """GET a list that pages by the Link header (followers, following):
        returns (items, max_id for the next page or None)."""
        r = self.s.get(self.base + path, params=params, timeout=30)
        if r.status_code >= 400:
            raise ApiError(r.status_code, error_text(r))
        log.debug("GET %s -> %s %d B", path, r.status_code, len(r.content or b""))
        nxt = (r.links or {}).get("next", {}).get("url", "")
        m = re.search(r"[?&]max_id=([^&]+)", nxt)
        return r.json() or [], (m.group(1) if m else None)

    def following(self, acc_id, max_id=None):
        return self.get_page(f"/api/v1/accounts/{seg(acc_id)}/following",
                             self._page(40, max_id))

    def followers(self, acc_id, max_id=None):
        return self.get_page(f"/api/v1/accounts/{seg(acc_id)}/followers",
                             self._page(40, max_id))

    def relationships(self, ids):
        return self.get("/api/v1/accounts/relationships", {"id[]": list(ids)}) or []

    def tag(self, name):
        """{name, url, history, following} — whether I follow the tag."""
        return self.get(f"/api/v1/tags/{quote(name, safe='')}")

    def follow_tag(self, name, on=True):
        return self.post(f"/api/v1/tags/{quote(name, safe='')}/"
                         f"{'follow' if on else 'unfollow'}")

    def markers(self, timelines=("home", "notifications")):
        """Where the reader stopped, shared by every client: {timeline: {last_read_id}}."""
        return self.get("/api/v1/markers", {"timeline[]": list(timelines)}) or {}

    def set_markers(self, positions):
        """positions: {timeline: last_read_id}."""
        data = {f"{tl}[last_read_id]": last for tl, last in positions.items()}
        return self.post("/api/v1/markers", data=data)

    def followed_tags(self):
        return self.get("/api/v1/followed_tags", {"limit": 200}) or []

    def account(self, acc_id):
        return self.get(f"/api/v1/accounts/{seg(acc_id)}")

    def search(self, q, kind=None, resolve=True, limit=5):
        """Ask my server to find (and fetch from its home, if needed) an address."""
        p = {"q": q, "resolve": "true" if resolve else "false", "limit": limit}
        if kind:
            p["type"] = kind
        return self.get("/api/v2/search", p) or {}

    # ---- silence: mute, block, filters ------------------------------------------
    def mute(self, acc_id, on=True, duration=0, notifications=True):
        """duration: seconds until it ends by itself (0 — for good); notifications:
        theirs muted too (the server's default) or still coming."""
        if not on:
            return self.post(f"/api/v1/accounts/{seg(acc_id)}/unmute")
        body = {"notifications": bool(notifications)}
        if duration:
            body["duration"] = int(duration)
        return self.post(f"/api/v1/accounts/{seg(acc_id)}/mute", json=body)

    def block(self, acc_id, on=True):
        return self.post(f"/api/v1/accounts/{seg(acc_id)}/{'block' if on else 'unblock'}")

    def _all_pages(self, path, pages=10):
        out, cursor = [], None
        for _ in range(pages):
            items, cursor = self.get_page(path, self._page(80, cursor))
            out += items
            if not cursor or len(items) < 80:  # a page not full is the last one
                break
        return out

    def mutes(self):
        return self._all_pages("/api/v1/mutes")

    def blocks(self):
        return self._all_pages("/api/v1/blocks")

    def filters(self):
        return self.get("/api/v2/filters") or []

    def create_filter(self, title, keywords, action="warn", contexts=("home", "public",
                                                                       "thread", "account"),
                      expires_in=None):
        """expires_in: seconds until the filter ends by itself (None — never)."""
        data = {"title": title, "filter_action": action, "context[]": list(contexts)}
        if expires_in:
            data["expires_in"] = str(int(expires_in))
        for i, word in enumerate(keywords):
            data[f"keywords_attributes[{i}][keyword]"] = word
            data[f"keywords_attributes[{i}][whole_word]"] = "true"
        return self.post("/api/v2/filters", data=data)

    def delete_filter(self, filter_id):
        return self.delete(f"/api/v2/filters/{seg(filter_id)}")

    def update_filter(self, filter_id, title=None, action=None, contexts=None,
                      expires_in=None, add=(), remove=()):
        """Change a filter: its title, what it does, where, how long (expires_in: seconds,
        0 — for good); add: words to add; remove: ids of its keywords to drop."""
        data = {}
        if title is not None:
            data["title"] = title
        if action is not None:
            data["filter_action"] = action
        if contexts is not None:
            data["context[]"] = list(contexts)
        if expires_in is not None:
            data["expires_in"] = str(int(expires_in)) if expires_in else ""
        i = 0
        for word in add:
            data[f"keywords_attributes[{i}][keyword]"] = word
            data[f"keywords_attributes[{i}][whole_word]"] = "true"
            i += 1
        for kid in remove:
            data[f"keywords_attributes[{i}][id]"] = str(kid)
            data[f"keywords_attributes[{i}][_destroy]"] = "true"
            i += 1
        return self.put(f"/api/v2/filters/{seg(filter_id)}", data=data)

    def filter_statuses(self, filter_id):
        """The posts a filter hides one by one: [{id, status_id}]."""
        return self.get(f"/api/v2/filters/{seg(filter_id)}/statuses") or []

    def filter_status(self, filter_id, status_id):
        """Hide this very post with that filter (not by its words)."""
        return self.post(f"/api/v2/filters/{seg(filter_id)}/statuses",
                         data={"status_id": status_id})

    def unfilter_status(self, filter_status_id):
        return self.delete(f"/api/v2/filters/statuses/{seg(filter_status_id)}")

    # ---- lists --------------------------------------------------------------
    def lists(self):
        return self.get("/api/v1/lists") or []

    def list_timeline(self, list_id, limit=40, max_id=None, min_id=None):
        return self.get(f"/api/v1/timelines/list/{seg(list_id)}", self._page(limit, max_id, min_id))

    def list_accounts(self, list_id):
        """Everyone in a list. limit=0 asks for all at once; a server that answers that
        with nothing (some versions do, for some lists) is asked again page by page."""
        path = f"/api/v1/lists/{seg(list_id)}/accounts"
        got = self.get(path, {"limit": 0}) or []
        if got:
            return got
        out, max_id = [], None
        for _ in range(50):  # 50 pages of 80: four thousand people is plenty
            page, max_id = self.get_page(path, {"limit": 80, **({"max_id": max_id}
                                                                 if max_id else {})})
            out += page or []
            if not max_id or not page:
                break
        if out:
            log.info("list %s: limit=0 gave nobody, pages gave %d", list_id, len(out))
        return out

    def create_list(self, title, exclusive=False, replies_policy=None):
        """replies_policy: whose replies the list shows — "followed" (to anyone I
        follow), "list" (to its members), "none"; None — the server's default."""
        data = {"title": title, "exclusive": "true" if exclusive else "false"}
        if replies_policy:
            data["replies_policy"] = replies_policy
        return self.post("/api/v1/lists", data=data)

    def update_list(self, list_id, title, exclusive, replies_policy=None):
        data = {"title": title, "exclusive": "true" if exclusive else "false"}
        if replies_policy:
            data["replies_policy"] = replies_policy
        return self.put(f"/api/v1/lists/{seg(list_id)}", data=data)

    def delete_list(self, list_id):
        return self.delete(f"/api/v1/lists/{seg(list_id)}")

    def list_add(self, list_id, acc_id):
        return self.post(f"/api/v1/lists/{seg(list_id)}/accounts", data={"account_ids[]": [acc_id]})

    def list_remove(self, list_id, acc_id):
        return self._req("DELETE", f"/api/v1/lists/{seg(list_id)}/accounts",
                         data={"account_ids[]": [acc_id]})

    # ---- writing ------------------------------------------------------------
    @staticmethod
    def _focus(focus):
        return f"{float(focus[0]):.2f},{float(focus[1]):.2f}"

    def upload_media(self, path, description="", focus=None, thumbnail=None):
        """focus: (x, y), each -1…1, y up — the part a cropped preview keeps;
        thumbnail: a picture's path, the cover of a video or a sound."""
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        data = {"description": description} if description else {}
        if focus:
            data["focus"] = self._focus(focus)
        thumb = open(thumbnail, "rb") if thumbnail else None  # noqa: SIM115 — closed below
        try:
            return self._upload(path, mime, data, thumb, thumbnail)
        finally:
            if thumb is not None:
                thumb.close()

    def _upload(self, path, mime, data, thumb, thumbnail):
        with open(path, "rb") as f:
            files = {"file": (os.path.basename(path), f, mime)}
            if thumb is not None:
                files["thumbnail"] = (os.path.basename(thumbnail), thumb,
                                      mimetypes.guess_type(thumbnail)[0] or "image/jpeg")
            try:
                media = self.post("/api/v2/media", data=data, files=files)
            except ApiError as e:
                if e.status != 404:
                    raise
                f.seek(0)
                if thumb is not None:
                    thumb.seek(0)
                media = self.post("/api/v1/media", data=data, files=files)
        # Mastodon processes v2 uploads asynchronously: wait until it's ready
        for _ in range(30):
            if media.get("url"):
                break
            time.sleep(1)
            media = self.get(f"/api/v1/media/{seg(media['id'])}")
        return media

    def post_status(self, text, visibility="private", in_reply_to_id=None,
                    spoiler_text="", media_ids=(), markdown=False, language="",
                    sensitive=False, poll=None, quoted_status_id=None, quote_policy="",
                    interaction_policy=None, scheduled_at=None, idempotency_key=None,
                    timeout=30):
        """poll: {"options": [...], "expires_in": seconds, "multiple": bool}.
        quoted_status_id: the post this one quotes; quote_policy: who may quote this one.
        idempotency_key: the same key sent again (a retry after a timeout) gives back the
        post already made instead of a second one — on servers that honour it (Mastodon)."""
        body = {"status": text, "visibility": visibility}
        if quoted_status_id:
            body["quoted_status_id"] = quoted_status_id
        if quote_policy:
            body["quote_approval_policy"] = quote_policy
        if interaction_policy:
            body["interaction_policy"] = interaction_policy
        if scheduled_at:  # then the answer is a ScheduledStatus, not a status
            body["scheduled_at"] = scheduled_at
        if sensitive:
            body["sensitive"] = True
        if poll:
            body["poll"] = poll
        if language:
            body["language"] = language
        if markdown:
            body["content_type"] = "text/markdown"
        if in_reply_to_id:
            body["in_reply_to_id"] = in_reply_to_id
        if spoiler_text:
            body["spoiler_text"] = spoiler_text
        if media_ids:
            body["media_ids"] = list(media_ids)
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self.post("/api/v1/statuses", json=body, headers=headers, timeout=timeout)

    def update_media(self, media_id, description=None, focus=None, thumbnail=None):
        """A picture not yet in a post (or mine being edited): its description, focus
        point, cover. None leaves a thing as it is."""
        data = {}
        if description is not None:
            data["description"] = description
        if focus:
            data["focus"] = self._focus(focus)
        if not thumbnail:
            return self.put(f"/api/v1/media/{seg(media_id)}", data=data)
        with open(thumbnail, "rb") as t:
            files = {"thumbnail": (os.path.basename(thumbnail), t,
                                   mimetypes.guess_type(thumbnail)[0] or "image/jpeg")}
            return self._req("PUT", f"/api/v1/media/{seg(media_id)}", data=data, files=files)

    def edit_status(self, sid, text, spoiler_text="", media_ids=(), markdown=False,
                    media_attributes=None):
        """Change my post. Media ids must be passed again, or they go away;
        media_attributes: [{id, description, focus "x,y"}] — their words and focus anew."""
        body = {"status": text, "spoiler_text": spoiler_text, "media_ids": list(media_ids)}
        if media_attributes:
            body["media_attributes"] = [dict(m) for m in media_attributes]
        if markdown:
            body["content_type"] = "text/markdown"
        return self._req("PUT", f"/api/v1/statuses/{seg(sid)}", json=body)

    def status_source(self, sid):
        """{text, spoiler_text} as I typed them (Markdown and all)."""
        return self.get(f"/api/v1/statuses/{seg(sid)}/source")

    def status_history(self, sid):
        return self.get(f"/api/v1/statuses/{seg(sid)}/history") or []

    def delete_status(self, sid):
        return self.delete(f"/api/v1/statuses/{seg(sid)}")

    def favourite(self, sid, on=True):
        return self.post(f"/api/v1/statuses/{seg(sid)}/{'favourite' if on else 'unfavourite'}")

    def poll(self, pid):
        return self.get(f"/api/v1/polls/{seg(pid)}")

    def vote(self, pid, choices):
        """choices: option indexes. Returns the poll with my votes and new counts."""
        return self.post(f"/api/v1/polls/{seg(pid)}/votes", json={"choices": list(choices)})

    def bookmark(self, sid, on=True):
        return self.post(f"/api/v1/statuses/{seg(sid)}/{'bookmark' if on else 'unbookmark'}")

    def bookmarks(self, limit=40, max_id=None, min_id=None):
        """Bookmarks page by the Link header (their ids aren't status ids), so
        max_id here is the cursor from the previous page."""
        items, nxt = self.get_page("/api/v1/bookmarks", self._page(limit, max_id))
        self.bookmarks_next = nxt
        return items

    def favourites(self, limit=40, max_id=None, min_id=None):
        """My likes, newest first; pages by the Link header like bookmarks."""
        items, nxt = self.get_page("/api/v1/favourites", self._page(limit, max_id))
        self.favourites_next = nxt
        return items

    def notify_posts(self, acc_id, on=True):
        """The bell: a notification for each new post of someone I follow."""
        return self.post(f"/api/v1/accounts/{seg(acc_id)}/follow", json={"notify": bool(on)})

    def follow_options(self, acc_id, reblogs=None, languages=None):
        """For someone I follow: their boosts in my Home or not; only posts in these
        languages ([] — all). Kept by the server, for every client."""
        body = {}
        if reblogs is not None:
            body["reblogs"] = bool(reblogs)
        if languages is not None:
            body["languages"] = list(languages)
        return self.post(f"/api/v1/accounts/{seg(acc_id)}/follow", json=body)

    def reblog(self, sid, on=True):
        return self.post(f"/api/v1/statuses/{seg(sid)}/{'reblog' if on else 'unreblog'}")

    def authorize_follow(self, acc_id):
        return self.post(f"/api/v1/follow_requests/{seg(acc_id)}/authorize")

    def reject_follow(self, acc_id):
        return self.post(f"/api/v1/follow_requests/{seg(acc_id)}/reject")

    # ---- 0.11: who reacted, quiet threads, conversations, people, trends, server ----
    def favourited_by(self, sid, max_id=None):
        """Who liked a post: (accounts, cursor of the next page or None)."""
        return self.get_page(f"/api/v1/statuses/{seg(sid)}/favourited_by", self._page(80, max_id))

    def reblogged_by(self, sid, max_id=None):
        """Who boosted a post: (accounts, cursor of the next page or None)."""
        return self.get_page(f"/api/v1/statuses/{seg(sid)}/reblogged_by", self._page(80, max_id))

    def quotes(self, sid, max_id=None):
        """Posts quoting my post: (statuses, cursor of the next page or None)."""
        return self.get_page(f"/api/v1/statuses/{seg(sid)}/quotes", self._page(40, max_id))

    def revoke_quote(self, sid, quoting_id):
        """Take my post out of someone's quote of it (I'm the quoted post's author)."""
        return self.post(f"/api/v1/statuses/{seg(sid)}/quotes/{seg(quoting_id)}/revoke")

    def mute_conversation(self, sid, on=True):
        """No more notifications from the thread this post is in (I take part in it)."""
        return self.post(f"/api/v1/statuses/{seg(sid)}/{'mute' if on else 'unmute'}")

    def conversations(self, limit=40):
        """Direct conversations, newest first: [{id, unread, accounts, last_status}]."""
        return self.get("/api/v1/conversations", {"limit": limit}) or []

    def read_conversation(self, cid):
        return self.post(f"/api/v1/conversations/{seg(cid)}/read")

    def dismiss_notification(self, nid):
        return self.post(f"/api/v1/notifications/{seg(nid)}/dismiss")

    def clear_notifications(self):
        """Every notification gone, on the server (for every app)."""
        return self.post("/api/v1/notifications/clear")

    def notifications_unread(self):
        """{"count": n} — what the server counts as unread (since the marker)."""
        return self.get("/api/v1/notifications/unread_count") or {}

    def remove_from_followers(self, acc_id):
        """They no longer follow me — without blocking them."""
        return self.post(f"/api/v1/accounts/{seg(acc_id)}/remove_from_followers")

    def endorse(self, acc_id, on=True):
        """Recommend someone on my profile (Mastodon 4.4+; older ones call it pin)."""
        try:
            return self.post(f"/api/v1/accounts/{seg(acc_id)}/{'endorse' if on else 'unendorse'}")
        except ApiError as e:
            if e.status != 404:
                raise
            return self.post(f"/api/v1/accounts/{seg(acc_id)}/{'pin' if on else 'unpin'}")

    def my_featured_tags(self):
        return self.get("/api/v1/featured_tags") or []

    def feature_tag(self, name):
        return self.post("/api/v1/featured_tags", data={"name": name.lstrip("#")})

    def unfeature_tag(self, tag_id):
        return self.delete(f"/api/v1/featured_tags/{seg(tag_id)}")

    def familiar_followers(self, ids):
        """[{id, accounts}] — of the people I follow, who follows each of these."""
        return self.get("/api/v1/accounts/familiar_followers", {"id[]": list(ids)}) or []

    def suggestions(self, limit=40):
        """Whom my server suggests following: [{source(s), account}]."""
        return self.get("/api/v2/suggestions", {"limit": limit}) or []

    def dismiss_suggestion(self, acc_id):
        return self.delete(f"/api/v1/suggestions/{seg(acc_id)}")

    def directory(self, offset=0, local=False, limit=40):
        """The profile directory: people who chose to be listed, recently active first."""
        return self.get("/api/v1/directory", {"offset": offset, "limit": limit,
                                              "order": "active",
                                              "local": "true" if local else "false"}) or []

    def trends(self, kind, offset=0, limit=20):
        """What's being talked about: kind = "statuses", "tags" or "links"."""
        return self.get(f"/api/v1/trends/{kind}", {"offset": offset, "limit": limit}) or []

    def instance_rules(self):
        return self.get("/api/v1/instance/rules") or []

    def instance_domain_blocks(self):
        """The servers my server cut off, as it shows them (may be closed to the public:
        403 then): [{domain, digest, severity, comment}]."""
        return self.get("/api/v1/instance/domain_blocks") or []

    def terms_of_service(self):
        """The server's terms (Mastodon 4.4): {effective_date, content (HTML)…}."""
        return self.get("/api/v1/instance/terms_of_service") or {}

    def translation_languages(self):
        """{source language: [targets]} — what the server's translator can do."""
        return self.get("/api/v1/instance/translation_languages") or {}

    def link_timeline(self, url, limit=20, max_id=None, min_id=None):
        """Posts that share this link (trending links only; Mastodon 4.3)."""
        return self.get("/api/v1/timelines/link", self._page(limit, max_id, min_id, url=url))

    def featured_tag_suggestions(self):
        """The tags I use most and haven't put forward on my profile yet."""
        return self.get("/api/v1/featured_tags/suggestions") or []

    # ---- Web Push: the server sends notifications to a browser itself ----------------
    def push_subscription(self):
        return self.get("/api/v1/push/subscription")

    def push_subscribe(self, endpoint, p256dh, auth, alerts=None, policy="all"):
        """The browser's push subscription, given to my server: it encrypts each
        notification for that browser and sends it through the browser's push service."""
        body = {"subscription": {"endpoint": endpoint, "keys": {"p256dh": p256dh,
                                                                 "auth": auth}},
                "data": {"alerts": dict(alerts or {}), "policy": policy}}
        return self.post("/api/v1/push/subscription", json=body)

    def push_unsubscribe(self):
        return self.delete("/api/v1/push/subscription")

    def instance_page(self, which):
        """The server's own text: which = "extended_description" or "privacy_policy";
        {"updated_at", "content" (HTML)}."""
        return self.get(f"/api/v1/instance/{which}") or {}

    def preferences(self):
        """What I set on the server's web side: default visibility, sensitivity,
        language, expanding media and CWs."""
        return self.get("/api/v1/preferences") or {}

    def react_announcement(self, aid, name, on=True):
        path = f"/api/v1/announcements/{seg(aid)}/reactions/{quote(name, safe='')}"
        return self.put(path) if on else self.delete(path)

    # ---- interaction requests (GoToSocial): replies, likes, boosts waiting for my yes
    def interaction_requests(self, status_id=None):
        p = {"limit": 80}
        if status_id:
            p["status_id"] = status_id
        return self.get("/api/v1/interaction_requests", p) or []

    def answer_interaction(self, req_id, approve):
        return self.post(f"/api/v1/interaction_requests/{seg(req_id)}/"
                         + ("authorize" if approve else "reject"))
