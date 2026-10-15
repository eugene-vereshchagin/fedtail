"""Mastodon-compatible REST client (GoToSocial, Mastodon, Akkoma, Pleroma).

Plain blocking calls; the core runs them in worker threads.
"""

import mimetypes
import os
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import requests

from .. import __version__

OOB = "urn:ietf:wg:oauth:2.0:oob"
SCOPES = "read write"
USER_AGENT = f"fedtail/{__version__}"
MARKDOWN_SERVERS = ("gotosocial", "akkoma", "pleroma", "glitch")


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
        markdown=md,
    )


class Api:
    def __init__(self, server, token=None, session=None):
        server = server.strip().rstrip("/")
        if not server.startswith(("http://", "https://")):
            server = "https://" + server
        self.base = server
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        if token:
            self.s.headers["Authorization"] = f"Bearer {token}"

    # ---- plumbing ---------------------------------------------------------
    def _req(self, method, path, **kw):
        kw.setdefault("timeout", 30)
        r = self.s.request(method, self.base + path, **kw)
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
    def me(self):
        return self.get("/api/v1/accounts/verify_credentials")

    def instance(self):
        return self.get("/api/v1/instance")

    def home(self, limit=40, max_id=None, min_id=None):
        return self.get("/api/v1/timelines/home", self._page(limit, max_id, min_id))

    def local(self, limit=40, max_id=None, min_id=None):
        return self.get("/api/v1/timelines/public",
                        self._page(limit, max_id, min_id, local="true"))

    def account_statuses(self, acc_id, limit=40, max_id=None, min_id=None):
        return self.get(f"/api/v1/accounts/{acc_id}/statuses",
                        self._page(limit, max_id, min_id))

    def mentions(self, limit=40, max_id=None, min_id=None):
        p = self._page(limit, max_id, min_id)
        p["types[]"] = ["mention"]
        return self.get("/api/v1/notifications", p)

    def status(self, sid):
        return self.get(f"/api/v1/statuses/{sid}")

    def context(self, sid):
        return self.get(f"/api/v1/statuses/{sid}/context")

    def follow_requests(self):
        return self.get("/api/v1/follow_requests", {"limit": 80})

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
                    spoiler_text="", media_ids=(), markdown=False):
        body = {"status": text, "visibility": visibility}
        if markdown:
            body["content_type"] = "text/markdown"
        if in_reply_to_id:
            body["in_reply_to_id"] = in_reply_to_id
        if spoiler_text:
            body["spoiler_text"] = spoiler_text
        if media_ids:
            body["media_ids"] = list(media_ids)
        return self.post("/api/v1/statuses", json=body)

    def delete_status(self, sid):
        return self.delete(f"/api/v1/statuses/{sid}")

    def favourite(self, sid, on=True):
        return self.post(f"/api/v1/statuses/{sid}/{'favourite' if on else 'unfavourite'}")

    def reblog(self, sid, on=True):
        return self.post(f"/api/v1/statuses/{sid}/{'reblog' if on else 'unreblog'}")

    def authorize_follow(self, acc_id):
        return self.post(f"/api/v1/follow_requests/{acc_id}/authorize")

    def reject_follow(self, acc_id):
        return self.post(f"/api/v1/follow_requests/{acc_id}/reject")
