"""Avatars and thumbnails: memory + disk cache, downloaded in worker threads.

The auth token is never sent along: media often lives on other servers.
"""

import hashlib
from concurrent.futures import ThreadPoolExecutor

import requests
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap

from ...core.api import USER_AGENT


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

    def _download(self, url):
        p = self.cache_dir / hashlib.sha1(url.encode()).hexdigest()
        if p.exists():
            data = p.read_bytes()
        else:
            r = self.http.get(url, timeout=30)
            r.raise_for_status()
            data = r.content
            p.write_bytes(data)
        img = QImage.fromData(data)  # QImage is fine outside the GUI thread
        if not img.isNull() and img.width() > 1200:
            img = img.scaledToWidth(1200, Qt.TransformationMode.SmoothTransformation)
        return img

    def get(self, url, callback):
        """callback(QPixmap) now or later; never called for broken images."""
        if not url:
            return
        if url in self.mem:
            callback(self.mem[url])
            return
        if url in self.waiting:
            self.waiting[url].append(callback)
            return
        self.waiting[url] = [callback]
        self.bridge.call(self.pool.submit(self._download, url),
                         ok=lambda img, u=url: self._ready(u, img),
                         fail=lambda _e, u=url: self.waiting.pop(u, None))

    def _ready(self, url, img):
        callbacks = self.waiting.pop(url, [])
        if img.isNull():
            return
        pm = QPixmap.fromImage(img)
        self.mem[url] = pm
        for cb in callbacks:
            try:
                cb(pm)
            except RuntimeError:  # its widget is gone
                pass
