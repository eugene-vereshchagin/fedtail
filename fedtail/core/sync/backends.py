"""Where the sealed batches meet: a sync server, or a folder every device sees.

A backend knows two things: put a blob (`push`, → its place in the journal) and give the
blobs other devices put since a cursor (`pull`) — and, where it can, drops a device's own
blobs older than a place (`can_compact`, `compact`: the device has just sent a snapshot of
all it knows) and keeps the pictures of drafts by name beside them (`media_kb`,
`media_put`, `media_get`, `media_delete`). It never opens a blob —
they are sealed (crypto.py) — so any dumb store will do; adding one is a class here and
an option in `[sync]` that says where it is (as `url` and `folder` do).

* `HttpBackend` — fedtail-sync (its own repository, fedtail-syncserver), protocol 2: the
  journal is the key's — the device names it by an id derived from the key and proves it
  has the key by a secret derived from it too (the key never goes there); a journal not
  there yet is made with the invite code the server's admin gave. No fediverse account
  is asked anything.
* `FolderBackend` — a folder: a mounted NAS share, WebDAV through davfs/rclone, a
  Syncthing folder. Each device writes only into its own subfolder, so two devices
  never write the same file.

The sync server is a service of its own, apart from the fediverse server: the user
names it in `sync.url`; nothing is looked up.
"""

import base64
import logging
import os
import re
from pathlib import Path

import requests

from ... import version

log = logging.getLogger(__name__)

TIMEOUT = (10, 30)
PAGE = 200  # blobs per pull
FOLDER_MEDIA_KB = 4096  # a picture a folder takes (the server says its own)
_MEDIA_NAME = re.compile(r"^[0-9a-f]{32,64}$")


class BackendError(Exception):
    """kind: "auth" (the token is refused), "full" (over the quota), "gone" (no such
    server or folder), "other"."""

    def __init__(self, kind, text):
        super().__init__(text)
        self.kind = kind


PROTOCOL = 2  # what fedtail-sync speaks with this fedtail (PROTOCOL.md)
# the most a sync server's answer may be: a page of blobs (PAGE of max_blob_kb, base64)
# or a picture — far more than either; beyond it the server isn't one to believe
ANSWER_MAX = 64 * 1024 * 1024


def _capped(r, most=ANSWER_MAX):
    """The answer's bytes, read once and kept on it; more than `most` — refused."""
    got = getattr(r, "_fedtail_body", None)
    if got is not None:
        return got
    chunks, size = [], 0
    for chunk in r.iter_content(64 * 1024):
        size += len(chunk)
        if size > most:
            r.close()
            raise BackendError("other", "sync: an answer bigger than any it should give")
        chunks.append(chunk)
    r._fedtail_body = got = b"".join(chunks)
    r._content = got  # r.json() and r.content read what was read
    r._content_consumed = True
    return got


