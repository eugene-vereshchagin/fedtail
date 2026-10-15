"""Avatars and thumbnails: memory + disk cache, downloaded in worker threads.

The auth token is never sent along: media often lives on other servers.
"""

import hashlib
from concurrent.futures import ThreadPoolExecutor

import requests
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from ...core.api import USER_AGENT

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
        if p.exists():
            data = p.read_bytes()
        else:
            r = self.http.get(url, timeout=60)
            r.raise_for_status()
            data = r.content
            p.write_bytes(data)
        img = QImage.fromData(data)  # QImage is fine outside the GUI thread
        if not img.isNull() and max(img.width(), img.height()) > max_side:
            img = img.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        return img

    def get(self, url, callback, max_side=FEED_SIDE):
        """callback(QPixmap) now or later; never called for broken images."""
        if not url:
            return
        key = (url, max_side)
        if key in self.mem:
            callback(self.mem[key])
            return
        if key in self.waiting:
            self.waiting[key].append(callback)
            return
        self.waiting[key] = [callback]
        self.bridge.call(self.pool.submit(self._download, url, max_side),
                         ok=lambda img, k=key: self._ready(k, img),
                         fail=lambda _e, k=key: self.waiting.pop(k, None))

    def _ready(self, key, img):
        callbacks = self.waiting.pop(key, [])
        if img.isNull():
            return
        pm = QPixmap.fromImage(img)
        if len(self.mem) > MEM_LIMIT:  # crude, but keeps a long session bounded
            self.mem.clear()
        self.mem[key] = pm
        for cb in callbacks:
            try:
                cb(pm)
            except RuntimeError:  # its widget is gone
                pass
