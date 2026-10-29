"""The read position shared with other clients (the server's markers): where Home and
the notifications were read up to, taken and given."""

import logging

from .model import id_after

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts


class MarkersMixin:
    """A part of Core (core/app.py): see the module's words."""

    MARKERS = {"home": "home", "notifications": "mentions"}  # marker timeline -> our source

    def _markers_get(self, timelines):
        """The server's markers, or None: none there (Sharkey, Misskey, Pleroma's older:
        28.10 — "markers: HTTP 404" in every round) asked no more till a restart, said
        once in words; another failure, in the log, asked again next round."""
        if getattr(self, "_no_markers", False):
            return None
        try:
            return self.api.markers(timelines) or {}
        except Exception as e:  # noqa: BLE001 — an old server, a network gone
            if getattr(e, "status", None) in self.NO_SUCH:
                self._no_markers = True
                log.info("markers: the server has none (%s) — the reading place isn't "
                         "shared with other clients here", e.status)
            else:
                log.info("markers: %s", e)
            return None

    def _unread_by_marker(self, statuses):
        """First start: the ids newer than where the server's home marker says reading
        stopped (read.sync_markers) — they stay unread; the marker is taken as known,
        so the next round doesn't push "all read" over it. No marker, no server answer:
        nothing kept (all read, as feed.first_run_mark_read says)."""
        if not self.cfg["read"].get("sync_markers", True):
            return set()
        remote = self._markers_get(("home",))
        if remote is None:
            return set()
        last = ((remote or {}).get("home") or {}).get("last_read_id")
        if not last:
            return set()
        self.store.kv_set("marker.home", last)
        keep = {st["id"] for st in statuses if id_after(st["id"], last)}
        log.info("first start: read up to %s elsewhere, %d newer stay unread", last,
                 len(keep))
        return keep

    def _sync_markers(self):
        """Pull: what another client marked as read up to its marker is read here too.
        Push: how far everything is read here, from the oldest on, goes to the server.
        (read.sync_markers)"""
        if not self.cfg["read"].get("sync_markers", True):
            return
        remote = self._markers_get(tuple(self.MARKERS))
        if remote is None:
            return
        push = {}
        for timeline, source in self.MARKERS.items():
            # oldest -> newest; the server's own items only (not mine put in "Direct")
            items = [x for x in self.store.items(source, 400)
                     if not str(x[0]).startswith("mine:")]
            if not items:
                continue
            last = ((remote or {}).get(timeline) or {}).get("last_read_id")
            seen_key = f"marker.{timeline}"
            if last and last != self.store.kv_get(seen_key):
                older = [st["id"] for item, st in items if not id_after(item, last)]
                fresh = [i for i in older if i not in self.store.read_set(older)]
                if fresh:
                    log.info("markers: %s read up to %s elsewhere: %d here", timeline, last,
                             len(fresh))
                    self.mark_read(fresh)
                self.store.kv_set(seen_key, last)
            read = self.store.read_set(st["id"] for _i, st in items)
            mine = None
            for item, st in items:
                if st["id"] not in read:
                    break
                mine = item
            if mine and (not last or id_after(mine, last)):
                push[timeline] = mine
        if push:
            try:
                self.api.set_markers(push)
                for timeline, mine in push.items():
                    self.store.kv_set(f"marker.{timeline}", mine)
                log.debug("markers: read up to %s", push)
            except Exception as e:  # noqa: BLE001
                if getattr(e, "status", None) in self.NO_SUCH:
                    self._no_markers = True
                log.info("markers: can't set: %s", e)
