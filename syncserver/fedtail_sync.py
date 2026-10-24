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

It faces the internet, so it guards itself (each a config option, docs/en/sync.md):
a connection is dropped after `timeout_seconds` of silence and only `max_connections`
are served at once; every client address has `requests_per_minute_per_ip`, and the
token checks it causes — calls to someone's fediverse server — are capped per address
and in all (`verifications_per_minute_per_ip`, `verifications_per_minute`), so it can
be made neither to hang nor to hammer a server; bodies are read only with an honest
Content-Length; the token check follows no redirect and, for "*", talks only to public
addresses (checked on the connected socket, not just the name); the disk is capped per
account (`quota_mb`) and in all (`total_mb`). Behind a proxy on the same machine
(cloudflared, nginx), `client_ip_header` names the header with the real address —
believed only from a loopback peer.

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
import http.client
import ipaddress
import json
import logging
import re
import socket
import sqlite3
import ssl
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
    "total_mb": 1024,           # all accounts together; 0 — no cap
    "timeout_seconds": 30,      # a silent connection is dropped after this
    "max_connections": 64,      # served at once; more are closed at the door
    "requests_per_minute_per_ip": 240,
    "verifications_per_minute_per_ip": 10,  # token checks at a fediverse server
    "verifications_per_minute": 60,         # … in all
    "client_ip_header": "",     # e.g. "CF-Connecting-IP"; believed from loopback only
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
SEQ_MAX = 2 ** 62    # beyond any real sequence; bigger numbers are nonsense
DEVICE_RE = re.compile(r"^[A-Za-z0-9_-]{0,32}$")
VERIFY_TIMEOUT = 10  # seconds for a fediverse server to say whose a token is


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
    if not text or "@" in text or "/" in text or not re.fullmatch(r"[a-z0-9.:\[\]-]+", text):
        return None
    return text


def is_public_ip(addr):
    try:
        return ipaddress.ip_address(addr.split("%", 1)[0]).is_global
    except ValueError:
        return False


