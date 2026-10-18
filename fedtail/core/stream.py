"""The server's live stream (poll.stream): something new → poll now, not in 90 s.

The stream only wakes the poller; what arrives is still fetched by the poll, so
nothing is lost when the stream drops (a laptop asleep, a proxy cutting long
connections) — it reconnects, and meanwhile polling goes on as before.

A minimal WebSocket client (RFC 6455) on the standard library: GoToSocial streams
over WebSocket only, Mastodon over both; no extra dependency for one feature.
The token goes in the Authorization header of the handshake — never into the URL,
never into the log.
"""

import base64
import hashlib
import json
import logging
import os
import socket
import ssl
import struct
import threading
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC11B85"
WAKE_ON = {"update", "notification", "status.update", "conversation", "announcement"}
IDLE_PING = 60  # no frame for this long: ping; twice in a row: reconnect
BACKOFF = (5, 15, 30, 60, 120, 300)


class StreamError(Exception):
    pass


def _ssl_context():
    try:
        import certifi  # requests brings it; the same roots as every other request
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def same_site(url, server):
    """The stream the server announces is its own: the same host, one under it
    (streaming.example.org for example.org) or a sibling (example.org's streaming and
    social hosts). Anything else gets no token."""
    a = (urlsplit(url if "://" in url else "x://" + url).hostname or "").lower()
    b = (urlsplit(server).hostname or "").lower()
    if not a or not b:
        return False
    if a == b or a.endswith("." + b):
        return True
    pa, pb = a.split(".", 1)[-1], b.split(".", 1)[-1]
    return pa == pb and "." in pa


def proxy_for(scheme, host):
    """The proxy the rest of fedtail goes through for this host (requests honours
    HTTPS_PROXY / ALL_PROXY / NO_PROXY, and on Windows the system's setting): the
    stream must not go around it straight from this IP. None: no proxy."""
    import urllib.request
    try:
        if urllib.request.proxy_bypass(host):
            return None
    except OSError:
        pass
    found = urllib.request.getproxies()
    return found.get("https" if scheme == "wss" else "http") or found.get("all") or None


def _tunnel(proxy, host, port):
    """A connection to host:port through an HTTP proxy (CONNECT). A SOCKS proxy the
    standard library can't speak: no stream then (polling goes on, through it)."""
    from urllib.parse import unquote
    p = urlsplit(proxy if "://" in proxy else "http://" + proxy)
    if p.scheme not in ("http", "https"):
        raise StreamError(f"{p.scheme} proxy: the stream can't go through it")
    raw = socket.create_connection((p.hostname, p.port or (443 if p.scheme == "https"
                                                           else 80)), timeout=15)
    try:
        if p.scheme == "https":
            raw = _ssl_context().wrap_socket(raw, server_hostname=p.hostname)
        lines = [f"CONNECT {host}:{port} HTTP/1.1", f"Host: {host}:{port}"]
        if p.username is not None:
            cred = f"{unquote(p.username)}:{unquote(p.password or '')}".encode()
            lines.append("Proxy-Authorization: Basic " + base64.b64encode(cred).decode())
        raw.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = raw.recv(4096)
            if not chunk or len(head) > 16384:
                raise StreamError("proxy: no answer to CONNECT")
            head += chunk
        status = head.split(b"\r\n", 1)[0].decode("latin-1")
        if " 200 " not in status + " ":
            raise StreamError(f"proxy refused: {status[:60]}")
    except BaseException:
        raw.close()
        raise
    return raw


