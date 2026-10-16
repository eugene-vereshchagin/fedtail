"""Avatars and thumbnails: memory + disk cache, downloaded in worker threads.

The auth token is never sent along: media often lives on other servers.
"""

import hashlib
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from ...core.api import USER_AGENT

log = logging.getLogger(__name__)
FEED_SIDE = 1200
MEM_LIMIT = 600


class Images:
    def __init__(self, core, bridge):
        self.core = core
        self.bridge = bridge
        self.cache_dir = core.paths.cache_dir
        self.mem = {}
        self.waiting = {}
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
                r = self.http.get(url, timeout=60)
                r.raise_for_status()
            except requests.RequestException as e:
                log.warning("image %s: %s after %.1f s", url, e.__class__.__name__,
                            time.monotonic() - t)
                raise
            img = QImage.fromData(r.content)
            log.debug("image %s %d B %.2f s%s", url, len(r.content), time.monotonic() - t,
                      "" if not img.isNull() else " (not an image)")
            if not img.isNull():  # never keep an error page or half a file
                p.write_bytes(r.content)
        if not img.isNull() and max(img.width(), img.height()) > max_side:
            img = img.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        return img

    def get(self, url, callback, max_side=FEED_SIDE, failed=None):
        """callback(QPixmap) now or later; for a broken or unreachable image
        failed() is called instead (if given)."""
        if not url:
            if failed:
                failed()
            return
        key = (url, max_side)
        if key in self.mem:
            callback(self.mem[key])
            return
        if key in self.waiting:
            self.waiting[key].append((callback, failed))
            return
        self.waiting[key] = [(callback, failed)]
        self.bridge.call(self.pool.submit(self._download, url, max_side),
                         ok=lambda img, k=key: self._ready(k, img),
                         fail=lambda _e, k=key: self._failed(k))

    def _failed(self, key):
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
        callbacks = [cb for cb, _f in self.waiting.pop(key, [])]
        pm = QPixmap.fromImage(img)
        if len(self.mem) > MEM_LIMIT:  # crude, but keeps a long session bounded
            self.mem.clear()
        self.mem[key] = pm
        for cb in callbacks:
            try:
                cb(pm)
            except RuntimeError:  # its widget is gone
                pass
