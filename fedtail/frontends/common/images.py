"""Avatars and thumbnails, for any window: memory + disk cache, downloaded in worker
threads, newest first, retried when a server was only busy; prefetched to disk, the
disk kept within its size; videos to disk; saving originals.

The auth token is never sent along: media often lives on other servers. What a toolkit
adds is four things (a subclass: qt/images.py, gtk/images.py): decode(data, max_side)
in a worker — a picture no bigger than max_side, or None; size(picture) → (w, h);
to_screen(picture) in the main loop — what widgets take (a QPixmap, a Gdk.Texture);
later(ms, fn) — a timer of its main loop.
"""

import hashlib
import logging
import os
import threading
import time
import weakref
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import requests

from ... import diag
from ...core import remote
from ...version import USER_AGENT

log = logging.getLogger(__name__)
FEED_SIDE = 1200
MEM_MB = 64  # default memory budget for decoded pictures (ui.image_cache_mb)
# the most one answer may bring: a picture's address comes from someone else's post, and
# an answer that never ends must not fill the memory or the disk
PICTURE_MAX = 20 * 1024 * 1024    # a preview, an avatar, a picture in the feed
ORIGINAL_MAX = 100 * 1024 * 1024  # a full-size original
VIDEO_MAX = 300 * 1024 * 1024     # one video or sound on disk
SAVE_MAX = 2 * 1024 * 1024 * 1024  # "save": asked for, and written piece by piece
MEDIA_SCHEMES = ("https", "http")


def face_side(size):
    """How big a face (an avatar) is decoded for a box of `size` px: twice that (sharp on
    a HiDPI screen), at least 64 — not a feed picture's 1200: a server's 400-px avatar was
    kept whole, 640 KB, for a 40-px circle (28.10)."""
    return max(64, int(size) * 2)


def _short(url):
    """The end of a picture's address: enough to find it, short enough to read."""
    return url if len(url) <= 60 else "…" + url[-57:]


def _where(url):
    """A picture in the normal log (and so in bug reports): its server and the name of
    its cache file — not the address, which may carry a signature."""
    from urllib.parse import urlsplit
    return f"{urlsplit(url).hostname or '?'}/{hashlib.sha1(url.encode()).hexdigest()[:8]}"


def _weakly(owner, fn):
    """fn kept alive by owner, and a stand-in that calls it while it lives."""
    try:
        kept = owner.__dict__.setdefault("_ft_picture_callbacks", [])
    except (AttributeError, TypeError):  # an owner without a __dict__: as it was
        return fn
    if len(kept) > 64:  # an owner asked over and over: the oldest go
        del kept[:32]

    def own(*a):  # (a plain function: a weak reference to any callable, GTK's too)
        fn(*a)
    kept.append(own)
    ref = weakref.ref(own)

    def call(*a):
        f = ref()
        if f is not None:
            f(*a)
    return call



class HostBusy(requests.RequestException):
    """A picture not asked for: its server said "too many requests" a moment ago."""


def _retry_after(headers):
    """Seconds a 429 asks to wait (Retry-After, or X-RateLimit-Reset), 60 if unsaid."""
    try:
        return min(900.0, max(5.0, float(headers.get("Retry-After") or 60)))
    except (TypeError, ValueError):
        return 60.0

