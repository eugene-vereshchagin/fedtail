"""GET from someone else's server: an ActivityPub object, nodeinfo, a picture.

Addresses come from other people's posts and servers, so each one is checked
before a connection is made, and again after every redirect (redirects are
followed here, by hand, never by requests):

* the scheme is one the caller allows (https for JSON; media may be http);
* the host resolves only to public addresses — not this computer, not the home
  network, not link-local (a cloud's metadata service), not multicast or reserved.
  The user's own server is exempt (some run it at home, on a private address);
* the body is read up to a limit and no further: a picture that never ends, a
  gigabyte "JSON", stop there;
* the connection goes to the very address that was checked (Adapter): a name that
  answers a public address to the check and 127.0.0.1 a moment later (DNS rebinding)
  meets a connection made already — the name is resolved once, when it connects.

No token is ever attached here: callers pass no Authorization and none is added.
"""

import ipaddress
import logging
import re
import socket
import time
from urllib.parse import urljoin, urlsplit

import requests

log = logging.getLogger(__name__)

JSON_MAX = 2 * 1024 * 1024
MAX_REDIRECTS = 3


class Refused(requests.RequestException):
    """Not fetched: the address or the answer breaks the rules above. A
    RequestException, so callers that give up on a dead server give up on it too."""


def _public_ip(text):
    ip = ipaddress.ip_address(text.split("%", 1)[0])
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified
                or ip in ipaddress.ip_network("100.64.0.0/10"))  # carrier NAT, Tailscale


def cleartext_ok(server):
    """May a secret go to this address — a token, a password, an invite code: https
    always; http only to a machine here or at home — localhost, a loopback or private
    address, a .local/.lan/.home.arpa name. The host as the URL parser reads it, so
    "http://localhost.evil.example" is not localhost."""
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


def check(url, schemes=("https",), own_hosts=()):
    """Raise Refused unless url may be fetched. own_hosts: hostnames exempt from the
    public-address rule (the user's own server)."""
    try:
        u = urlsplit(url)
        host = (u.hostname or "").rstrip(".").lower()
        u.port  # noqa: B018 — raises ValueError for a port that isn't one
    except (ValueError, AttributeError):
        raise Refused("not an address") from None
    if u.scheme not in schemes:
        raise Refused(f"scheme {u.scheme or '-'}")
    if not host or u.username is not None or u.password is not None:
        raise Refused("no host, or a login in the address")
    if host in own_hosts:
        return
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise Refused(f"local name {host}")
    try:
        addrs = {a[4][0] for a in socket.getaddrinfo(host, u.port or 443,
                                                     type=socket.SOCK_STREAM)}
    except (OSError, UnicodeError):
        return  # unresolvable: the request fails on its own, nothing to protect
    if not addrs or not all(_public_ip(a) for a in addrs):
        raise Refused(f"{host}: not a public address")


def _addresses(host, port, own):
    """The addresses a connection to host may go to: all of them public (or the host
    one of the user's own) — else Refused. Resolved here, once: what is checked is what
    is connected to."""
    host = (host or "").rstrip(".").lower()
    try:
        literal = ipaddress.ip_address(host.strip("[]").split("%", 1)[0])
    except ValueError:
        literal = None
    if host in own:
        return None  # the user's own server: as the system resolves it
    if literal is not None:
        if not _public_ip(str(literal)):
            raise Refused(f"{host}: not a public address")
        return [str(literal)]
    if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
        raise Refused(f"local name {host}")
    try:
        addrs = list(dict.fromkeys(a[4][0] for a in socket.getaddrinfo(
            host, port, type=socket.SOCK_STREAM)))
    except (OSError, UnicodeError):
        return None  # unresolvable: the connection fails on its own
    if not addrs or not all(_public_ip(a) for a in addrs):
        raise Refused(f"{host}: not a public address")
    return addrs


def _pinned(base, own):
    """A urllib3 connection class that connects to the addresses _addresses checked —
    the certificate and the Host header still the name's."""
    class Pinned(base):
        def _new_conn(self):
            addrs = _addresses(self._dns_host, self.port, own)
            if not addrs:
                return super()._new_conn()
            name, last = self._dns_host, None
            try:
                for addr in addrs:  # as create_connection would: each in turn
                    self._dns_host = addr
                    try:
                        return super()._new_conn()
                    except Exception as e:  # noqa: BLE001 — the next address, or this
                        last = e
                raise last
            finally:
                self._dns_host = name
    return Pinned


