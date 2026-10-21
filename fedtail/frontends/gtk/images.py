"""Pictures for the GTK window: avatars and post previews as Gdk.Textures.

The bytes come from View.media_bytes (the disk cache the Qt window shares, without the
token, size-capped); decoding happens in the media workers — a Gdk.Texture may be
made in any thread — and the widget gets it in the main loop. Textures are kept in a
small LRU bounded in bytes (ui.image_cache_mb, as Qt). The full cache policy of
qt/images.py (retries, newest first, disk pruning) moves to a shared module later
(docs/GTK.md, stage 0); until then failures are simply not retried for a while.
"""

from __future__ import annotations

import logging
import time
from collections import OrderedDict

from .gi_setup import GLib

log = logging.getLogger(__name__)

RETRY_AFTER = 300  # s: a picture that failed isn't asked for again before this


def _decode(data):
    from gi.repository import Gdk
    return Gdk.Texture.new_from_bytes(GLib.Bytes.new(data))


class Images:
    def __init__(self, view, bridge, cap_mb=64):
        self.view, self.bridge = view, bridge
        self.cap = max(8, int(cap_mb or 64)) * 1024 * 1024
        self.mem = OrderedDict()      # url -> (texture, bytes)
        self.mem_bytes = 0
        self.waiting = {}             # url -> [callbacks]
        self.failed = {}              # url -> when

    def get(self, url, callback):
        """callback(texture) in the main loop, now if known, later when fetched; never
        for a picture that can't be had."""
        if not url:
            return
        hit = self.mem.get(url)
        if hit is not None:
            self.mem.move_to_end(url)
            callback(hit[0])
            return
        if time.monotonic() - self.failed.get(url, -RETRY_AFTER) < RETRY_AFTER:
            return
        if url in self.waiting:
            self.waiting[url].append(callback)
            return
        self.waiting[url] = [callback]

        def fetch():
            data = self.view.media_bytes(url).result()
            return _decode(data), len(data)

        from concurrent.futures import ThreadPoolExecutor
        if not hasattr(self, "_pool"):
            self._pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="fedtail-gtkimg")
        self.bridge.call(self._pool.submit(fetch), lambda got: self._got(url, got),
                         lambda err: self._fail(url, err))

    def _got(self, url, got):
        texture, size = got
        self.mem[url] = (texture, size)
        self.mem_bytes += size * 4  # decoded: about four times the file
        while self.mem_bytes > self.cap and len(self.mem) > 1:
            _u, (_t, s) = self.mem.popitem(last=False)
            self.mem_bytes -= s * 4
        for cb in self.waiting.pop(url, []):
            try:
                cb(texture)
            except Exception:  # noqa: BLE001 — a widget gone meanwhile
                log.debug("picture callback failed", exc_info=True)

    def _fail(self, url, err):
        self.waiting.pop(url, None)
        self.failed[url] = time.monotonic()
        log.debug("picture not loaded: %s", err)

    def shutdown(self):
        pool = getattr(self, "_pool", None)
        if pool is not None:
            pool.shutdown(wait=False, cancel_futures=True)