class Cache:
    RETRY_AFTER = 60  # s: a picture that just failed isn't asked for again before that
    # a server that fetches remote media on demand may take longer than a feed picture
    # is allowed to: such a picture is asked for once more, soon and with more patience,
    # before it counts as broken. A server stuck on one picture is often quick the
    # second time (it has fetched it meanwhile), so the first try gives up early.
    SECOND_TRY_AFTER = 1500  # ms
    # a picture that failed twice is asked again by itself later, for the cards still
    # waiting on it: a server briefly answering 4xx/5xx (busy, restarting, still fetching
    # a remote post's media) must not leave it blank until fedtail is restarted
    LATER_TRIES = (60, 300, 1800)  # s, then three more at the last one; then it rests
    STUCK_AFTER = 180  # s: a request this old with no answer is asked for again
    STARVING = 6  # s: newest first — but a request waiting this long goes next
    FORMAT_HINT = "this format can't be shown"
    FEED_WORKERS = 8  # previews, avatars, emoji: small, many, on screen now
    BIG_WORKERS = 3   # originals (a single picture made sharp, the viewer, saving)

    # ---- what a toolkit gives ------------------------------------------------------------
    def decode(self, data, max_side, fmt=None):
        """In a worker: the picture in data, no bigger than max_side — or None. fmt: what
        imagesniff found it to be (the toolkit reads it as that, and only as that)."""
        raise NotImplementedError

    # the formats read by plugins outside the toolkit's own (KDE's kimageformats,
    # GdkPixbuf's extra loaders): one at a time — some aren't safe in two threads at once
    _alone = threading.Lock()

    @staticmethod
    def _readable(data):
        from . import imagesniff
        return imagesniff.readable(data)

    def _decode(self, data, max_side):
        """decode(), but only for bytes that are one of a post's picture formats and
        came whole: anything else never reaches a decoder (see imagesniff)."""
        from . import imagesniff
        fmt, why = self._readable(data)
        if fmt is None:
            log.debug("image: %d B not decoded: %s", len(data), why)
            self._t.why = why
            return None
        if fmt in imagesniff.RISKY:
            with self._alone:
                return self.decode(data, max_side, fmt)
        return self.decode(data, max_side, fmt)

    def size(self, picture):
        """(width, height) of a decoded picture or of what to_screen made of it."""
        raise NotImplementedError

    def to_screen(self, picture):
        """In the main loop: what the widgets take."""
        return picture

    def later(self, ms, fn):
        """fn() in the main loop, ms from now."""
        raise NotImplementedError

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
        self._busy_hosts = {}  # host -> time.monotonic() its 429 asked to wait till
        self.asked = {}   # key -> when it was handed to the workers (monotonic)
        self.patient = set()  # keys on their second try: longer read timeout
        # a preview and its original are the same picture: when one comes, a preview
        # that gave up is asked again (a server that was still fetching it has it now)
        self.related = {}   # original url -> {preview urls}
        self.gave_up = {}   # url -> [(max_side, callback, failed)] whose request failed
        self.tries = {}     # url -> how many later tries it has had (LATER_TRIES)
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
        # one download of a url at a time: asked at two sizes (the card's, the viewer's)
        # it was fetched twice at once — the night of 22.10, both 120 s to a timeout
        self._fetching = {}  # url -> Event set when its download is over
        self._fetch_lock = threading.Lock()
        self.http = requests.Session()
        self.http.headers["User-Agent"] = USER_AGENT
        # every worker keeps its connection to the server instead of opening a new one
        conns = self.FEED_WORKERS + self.BIG_WORKERS + 1
        # every connection to an address checked as it's made (core/remote.py: no DNS
        # rebinding a picture's address into the home network)
        adapter = remote.Adapter(pool_connections=16, pool_maxsize=conns)
        self.http.mount("https://", adapter)
        self.http.mount("http://", adapter)
        # timings for the log and the stats line: where the time of a picture goes
        self._t = threading.local()  # this worker's last download: bytes, seconds
        self._stats_lock = threading.Lock()
        self._reset_stats()
        # pictures of posts just arrived, fetched to disk ahead of time (feed.prefetch)
        # by workers of their own, so the ones on screen never wait behind them
        self.pre_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="fedtail-pre")
        # videos one at a time: big, and never in the way of the pictures
        self.video_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="fedtail-vid")
        self.video_dir = self.cache_dir / "video"
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self._video_seen = set()
        self._pre_seen = set()
        self._since_prune = 0
        self.big_pool.submit(self.prune_disk)
        self.big_pool.submit(self.prune_videos)

    def _reset_stats(self):
        self._st = {"done": 0, "failed": 0, "big": 0, "cached": 0, "wait_max_s": 0.0,
                    "dl_n": 0, "dl_s": 0.0, "dl_max_s": 0.0, "dec_n": 0, "dec_ms": 0.0,
                    "dec_max_ms": 0.0, "gui_max_ms": 0.0, "gui_ms": 0.0}

    def _note(self, **kw):
        with self._stats_lock:
            st = self._st
            for k, v in kw.items():
                if k.endswith("_max_s") or k.endswith("_max_ms"):
                    st[k] = max(st[k], v)
                else:
                    st[k] += v

    def counts(self):
        """For the stats line (every few minutes): what happened since the last one."""
        with self._stats_lock:
            st, _ = self._st, self._reset_stats()
        with self._stack_lock:
            feed_q, big_q = len(self._stacks[False]), len(self._stacks[True])
        return {"done": st["done"], "failed": st["failed"], "originals": st["big"],
                "from_disk": st["cached"], "queued": feed_q, "queued_originals": big_q,
                "wait_max_s": round(st["wait_max_s"], 1),
                "download_avg_s": round(st["dl_s"] / st["dl_n"], 2) if st["dl_n"] else 0,
                "download_max_s": round(st["dl_max_s"], 1),
                "decode_avg_ms": round(st["dec_ms"] / st["dec_n"]) if st["dec_n"] else 0,
                "decode_max_ms": round(st["dec_max_ms"]),
                "gui_total_ms": round(st["gui_ms"]), "gui_max_ms": round(st["gui_max_ms"])}

    def shutdown(self):
        self.closed = True
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
        self._note(wait_max_s=waited, big=1 if big else 0)
        self._t.got = None
        t = time.monotonic()
        try:
            img = self._download(url, max_side, patient, big)
        except Exception:  # noqa: BLE001 — said in the log by _download; the card says it
            self._note(failed=1)
            return (url, max_side), None
        total = time.monotonic() - t
        got = getattr(self._t, "got", None)  # (bytes, download s) or None: from disk
        dl = got[1] if got else 0.0
        dec_ms = (total - dl) * 1000
        self._note(done=1, cached=0 if got else 1, dec_n=1, dec_ms=dec_ms, dec_max_ms=dec_ms,
                   **({"dl_n": 1, "dl_s": dl, "dl_max_s": dl} if got else {}))
        log.debug("image %s %s: queue %.2f s, %s, decode %.0f ms -> %dx%d", "big" if big
                  else "feed", _short(url), waited,
                  f"download {got[0]} B {dl:.2f} s" if got else "from disk", dec_ms,
                  *(self.size(img) if img is not None else (0, 0)))
        return (url, max_side), img

    def _download(self, url, max_side, patient=False, big=False):
        p = self.cache_dir / hashlib.sha1(url.encode()).hexdigest()
        img = None
        if p.exists():
            img = self._decode(p.read_bytes(), max_side)
            if img is None:
                p.unlink(missing_ok=True)  # a broken file from before: fetch again
            else:
                try:  # used now: the cache cleanup keeps what's used, drops what's not
                    os.utime(p)
                except OSError:
                    pass
        if img is None:
            with self._fetch_lock:
                ev = self._fetching.get(url)
                mine = ev is None
                if mine:
                    ev = self._fetching[url] = threading.Event()
            if not mine:  # another worker is fetching it: its file, when it's there
                ev.wait(150)
                if p.exists():
                    img = self._decode(p.read_bytes(), max_side)
                    if img is not None:
                        return img
                raise requests.ConnectionError(f"{_where(url)}: the same download failed")
            try:
                return self._fetch(url, max_side, p, patient, big)
            finally:
                with self._fetch_lock:
                    self._fetching.pop(url, None)
                ev.set()
        return img

    HOST_MAX = 4  # pictures asked of one server at once

    def _host_slot(self, host):
        """At most HOST_MAX pictures asked of one server at a time: a small server
        (one's own, on a little VM) answered every one late with all the workers on it
        at once — fourteen connections, the pool full, previews timing out (27.10)."""
        slots = self.__dict__.setdefault("_host_slots", {})
        lock = self.__dict__.setdefault("_host_slots_lock", threading.Lock())
        with lock:
            sem = slots.get(host)
            if sem is None:
                sem = slots[host] = threading.BoundedSemaphore(self.HOST_MAX)
        return sem

    def _fetch(self, url, max_side, p, patient, big):
        """The url from the network into the disk cache (p), decoded at max_side."""
        t = time.monotonic()
        host = urlsplit(url).hostname or ""
        busy = self.__dict__.setdefault("_busy_hosts", {})
        quiet = busy.get(host, 0)
        if quiet > time.monotonic():  # it said "too many": nothing asked of it till then
            self.why[url] = ("network", "HTTP 429")
            raise HostBusy(f"{host}: waiting {quiet - time.monotonic():.0f} s (HTTP 429)")
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
            with self._host_slot(host), self._open(url, (6, slow)) as r:
                r.raise_for_status()
                kind = (r.headers.get("Content-Type") or "").split(";")[0].strip()
                data = remote.read(r, ORIGINAL_MAX if big else PICTURE_MAX)
        except requests.RequestException as e:
            resp = getattr(e, "response", None)
            code = getattr(resp, "status_code", None)
            what = f"refused ({e})" if isinstance(e, remote.Refused) else \
                f"HTTP {code}" if code else e.__class__.__name__
            if code == 429:  # the server's pictures are rationed: its window waited out
                wait = _retry_after(getattr(resp, "headers", None) or {})
                first = busy.get(host, 0) <= time.monotonic()
                busy[host] = time.monotonic() + wait
                (log.info if first else log.debug)(
                    "image %s: HTTP 429 — no pictures asked of %s for %.0f s",
                    _where(url), host, wait)
            else:  # gone (404, 410) is a picture's ordinary end, not a problem of ours;
                # a preview's first 12 s run out is asked again with patience (info)
                again = isinstance(e, requests.Timeout) and not (patient or big)
                (log.info if code in (404, 410) or again else log.warning)(
                    "image %s: %s after %.1f s", _where(url), what, time.monotonic() - t)
            self.why[url] = ("network", what)
            raise
        self._t.got = (len(data), time.monotonic() - t)
        self._t.why = ""
        img = self._decode(data, max_side)
        if img is None and self._t.why == "cut short":  # the connection let go mid-file
            self.why[url] = ("network", "cut short")
            log.info("image %s: %d B, cut short — asked again later", _where(url), len(data))
            raise requests.ConnectionError(f"{_where(url)}: cut short")
        if img is None:  # downloaded fine, but can't be read (webp, avif, heic…)
            self.why[url] = ("format", kind or "?")
            said = self.__dict__.setdefault("_formats_said", set())
            (log.debug if kind in said else log.warning)(
                "image %s: %s, %d B — %s", _where(url), kind or "unknown type",
                len(data), self.FORMAT_HINT)  # once per kind in the normal log
            said.add(kind)
        else:  # never keep an error page or half a file
            p.write_bytes(data)
            self._count_write()
        return img

    def _open(self, url, timeout):
        """A streamed answer for a picture or video (see core.remote): no token, public
        addresses only (my own server excepted), redirects checked one by one."""
        return remote.open_url(self.http, url, timeout=timeout, schemes=MEDIA_SCHEMES,
                               own_hosts=self.core._own_hosts())

    # ---- the disk cache: fetched ahead, kept within a size ----------------------------
    def prefetch(self, urls):
        """Pictures of posts that just came: into the disk cache now, so the lane shows
        them at once when it opens (feed.prefetch). Never decoded here, never twice."""
        for url in urls:
            if not url or url in self._pre_seen:
                continue
            self._pre_seen.add(url)
            self.pre_pool.submit(self._prefetch_one, url)
        if len(self._pre_seen) > 20000:
            self._pre_seen.clear()

    def _prefetch_one(self, url):
        if picture_path(self.cache_dir, url).exists():
            return
        if fetch_picture(self.cache_dir, url, self._open, self._readable) is not None:
            self._count_write()

    # ---- videos on disk: fetched ahead ("all"), and every one played ------------------
    def _video_path(self, url):
        from urllib.parse import urlparse
        ext = os.path.splitext(urlparse(url).path)[1].lower()
        ext = ext if ext in (".mp4", ".webm", ".m4v", ".mov", ".mp3", ".ogg", ".m4a",
                             ".opus", ".wav", ".flac") else ".bin"
        return self.video_dir / (hashlib.sha1(url.encode()).hexdigest() + ext)

    def video_local(self, url):
        p = self._video_path(url)
        if p.exists() and p.stat().st_size:
            try:
                os.utime(p)  # used: the cleanup keeps it
            except OSError:
                pass
            return str(p)
        return None

    def prefetch_video(self, urls):
        if int(self.core.cfg["ui"].get("video_disk_mb", 10000)) <= 0:
            return
        for url in urls:
            if url and url not in self._video_seen:
                self._video_seen.add(url)
                self.video_pool.submit(self._fetch_video, url)

    def _fetch_video(self, url):
        p = self._video_path(url)
        if p.exists():
            return
        part = p.with_suffix(p.suffix + ".part")
        t = time.monotonic()
        size = 0
        try:
            with self._host_slot(urlsplit(url).hostname or ""), self._open(url, (6, 60)) as r:
                r.raise_for_status()
                said = r.headers.get("Content-Length") or ""
                if said.isdigit() and int(said) > VIDEO_MAX:
                    raise remote.Refused(f"video over {VIDEO_MAX >> 20} MB")
                with open(part, "wb") as f:
                    for chunk in r.iter_content(1 << 16):
                        f.write(chunk)
                        size += len(chunk)
                        if size > VIDEO_MAX:
                            raise remote.Refused(f"video over {VIDEO_MAX >> 20} MB")
            part.replace(p)  # whole or not at all: the player never gets half a file
        except (requests.RequestException, OSError) as e:
            part.unlink(missing_ok=True)
            log.debug("video %s: %s", url, e.__class__.__name__)
            return
        log.info("video to disk: %.1f MB in %.1f s", size / 2**20, time.monotonic() - t)
        self._videos_written = getattr(self, "_videos_written", 0) + 1
        if self._videos_written % 10 == 0:
            self.prune_videos()

    def prune_videos(self):
        """The video cache within ui.video_disk_mb (10 GB): the ones not played the
        longest go first."""
        limit = int(self.core.cfg["ui"].get("video_disk_mb", 10000)) * 1024 * 1024
        return self._prune(self.video_dir, limit,
                           lambda p: len(p.stem) == 40 and p.suffix != ".part",
                           "video cache")

    def _count_write(self):
        self._since_prune += 1
        if self._since_prune >= 300:  # every few hundred new files: still within size?
            self._since_prune = 0
            self.big_pool.submit(self.prune_disk)

    def prune_disk(self):
        """The disk cache within ui.image_disk_mb: the pictures not used the longest go
        first (a cache that only grew held gigabytes after a few weeks). Only our
        picture files are touched — names of 40 hex digits."""
        limit = int(self.core.cfg["ui"].get("image_disk_mb", 1000)) * 1024 * 1024
        return self._prune(self.cache_dir, limit,
                           lambda p: len(p.name) == 40 and
                           all(c in "0123456789abcdef" for c in p.name), "image cache")

    def _prune(self, folder, limit, ours, what):
        if limit <= 0:
            return 0
        files, total = [], 0
        try:
            for p in folder.iterdir():
                if not p.is_file() or not ours(p):
                    continue
                try:
                    st = p.stat()
                except OSError:
                    continue
                files.append((st.st_mtime, st.st_size, p))
                total += st.st_size
        except OSError:
            return 0
        if total <= limit:
            return 0
        files.sort()  # oldest used first
        target = int(limit * 0.8)  # some room, so it isn't pruned again right away
        freed = gone = 0
        for _mtime, size, p in files:
            if total - freed <= target:
                break
            try:
                p.unlink()
                freed += size
                gone += 1
            except OSError:
                pass
        log.info("%s: %d files, %.0f MB let go (%.0f MB kept, limit %d MB)", what, gone,
                 freed / 2**20, (total - freed) / 2**20, limit // 2**20)
        return gone

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
            t = time.monotonic()
            if cached.exists():
                data = cached.read_bytes()
                path = saving.free_path(folder, saving.file_name(url, ""))
                path.write_bytes(data)
                size = len(data)
            else:
                # straight to the file a piece at a time: a video can be big
                with self._open(url, 120) as r:
                    r.raise_for_status()
                    path = saving.free_path(folder, saving.file_name(
                        url, r.headers.get("Content-Type", "")))
                    size = 0
                    try:
                        with open(path, "wb") as f:
                            for chunk in r.iter_content(1 << 16):
                                f.write(chunk)
                                size += len(chunk)
                                if size > SAVE_MAX:
                                    raise remote.Refused("over the size a file may have")
                    except BaseException:
                        path.unlink(missing_ok=True)  # no half files left behind
                        raise
            log.info("saved %s -> %s (%d B, %.1f s)", url, path, size, time.monotonic() - t)
            return path
        return self.big_pool.submit(job)

    def face(self, url, size, callback, owner=None):
        """An avatar for a box of `size` px: decoded small (face_side)."""
        self.get(url, callback, max_side=face_side(size), owner=owner)

    def get(self, url, callback, max_side=FEED_SIDE, failed=None, retry=False, original=None,
            big=False, owner=None):
        """callback(picture on screen) now or later; for a broken or unreachable image
        failed() is called instead (if given). retry: ask again even if it just failed.
        original: the full picture this one is a preview of — if the preview gives up and
        the original comes later (opened in the viewer), the preview is asked again.
        big: a full-size original (also anything bigger than a feed picture) — fetched
        by its own workers, so it never holds up the previews.
        owner: the widget the picture is for. The cache then keeps its callbacks only
        weakly (the owner keeps them): a card thrown away isn't held alive by a picture
        still on its way or one that failed and is waited for — in GTK every card of every
        closed tab stayed so (25.10)."""
        if owner is not None:
            callback = _weakly(owner, callback)
            failed = _weakly(owner, failed) if failed else None
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
            log.warning("image %s: no answer for %.0f s, asking again", _where(url), since)
        else:
            self.waiting[key] = [(callback, failed)]
        self._ask(key)

    def _ask(self, key):
        if getattr(self, "closed", False):  # a second try timed after the window closed
            return
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

    def _bytes(self, pm):
        w, h = self.size(pm)
        return w * h * 4

    def _remember(self, key, pm):
        self.mem[key] = pm
        self.mem_bytes += self._bytes(pm)
        while self.mem_bytes > self.mem_budget and len(self.mem) > 1:
            _k, old = self.mem.popitem(last=False)
            self.mem_bytes -= self._bytes(old)
        # pictures already on screen keep their own copies; this only stops the
        # cache from holding every picture ever seen

    def _failed(self, key):
        self.asked.pop(key, None)
        if (self.why.get(key[0], ("",))[0] == "network" and key not in self.patient
                and key in self.waiting and key not in self.big):
            # once more, later and with more patience; the pictures keep waiting
            log.info("image %s: second try in %d s", key[0], self.SECOND_TRY_AFTER // 1000)
            self.patient.add(key)
            self.later(self.SECOND_TRY_AFTER, lambda: self._ask(key))
            return
        self.patient.discard(key)
        self.broken[key[0]] = time.monotonic()
        waiting = self.waiting.pop(key, [])
        for cb, failed in waiting:
            self._give_up(key[0], key[1], cb, failed)
        if waiting and self.why.get(key[0], ("",))[0] == "network":
            self._try_later(key[0])
        for _cb, failed in waiting:
            if failed:
                try:
                    failed()
                except RuntimeError:  # its widget is gone
                    pass
                except Exception:  # noqa: BLE001 — one bad card mustn't keep the others waiting
                    log.exception("image failure handler")

    def _try_later(self, url):
        """Ask a failed picture again in a while (LATER_TRIES), for whoever still waits."""
        n = self.tries.get(url, 0)
        if n >= len(self.LATER_TRIES) + 3:
            log.info("image %s: given up after %d later tries", _where(url), n)
            return
        if len(self.tries) > 2000:
            self.tries.pop(next(iter(self.tries)))
        self.tries[url] = n + 1
        delay = self.LATER_TRIES[min(n, len(self.LATER_TRIES) - 1)]
        log.info("image %s: asking again in %d s (try %d)", _where(url), delay, n + 1)
        self.later(delay * 1000, lambda: self._again(url))

    def _again(self, url):
        waiters = self.gave_up.pop(url, [])
        if not waiters:
            return  # nobody waits for it any more (cards gone, or it came meanwhile)
        self.broken.pop(url, None)
        for max_side, cb, failed in waiters:
            key = (url, max_side)
            self.patient.add(key)  # straight to the patient timeout, no quick second try
            self.get(url, cb, max_side, failed)

    def _ready(self, key, img):
        if img is None:
            self._failed(key)
            return
        self.broken.pop(key[0], None)
        self.why.pop(key[0], None)
        self.tries.pop(key[0], None)
        again = self.gave_up.pop(key[0], [])  # cards that gave up on it: here it is now
        for max_side, cb, _failed in again:
            if max_side == key[1]:
                self.waiting.setdefault(key, []).append((cb, None))
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
        t = time.monotonic()
        with diag.busy(f"picture in ({len(callbacks)} cards)"):
            pm = self.to_screen(img)
            self._remember(key, pm)
            for cb in callbacks:
                try:
                    cb(pm)
                except RuntimeError:  # its widget is gone
                    pass
                except Exception:  # noqa: BLE001 — one bad card mustn't keep the others waiting
                    log.exception("image handler")
        ms = (time.monotonic() - t) * 1000
        self._note(gui_ms=ms, gui_max_ms=ms)
        if ms > 50:
            log.debug("image %s: %.0f ms in the window for %d cards (%dx%d)", _short(key[0]),
                      ms, len(callbacks), *self.size(img))


def picture_path(cache_dir, url):
    """Where the disk cache keeps url's picture (whether it is there or not)."""
    return Path(cache_dir) / hashlib.sha1(url.encode()).hexdigest()


def fetch_picture(cache_dir, url, opener, readable=None):
    """url's picture into the disk cache (the windows' and the web page's one cache) if
    it isn't there: only an image, whole and of a picture format (imagesniff), never an
    error page. opener(url, timeout): a streamed answer through core.remote (no token,
    public addresses, redirects checked). → the file, or None."""
    from . import imagesniff
    p = picture_path(cache_dir, url)
    if p.exists() and p.stat().st_size:
        return p
    t = time.monotonic()
    try:
        with opener(url, (6, 30)) as r:
            r.raise_for_status()
            kind = (r.headers.get("Content-Type") or "").split(";")[0].strip()
            if not kind.startswith("image/"):
                return None  # an error page, a video: not for the picture cache
            data = remote.read(r, PICTURE_MAX)
    except requests.RequestException as e:
        log.debug("prefetch %s: %s", url, e.__class__.__name__)
        return None
    if not data:
        return None
    fmt, why = (readable or imagesniff.readable)(data)
    if fmt is None:  # cut short, or not a picture: never into the cache
        log.debug("prefetch %s: %d B, %s — not kept", url, len(data), why)
        return None
    p.write_bytes(data)
    log.debug("prefetch %s: %d B in %.1f s", url, len(data), time.monotonic() - t)
    return p
