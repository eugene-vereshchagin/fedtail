"""fedtail-sync: the meeting point of one account's devices (fedtail/core/sync).

A small HTTP server on the standard library alone: one file, Python 3.11+, SQLite. It
keeps sealed blobs — each device's journal of read marks and thread states — and hands
an account's blobs to its other devices. It can't read them: they are encrypted with a
key only the devices have. All it learns is whose they are, how big and when.

Whose: a device sends a token of its fediverse account limited to `read:accounts` (all
it allows is "who am I") and names its server; this server asks that server who the
token belongs to (`/api/v1/accounts/verify_credentials`) and files the blobs under the
answer. No accounts or passwords of its own. Which servers' people it serves is a list
in the config — "*" for anyone.

    python3 fedtail_sync.py --config /etc/fedtail-sync.toml
    python3 fedtail_sync.py --listen 127.0.0.1:8471 --db sync.db --instance my.server

It lives apart from the fedtail package on purpose: an admin copies this one file to
the server, nothing else of fedtail is needed there.

Behind nginx/Caddy or a Cloudflare tunnel for TLS, on a name of its own: it is a
service apart from the fediverse server, and fedtail finds it only by the address the
user puts in sync.url. docs/en/sync.md has the config, a systemd unit, the proxy lines.

API (JSON; every call but the first needs the token):

    GET    /v1                         {"fedtail-sync": version}
    POST   /v1/blobs                   body: one blob; X-Fedtail-Device → {"seq": n}
    GET    /v1/blobs?after=N&limit=M&exclude=DEVICE
                                       {"blobs": [{"seq", "device", "data": base64}],
                                        "last": N, "more": bool}
    DELETE /v1/blobs                   the account's journal gone → {"deleted": n}
"""

import argparse
import base64
import hashlib
import ipaddress
import json
import logging
import socket
import sqlite3
import threading
import time
import tomllib
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

VERSION = 1
log = logging.getLogger("fedtail-sync")