class HttpBackend:
    """key None: only what needs no journal — the server's hello, the key under a
    password (escrow_get)."""

    def __init__(self, url, key=None, invite="", session=None):
        from . import crypto
        self.url = url.rstrip("/")
        self.where = f"server {self.url}"
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = version.USER_AGENT
        if key is not None:
            self.s.headers["Authorization"] = f"Bearer {crypto.journal_secret(key)}"
            self.s.headers["X-Fedtail-Journal"] = crypto.journal_id(key)
            self.where = f"server {self.url} {crypto.journal_id(key)}"
        if invite:
            self.s.headers["X-Fedtail-Invite"] = str(invite).strip()

    def _net(self, e):
        """Not got through: in words — no such name, refused, no answer, a bad
        certificate (core/neterr.py), naming the host, not "ConnectionError"."""
        from urllib.parse import urlsplit

        from .. import neterr
        log.info("sync server %s: %s: %s", self.url, e.__class__.__name__, e)
        return neterr.words(e, urlsplit(self.url).hostname or self.url)

    def _check(self, r):
        if r.status_code == 401:
            raise BackendError("auth", "sync server: 401 (not this journal's key)")
        if r.status_code == 403:
            raise BackendError("invite", "sync server: 403 (an invite code is needed, or "
                                         "it was taken back)")
        if r.status_code in (413, 507):
            raise BackendError("full", f"sync server: {r.status_code} (quota)")
        if r.status_code == 404:
            raise BackendError("gone", "sync server: 404 (not a fedtail-sync 0.22 here?)")
        if r.status_code >= 400:
            raise BackendError("other", f"sync server: HTTP {r.status_code}")
        if r.status_code >= 300:  # not followed (_call): sync.url should be where it points
            raise BackendError("other", f"sync server: HTTP {r.status_code} to "
                                        f"{r.headers.get('Location', '?')} — put that "
                                        "address in sync.url")

    def _call(self, method, path, **kw):
        """One request to the server — never followed elsewhere: a redirect would carry
        the journal's id and the invite code to another host (requests drops only
        Authorization); the answer read at most ANSWER_MAX (the store is not trusted)."""
        self.ready()
        try:
            r = self.s.request(method, f"{self.url}/v2{path}", timeout=TIMEOUT,
                               allow_redirects=False, stream=True, **kw)
            _capped(r)  # read (capped) while the error can still say why
            return r
        except requests.RequestException as e:
            raise BackendError("other", f"sync server: {self._net(e)}") from e

    def _hello(self):
        """GET /v2, asked once: what this server does ({} when it couldn't say — asked
        again next time)."""
        if getattr(self, "_said", None) is None:
            try:
                r = self.s.get(f"{self.url}/v2", timeout=TIMEOUT, allow_redirects=False,
                               stream=True)
                _capped(r)
                said = r.json() if r.ok else {}
            except (requests.RequestException, ValueError, BackendError):
                return {}
            self._said = said if isinstance(said, dict) else {}
        return self._said

    def ready(self):
        """A server that speaks another protocol is told, not talked to: an older
        fedtail-sync (1) files journals by fediverse accounts."""
        said = self._hello()
        got = said.get("fedtail-sync")
        if said and got != PROTOCOL:
            raise BackendError("gone", f"sync server: protocol {got}, this fedtail speaks "
                                       f"{PROTOCOL} — the server needs fedtail-sync 0.22+")

    def push(self, blob, device):
        """→ the blob's seq: its place in the journal (0 if not said)."""
        r = self._call("POST", "/blobs", data=blob,
                       headers={"Content-Type": "application/octet-stream",
                                "X-Fedtail-Device": device})
        self._check(r)
        try:
            return int(r.json().get("seq") or 0)
        except (ValueError, AttributeError, TypeError):
            return 0

    def pull(self, cursor, device):
        """→ (blobs, new cursor, more). The cursor is the server's last sequence seen."""
        after = int(cursor or 0)
        r = self._call("GET", "/blobs",
                       params={"after": after, "limit": PAGE, "exclude": device})
        self._check(r)
        try:
            data = r.json()
            got = [(int(b["seq"]), base64.b64decode(b["data"])) for b in data["blobs"]]
        except (ValueError, KeyError, TypeError) as e:
            raise BackendError("other", "sync server: an answer not understood") from e
        last = max([seq for seq, _ in got] + [int(data.get("last") or 0), after])
        return [b for _, b in got], last, bool(data.get("more"))

    def can_compact(self):
        return bool(self._hello().get("compact"))

    def compact(self, device, before):
        """This device's blobs older than `before` (a seq) gone (PROTOCOL.md). → how many."""
        if not _DEVICE.match(device) or not self.can_compact():
            return 0
        r = self._call("DELETE", f"/devices/{device}", params={"before": int(before)})
        self._check(r)
        try:
            return int(r.json().get("deleted") or 0)
        except (ValueError, AttributeError, TypeError):
            return 0

    # ---- the key under a password: /v2/escrow, its id in a header -------------------
    # (the id is a password's stretch: in a URL it would sit in every log of a request)
    def escrow_put(self, eid, blob):
        r = self._call("PUT", "/escrow", data=blob,
                       headers={"Content-Type": "application/octet-stream",
                                "X-Fedtail-Escrow": eid})
        if r.status_code == 409:
            raise BackendError("other", "sync server: 409 (another journal's key is kept "
                                        "under this password: choose another)")
        self._check(r)

    def escrow_get(self, eid):
        """The sealed key, or None — none under this id (the password is another)."""
        r = self._call("GET", "/escrow", headers={"X-Fedtail-Escrow": eid})
        if r.status_code == 404:
            return None
        self._check(r)
        return _capped(r)

    # ---- the pictures of drafts (PROTOCOL.md: /v2/media) ---------------------------
    def media_kb(self):
        """The biggest picture the server keeps, in KB; 0 — it keeps none (an older one,
        or turned off)."""
        try:
            return int(self._hello().get("media_kb") or 0)
        except (ValueError, TypeError):
            return 0

    def _media(self, method, name, **kw):
        if not _MEDIA_NAME.match(name):
            raise ValueError(name)
        return self._call(method, f"/media/{name}", **kw)

    def media_put(self, name, blob):
        r = self._media("PUT", name, data=blob,
                        headers={"Content-Type": "application/octet-stream"})
        self._check(r)

    def media_get(self, name):
        """The sealed bytes, or None — gone (the server drops the least used)."""
        r = self._media("GET", name)
        if r.status_code == 404:
            return None
        self._check(r)
        return r.content

    def media_delete(self, name):
        r = self._media("DELETE", name)
        if r.status_code != 404:
            self._check(r)