class WebSocket:
    def __init__(self, url, headers, timeout=IDLE_PING):
        u = urlsplit(url)
        if u.scheme not in ("ws", "wss"):
            raise StreamError(f"not a websocket url: {u.scheme}")
        port = u.port or (443 if u.scheme == "wss" else 80)
        proxy = proxy_for(u.scheme, u.hostname)
        raw = _tunnel(proxy, u.hostname, port) if proxy else \
            socket.create_connection((u.hostname, port), timeout=15)
        if u.scheme == "wss":
            raw = _ssl_context().wrap_socket(raw, server_hostname=u.hostname)
        self.sock = raw
        self.buf = b""
        self._send_lock = threading.Lock()
        try:
            self._handshake(u, headers, timeout)
        except BaseException:
            raw.close()
            raise

    def _handshake(self, u, headers, timeout):
        key = base64.b64encode(os.urandom(16)).decode()
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        host = u.hostname + (f":{u.port}" if u.port else "")
        lines = [f"GET {path} HTTP/1.1", f"Host: {host}", "Upgrade: websocket",
                 "Connection: Upgrade", f"Sec-WebSocket-Key: {key}",
                 "Sec-WebSocket-Version: 13"]
        lines += [f"{k}: {v}" for k, v in headers.items()]
        self.sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode())
        head = self._read_until(b"\r\n\r\n").decode("latin-1")
        status = head.split("\r\n", 1)[0]
        if " 101 " not in status + " ":
            raise StreamError(f"handshake refused: {status[:80]}")
        want = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        got = {k.strip().lower(): v.strip() for k, _s, v in
               (line.partition(":") for line in head.split("\r\n")[1:]) if k}
        if got.get("sec-websocket-accept") != want:
            # Some servers' front proxies (a CDN before mastodon.social's streaming) answer
            # with an accept of their own. The 101 says the upgrade happened; if the stream
            # isn't really one, the first frame fails and the poll carries on as before.
            log.info("stream handshake: Sec-WebSocket-Accept %r, expected %r (server %s) — "
                     "going on", got.get("sec-websocket-accept"), want,
                     got.get("server") or got.get("via") or "?")
        self.sock.settimeout(timeout)

    def _read_until(self, end):
        while end not in self.buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise StreamError("closed during handshake")
            self.buf += chunk
            if len(self.buf) > 65536:
                raise StreamError("handshake too long")
        head, _s, self.buf = self.buf.partition(end)
        return head

    def _read(self, n):
        while len(self.buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise StreamError("closed")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, opcode, payload=b""):
        """A client frame: always masked (RFC 6455 §5.3)."""
        mask = os.urandom(4)
        n = len(payload)
        head = bytes([0x80 | opcode])
        if n < 126:
            head += bytes([0x80 | n])
        elif n < 65536:
            head += bytes([0x80 | 126]) + struct.pack("!H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack("!Q", n)
        body = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        with self._send_lock:
            self.sock.sendall(head + mask + body)

    def frame(self):
        """(opcode, payload) of the next whole message; pings answered on the way."""
        parts, first = [], None
        while True:
            b0, b1 = self._read(2)  # a timeout here: just quiet, the caller pings
            try:
                opcode, data, fin = self._rest(b0, b1)
            except TimeoutError:  # in the middle of a frame: the connection is gone
                raise StreamError("stalled mid-frame") from None
            if opcode == 0x9:  # ping
                self.send(0xA, data)
                continue
            if opcode in (0xA, 0x8):  # pong, close
                return opcode, data
            if first is None:
                first = opcode
            parts.append(data)
            if fin:
                return first, b"".join(parts)

    def _rest(self, b0, b1):
        fin, opcode = b0 & 0x80, b0 & 0x0F
        n = b1 & 0x7F
        if n == 126:
            n = struct.unpack("!H", self._read(2))[0]
        elif n == 127:
            n = struct.unpack("!Q", self._read(8))[0]
        if n > 16 * 1024 * 1024:
            raise StreamError("frame too big")
        mask = self._read(4) if b1 & 0x80 else None
        data = self._read(n)
        if mask:
            data = bytes(b ^ mask[i % 4] for i, b in enumerate(data))
        return opcode, data, fin

    def close(self):
        try:
            self.send(0x8, struct.pack("!H", 1000))
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass


class Stream(threading.Thread):
    """Keeps a stream open while running; on_event(name) for each event that arrives."""

    def __init__(self, base, token, on_event, streams=("user",), user_agent="fedtail"):
        """base: the streaming server (wss://host); streams: the first goes in the url
        (?stream=user, what every server understands), the rest are subscribed to."""
        super().__init__(name="fedtail-stream", daemon=True)
        self.url = base.rstrip("/") + f"/api/v1/streaming?stream={streams[0]}"
        self.token, self.on_event = token, on_event
        self.streams = streams
        self.user_agent = user_agent
        self.stop_event = threading.Event()
        self.ws = None
        self.connected = threading.Event()
        self.failures = 0

    def stop(self):
        self.stop_event.set()
        ws = self.ws
        if ws is not None:
            ws.close()

    def run(self):
        host = urlsplit(self.url).hostname
        while not self.stop_event.is_set():
            try:
                self._session()
            except (OSError, StreamError, ValueError) as e:
                if self.stop_event.is_set():
                    return
                self.failures += 1
                log.info("stream %s: %s (%s), again in %d s", host, e.__class__.__name__,
                         str(e)[:120], BACKOFF[min(self.failures, len(BACKOFF)) - 1])
            finally:
                self.connected.clear()
                if self.ws is not None:
                    self.ws.close()
                    self.ws = None
            self.stop_event.wait(BACKOFF[min(max(self.failures, 1), len(BACKOFF)) - 1])

    def _session(self):
        # GoToSocial reads the token from Sec-WebSocket-Protocol, Mastodon from either
        self.ws = WebSocket(self.url, {"Authorization": f"Bearer {self.token}",
                                       "Sec-WebSocket-Protocol": self.token,
                                       "User-Agent": self.user_agent})
        for name in self.streams[1:]:  # the first is in the url already
            self.ws.send(0x1, json.dumps({"type": "subscribe", "stream": name}).encode())
        self.connected.set()
        self.failures = 0
        log.info("stream %s: open (%s)", urlsplit(self.url).hostname, ", ".join(self.streams))
        idle = 0
        while not self.stop_event.is_set():
            try:
                opcode, data = self.ws.frame()
            except TimeoutError:
                idle += 1
                if idle >= 2:
                    raise StreamError("no answer to ping") from None
                self.ws.send(0x9, b"fedtail")
                continue
            idle = 0
            if opcode == 0x8:
                raise StreamError("closed by the server")
            if opcode != 0x1:
                continue
            try:
                msg = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                continue
            event = msg.get("event") if isinstance(msg, dict) else None
            if event:
                self.on_event(event)