DEFAULTS = {
    "listen": "127.0.0.1:8471",
    "db": "fedtail-sync.db",
    "instances": [],            # hosts whose accounts are served; ["*"] — any
    "quota_mb": 20,             # per account
    "max_blob_kb": 512,
    "requests_per_minute": 120,  # per account
    "keep_days": 0,             # 0: blobs are kept until the account deletes them
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS blobs (
    seq     INTEGER PRIMARY KEY AUTOINCREMENT,
    account TEXT NOT NULL,
    device  TEXT NOT NULL,
    at      INTEGER NOT NULL,
    data    BLOB NOT NULL
);
CREATE INDEX IF NOT EXISTS blobs_account ON blobs (account, seq);
"""
# options of older versions: public_url fed /.well-known/fedtail-sync, gone with
# fedtail 0.19 (it no longer looks the server up)
RETIRED = {"public_url"}
RETIRED_WHY = "no more /.well-known: fedtail takes the address from sync.url"
TOKEN_TTL = 600      # a verified token is believed this long, seconds
REFUSED_TTL = 60     # a refused one is refused without asking again this long
PAGE_MAX = 500


class Refused(Exception):
    def __init__(self, status, text):
        super().__init__(text)
        self.status = status


def host_of(instance):
    """'https://Social.Example/' or 'social.example' → 'social.example' (None: not a
    host we would ever call)."""
    text = (instance or "").strip()
    if "://" in text:
        parts = urlsplit(text)
        if parts.scheme != "https" or parts.path not in ("", "/") or parts.query:
            return None
        text = parts.netloc
    text = text.lower().rstrip("/")
    if not text or "@" in text or "/" in text:
        return None
    return text


def public_host(host):
    """Every address the name resolves to is a public one (no calls into the LAN)."""
    name = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    try:
        infos = socket.getaddrinfo(name, 443, type=socket.SOCK_STREAM)
    except OSError:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


class Server:
    def __init__(self, cfg, verify=None):
        self.cfg = {**DEFAULTS, **cfg}
        self.allowed = {str(h).lower() for h in self.cfg["instances"]}
        self.db = sqlite3.connect(self.cfg["db"], check_same_thread=False,
                                  isolation_level=None)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.executescript(SCHEMA)
        self.lock = threading.Lock()
        self.verify = verify or self._verify_at_instance
        self._tokens = {}   # sha256(host, token) -> (account or None, until)
        self._rate = {}     # account -> [window start, count]

    # ---- who is asking ---------------------------------------------------------------
    def allowed_host(self, host):
        if "*" in self.allowed:
            return public_host(host)
        return host in self.allowed

    def _verify_at_instance(self, host, token):
        """→ the account's id on its server, or None (the server says no)."""
        req = urllib.request.Request(
            f"https://{host}/api/v1/accounts/verify_credentials",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json",
                     "User-Agent": f"fedtail-sync/{VERSION}"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                data = json.loads(r.read(1024 * 1024))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return None
            raise Refused(HTTPStatus.BAD_GATEWAY, f"{host}: HTTP {e.code}") from e
        except (OSError, ValueError) as e:
            raise Refused(HTTPStatus.BAD_GATEWAY, f"{host}: {e.__class__.__name__}") from e
        acc_id = data.get("id") if isinstance(data, dict) else None
        return str(acc_id) if acc_id else None

    def account(self, headers):
        """The account behind a request's token, as 'id@host'. Refused otherwise."""
        auth = headers.get("Authorization") or ""
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        host = host_of(headers.get("X-Fedtail-Instance"))
        if not token or not host:
            raise Refused(HTTPStatus.UNAUTHORIZED, "a token and X-Fedtail-Instance, please")
        if not self.allowed_host(host):
            raise Refused(HTTPStatus.FORBIDDEN, f"{host}: not served here")
        h = hashlib.sha256(f"{host}\0{token}".encode()).hexdigest()
        now = time.monotonic()
        known = self._tokens.get(h)
        if known and known[1] > now:
            acc = known[0]
        else:
            acc_id = self.verify(host, token)
            acc = f"{acc_id}@{host}" if acc_id else None
            self._tokens[h] = (acc, now + (TOKEN_TTL if acc else REFUSED_TTL))
            if len(self._tokens) > 10000:
                self._tokens = {k: v for k, v in self._tokens.items() if v[1] > now}
        if not acc:
            raise Refused(HTTPStatus.UNAUTHORIZED, "the token is refused by its server")
        self._pace(acc)
        return acc

    def _pace(self, acc):
        now = time.monotonic()
        w = self._rate.setdefault(acc, [now, 0])
        if now - w[0] > 60:
            w[0], w[1] = now, 0
        w[1] += 1
        if w[1] > self.cfg["requests_per_minute"]:
            raise Refused(HTTPStatus.TOO_MANY_REQUESTS, "too many requests, slow down")

    # ---- the journal -----------------------------------------------------------------
    def put(self, acc, device, blob):
        if not blob:
            raise Refused(HTTPStatus.BAD_REQUEST, "an empty blob")
        if len(blob) > self.cfg["max_blob_kb"] * 1024:
            raise Refused(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "the blob is too big")
        with self.lock:
            used = self.db.execute("SELECT COALESCE(SUM(LENGTH(data)), 0) FROM blobs "
                                   "WHERE account=?", (acc,)).fetchone()[0]
            if used + len(blob) > self.cfg["quota_mb"] * 1024 * 1024:
                raise Refused(HTTPStatus.INSUFFICIENT_STORAGE, "over the quota")
            cur = self.db.execute("INSERT INTO blobs (account, device, at, data) "
                                  "VALUES (?, ?, ?, ?)", (acc, device, int(time.time()), blob))
            return cur.lastrowid

    def get(self, acc, after, limit, exclude):
        limit = max(1, min(int(limit), PAGE_MAX))
        with self.lock:
            rows = self.db.execute(
                "SELECT seq, device, data FROM blobs WHERE account=? AND seq>? "
                "ORDER BY seq LIMIT ?", (acc, int(after), limit + 1)).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        # the cursor moves past the asker's own blobs too, though they aren't sent
        last = rows[-1][0] if rows else max(int(after), 0)
        return {"blobs": [{"seq": s, "device": d, "data": base64.b64encode(b).decode()}
                          for s, d, b in rows if not exclude or d != exclude],
                "last": last, "more": more}

    def wipe(self, acc):
        with self.lock:
            return self.db.execute("DELETE FROM blobs WHERE account=?", (acc,)).rowcount

    def expire(self):
        days = self.cfg["keep_days"]
        if days:
            with self.lock:
                n = self.db.execute("DELETE FROM blobs WHERE at < ?",
                                    (int(time.time()) - days * 86400,)).rowcount
            if n:
                log.info("expired %d blobs older than %d days", n, days)


class Handler(BaseHTTPRequestHandler):
    server_version = f"fedtail-sync/{VERSION}"
    app = None  # the Server, set by make_http_server

    def log_message(self, fmt, *args):  # one line per request, never a token
        log.info("%s %s", self.address_string(), fmt % args)

    def _send(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _route(self, method):
        url = urlsplit(self.path)
        q = {k: v[-1] for k, v in parse_qs(url.query).items()}
        try:
            if method == "GET" and url.path in ("/v1", "/v1/"):
                return self._send(200, {"fedtail-sync": VERSION})
            if url.path != "/v1/blobs":
                return self._send(404, {"error": "no such thing"})
            acc = self.app.account(self.headers)
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                if n > self.app.cfg["max_blob_kb"] * 1024:
                    raise Refused(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "the blob is too big")
                device = (self.headers.get("X-Fedtail-Device") or "")[:32]
                seq = self.app.put(acc, device, self.rfile.read(n))
                return self._send(200, {"seq": seq})
            if method == "GET":
                return self._send(200, self.app.get(acc, q.get("after", 0) or 0,
                                                    q.get("limit", 200) or 200,
                                                    q.get("exclude", "")))
            if method == "DELETE":
                return self._send(200, {"deleted": self.app.wipe(acc)})
            return self._send(405, {"error": "no such method"})
        except Refused as e:
            return self._send(e.status, {"error": str(e)})
        except ValueError:
            return self._send(400, {"error": "a number was expected"})

    def do_GET(self):  # noqa: N802 — http.server's names
        self._route("GET")

    def do_POST(self):  # noqa: N802
        self._route("POST")

    def do_DELETE(self):  # noqa: N802
        self._route("DELETE")


def make_http_server(app):
    host, _, port = app.cfg["listen"].rpartition(":")
    handler = type("BoundHandler", (Handler,), {"app": app})
    return ThreadingHTTPServer((host.strip("[]") or "127.0.0.1", int(port)), handler)


def load_config(path):
    with open(path, "rb") as f:
        data = tomllib.load(f)
    for gone in RETIRED & set(data):  # an older config: said, not fatal
        log.warning("option %s is gone (%s) — ignored", gone, RETIRED_WHY)
        del data[gone]
    unknown = set(data) - set(DEFAULTS)
    if unknown:
        raise SystemExit(f"fedtail-sync: unknown options {sorted(unknown)} in {path}")
    return data


def main(argv=None):
    p = argparse.ArgumentParser(prog="fedtail-sync", description=__doc__.split("\n")[0])
    p.add_argument("--config", help="a TOML file with the options (see docs/en/sync.md)")
    p.add_argument("--listen", help=f"address:port (default {DEFAULTS['listen']})")
    p.add_argument("--db", help="the SQLite file")
    p.add_argument("--instance", action="append", help="a server whose people are served "
                   "(again for more; * — anyone)")
    a = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    cfg = load_config(a.config) if a.config else {}
    for k in ("listen", "db"):
        if getattr(a, k):
            cfg[k] = getattr(a, k)
    if a.instance:
        cfg["instances"] = a.instance
    app = Server(cfg)
    if not app.allowed:
        log.warning("no instances allowed: every request will be refused (set instances)")
    httpd = make_http_server(app)
    log.info("fedtail-sync %d on %s, serving %s", VERSION, app.cfg["listen"],
             ", ".join(sorted(app.allowed)) or "nobody")

    def expiring():
        while True:
            app.expire()
            time.sleep(3600)
    threading.Thread(target=expiring, daemon=True, name="expire").start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