_NAME = re.compile(r"^(\d{12})\.fts$")
_DEVICE = re.compile(r"^[0-9a-f]{8,32}$")


class TreeBackend:
    """A journal kept as files in a tree: <root>/<device>/<number>.fts, each device
    writing only into its own folder (so two devices never write the same file), the
    drafts' pictures in <root>/media/. What the tree is — a folder here, a WebDAV
    folder over the net — is its `tree` (LocalTree, DavTree): the same few calls."""

    def __init__(self, tree, where):
        self.tree = tree
        self.where = where

    def _numbers(self, device):
        # one that can't be read yet stays in: the reading stops at it, not past it
        return sorted(int(m.group(1)) for name, _is_dir in self.tree.list(device) or ()
                      if (m := _NAME.match(name)))

    def push(self, blob, device):
        """→ the blob's number in this device's folder."""
        self.tree.ready()
        self.tree.mkdir(device)
        n = (self._numbers(device) or [0])[-1] + 1
        self.tree.write(f"{device}/{n:012d}.fts", blob)
        return n

    def pull(self, cursor, device):
        """The cursor: {device: the last number read from its folder}."""
        self.tree.ready()
        cursor = dict(cursor or {})
        out, more = [], False
        for sub, is_dir in sorted(self.tree.list("") or ()):
            if not is_dir or sub == device or not _DEVICE.match(sub):
                continue
            seen = int(cursor.get(sub, 0))
            for n in (n for n in self._numbers(sub) if n > seen):
                if len(out) >= PAGE:
                    more = True
                    break
                blob = self.tree.read(f"{sub}/{n:012d}.fts")
                if blob is None:  # being synced in right now: the next round
                    break
                out.append(blob)
                cursor[sub] = n
        return out, cursor, more

    def can_compact(self):
        return True

    def compact(self, device, before):
        """This device's files numbered below `before` gone. The newest stays always, so
        the numbers go on from it. → how many."""
        self.tree.ready()
        if not _DEVICE.match(device):
            return 0
        old = [n for n in self._numbers(device)[:-1] if n < int(before)]
        for n in old:
            self.tree.delete(f"{device}/{n:012d}.fts")
        return len(old)

    # ---- the pictures of drafts: <root>/media/<name> -------------------------------
    def media_kb(self):
        return FOLDER_MEDIA_KB

    def _media(self, name):
        if not _MEDIA_NAME.match(name):
            raise ValueError(name)
        self.tree.ready()
        return f"media/{name}"

    def media_put(self, name, blob):
        path = self._media(name)
        if self.tree.read(path) is not None:
            return
        self.tree.mkdir("media")
        self.tree.write(path, blob)

    def media_get(self, name):
        return self.tree.read(self._media(name))

    def media_delete(self, name):
        self.tree.delete(self._media(name))


class LocalTree:
    """A folder on this computer: a mounted share, a Syncthing folder."""

    def __init__(self, root):
        self.root = root

    def ready(self):
        if not self.root.is_dir():
            raise BackendError("gone", f"sync folder {self.root}: not there")

    def list(self, sub):
        try:
            return [(p.name, p.is_dir()) for p in (self.root / sub).iterdir()]
        except (FileNotFoundError, NotADirectoryError):
            return None

    def read(self, path):
        try:
            return (self.root / path).read_bytes()
        except OSError as e:  # gone, or a file still arriving
            log.debug("sync folder: %s: %s", path, e)
            return None

    def write(self, path, blob):
        f = self.root / path
        tmp = f.with_name(f".{f.name}.part")
        tmp.write_bytes(blob)
        os.replace(tmp, f)  # a half-written file is never seen by the others

    def mkdir(self, sub):
        (self.root / sub).mkdir(exist_ok=True)

    def delete(self, path):
        (self.root / path).unlink(missing_ok=True)


class FolderBackend(TreeBackend):
    def __init__(self, root):
        self.root = Path(os.path.expanduser(str(root)))
        super().__init__(LocalTree(self.root), f"folder {self.root}")


DAV_LIST_MAX = 8 * 1024 * 1024  # the most a folder's listing may be: it's someone's server
_DAV = "{DAV:}"


