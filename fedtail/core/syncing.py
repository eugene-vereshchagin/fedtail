"""Sync with the account's other devices, the Core's side (the engine is core/sync): the
key, where they meet, a round now; what travels besides read marks — the lanes' rules
and the threads' state."""

import logging

from . import remote, subs

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts


class SyncMixin:
    """A part of Core (core/app.py): see the module's words."""

    def sync_key(self):
        from .sync import engine
        return engine.shown_key(self)

    def sync_join(self, text):
        from .sync import engine
        return engine.join(self, text)

    def sync_put_escrow(self, password):
        """This device's key into the journal under a password: another device takes it
        with the password alone (sync_take_escrow)."""
        if self.sync is None:
            raise RuntimeError("sync is off")
        self.sync.put_escrow(password)

    def sync_take_escrow(self, password):
        from .sync import engine
        return engine.take_escrow(self, password)

    def sync_first_key(self):
        from .sync import engine
        return engine.first_key(self)

    def sync_journal_there(self):
        """Has another device written into the store already? (None — can't tell now; a
        server can't ever: its journals are found by their keys.)"""
        from .sync import crypto
        if self.sync is None or self.sync.kind() == "server":
            return None
        try:
            backend = self.sync.backend()
            if backend is None:
                return None
            blobs, _c, _m = backend.pull(None, self.sync.device)
        except Exception as e:  # noqa: BLE001 — the store away: not known
            log.info("sync: looking at the journal: %s", e)
            return None
        return any(not crypto.is_escrow(b) for b in blobs)

    def sync_fresh_key(self):
        from .sync import engine
        return engine.fresh_key(self)

    def sync_has_escrow(self):
        """Is the key in the journal under a password (seen, or found there now)? None:
        can't be told — a server keeps it under what the password makes."""
        if self.sync is not None and self.sync.kind() == "server":
            return None
        try:
            return self.sync is not None and self.sync.find_escrow() is not None
        except Exception as e:  # noqa: BLE001 — the store away: not known, so no
            log.info("sync: looking for the key in the journal: %s", e)
            return False

    def sync_setup(self, url=None, folder=None, webdav=None, invite=None):
        """Where the devices meet, from the window: written into config.toml (sync.url,
        sync.folder, sync.webdav) and used at once — sync started, moved or stopped
        without a restart; the server's invite code into the data folder (not the
        config: it makes journals). None — that one unchanged."""
        from ..i18n import _
        from . import config_edit
        from .sync.engine import save_invite, wanted
        for where in (url, webdav):  # a secret goes there: never in clear across the net
            where = str(where or "").strip()
            if where and not (where.startswith(("https://", "http://")) and
                              remote.cleartext_ok(where)):
                raise ValueError(_("sync_cleartext", where=where))
        if invite is not None:
            save_invite(self.paths, invite)
        changes = {}
        for key, value in (("url", url), ("folder", folder), ("webdav", webdav)):
            if value is not None and str(value).strip() != str(self.cfg["sync"].get(key) or ""):
                changes[("sync", key)] = str(value).strip()
        if changes:
            config_edit.save(self.paths.config_file, changes)
            for (_s, key), value in changes.items():
                self.cfg["sync"][key] = value
        if self.sync is not None:
            self.sync.stop()
            self.sync = None
        if wanted(self.cfg):
            from .sync import Sync
            self.sync = Sync(self)
            if getattr(self, "_poller", None) is not None:
                self.sync.start()
        self.emit("sync_changed", None)
        return self.sync is not None

    def sync_webdav_login(self, user, password):
        """The WebDAV folder's user (config.toml) and password (the data folder, never the
        config), checked there at once: → None, or what's wrong in words (nothing kept)."""
        from ..i18n import _
        from .sync import backends, engine
        user = str(user or "").strip()
        if not user or not password:
            return _("sync_webdav_need")
        tree = backends.DavTree(self.cfg["sync"]["webdav"], user, password)
        try:
            tree.ready()
        except backends.BackendError as e:
            return _("sync_webdav_refused") if e.kind == "auth" else str(e)
        engine.save_webdav(self.paths, password)
        if user != self.cfg["sync"].get("webdav_user"):
            from . import config_edit
            config_edit.save(self.paths.config_file, {("sync", "webdav_user"): user})
            self.cfg["sync"]["webdav_user"] = user
        self.sync_setup()  # the engine anew, with it
        return None

    def sync_now(self):
        """One round at once: (sent, got), or None (sync.last says why)."""
        return self.sync.step() if self.sync else None

    def sync_status(self):
        return self.sync.status() if self.sync else None

    # the lanes' settings that travel with sync.lane_rules (core/sync)
    LANE_RULES = ("preset", "enabled", "custom", "posts_only")

    def _lane_rules(self):
        return {k: self.cfg["lanes"].get(k) for k in self.LANE_RULES}

    def _note_lane_rules(self):
        """The lanes as config.toml has them now, kept (kv "lane_rules"); changed since
        last time (edited by hand, in the lane editor) — they go to the other devices."""
        now = self._lane_rules()
        before = self.store.kv_get("lane_rules")
        if before == now:
            return
        self.store.kv_set("lane_rules", now)
        # the first time (a new device, a store started anew) is where it starts, not a
        # change: sent, it would win over the lanes the other devices have
        if self.sync and before is not None:
            self.sync.record_setting("lane_rules")

    def lanes_saved(self, cfg):
        """The lanes were written into config.toml here (the lane editor): this run takes
        them at once, and they travel (sync.lane_rules)."""
        for k in self.LANE_RULES:
            self.cfg["lanes"][k] = cfg["lanes"][k]
        self._note_lane_rules()
        self._apply_lists(list(self.lists), self.list_members)

    def _take_lane_rules(self):
        """Another device's lanes (sync.lane_rules): into this config.toml, then shown."""
        from . import config_edit
        got = self.store.kv_get("lane_rules")
        if not isinstance(got, dict):
            return
        changes = {("lanes", k): got[k] if got.get(k) is not None else config_edit.UNSET
                   for k in self.LANE_RULES if k in got}
        cfg, _w = config_edit.save(self.paths.config_file, changes)
        for k in self.LANE_RULES:
            self.cfg["lanes"][k] = cfg["lanes"][k]
        self.store.kv_set("lane_rules", self._lane_rules())  # as this file reads them

    def apply_lanes_state(self, keys):
        """Another device rearranged my lanes (core/sync: the order of lists, saved tag
        lanes; with sync.lane_rules the lanes themselves) — the new values are in the
        store already: the sidebar follows."""
        log.info("sync: %s from another device", ", ".join(keys))
        if "lane_rules" in keys:
            self._take_lane_rules()
        self._apply_lists(list(self.lists), self.list_members)

    def apply_thread_state(self, root, state):
        """Another device set this thread's state (core/sync): do the same here, without
        recording it again. Blocking (asks the server for the thread)."""
        post = {"id": root}
        if state == "sub":
            subs.subscribe(self.store, self.api, post)
        else:
            subs.leave(self.store, self.api, post, quiet=state == "muted")
            if state == "left":
                self.store.quiet_set(root, False)
            self._silence_seen = {}
        log.info("sync: thread %s → %s (another device)", root, state)
        self.emit("subs_changed", root)
        self.redraw("subs", "mentions")
