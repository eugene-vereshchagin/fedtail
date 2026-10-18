"""The web interface's server: the page, and a small JSON API over the Core.

Standard library only (http.server). Who may use it: whoever has the key — a
random secret kept in the profile's data folder and printed as a link at start;
the link puts it into a cookie (HttpOnly, SameSite=Strict). Every POST also needs
the X-Fedtail header, which a form on another site can't send. The page loads
scripts from here only (Content-Security-Policy); server HTML is cleaned here,
before it reaches the page. The key never goes into the log.
"""

import hmac
import json
import logging
import os
import secrets
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from urllib.parse import parse_qs, urlsplit

from ... import __version__
from ...core import config, links
from ...core.model import real, snippet
from ...i18n import _
from ..richtext import clean
from ..tui.model import Commands

log = logging.getLogger(__name__)

COOKIE = "fedtail_web"
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/app.css": ("app.css", "text/css; charset=utf-8")}
CSP = ("default-src 'self'; img-src https: data:; media-src https:; style-src 'self'; "
       "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
       "form-action 'self'")
WAIT_SECONDS = 25


def load_key(data_dir):
    """The profile's web key: made once, kept readable by the owner only."""
    path = data_dir / "web.key"
    try:
        key = path.read_text("utf-8").strip()
        if len(key) >= 20:
            return key
    except OSError:
        pass
    key = secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(key)
    return key


def static_text(name):
    return resources.files("fedtail").joinpath(f"data/web/{name}").read_text("utf-8")


# ---- what the page gets -------------------------------------------------------------
def account_json(acc):
    acc = acc or {}
    return {"id": acc.get("id"), "acct": acc.get("acct", ""),
            "name": acc.get("display_name") or acc.get("username") or "",
            "avatar": _https(acc.get("avatar_static") or acc.get("avatar")),
            "url": _https(acc.get("url")), "bot": bool(acc.get("bot"))}


def web_clean(html):
    """Server HTML, cleaned (richtext.clean) — minus the inline styles meant for Qt,
    which the page's CSP refuses anyway."""
    return clean(html).replace(' style="text-decoration:none;"', "")


def _https(url):
    return url if isinstance(url, str) and url.startswith("https://") else ""


def post_json(core, wrapper, alias=None, unread=False, parent=None, number=None, depth=None,
              item_id=None):
    st = real(wrapper)
    html = st.get("content") or ""
    if core.cfg["ui"]["links_in_app"]:
        html = links.in_app(html, st)
    out = {
        "id": wrapper["id"], "item": item_id or wrapper["id"], "sid": st["id"],
        "alias": alias, "account": account_json(st.get("account")),
        "created_at": st.get("created_at", ""), "visibility": st.get("visibility", "public"),
        "spoiler": st.get("spoiler_text") or "", "html": web_clean(html),
        "url": _https(st.get("url") or st.get("uri")),
        "media": [{"type": m.get("type"), "preview": _https(m.get("preview_url")),
                   "url": _https(m.get("url") or m.get("remote_url")),
                   "desc": m.get("description") or ""}
                  for m in st.get("media_attachments") or []],
        "replies": st.get("replies_count") or 0, "boosts": st.get("reblogs_count") or 0,
        "favs": st.get("favourites_count") or 0, "favourited": bool(st.get("favourited")),
        "reblogged": bool(st.get("reblogged")), "bookmarked": bool(st.get("bookmarked")),
        "sensitive": bool(st.get("sensitive")), "poll": bool(st.get("poll")),
        "unread": bool(unread), "mine": bool(core.me and st["account"]["id"] == core.me["id"]),
        "reply_to": st.get("in_reply_to_id"),
    }
    if wrapper.get("reblog"):
        out["boosted_by"] = account_json(wrapper.get("account"))
    if number is not None:
        out["number"], out["depth"] = number, depth or 0
    if st.get("in_reply_to_id") and number is None:
        if isinstance(parent, dict):
            out["context"] = {"acct": real(parent)["account"]["acct"],
                              "text": snippet(parent, 140), "id": real(parent)["id"]}
        elif parent == "missing":
            out["context"] = {"missing": True}
    return out