def _xml(body):
    """Someone's server's XML, parsed without what makes XML dangerous: no DTD at all, so
    no entities to expand (the billion laughs) and none pointing outside (XXE). A
    multistatus never needs one: expat looks first and stops at a DTD."""
    import xml.etree.ElementTree as ET
    from xml.parsers import expat

    def refused(*_a):
        raise ValueError("a DTD in a WebDAV answer")
    look = expat.ParserCreate()
    look.StartDoctypeDeclHandler = refused
    look.EntityDeclHandler = refused
    try:
        look.Parse(body, True)
    except expat.ExpatError as e:
        raise ET.ParseError(str(e)) from e
    # no DTD in it (above): nothing left for defusedxml to defuse
    return ET.fromstring(body)  # noqa: S314  # nosec B314


class DavTree:
    """A WebDAV folder (Nextcloud, ownCloud, a NAS, Apache's mod_dav, rclone serve
    webdav…) spoken directly: PROPFIND to list, GET, PUT, DELETE, MKCOL. The password is
    sent only to that address (Basic, so https:// — or a plain address on one's own
    network, the user's choice)."""

    def __init__(self, url, user, password, session=None):
        from urllib.parse import urlsplit
        self.url = url.rstrip("/") + "/"
        self.base = urlsplit(self.url).path
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = version.USER_AGENT
        self.s.auth = (user, password)
        self._made = set()

    def _call(self, method, path="", **kw):
        from urllib.parse import quote
        try:
            most = kw.pop("most", ANSWER_MAX)
            r = self.s.request(method, self.url + quote(path), timeout=TIMEOUT,
                               allow_redirects=False, stream=True, **kw)
            _capped(r, most)  # someone's server: no answer bigger than it should be
            return r
        except requests.RequestException as e:
            from urllib.parse import urlsplit

            from .. import neterr
            log.info("sync webdav %s: %s: %s", self.url, e.__class__.__name__, e)
            host = urlsplit(self.url).hostname or self.url
            raise BackendError("other", f"WebDAV: {neterr.words(e, host)}") from e

    def _check(self, r, path):
        if r.status_code in (401, 403):
            raise BackendError("auth", f"WebDAV: {r.status_code} (the user or the password)")
        if r.status_code == 507:
            raise BackendError("full", "WebDAV: 507 (no room)")
        if r.status_code >= 400 or 300 <= r.status_code < 400:
            raise BackendError("other", f"WebDAV {path or '/'}: HTTP {r.status_code}")

    def ready(self):
        if "" in self._made:
            return
        r = self._call("PROPFIND", headers={"Depth": "0"})
        if r.status_code == 404:  # the folder isn't there yet: made (its parent must be)
            r = self._call("MKCOL")
            if r.status_code == 409:
                raise BackendError("gone", f"WebDAV {self.url}: no such folder above it")
        self._check(r, "")
        self._made.add("")

    def list(self, sub):
        """[(name, is a folder)], or None — no such folder."""
        import xml.etree.ElementTree as ET
        from urllib.parse import unquote, urlsplit
        path = f"{sub}/" if sub else ""
        r = self._call("PROPFIND", path, headers={"Depth": "1", "Content-Type": "text/xml"},
                       data=b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:"><d:prop>'
                            b'<d:resourcetype/></d:prop></d:propfind>', most=DAV_LIST_MAX)
        if r.status_code == 404:
            return None
        self._check(r, path)
        body = _capped(r)
        try:
            root = _xml(body)
        except (ET.ParseError, ValueError) as e:
            raise BackendError("other", f"WebDAV {path}: an answer not understood") from e
        here = (self.base + path).rstrip("/")
        out = []
        for resp in root.iter(f"{_DAV}response"):
            href = unquote(urlsplit((resp.findtext(f"{_DAV}href") or "").strip()).path)
            name = href.rstrip("/").rsplit("/", 1)[-1]
            if href.rstrip("/") == here or not name:
                continue
            out.append((name, resp.find(f".//{_DAV}collection") is not None))
        return out

    def read(self, path):
        r = self._call("GET", path)
        if r.status_code == 404:
            return None
        self._check(r, path)
        return r.content

    def write(self, path, blob):
        self._check(self._call("PUT", path, data=blob,
                               headers={"Content-Type": "application/octet-stream"}), path)

    def mkdir(self, sub):
        if sub in self._made:
            return
        r = self._call("MKCOL", f"{sub}/")
        if r.status_code != 405:  # 405: it is there already
            self._check(r, sub)
        self._made.add(sub)

    def delete(self, path):
        r = self._call("DELETE", path)
        if r.status_code != 404:
            self._check(r, path)


class WebDavBackend(TreeBackend):
    def __init__(self, url, user, password, session=None):
        super().__init__(DavTree(url, user, password, session), f"webdav {url}")