class Adapter(requests.adapters.HTTPAdapter):
    """requests' adapter for other people's servers: every connection to an address
    checked when it is made (see the module's words). own: the user's own hosts, exempt
    from the public-address rule. Through a proxy (net.proxy) the proxy resolves, as the
    user chose."""

    def __init__(self, *args, own=(), **kw):
        self.own = set(own)
        super().__init__(*args, **kw)

    def init_poolmanager(self, *args, **kw):
        from urllib3.connection import HTTPConnection, HTTPSConnection
        from urllib3.connectionpool import HTTPConnectionPool, HTTPSConnectionPool
        super().init_poolmanager(*args, **kw)
        http = type("PinnedPool", (HTTPConnectionPool,),
                    {"ConnectionCls": _pinned(HTTPConnection, self.own)})
        https = type("PinnedTLSPool", (HTTPSConnectionPool,),
                     {"ConnectionCls": _pinned(HTTPSConnection, self.own)})
        self.poolmanager.pool_classes_by_scheme = {"http": http, "https": https}


_SHARED = None


def pinned(session, own_hosts=()):
    """session with Adapter on it (mounted once; its own pool size kept), or a shared
    one of ours for the requests module itself (or None). own_hosts join the adapter's.
    Anything else that only looks like a session (a transport of its own: a test's,
    another library's) is used as it is — it does its own connecting."""
    global _SHARED
    if session is None or session is requests:
        if _SHARED is None:
            _SHARED = requests.Session()
        session = _SHARED
    elif not isinstance(session, requests.Session):
        return session
    for scheme in ("https://", "http://"):
        got = session.get_adapter(scheme)
        if not isinstance(got, Adapter):
            size = getattr(got, "_pool_maxsize", requests.adapters.DEFAULT_POOLSIZE)
            got = Adapter(pool_connections=getattr(got, "_pool_connections", 10),
                          pool_maxsize=size, own=own_hosts)
            session.mount(scheme, got)
        else:
            got.own.update(own_hosts)
    return session


def open_url(session, url, *, timeout, schemes=("https",), own_hosts=(), headers=None):
    """A streamed response for url, its redirects followed by hand and each checked —
    and connected to the address checked (pinned). The caller closes it (with ... as r:)."""
    from . import health
    session = pinned(session, {h.lower() for h in own_hosts})
    for _ in range(MAX_REDIRECTS + 1):
        u = urlsplit(url)
        t = time.monotonic()
        try:
            check(url, schemes, own_hosts)
            r = session.get(url, timeout=timeout, headers=headers, stream=True,
                            allow_redirects=False)
        except requests.RequestException as e:  # Refused too: what keeps failing, where
            health.REC.note(u.hostname, "GET", u.path, health.outcome_of(e), kind="remote")
            raise
        if not getattr(r, "is_redirect", False):
            health.REC.note(u.hostname, "GET", u.path, getattr(r, "status_code", 200),
                            time.monotonic() - t, kind="remote")
        if r.is_redirect and r.headers.get("Location"):
            r.close()
            url = urljoin(url, r.headers["Location"])
            continue
        return r
    raise Refused("too many redirects")


def read(r, limit):
    """The body, at most limit bytes: more than that is refused, not cut."""
    size = r.headers.get("Content-Length")
    if size and size.isdigit() and int(size) > limit:
        raise Refused(f"{size} B, more than {limit}")
    out = bytearray()
    for chunk in r.iter_content(1 << 16):
        out += chunk
        if len(out) > limit:
            raise Refused(f"more than {limit} B")
    # a connection let go before the end: what came is not the file (urllib3 says so
    # itself mostly; not always — a proxy that closes quietly, an old urllib3)
    if size and size.isdigit() and not r.headers.get("Content-Encoding") and \
            len(out) < int(size):
        raise requests.exceptions.ChunkedEncodingError(
            f"cut short: {len(out)} of {size} B")
    return bytes(out)


def get_json(url, *, headers=None, timeout=8, own_hosts=(), session=requests):
    """Parsed JSON from someone else's server, or None (not 200, not JSON, refused).
    Only the host goes into the log: whole addresses may carry signatures."""
    host = urlsplit(str(url)).hostname or "?"
    try:
        with open_url(session, url, timeout=timeout, headers=headers,
                      own_hosts=own_hosts) as r:
            if r.status_code != 200:
                return None
            body = read(r, JSON_MAX)
    except Refused as e:
        log.warning("remote %s: refused (%s)", host, e)
        return None
    try:
        import json
        return json.loads(body)
    except ValueError:
        return None


# a server's name as people type it: example.org, https://example.org/about, @x@example.org
_HOST = re.compile(r"^(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}(?::\d{1,5})?$")


def server_host(text):
    """example.org out of what was typed, or "" (not a server's name)."""
    t = (text or "").strip().lower()
    if "://" in t:
        t = urlsplit(t).netloc
    t = t.rsplit("@", 1)[-1].split("/")[0].strip(".")
    return t if _HOST.match(t) else ""