class Web:
    """The state behind the handler: the core, the key, a version for long polls."""

    def __init__(self, core, key):
        self.core = core
        self.key = key
        self.cmds = Commands(core)
        self.version = 0
        self.changed = threading.Condition()
        for event in ("lanes_updated", "read_changed", "status_updated", "status_deleted",
                      "lists_changed"):
            core.events.on(event, lambda _n, _p: self.bump())

    def bump(self):
        with self.changed:
            self.version += 1
            self.changed.notify_all()

    def wait(self, since, timeout=WAIT_SECONDS):
        with self.changed:
            self.changed.wait_for(lambda: self.version != since, timeout)
            return self.version

    # ---- API ---------------------------------------------------------------------
    def me(self):
        c = self.core.cfg
        return {"acct": (self.core.me or {}).get("acct"), "version": __version__,
                "server": (self.core.auth or {}).get("server"),
                "mark_read": c["read"]["mark_read"], "order": c["feed"]["order"],
                "start_at": c["feed"]["start_at"], "expand_cw": config.expand_cw(c),
                "visibility": self.core.default_visibility(),
                "sensitive_media": config.sensitive_media(c),
                "words": {k: _(k) for k in WORDS}}

    def lanes(self):
        from ..tui.model import lane_label, ordered_lanes, start_lane
        out = []
        for group, names in ordered_lanes(self.core):
            for i, name in enumerate(names):
                title, n = lane_label(self.core, name, 60)
                out.append({"name": name, "title": title, "unread": n,
                            "group": group if i == 0 else None})
        first = start_lane(self.core, [x["name"] for x in out])
        for x in out:
            x["start"] = x["name"] == first
        return out

    def lane(self, name):
        core = self.core
        from ...core.lanes import canonical
        name = canonical(name)  # an old name ("comments") still finds its lane
        if name not in core.lane_by_name:
            raise KeyError(name)
        core.set_active_lane(name)
        core.set_state("lane", name)
        entries = core.lane_entries(name)
        unread = core.unread_ids(entries)
        short = core.short_ids([st for _i, st in entries])
        posts = [post_json(core, st, short.get(real(st)["id"]), st["id"] in unread,
                           core.parent_of(st), item_id=item) for item, st in entries]
        return {"name": name, "title": core.lane_title(name) or _("lane_" + name),
                "posts": posts}

    def thread(self, sid):
        core = self.core
        nodes = core.thread(sid).result()
        short = core.short_ids([n.status for n in nodes])
        unread = core.unread_ids([(None, n.status) for n in nodes])
        return {"focus": sid,
                "posts": [post_json(core, n.status, short.get(real(n.status)["id"]),
                                    n.status["id"] in unread, number=n.number, depth=n.depth)
                          for n in nodes]}

    def account(self, acc_id):
        core = self.core
        acc = core.account(acc_id).result()
        try:
            rel = core.relationship(acc_id).result() if acc_id != (core.me or {}).get("id") \
                else {}
        except Exception:  # noqa: BLE001 — the profile shows without it
            rel = {}
        page = core.account_statuses(acc_id).result()
        short = core.short_ids(page)
        info = account_json(acc)
        info.update(note=web_clean(acc.get("note") or ""), posts=acc.get("statuses_count"),
                    followers=acc.get("followers_count"), following=acc.get("following_count"),
                    fields=[{"name": f.get("name", ""), "value": web_clean(f.get("value", ""))}
                            for f in acc.get("fields") or []])
        return {"account": info,
                "relation": {k: bool(rel.get(k)) for k in ("following", "followed_by",
                                                           "requested")},
                "posts": [post_json(core, st, short.get(real(st)["id"]),
                                    parent=core.parent_of(st)) for st in page]}

    def act(self, action, sid):
        core = self.core
        st = core.store.get_status(sid)
        if st is None:
            raise KeyError(sid)
        if action == "fav":
            got = core.favourite(st).result()
        elif action == "boost":
            got = core.boost(st).result()
        elif action == "bookmark":
            got = core.bookmark(st).result()
        else:
            raise ValueError(action)
        got = got or core.store.get_status(sid) or st
        return post_json(core, got, core.short_ids([got]).get(real(got)["id"]))

    def follow(self, acc_id, on):
        self.core.follow(acc_id, bool(on)).result()
        return {"following": bool(on)}

    def post(self, body):
        core = self.core
        text = (body.get("text") or "").strip()
        if not text:
            raise ValueError("empty")
        parent = core.store.get_status(body["reply_to"]) if body.get("reply_to") else None
        vis = body.get("visibility") or core.reply_visibility(parent)
        if vis not in ("public", "unlisted", "private", "direct"):
            raise ValueError(vis)
        st = core.post(text, vis, real(parent)["id"] if parent else None,
                       (body.get("cw") or "").strip()).result()
        return {"id": st.get("id"), "url": st.get("url")}

    def command(self, line):
        fut, message = self.cmds.run(line)
        if fut is None:
            return {"ok": False, "message": message}
        result = fut.result()
        if isinstance(result, tuple):
            kind, what = result
            if kind == "thread":
                return {"ok": True, "open": {"thread": what}}
            if kind == "profile":
                return {"ok": True, "open": {"account": what["id"]}}
            if kind == "delete":
                self.core.delete(what).result()
                return {"ok": True, "message": _("deleted")}
        return {"ok": True, "message": result if isinstance(result, str) else message}

    def resolve(self, url):
        found = self.core.resolve(url).result()
        if not found:
            return {"found": None}
        kind, what = found
        return {"found": "thread" if kind == "status" else "account",
                "id": real(what)["id"] if kind == "status" else what["id"]}


