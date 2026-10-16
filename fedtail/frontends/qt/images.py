"""Avatars and thumbnails: memory + disk cache, downloaded in worker threads.

The auth token is never sent along: media often lives on other servers.
"""

import hashlib
import logging
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import requests
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from ...core.api import USER_AGENT

log = logging.getLogger(__name__)
FEED_SIDE = 1200
MEM_MB = 128  # default memory budget for decoded pictures (ui.image_cache_mb)


class Images:
    RETRY_AFTER = 300  # s: a picture that just failed isn't asked for again before that
    def __init__(self, core, bridge):
        self.core = core
        self.bridge = bridge
        self.cache_dir = core.paths.cache_dir
        # decoded pictures, least recently used first; bounded by bytes, not by count:
        # a hundred 1200-px photos alone are half a gigabyte
        self.mem = OrderedDict()
        self.mem_bytes = 0
        self.mem_budget = int(core.cfg["ui"].get("image_cache_mb", MEM_MB)) * 1024 * 1024
        self.waiting = {}
        self.broken = {}  # url -> when it last failed (monotonic)
        self.why = {}     # url -> ("network" | "format", detail) of its last failure
        # own pool: a backlog of avatars must never delay sending a post
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="fedtail-img")
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT

    def _download(self, url, max_side):
        p = self.cache_dir / hashlib.sha1(url.encode()).hexdigest()
        img = QImage()  # QImage is fine outside the GUI thread
        if p.exists():
            img = QImage.fromData(p.read_bytes())
            if img.isNull():
                p.unlink(missing_ok=True)  # a broken file from before: fetch again
        if img.isNull():
            t = time.monotonic()
            try:
                # 10 s to connect, 30 s of silence at most: a server stuck fetching a
                # remote original must not hold one of the four image workers for a minute
                # — but an original opened in the viewer is worth waiting for: a server
                # may be fetching it from the author's server right now
                r = self.http.get(url, timeout=(10, 30 if max_side <= FEED_SIDE else 120))
                r.raise_for_status()
            except requests.RequestException as e:
                log.warning("image %s: %s after %.1f s", url, e.__class__.__name__,
                            time.monotonic() - t)
                self.why[url] = ("network", e.__class__.__name__)
                raise
            img = QImage.fromData(r.content)
            log.debug("image %s %d B %.2f s%s", url, len(r.content), time.monotonic() - t,
                      "" if not img.isNull() else " (not an image)")
            if img.isNull():  # downloaded fine, but Qt can't read it (webp, avif, heic…)
                kind = (r.headers.get("Content-Type") or "").split(";")[0].strip()
                self.why[url] = ("format", kind or "?")
                log.warning("image %s: %s, %d B — Qt can't show this format "
                            "(qt6-image-formats-plugins?)", url, kind or "unknown type",
                            len(r.content))
            if not img.isNull():  # never keep an error page or half a file
                p.write_bytes(r.content)
        if not img.isNull() and max(img.width(), img.height()) > max_side:
            img = img.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        return img

    def save(self, url, folder):
        """The original file into folder (from the cache when it's there).
        Returns a future with the saved path."""
        def job():
            from ...core import saving
            folder.mkdir(parents=True, exist_ok=True)
            cached = self.cache_dir / hashlib.sha1(url.encode()).hexdigest()
            ctype = ""
            if cached.exists():
                data = cached.read_bytes()
            else:
                r = self.http.get(url, timeout=120)
                r.raise_for_status()
                data, ctype = r.content, r.headers.get("Content-Type", "")
            path = saving.free_path(folder, saving.file_name(url, ctype))
            path.write_bytes(data)
            log.info("saved %s -> %s (%d B)", url, path, len(data))
            return path
        return self.pool.submit(job)

    def get(self, url, callback, max_side=FEED_SIDE, failed=None, retry=False):
        """callback(QPixmap) now or later; for a broken or unreachable image
        failed() is called instead (if given). retry: ask again even if it just failed."""
        if not url:
            if failed:
                failed()
            return
        if retry:
            self.broken.pop(url, None)
        key = (url, max_side)
        broke = self.broken.get(url)
        if broke is not None and time.monotonic() - broke < self.RETRY_AFTER:
            if failed:  # it just failed: don't keep a worker on it again so soon
                failed()
            return
        if key in self.mem:
            self.mem.move_to_end(key)
            callback(self.mem[key])
            return
        if key in self.waiting:
            self.waiting[key].append((callback, failed))
            return
        self.waiting[key] = [(callback, failed)]
        self.bridge.call(self.pool.submit(self._download, url, max_side),
                         ok=lambda img, k=key: self._ready(k, img),
                         fail=lambda _e, k=key: self._failed(k))

    def _remember(self, key, pm):
        size = pm.width() * pm.height() * 4
        self.mem[key] = pm
        self.mem_bytes += size
        while self.mem_bytes > self.mem_budget and len(self.mem) > 1:
            _k, old = self.mem.popitem(last=False)
            self.mem_bytes -= old.width() * old.height() * 4
        # pictures already on screen keep their own copies; this only stops the
        # cache from holding every picture ever seen

    def _failed(self, key):
        self.broken[key[0]] = time.monotonic()
        for _cb, failed in self.waiting.pop(key, []):
            if failed:
                try:
                    failed()
                except RuntimeError:  # its widget is gone
                    pass

    def _ready(self, key, img):
        if img.isNull():
            self._failed(key)
            return
        self.broken.pop(key[0], None)
        callbacks = [cb for cb, _f in self.waiting.pop(key, [])]
        pm = QPixmap.fromImage(img)
        self._remember(key, pm)
        for cb in callbacks:
            try:
                cb(pm)
            except RuntimeError:  # its widget is gone
                pass
