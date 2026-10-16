"""Avatars and thumbnails: memory + disk cache, downloaded in worker threads.

The auth token is never sent along: media often lives on other servers.
"""

import hashlib
import logging
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import requests
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QPixmap

from ...core.api import USER_AGENT

log = logging.getLogger(__name__)
FEED_SIDE = 1200
MEM_MB = 128  # default memory budget for decoded pictures (ui.image_cache_mb)


class Images:
    RETRY_AFTER = 300  # s: a picture that just failed isn't asked for again before that
    # a server that fetches remote media on demand may take longer than a feed picture
    # is allowed to: such a picture is asked for once more, a bit later and with more
    # patience, before it counts as broken (it used to stay grey until a restart)
    SECOND_TRY_AFTER = 8000  # ms
    STUCK_AFTER = 180  # s: a request this old with no answer is asked for again
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
        self.asked = {}   # key -> when it was handed to the workers (monotonic)
        self.patient = set()  # keys on their second try: longer read timeout
        # own pool: a backlog of avatars must never delay sending a post
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="fedtail-img")
        # newest first: the picture asked for last is the one on screen now; a lane full
        # of pictures scrolled past must not make it wait behind them all
        self._stack = []
        self._stack_lock = threading.Lock()
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT

    def _next(self, key):
        """A worker takes the newest request still waiting (not necessarily `key`:
        every request has its own worker call, so all get done, newest first).
        Returns (key, image) for the request it actually did."""
        with self._stack_lock:
            url, max_side, asked = self._stack.pop()
            patient = (url, max_side) in self.patient
        waited = time.monotonic() - asked
        if waited > 2:
            log.info("image waited %.1f s for a worker (%d more waiting)", waited,
                     len(self._stack))
        try:
            return (url, max_side), self._download(url, max_side, patient)
        except Exception:  # noqa: BLE001 — said in the log by _download; the card says it
            return (url, max_side), None

    def _download(self, url, max_side, patient=False):
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
                slow = 30 if max_side <= FEED_SIDE and not patient else 120
                r = self.http.get(url, timeout=(10, slow))
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
            since = time.monotonic() - self.asked.get(key, time.monotonic())
            if since < self.STUCK_AFTER:
                return
            # no answer for minutes (a lost result?): ask again rather than wait forever
            log.warning("image %s: no answer for %.0f s, asking again", url, since)
        else:
            self.waiting[key] = [(callback, failed)]
        self._ask(key)

    def _ask(self, key):
        url, max_side = key
        self.asked[key] = time.monotonic()
        with self._stack_lock:
            self._stack.append((url, max_side, time.monotonic()))
        self.bridge.call(self.pool.submit(self._next, key),
                         ok=lambda done: self._ready(*done) if done[1] is not None
                         else self._failed(done[0]))

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
        self.asked.pop(key, None)
        if (self.why.get(key[0], ("",))[0] == "network" and key not in self.patient
                and key in self.waiting):
            # once more, later and with more patience; the pictures keep waiting
            log.info("image %s: second try in %d s", key[0], self.SECOND_TRY_AFTER // 1000)
            self.patient.add(key)
            QTimer.singleShot(self.SECOND_TRY_AFTER, lambda: self._ask(key))
            return
        self.patient.discard(key)
        self.broken[key[0]] = time.monotonic()
        for _cb, failed in self.waiting.pop(key, []):
            if failed:
                try:
                    failed()
                except RuntimeError:  # its widget is gone
                    pass
                except Exception:  # noqa: BLE001 — one bad card mustn't keep the others waiting
                    log.exception("image failure handler")

    def _ready(self, key, img):
        if img.isNull():
            self._failed(key)
            return
        self.broken.pop(key[0], None)
        self.why.pop(key[0], None)
        self.asked.pop(key, None)
        self.patient.discard(key)
        callbacks = [cb for cb, _f in self.waiting.pop(key, [])]
        pm = QPixmap.fromImage(img)
        self._remember(key, pm)
        for cb in callbacks:
            try:
                cb(pm)
            except RuntimeError:  # its widget is gone
                pass
            except Exception:  # noqa: BLE001 — one bad card mustn't keep the others waiting
                log.exception("image handler")
