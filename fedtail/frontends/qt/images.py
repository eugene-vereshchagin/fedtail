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
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QTimer
from PySide6.QtGui import QImage, QImageReader, QPixmap
from requests.adapters import HTTPAdapter

from ...core.api import USER_AGENT

log = logging.getLogger(__name__)
FEED_SIDE = 1200
MEM_MB = 128  # default memory budget for decoded pictures (ui.image_cache_mb)


def decode(data, max_side):
    """The picture in data, already no bigger than max_side: the decoder makes it small
    (a JPEG is read at a fraction of its size) instead of decoding all of a 4000-px
    photo and shrinking it after — less time, less memory, the GUI thread waits less."""
    buf = QBuffer()
    buf.setData(QByteArray(data))
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buf)
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > max_side:
        reader.setScaledSize(size.scaled(max_side, max_side,
                                         Qt.AspectRatioMode.KeepAspectRatio))
    img = reader.read()
    if img.isNull():  # some plugins can't read scaled: the plain way
        img = QImage.fromData(data)
    return img


class Images:
    RETRY_AFTER = 60  # s: a picture that just failed isn't asked for again before that
    # a server that fetches remote media on demand may take longer than a feed picture
    # is allowed to: such a picture is asked for once more, soon and with more patience,
    # before it counts as broken. A server stuck on one picture is often quick the
    # second time (it has fetched it meanwhile), so the first try gives up early.
    SECOND_TRY_AFTER = 1500  # ms
    STUCK_AFTER = 180  # s: a request this old with no answer is asked for again
    STARVING = 6  # s: newest first — but a request waiting this long goes next
    FEED_WORKERS = 8  # previews, avatars, emoji: small, many, on screen now
    BIG_WORKERS = 3   # originals (a single picture made sharp, the viewer, saving)
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
        # a preview and its original are the same picture: when one comes, a preview
        # that gave up is asked again (a server that was still fetching it has it now)
        self.related = {}   # original url -> {preview urls}
        self.gave_up = {}   # url -> [(max_side, callback, failed)] whose request failed
        # own pools: a backlog of avatars must never delay sending a post, and a few
        # big originals from a slow server must never hold up the previews on screen
        self.pool = ThreadPoolExecutor(max_workers=self.FEED_WORKERS,
                                       thread_name_prefix="fedtail-img")
        self.big_pool = ThreadPoolExecutor(max_workers=self.BIG_WORKERS,
                                           thread_name_prefix="fedtail-big")
        self.big = set()  # keys of originals: they go to big_pool
        # newest first: the picture asked for last is the one on screen now; a lane full
        # of pictures scrolled past must not make it wait behind them all
        self._stacks = {False: [], True: []}
        self._stack_lock = threading.Lock()
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT
        # every worker keeps its connection to the server instead of opening a new one
        conns = self.FEED_WORKERS + self.BIG_WORKERS + 1
        adapter = HTTPAdapter(pool_connections=16, pool_maxsize=conns)
        self.http.mount("https://", adapter)
        self.http.mount("http://", adapter)

    def shutdown(self):
        for pool in (self.pool, self.big_pool):
            pool.shutdown(wait=False, cancel_futures=True)

    def _next(self, big):
        """A worker takes the newest request still waiting in its pool's stack (every
        request has its own worker call, so all get done, newest first).
        Returns (key, image) for the request it actually did."""
        with self._stack_lock:
            stack = self._stacks[big]
            # newest first, but nobody starves: with avatars and pictures asked for all
            # the time, the oldest request could wait behind them forever
            starving = time.monotonic() - stack[0][2] > self.STARVING
            url, max_side, asked = stack.pop(0 if starving else -1)
            patient = (url, max_side) in self.patient
            left = len(stack)
        waited = time.monotonic() - asked
        if waited > 2:
            log.info("image waited %.1f s for a worker (%d more waiting%s)", waited, left,
                     ", originals" if big else "")
        try:
            return (url, max_side), self._download(url, max_side, patient, big)
        except Exception:  # noqa: BLE001 — said in the log by _download; the card says it
            return (url, max_side), None

    def _download(self, url, max_side, patient=False, big=False):
        p = self.cache_dir / hashlib.sha1(url.encode()).hexdigest()
        img = QImage()  # QImage is fine outside the GUI thread
        if p.exists():
            img = decode(p.read_bytes(), max_side)
            if img.isNull():
                p.unlink(missing_ok=True)  # a broken file from before: fetch again
        if img.isNull():
            t = time.monotonic()
            try:
                # a preview that hasn't come in 12 s is asked again soon with a minute of
                # patience: a server stuck on it (fetching it from the author's server)
                # mostly has it by then — waiting longer on the first try only held a
                # worker. An original is worth waiting for from the start.
                if big:
                    slow = 120
                elif patient:
                    slow = 60
                else:
                    slow = 12
                r = self.http.get(url, timeout=(6, slow))
                r.raise_for_status()
            except requests.RequestException as e:
                log.warning("image %s: %s after %.1f s", url, e.__class__.__name__,
                            time.monotonic() - t)
                self.why[url] = ("network", e.__class__.__name__)
                raise
            img = decode(r.content, max_side)
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

    def local(self, url):
        """The cached file of a picture already downloaded, or None (for rich text that
        points at it: custom emoji)."""
        if not url:
            return None
        p = self.cache_dir / hashlib.sha1(url.encode()).hexdigest()
        return str(p) if p.exists() and p.stat().st_size else None

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
        return self.big_pool.submit(job)

    def get(self, url, callback, max_side=FEED_SIDE, failed=None, retry=False, original=None,
            big=False):
        """callback(QPixmap) now or later; for a broken or unreachable image
        failed() is called instead (if given). retry: ask again even if it just failed.
        original: the full picture this one is a preview of — if the preview gives up and
        the original comes later (opened in the viewer), the preview is asked again.
        big: a full-size original (also anything bigger than a feed picture) — fetched
        by its own workers, so it never holds up the previews."""
        if not url:
            if failed:
                failed()
            return
        if big or max_side > FEED_SIDE:
            if len(self.big) > 4000:
                self.big.clear()
            self.big.add((url, max_side))
        if original and original != url:
            if len(self.related) > 2000:
                self.related.pop(next(iter(self.related)))
            self.related.setdefault(original, set()).add(url)
        if retry:
            self.broken.pop(url, None)
        key = (url, max_side)
        broke = self.broken.get(url)
        if broke is not None and time.monotonic() - broke < self.RETRY_AFTER:
            self._give_up(url, max_side, callback, failed)
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
        big = key in self.big
        self.asked[key] = time.monotonic()
        with self._stack_lock:
            self._stacks[big].append((url, max_side, time.monotonic()))
        pool = self.big_pool if big else self.pool
        self.bridge.call(pool.submit(self._next, big),
                         ok=lambda done: self._ready(*done) if done[1] is not None
                         else self._failed(done[0]))

    def _give_up(self, url, max_side, callback, failed):
        """Keep who wanted a picture that failed, to hand it over if it comes after all."""
        if len(self.gave_up) > 500:
            self.gave_up.pop(next(iter(self.gave_up)))
        waiters = self.gave_up.setdefault(url, [])
        if len(waiters) < 8:
            waiters.append((max_side, callback, failed))

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
                and key in self.waiting and key not in self.big):
            # once more, later and with more patience; the pictures keep waiting
            log.info("image %s: second try in %d s", key[0], self.SECOND_TRY_AFTER // 1000)
            self.patient.add(key)
            QTimer.singleShot(self.SECOND_TRY_AFTER, lambda: self._ask(key))
            return
        self.patient.discard(key)
        self.broken[key[0]] = time.monotonic()
        waiting = self.waiting.pop(key, [])
        for cb, failed in waiting:
            self._give_up(key[0], key[1], cb, failed)
        for _cb, failed in waiting:
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
        self.gave_up.pop(key[0], None)
        for preview in self.related.pop(key[0], ()):
            again = self.gave_up.pop(preview, [])
            if again:
                log.info("image %s: its original came, asking the preview again", preview)
                self.broken.pop(preview, None)
            for max_side, cb, failed in again:
                self.get(preview, cb, max_side, failed)
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
