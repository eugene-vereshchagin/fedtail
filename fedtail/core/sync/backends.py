"""Where the sealed batches meet: a sync server, or a folder every device sees.

A backend knows two things: put a blob (`push`) and give the blobs other devices put
since a cursor (`pull`). It never opens a blob — they are sealed (crypto.py) — so any
dumb store will do; adding one is a class here and an option in `[sync]` that says
where it is (as `url` and `folder` do).

* `HttpBackend` — fedtail-sync (its own repository, fedtail-syncserver) or anything speaking its two
  calls. The device proves who it is with a token of the account limited to
  `read:accounts` (never the main token: that one opens the whole account), and names
  its server in `X-Fedtail-Instance` for the sync server to check the token there.
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


class BackendError(Exception):
    """kind: "auth" (the token is refused), "full" (over the quota), "gone" (no such
    server or folder), "other"."""

    def __init__(self, kind, text):
        super().__init__(text)
        self.kind = kind


class HttpBackend:
    def __init__(self, url, instance, token, session=None):
        self.url = url.rstrip("/")
        self.where = f"server {self.url} {instance}"
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = version.USER_AGENT
        self.s.headers["Authorization"] = f"Bearer {token}"
        self.s.headers["X-Fedtail-Instance"] = instance

    def _net(self, e):
        """Not got through: in words — no such name, refused, no answer, a bad
        certificate (core/neterr.py), naming the host, not "ConnectionError"."""
        from urllib.parse import urlsplit

        from .. import neterr
        log.info("sync server %s: %s: %s", self.url, e.__class__.__name__, e)
        return neterr.words(e, urlsplit(self.url).hostname or self.url)

    def _check(self, r):
        if r.status_code in (401, 403):
            raise BackendError("auth", f"sync server: {r.status_code} (token refused)")
        if r.status_code in (413, 507):
            raise BackendError("full", f"sync server: {r.status_code} (quota)")
        if r.status_code == 404:
            raise BackendError("gone", "sync server: 404 (not a fedtail-sync here?)")
        if r.status_code >= 400:
            raise BackendError("other", f"sync server: HTTP {r.status_code}")

    def push(self, blob, device):
        try:
            r = self.s.post(f"{self.url}/v1/blobs", data=blob, timeout=TIMEOUT,
                            headers={"Content-Type": "application/octet-stream",
                                     "X-Fedtail-Device": device})
        except requests.RequestException as e:
            raise BackendError("other", f"sync server: {self._net(e)}") from e
        self._check(r)

    def pull(self, cursor, device):
        """→ (blobs, new cursor, more). The cursor is the server's last sequence seen."""
        after = int(cursor or 0)
        try:
            r = self.s.get(f"{self.url}/v1/blobs", timeout=TIMEOUT,
                           params={"after": after, "limit": PAGE, "exclude": device})
        except requests.RequestException as e:
            raise BackendError("other", f"sync server: {self._net(e)}") from e
        self._check(r)
        try:
            data = r.json()
            got = [(int(b["seq"]), base64.b64decode(b["data"])) for b in data["blobs"]]
        except (ValueError, KeyError, TypeError) as e:
            raise BackendError("other", "sync server: an answer not understood") from e
        last = max([seq for seq, _ in got] + [int(data.get("last") or 0), after])
        return [b for _, b in got], last, bool(data.get("more"))


_NAME = re.compile(r"^(\d{12})\.fts$")
_DEVICE = re.compile(r"^[0-9a-f]{8,32}$")


class FolderBackend:
    def __init__(self, root):
        self.root = Path(os.path.expanduser(str(root)))
        self.where = f"folder {self.root}"

    def _ready(self):
        if not self.root.is_dir():
            raise BackendError("gone", f"sync folder {self.root}: not there")

    def push(self, blob, device):
        self._ready()
        mine = self.root / device
        mine.mkdir(exist_ok=True)
        last = max([int(m.group(1)) for p in mine.iterdir() if (m := _NAME.match(p.name))],
                   default=0)
        name = mine / f"{last + 1:012d}.fts"
        tmp = mine / f".{name.name}.part"
        tmp.write_bytes(blob)
        os.replace(tmp, name)  # a half-written file is never seen by the others

    def pull(self, cursor, device):
        """The cursor: {device: the last number read from its subfolder}."""
        self._ready()
        cursor = dict(cursor or {})
        out, more = [], False
        for sub in sorted(self.root.iterdir()):
            if not sub.is_dir() or sub.name == device or not _DEVICE.match(sub.name):
                continue
            seen = int(cursor.get(sub.name, 0))
            files = sorted((int(m.group(1)), p) for p in sub.iterdir()
                           if (m := _NAME.match(p.name)) and int(m.group(1)) > seen)
            for n, p in files:
                if len(out) >= PAGE:
                    more = True
                    break
                try:
                    out.append(p.read_bytes())
                except OSError as e:  # being synced in right now: the next round
                    log.debug("sync folder: %s: %s", p, e)
                    break
                cursor[sub.name] = n
        return out, cursor, more