def public_host(host):
    """Every address the name resolves to is a public one (no calls into the LAN)."""
    name = host.rsplit(":", 1)[0] if host.count(":") == 1 else host
    try:
        infos = socket.getaddrinfo(name.strip("[]"), 443, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return False
    return bool(infos) and all(is_public_ip(i[4][0]) for i in infos)


class NotPublic(OSError):
    pass


class _PublicOnlyHTTPS(http.client.HTTPSConnection):
    """HTTPS that refuses, once connected, a peer that isn't a public address — the name
    may resolve to another address than the one checked a moment before (DNS
    rebinding)."""

    def connect(self):
        super().connect()
        peer = self.sock.getpeername()[0]
        if not is_public_ip(peer):
            self.sock.close()
            raise NotPublic(f"{self.host} is at {peer}, not a public address")


class _PublicOnlyHandler(urllib.request.HTTPSHandler):
    def https_open(self, req):
        return self.do_open(_PublicOnlyHTTPS, req, context=self._context)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """A token check follows no redirect: a 3xx would carry the token elsewhere, and
    with "*" anywhere, the LAN included."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # urllib raises HTTPError for the 3xx itself


def opener(public_only):
    ctx = ssl.create_default_context()
    https = _PublicOnlyHandler(context=ctx) if public_only else \
        urllib.request.HTTPSHandler(context=ctx)
    return urllib.request.build_opener(_NoRedirect, https)


class Window:
    """Counts per key in one-minute windows, thread-safe, never growing without end."""

    def __init__(self, limit_per_minute, max_keys=50_000):
        self.limit = limit_per_minute
        self.max_keys = max_keys
        self.counts = {}
        self.lock = threading.Lock()

    def hit(self, key):
        """Count one; → False when the key is over its limit this minute (0: no limit)."""
        if not self.limit:
            return True
        now = time.monotonic()
        with self.lock:
            w = self.counts.get(key)
            if w is None or now - w[0] > 60:
                if len(self.counts) >= self.max_keys:
                    self.counts = {k: v for k, v in self.counts.items() if now - v[0] <= 60}
                    if len(self.counts) >= self.max_keys:
                        return False  # flooded with keys: no one new this minute
                w = self.counts[key] = [now, 0]
            w[1] += 1
            return w[1] <= self.limit


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
        self._tokens_lock = threading.Lock()
        self.per_account = Window(self.cfg["requests_per_minute"])
        self.per_ip = Window(self.cfg["requests_per_minute_per_ip"])
        self.verify_ip = Window(self.cfg["verifications_per_minute_per_ip"])
        self.verify_all = Window(self.cfg["verifications_per_minute"])
        # bytes kept: per account and in all (checked on every put without a scan)
        self.used = dict(self.db.execute(
            "SELECT account, SUM(LENGTH(data)) FROM blobs GROUP BY account").fetchall())
        self.total = sum(self.used.values())

    # ---- who is asking ---------------------------------------------------------------
    def allowed_host(self, host):
        if "*" in self.allowed:
            return public_host(host)
        return host in self.allowed

    def _verify_at_instance(self, host, token):
        """→ the account's id on its server, or None (the server says no)."""
        return self.fetch_account(f"https://{host}/api/v1/accounts/verify_credentials",
                                  token, public_only="*" in self.allowed)

    @staticmethod
    def fetch_account(url, token, public_only=False):
        if urlsplit(url).scheme not in ("https", "http"):  # http:// only in the tests
            raise Refused(HTTPStatus.BAD_GATEWAY, "not a web address")
        req = urllib.request.Request(  # noqa: S310 — the scheme is checked just above
            url, headers={"Authorization": f"Bearer {token}", "Accept": "application/json",
                          "User-Agent": f"fedtail-sync/{VERSION}"})
        host = urlsplit(url).netloc
        try:
            with opener(public_only).open(req, timeout=VERIFY_TIMEOUT) as r:  # nosec B310
                data = json.loads(r.read(64 * 1024))
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return None
            raise Refused(HTTPStatus.BAD_GATEWAY, f"{host}: HTTP {e.code}") from e
        except (OSError, ValueError, http.client.HTTPException) as e:
            raise Refused(HTTPStatus.BAD_GATEWAY, f"{host}: {e.__class__.__name__}") from e
        acc_id = data.get("id") if isinstance(data, dict) else None
        if not isinstance(acc_id, (str, int)) or not str(acc_id) or len(str(acc_id)) > 64:
            return None
        return str(acc_id)

    def let_in(self, ip):
        """The door: every request counts against its address."""
        if not self.per_ip.hit(ip):
            raise Refused(HTTPStatus.TOO_MANY_REQUESTS, "too many requests from you, slow down")

    def account(self, headers, ip="?"):
        """The account behind a request's token, as 'id@host'. Refused otherwise."""
        auth = headers.get("Authorization") or ""
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        host = host_of(headers.get("X-Fedtail-Instance"))
        if not token or not host or len(token) > 512:
            raise Refused(HTTPStatus.UNAUTHORIZED, "a token and X-Fedtail-Instance, please")
        if not self.allowed_host(host):
            raise Refused(HTTPStatus.FORBIDDEN, f"{host}: not served here")
        h = hashlib.sha256(f"{host}\0{token}".encode()).hexdigest()
        now = time.monotonic()
        with self._tokens_lock:
            known = self._tokens.get(h)
        if known and known[1] > now:
            acc = known[0]
        else:
            # a call to someone's server: capped per address and in all, so that
            # random tokens can't turn this server into a hammer
            if not self.verify_ip.hit(ip) or not self.verify_all.hit("*"):
                raise Refused(HTTPStatus.TOO_MANY_REQUESTS, "too many token checks, later")
            acc_id = self.verify(host, token)
            acc = f"{acc_id}@{host}" if acc_id else None
            with self._tokens_lock:
                self._tokens[h] = (acc, now + (TOKEN_TTL if acc else REFUSED_TTL))
                if len(self._tokens) > 10000:
                    self._tokens = {k: v for k, v in self._tokens.items() if v[1] > now}
        if not acc:
            raise Refused(HTTPStatus.UNAUTHORIZED, "the token is refused by its server")
        if not self.per_account.hit(acc):
            raise Refused(HTTPStatus.TOO_MANY_REQUESTS, "too many requests, slow down")
        return acc

    # ---- the journal -----------------------------------------------------------------
    def put(self, acc, device, blob):
        if not blob:
            raise Refused(HTTPStatus.BAD_REQUEST, "an empty blob")
        if len(blob) > self.cfg["max_blob_kb"] * 1024:
            raise Refused(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "the blob is too big")
        if not DEVICE_RE.match(device):
            raise Refused(HTTPStatus.BAD_REQUEST, "X-Fedtail-Device: letters and digits")
        with self.lock:
            if self.used.get(acc, 0) + len(blob) > self.cfg["quota_mb"] * 1024 * 1024:
                raise Refused(HTTPStatus.INSUFFICIENT_STORAGE, "over the quota")
            cap = self.cfg["total_mb"] * 1024 * 1024
            if cap and self.total + len(blob) > cap:
                log.warning("the server is full (total_mb = %d)", self.cfg["total_mb"])
                raise Refused(HTTPStatus.INSUFFICIENT_STORAGE, "the server is full")
            cur = self.db.execute("INSERT INTO blobs (account, device, at, data) "
                                  "VALUES (?, ?, ?, ?)", (acc, device, int(time.time()), blob))
            self.used[acc] = self.used.get(acc, 0) + len(blob)
            self.total += len(blob)
            return cur.lastrowid

    def get(self, acc, after, limit, exclude):
        limit = max(1, min(int(limit), PAGE_MAX))
        after = max(0, min(int(after), SEQ_MAX))
        with self.lock:
            rows = self.db.execute(
                "SELECT seq, device, data FROM blobs WHERE account=? AND seq>? "
                "ORDER BY seq LIMIT ?", (acc, after, limit + 1)).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        # the cursor moves past the asker's own blobs too, though they aren't sent
        last = rows[-1][0] if rows else after
        return {"blobs": [{"seq": s, "device": d, "data": base64.b64encode(b).decode()}
                          for s, d, b in rows if not exclude or d != exclude],
                "last": last, "more": more}

    def wipe(self, acc):
        with self.lock:
            n = self.db.execute("DELETE FROM blobs WHERE account=?", (acc,)).rowcount
            self.total -= self.used.pop(acc, 0)
            return n

    def expire(self):
        days = self.cfg["keep_days"]
        if days:
            with self.lock:
                n = self.db.execute("DELETE FROM blobs WHERE at < ?",
                                    (int(time.time()) - days * 86400,)).rowcount
                if n:
                    self.used = dict(self.db.execute(
                        "SELECT account, SUM(LENGTH(data)) FROM blobs GROUP BY account"))
                    self.total = sum(self.used.values())
            if n:
                log.info("expired %d blobs older than %d days", n, days)


def _number(q, name, default):
    text = q.get(name, "")
    if text == "":
        return default
    if not re.fullmatch(r"\d{1,19}", text):
        raise Refused(HTTPStatus.BAD_REQUEST, f"{name}: a number was expected")
    return min(int(text), SEQ_MAX)


class Handler(BaseHTTPRequestHandler):
    server_version = f"fedtail-sync/{VERSION}"
    sys_version = ""
    protocol_version = "HTTP/1.0"  # one request per connection: nothing kept open
    app = None  # the Server, set by make_http_server
    timeout = 30  # set from the config by make_http_server

    def log_message(self, fmt, *args):  # one line per request, never a token
        log.info("%s %s", getattr(self, "client_ip", self.client_address[0]), fmt % args)

    def _send(self, status, obj):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _real_ip(self):
        """The address requests count against: a loopback peer's proxy header, if the
        config names one and it holds an address; the peer itself otherwise."""
        peer = self.client_address[0]
        name = self.app.cfg["client_ip_header"]
        if name:
            try:
                local = ipaddress.ip_address(peer.split("%", 1)[0]).is_loopback
            except ValueError:
                local = False
            given = (self.headers.get(name) or "").strip()
            if local and given:
                try:
                    return str(ipaddress.ip_address(given))
                except ValueError:
                    pass
        return peer

    def _body(self):
        """Exactly Content-Length bytes, or Refused: no length, a strange one, too big,
        or fewer bytes than promised before the timeout."""
        text = self.headers.get("Content-Length")
        if text is None or self.headers.get("Transfer-Encoding"):
            raise Refused(HTTPStatus.LENGTH_REQUIRED, "Content-Length, please")
        if not re.fullmatch(r"\d{1,12}", text.strip()):
            raise Refused(HTTPStatus.BAD_REQUEST, "Content-Length: a number")
        n = int(text)
        if n > self.app.cfg["max_blob_kb"] * 1024:
            raise Refused(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "the blob is too big")
        data = self.rfile.read(n)
        if len(data) != n:
            raise Refused(HTTPStatus.BAD_REQUEST, "the body is shorter than promised")
        return data

    def _route(self, method):
        self.client_ip = self._real_ip()
        url = urlsplit(self.path)
        try:
            q = {k: v[-1] for k, v in parse_qs(url.query, max_num_fields=10).items()}
            self.app.let_in(self.client_ip)
            if method == "GET" and url.path in ("/v1", "/v1/"):
                return self._send(200, {"fedtail-sync": VERSION})
            if url.path != "/v1/blobs":
                return self._send(404, {"error": "no such thing"})
            if method not in ("GET", "POST", "DELETE"):
                return self._send(405, {"error": "no such method"})
            acc = self.app.account(self.headers, self.client_ip)
            if method == "POST":
                blob = self._body()
                device = self.headers.get("X-Fedtail-Device") or ""
                return self._send(200, {"seq": self.app.put(acc, device, blob)})
            if method == "GET":
                exclude = q.get("exclude", "")
                if not DEVICE_RE.match(exclude):
                    raise Refused(HTTPStatus.BAD_REQUEST, "exclude: a device id")
                return self._send(200, self.app.get(acc, _number(q, "after", 0),
                                                    _number(q, "limit", 200), exclude))
            return self._send(200, {"deleted": self.app.wipe(acc)})
        except Refused as e:
            return self._send(e.status, {"error": str(e)})
        except (TimeoutError, ConnectionError):
            self.close_connection = True  # the client went quiet or away: nothing to say
        except ValueError:
            return self._send(400, {"error": "a bad request"})
        except Exception:  # noqa: BLE001 — logged here, never shown to the client
            log.exception("%s %s failed", method, url.path)
            return self._send(500, {"error": "internal error"})

    def do_GET(self):  # noqa: N802 — http.server's names
        self._route("GET")

    def do_POST(self):  # noqa: N802
        self._route("POST")

    def do_DELETE(self):  # noqa: N802
        self._route("DELETE")


class HTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer with a cap: past `max_connections` at once, a new connection
    is closed at the door instead of getting a thread of its own."""

    daemon_threads = True
    request_queue_size = 128

    def __init__(self, address, handler, max_connections):
        self.slots = threading.BoundedSemaphore(max_connections)
        super().__init__(address, handler)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            log.warning("%s: too many connections, closed", client_address[0])
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        # a whole request in twice the timeout: a client trickling a byte now and then
        # (each under the timeout) is cut all the same
        def cut():
            try:
                request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        timer = threading.Timer(2 * self.RequestHandlerClass.timeout, cut)
        timer.daemon = True
        timer.start()
        try:
            super().process_request_thread(request, client_address)
        finally:
            timer.cancel()
            self.slots.release()

    def handle_error(self, request, client_address):  # a dropped client: one quiet line
        log.debug("%s: connection error", client_address[0], exc_info=True)


def make_http_server(app):
    host, _, port = app.cfg["listen"].rpartition(":")
    host = host.strip("[]") or "127.0.0.1"
    handler = type("BoundHandler", (Handler,), {"app": app,
                                                 "timeout": app.cfg["timeout_seconds"]})
    try:
        if not ipaddress.ip_address(host).is_loopback:
            log.warning("listening on %s: plain HTTP to the network — put it behind a "
                        "proxy that does TLS and listen on 127.0.0.1", host)
    except ValueError:
        pass
    cls = type("HTTPServer6", (HTTPServer,), {"address_family": socket.AF_INET6}) \
        if ":" in host else HTTPServer
    return cls((host, int(port)), handler, app.cfg["max_connections"])


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
