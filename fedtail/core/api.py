"""Mastodon-compatible REST client (GoToSocial, Mastodon, Akkoma, Pleroma).

Plain blocking calls; the core runs them in worker threads.
"""

import logging
import mimetypes
import os
import re
import threading
import time
from dataclasses import dataclass
from urllib.parse import quote, urlencode

import requests

from .. import __version__

OOB = "urn:ietf:wg:oauth:2.0:oob"
SCOPES = "read write"
USER_AGENT = f"fedtail/{__version__}"
MARKDOWN_SERVERS = ("gotosocial", "akkoma", "pleroma", "glitch")
SLOW_SECONDS = 5.0  # set from [debug] slow_request_seconds
log = logging.getLogger("fedtail.api")
# query keys that are fine in a log line (paging, kinds); anything else is left out
_SAFE_PARAMS = {"limit", "max_id", "min_id", "since_id", "local", "types[]"}


class ApiError(Exception):
    def __init__(self, status, message):
        super().__init__(f"HTTP {status}: {message}")
        self.status = status


@dataclass
class Capabilities:
    software: str = ""
    max_characters: int = 500
    max_media: int = 4
    markdown: bool = False
    max_poll_options: int = 4
    translation: bool = False


def capabilities_from_instance(inst):
    inst = inst or {}
    version = str(inst.get("version", "")).lower()
    conf = inst.get("configuration") or {}
    st = conf.get("statuses") or {}
    mimes = st.get("supported_mime_types") or []
    md = "text/markdown" in mimes or any(s in version for s in MARKDOWN_SERVERS)
    software = next((s for s in MARKDOWN_SERVERS if s in version), "mastodon")
    return Capabilities(
        software=software,
        max_characters=int(st.get("max_characters") or inst.get("max_toot_chars") or 500),
        max_media=int(st.get("max_media_attachments") or 4),
        max_poll_options=int((conf.get("polls") or {}).get("max_options") or 4),
        translation=bool((conf.get("translation") or {}).get("enabled")),
        markdown=md,
    )