# words the page shows, in the profile's language
WORDS = ("reply", "fav", "faved", "boost", "boosted", "bookmark", "unbookmark", "thread",
         "write", "send", "sent", "tui_back", "web_thread", "follow", "unfollow",
         "acc_follows_you", "web_cw", "web_show", "web_load_error", "web_empty",
         "web_reply_to", "web_cancel", "web_cmd", "web_visibility", "vis_public",
         "vis_unlisted", "vis_private", "vis_direct", "web_media", "web_sensitive",
         "web_parent_gone", "web_mark_read", "tui_profile", "open_browser")


class Handler(BaseHTTPRequestHandler):
    server_version = "fedtail"
    sys_version = ""
    web = None  # set by make_server

    def log_message(self, fmt, *args):  # the path without its query: no key in the log
        log.debug("web %s %s -> %s", self.command, urlsplit(self.path).path,
                  args[1] if len(args) > 1 else "")

    # ---- plumbing ----------------------------------------------------------------
    def _authorized(self):
        raw = self.headers.get("Cookie") or ""
        for part in raw.split(";"):
            name, _sep, value = part.strip().partition("=")
            if name == COOKIE and hmac.compare_digest(value.encode(), self.web.key.encode()):
                return True
        return False

    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=()):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        for k, v in extra:
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json(self, obj, status=HTTPStatus.OK):
        self._send(status, json.dumps(obj, ensure_ascii=False))

    def _forbidden(self):
        self._send(HTTPStatus.FORBIDDEN, _("web_forbidden"), "text/plain; charset=utf-8")

    # ---- GET ---------------------------------------------------------------------
    def do_GET(self):  # noqa: N802 — http.server's name
        u = urlsplit(self.path)
        q = {k: v[-1] for k, v in parse_qs(u.query).items()}
        if u.path == "/" and "k" in q:
            if hmac.compare_digest(q["k"].encode(), self.web.key.encode()):
                cookie = f"{COOKIE}={self.web.key}; HttpOnly; SameSite=Strict; Path=/; " \
                         f"Max-Age={400 * 24 * 3600}"
                self._send(HTTPStatus.SEE_OTHER, b"", "text/plain",
                           extra=(("Set-Cookie", cookie), ("Location", "/")))
            else:
                self._forbidden()
            return
        if not self._authorized():
            return self._forbidden()
        if u.path in STATIC:
            name, ctype = STATIC[u.path]
            return self._send(HTTPStatus.OK, static_text(name), ctype)
        routes = {"/api/me": lambda: self.web.me(),
                  "/api/lanes": lambda: self.web.lanes(),
                  "/api/lane": lambda: self.web.lane(q.get("name", "")),
                  "/api/thread": lambda: self.web.thread(q.get("id", "")),
                  "/api/account": lambda: self.web.account(q.get("id", "")),
                  "/api/resolve": lambda: self.web.resolve(q.get("url", "")),
                  "/api/wait": lambda: {"v": self.web.wait(int(q.get("v", "-1") or -1))}}
        self._run(routes.get(u.path))

    # ---- POST --------------------------------------------------------------------
    def do_POST(self):  # noqa: N802
        if not self._authorized() or self.headers.get("X-Fedtail") != "1":
            return self._forbidden()
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n < 0:  # read(-1) would read to the end: no limit at all
                raise ValueError(n)
            body = json.loads(self.rfile.read(min(n, 1_000_000)) or b"{}")
        except ValueError:
            return self._json({"error": "bad json"}, HTTPStatus.BAD_REQUEST)
        if not isinstance(body, dict):
            return self._json({"error": "bad json"}, HTTPStatus.BAD_REQUEST)
        path = urlsplit(self.path).path
        web = self.web
        routes = {
            "/api/read": lambda: (web.core.mark_read([str(i) for i in body.get("ids", [])
                                                      ][:500]), {"ok": True})[1],
            "/api/act": lambda: web.act(body.get("action"), str(body.get("id"))),
            "/api/follow": lambda: web.follow(str(body.get("id")), body.get("on")),
            "/api/post": lambda: web.post(body),
            "/api/command": lambda: web.command(str(body.get("line", ""))),
        }
        self._run(routes.get(path))

    def _run(self, fn):
        if fn is None:
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        try:
            return self._json(fn())
        except (KeyError, ValueError) as e:
            return self._json({"error": f"{e.__class__.__name__}: {e}"},
                              HTTPStatus.BAD_REQUEST)
        except Exception as e:  # noqa: BLE001 — the page says what failed
            log.warning("web %s: %s", urlsplit(self.path).path, e)
            return self._json({"error": str(e)[:300]}, HTTPStatus.BAD_GATEWAY)


def make_server(core, host, port, key):
    web = Web(core, key)
    handler = type("FedtailHandler", (Handler,), {"web": web})
    srv = ThreadingHTTPServer((host, port), handler)
    srv.daemon_threads = True
    srv.web = web
    return srv