class Api:
    def __init__(self, server, token=None, session=None):
        server = server.strip().rstrip("/")
        if not server.startswith(("http://", "https://")):
            server = "https://" + server
        self.base = server
        self._last = threading.local()  # the latest response's headers, per thread
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"

    # ---- plumbing ---------------------------------------------------------
    def _req(self, method, path, **kw):
        kw.setdefault("timeout", 30)
        params = kw.get("params") or {}
        shown = " ".join(f"{k}={v}" for k, v in params.items() if k in _SAFE_PARAMS)
        t = time.monotonic()
        try:
            r = self.s.request(method, self.base + path, **kw)
        except requests.RequestException as e:
            log.warning("%s %s %s -> %s after %.2f s", method, path, shown,
                        e.__class__.__name__, time.monotonic() - t)
            raise
        took = time.monotonic() - t
        # path, paging and timing only: never the token, a body or a post's text
        log.log(logging.WARNING if took > SLOW_SECONDS or r.status_code >= 400
                else logging.DEBUG, "%s %s %s -> %s %.2f s %d B", method, path, shown,
                r.status_code, took, len(r.content or b""))
        self._last.headers = r.headers
        if r.status_code >= 400:
            try:
                msg = r.json().get("error") or r.text
            except ValueError:
                msg = r.text
            raise ApiError(r.status_code, str(msg)[:300])
        if not r.content:
            return None
        return r.json()

    def get(self, path, params=None):
        return self._req("GET", path, params=params)

    def post(self, path, json=None, data=None, files=None):
        return self._req("POST", path, json=json, data=data, files=files)

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
    def register_app(self):
        return self.post("/api/v1/apps", data={
            "client_name": "fedtail",
            "redirect_uris": OOB,
            "scopes": SCOPES,
            "website": "https://github.com/eugene-vereshchagin/fedtail",
        })

    def authorize_url(self, client_id):
        q = urlencode({"client_id": client_id, "redirect_uri": OOB,
                       "response_type": "code", "scope": SCOPES})
        return f"{self.base}/oauth/authorize?{q}"

    def get_token(self, client_id, client_secret, code):
        res = self.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": OOB,
            "code": code.strip(),
            "scope": SCOPES,
        })
        return res["access_token"]

    # ---- reading ------------------------------------------------------------
    def verify_credentials(self):
        """My account with `source`: the bio and fields as I typed them."""
        return self.get("/api/v1/accounts/verify_credentials")

    def update_credentials(self, display_name=None, note=None, fields=None, locked=None,
                           bot=None, discoverable=None, avatar=None, header=None):
        """Change my profile. fields: [(name, value)] up to the server's limit;
        avatar/header: paths of new pictures. None leaves a thing as it is."""
        data = {}
        for key, val in (("display_name", display_name), ("note", note)):
            if val is not None:
                data[key] = val
        for key, val in (("locked", locked), ("bot", bot), ("discoverable", discoverable)):
            if val is not None:
                data[key] = "true" if val else "false"
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
                    files[key] = (path.rsplit("/", 1)[-1], f)
            return self.patch("/api/v1/accounts/update_credentials", data=data,
                              files=files or None)
        finally:
            for f in opened:
                f.close()

    def me(self):
        return self.get("/api/v1/accounts/verify_credentials")

    def instance(self):
        return self.get("/api/v1/instance")

    def home(self, limit=40, max_id=None, min_id=None):
        return self.get("/api/v1/timelines/home", self._page(limit, max_id, min_id))

    def local(self, limit=40, max_id=None, min_id=None):
        return self.get("/api/v1/timelines/public",
                        self._page(limit, max_id, min_id, local="true"))

    def federated(self, limit=40, max_id=None, min_id=None):
        """The whole fediverse as this server knows it."""
        return self.get("/api/v1/timelines/public", self._page(limit, max_id, min_id))

    def account_statuses(self, acc_id, limit=40, max_id=None, min_id=None):
        return self.get(f"/api/v1/accounts/{acc_id}/statuses",
                        self._page(limit, max_id, min_id))

    def notification_policy(self):
        return self.get("/api/v2/notifications/policy")

    def set_notification_policy(self, **fields):
        return self.patch("/api/v2/notifications/policy", data=fields)

    def notification_requests(self):
        return self.get("/api/v1/notifications/requests", {"limit": 40}) or []

    def answer_notification_request(self, rid, accept):
        return self.post(f"/api/v1/notifications/requests/{rid}/"
                         + ("accept" if accept else "dismiss"))

    def announcements(self):
        return self.get("/api/v1/announcements") or []

    def dismiss_announcement(self, aid):
        return self.post(f"/api/v1/announcements/{aid}/dismiss")

    def scheduled(self):
        return self.get("/api/v1/scheduled_statuses", {"limit": 40}) or []

    def cancel_scheduled(self, sid):
        return self.delete(f"/api/v1/scheduled_statuses/{sid}")

    def domain_blocks(self):
        return self.get("/api/v1/domain_blocks", {"limit": 200}) or []

    def block_domain(self, domain, on=True):
        return self._req("POST" if on else "DELETE", "/api/v1/domain_blocks",
                         params={"domain": domain})

    def set_note(self, acc_id, text):
        """My private note on someone (only I see it)."""
        return self.post(f"/api/v1/accounts/{acc_id}/note", json={"comment": text})

    def translate(self, sid, lang=None):
        """{content, spoiler_text, detected_source_language, provider} in my language."""
        return self.post(f"/api/v1/statuses/{sid}/translate",
                         json={"lang": lang} if lang else None)

    def report(self, acc_id, status_ids=(), comment="", forward=False, category="other"):
        body = {"account_id": acc_id, "status_ids": list(status_ids), "comment": comment,
                "forward": bool(forward), "category": category}
        return self.post("/api/v1/reports", json=body)

    def pinned(self, acc_id):
        return self.get(f"/api/v1/accounts/{acc_id}/statuses", {"pinned": "true"}) or []

    def pin(self, sid, on=True):
        return self.post(f"/api/v1/statuses/{sid}/{'pin' if on else 'unpin'}")

    def mentions(self, limit=40, max_id=None, min_id=None):
        p = self._page(limit, max_id, min_id)
        p["types[]"] = ["mention"]
        return self.get("/api/v1/notifications", p)

    def notifications(self, types, limit=40, max_id=None, min_id=None):
        p = self._page(limit, max_id, min_id)
        p["types[]"] = list(types)
        return self.get("/api/v1/notifications", p)

    def status(self, sid):
        return self.get(f"/api/v1/statuses/{sid}")

    def context(self, sid):
        return self.get(f"/api/v1/statuses/{sid}/context")

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
        return self.post(f"/api/v1/accounts/{acc_id}/{'follow' if on else 'unfollow'}")

    def tag_timeline(self, tag, limit=40, max_id=None, min_id=None):
        return self.get(f"/api/v1/timelines/tag/{quote(tag, safe='')}",
                        self._page(limit, max_id, min_id))

    def get_page(self, path, params=None):
        """GET a list that pages by the Link header (followers, following):
        returns (items, max_id for the next page or None)."""
        r = self.s.get(self.base + path, params=params, timeout=30)
        if r.status_code >= 400:
            raise ApiError(r.status_code, r.text[:300])
        log.debug("GET %s -> %s %d B", path, r.status_code, len(r.content or b""))
        nxt = (r.links or {}).get("next", {}).get("url", "")
        m = re.search(r"[?&]max_id=([^&]+)", nxt)
        return r.json() or [], (m.group(1) if m else None)

    def following(self, acc_id, max_id=None):
        return self.get_page(f"/api/v1/accounts/{acc_id}/following",
                             self._page(40, max_id))

    def followers(self, acc_id, max_id=None):
        return self.get_page(f"/api/v1/accounts/{acc_id}/followers",
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

    def search(self, q, kind=None, resolve=True, limit=5):
        """Ask my server to find (and fetch from its home, if needed) an address."""
        p = {"q": q, "resolve": "true" if resolve else "false", "limit": limit}
        if kind:
            p["type"] = kind
        return self.get("/api/v2/search", p) or {}

    # ---- silence: mute, block, filters ------------------------------------------
    def mute(self, acc_id, on=True):
        return self.post(f"/api/v1/accounts/{acc_id}/{'mute' if on else 'unmute'}")

    def block(self, acc_id, on=True):
        return self.post(f"/api/v1/accounts/{acc_id}/{'block' if on else 'unblock'}")

    def _all_pages(self, path, pages=10):
        out, cursor = [], None
        for _ in range(pages):
            items, cursor = self.get_page(path, self._page(80, cursor))
            out += items
            if not cursor or not items:
                break
        return out

    def mutes(self):
        return self._all_pages("/api/v1/mutes")

    def blocks(self):
        return self._all_pages("/api/v1/blocks")

    def filters(self):
        return self.get("/api/v2/filters") or []

    def create_filter(self, title, keywords, action="warn", contexts=("home", "public",
                                                                       "thread", "account")):
        data = {"title": title, "filter_action": action, "context[]": list(contexts)}
        for i, word in enumerate(keywords):
            data[f"keywords_attributes[{i}][keyword]"] = word
            data[f"keywords_attributes[{i}][whole_word]"] = "true"
        return self.post("/api/v2/filters", data=data)

    def delete_filter(self, filter_id):
        return self.delete(f"/api/v2/filters/{filter_id}")

    # ---- lists --------------------------------------------------------------
    def lists(self):
        return self.get("/api/v1/lists") or []

    def list_timeline(self, list_id, limit=40, max_id=None, min_id=None):
        return self.get(f"/api/v1/timelines/list/{list_id}", self._page(limit, max_id, min_id))

    def list_accounts(self, list_id):
        # limit=0: everyone at once (Mastodon and GoToSocial both understand it)
        return self.get(f"/api/v1/lists/{list_id}/accounts", {"limit": 0}) or []

    def create_list(self, title, exclusive=False):
        return self.post("/api/v1/lists", data={"title": title,
                                                "exclusive": "true" if exclusive else "false"})

    def update_list(self, list_id, title, exclusive):
        return self.put(f"/api/v1/lists/{list_id}",
                        data={"title": title, "exclusive": "true" if exclusive else "false"})

    def delete_list(self, list_id):
        return self.delete(f"/api/v1/lists/{list_id}")

    def list_add(self, list_id, acc_id):
        return self.post(f"/api/v1/lists/{list_id}/accounts", data={"account_ids[]": [acc_id]})

    def list_remove(self, list_id, acc_id):
        return self._req("DELETE", f"/api/v1/lists/{list_id}/accounts",
                         data={"account_ids[]": [acc_id]})

    # ---- writing ------------------------------------------------------------
    def upload_media(self, path, description=""):
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        data = {"description": description} if description else {}
        with open(path, "rb") as f:
            files = {"file": (os.path.basename(path), f, mime)}
            try:
                media = self.post("/api/v2/media", data=data, files=files)
            except ApiError as e:
                if e.status != 404:
                    raise
                f.seek(0)
                media = self.post("/api/v1/media", data=data, files=files)
        # Mastodon processes v2 uploads asynchronously: wait until it's ready
        for _ in range(30):
            if media.get("url"):
                break
            time.sleep(1)
            media = self.get(f"/api/v1/media/{media['id']}")
        return media

    def post_status(self, text, visibility="private", in_reply_to_id=None,
                    spoiler_text="", media_ids=(), markdown=False, language="",
                    sensitive=False, poll=None, quoted_status_id=None, quote_policy="",
                    interaction_policy=None, scheduled_at=None):
        """poll: {"options": [...], "expires_in": seconds, "multiple": bool}.
        quoted_status_id: the post this one quotes; quote_policy: who may quote this one."""
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
        return self.post("/api/v1/statuses", json=body)

    def edit_status(self, sid, text, spoiler_text="", media_ids=(), markdown=False):
        """Change my post. Media ids must be passed again, or they go away."""
        body = {"status": text, "spoiler_text": spoiler_text, "media_ids": list(media_ids)}
        if markdown:
            body["content_type"] = "text/markdown"
        return self._req("PUT", f"/api/v1/statuses/{sid}", json=body)

    def status_source(self, sid):
        """{text, spoiler_text} as I typed them (Markdown and all)."""
        return self.get(f"/api/v1/statuses/{sid}/source")

    def status_history(self, sid):
        return self.get(f"/api/v1/statuses/{sid}/history") or []

    def delete_status(self, sid):
        return self.delete(f"/api/v1/statuses/{sid}")

    def favourite(self, sid, on=True):
        return self.post(f"/api/v1/statuses/{sid}/{'favourite' if on else 'unfavourite'}")

    def poll(self, pid):
        return self.get(f"/api/v1/polls/{pid}")

    def vote(self, pid, choices):
        """choices: option indexes. Returns the poll with my votes and new counts."""
        return self.post(f"/api/v1/polls/{pid}/votes", json={"choices": list(choices)})

    def bookmark(self, sid, on=True):
        return self.post(f"/api/v1/statuses/{sid}/{'bookmark' if on else 'unbookmark'}")

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
        return self.post(f"/api/v1/accounts/{acc_id}/follow", json={"notify": bool(on)})

    def reblog(self, sid, on=True):
        return self.post(f"/api/v1/statuses/{sid}/{'reblog' if on else 'unreblog'}")

    def authorize_follow(self, acc_id):
        return self.post(f"/api/v1/follow_requests/{acc_id}/authorize")

    def reject_follow(self, acc_id):
        return self.post(f"/api/v1/follow_requests/{acc_id}/reject")
