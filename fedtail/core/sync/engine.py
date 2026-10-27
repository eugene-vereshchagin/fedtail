"""The sync of one account between its devices: a journal out, the others' journals in.

What travels — a switch for each in `[sync]`:

* "read" — read marks the user made (scrolling, opening, "mark read"). Not the ones
  fedtail makes by itself: the first run's "everything is read", older history, my own
  posts — each device decides those, and a new phone must not mark the desktop's unread
  lanes read. A mark is never taken back, so marks merge by union: no conflicts.
* "threads" — a thread's state set by hand: followed ("sub"), left ("left"), muted
  ("muted"). The newest setting wins (time in ms, the device's id breaking a tie);
  automatic subscriptions to my own posts aren't sent — every device makes them itself.
* "lanes" — my own lanes as I arranged them: the order of lists (servers keep none, so
  each device would show them as they came) and the tag lanes saved from a search. Each
  is one value, the newest wins.
* "drafts" — unsent posts, one per draft key ("new", "reply:<id>", "quote:<id>": post
  ids are the account's, the same everywhere); the newest version wins, a sent or
  emptied draft goes everywhere. Attachments are files of this computer: they stay here
  (a draft from elsewhere keeps the ones this device had for it).
* "activity" — notifications I dismissed from Activity (the server can't always forget
  them): hidden on every device. Like read marks, they only add up.
* "tiles" — which lanes the phone pins as tiles (kv "pinned_tiles", set through
  `Core.set_pinned_tiles`): one value, the newest wins.
* "lane_rules" (off by default: it writes config.toml) — the lanes themselves: which set
  (`lanes.preset`), which lanes and in what order (`lanes.enabled`), one's own lanes
  (`[[lanes.custom]]`), `lanes.posts_only`. One value (kv "lane_rules"), the newest wins;
  a device that gets it writes it into its config.toml and shows the lanes anew.

Sync is on when it has a place to meet: `sync.url` (a fedtail-sync server) or
`sync.folder`. Nothing set — no sync, and nothing is recorded.

Recording works without the sync thread (`fedtail read …` in a terminal, the window
closed): the journal is in the store; whichever process of the profile runs the thread
sends it. The thread (`fedtail-sync`, started with polling) sends and fetches every
`sync.interval_seconds`, and a few seconds after something was recorded.

The key: the first device makes one when the store is empty, and says so in the log;
a device without a key facing someone's journal stops and asks for `fedtail sync join`.
"""

import json
import logging
import threading
import time
import uuid
from datetime import UTC, datetime

from ...i18n import _
from .. import auth
from . import backends, crypto

log = logging.getLogger(__name__)

THREAD_STATES = ("sub", "left", "muted")
WHAT = ("read", "threads", "lanes", "drafts", "activity", "tiles",
        "lane_rules")  # = config.SYNC_WHAT
# kv values carried whole (the newest wins) → the switch that lets them travel; app.py
# records them where they change
SETTINGS = {"list_order": "lanes", "tag_groups": "lanes", "pinned_tiles": "tiles",
            "lane_rules": "lane_rules"}
LANE_KEYS = tuple(k for k, w in SETTINGS.items() if w in ("lanes", "lane_rules"))
READ_CHUNK = 1000   # ids in one recorded op
BATCH_OPS = 400     # ops in one sealed blob
DEBOUNCE = 3        # seconds after a mark before sending: scrolling marks in bursts
SCOPES = "read:accounts"  # all a sync server needs to know whose journal it is


def wanted(cfg):
    """Is sync on? It is when it has somewhere to go."""
    s = cfg.get("sync") or {}
    return bool(s.get("url") or s.get("folder"))


def now_ms():
    return int(time.time() * 1000)


def _iso():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def key_path(paths):
    return paths.data_dir / "sync.key"


def auth_path(paths):
    return paths.data_dir / "sync_auth.json"


def load_auth(path):
    try:
        data = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    ok = isinstance(data, dict) and all(isinstance(data.get(k), str) and data[k]
                                        for k in ("instance", "token"))
    return data if ok else None


class Sync:
    def __init__(self, core):
        self.core = core
        self.store = core.store
        self.cfg = core.cfg["sync"]
        self.paths = core.paths
        self.what = {k for k in WHAT if self.cfg.get(k)}
        self.device = self._device()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread = None
        self._said = set()  # problems shown to the user this run (each once)
        self._trouble = ""
        self._last_at = 0  # stamps strictly rise: two changes in one ms keep their order
        self._drafts = {}  # draft key → when it changed: sent at the next round, once
        self._lock_at = threading.Lock()  # guards both

    def _device(self):
        d = self.store.kv_get("sync.device")
        if not d:
            d = uuid.uuid4().hex[:16]
            self.store.kv_set("sync.device", d)
        return d

    # ---- recording (any thread; the core calls these) ----------------------------
    def record_read(self, status_ids):
        if "read" not in self.what:
            return
        ids = [str(i) for i in status_ids if i]
        for i in range(0, len(ids), READ_CHUNK):
            self.store.sync_record({"r": ids[i:i + READ_CHUNK]})
        if ids:
            self._wake.set()

    def record_setting(self, key):
        """A setting carried whole (SETTINGS) changed here: its new value goes out."""
        if SETTINGS.get(key) not in self.what:
            return
        value = self.store.kv_get(key)
        at = self._stamp()
        self.store.sync_newer(f"k:{key}", at, self.device, json.dumps(value))
        self.store.sync_record({"k": key, "v": value, "at": at})
        self._wake.set()

    record_lanes = record_setting  # the order of lists, saved tag lanes

    def record_draft(self, key):
        """A draft saved or gone here. Typing saves often: only the last version of each
        goes out, at the next round (time stamped now, so the newest still wins)."""
        if "drafts" not in self.what or not key:
            return
        with self._lock_at:
            self._drafts[key] = self._stamp_locked()
        self._wake.set()

    def record_activity(self, hidden):
        """Notifications dismissed here: [(id, sort, group key or "")]."""
        if "activity" not in self.what:
            return
        rows = [[str(i), str(s or ""), str(g or "")] for i, s, g in hidden if i]
        if rows:
            self.store.sync_record({"h": rows})
            self._wake.set()

    def _flush_drafts(self):
        with self._lock_at:
            dirty, self._drafts = self._drafts, {}
        for key, at in dirty.items():
            d = self.store.get_draft(key)
            value = None
            if d:
                value = {k: v for k, v in d.items() if k != "media"}
                if not any(value.get(k) for k in ("text", "cw", "poll")):
                    continue  # only pictures: nothing another device could use
            self.store.sync_newer(f"d:{key}", at, self.device, json.dumps(value))
            self.store.sync_record({"dr": key, "v": value, "at": at})

    def record_thread(self, root, state):
        if "threads" not in self.what or not root or state not in THREAD_STATES:
            return
        at = self._stamp()
        self.store.sync_newer(f"t:{root}", at, self.device, state)
        self.store.sync_record({"t": str(root), "s": state, "at": at})
        self._wake.set()

    def _stamp(self):
        """Now in ms, never twice the same here: two moves in one millisecond must stay
        in order (the newest wins, and equal times would leave the second unapplied)."""
        with self._lock_at:
            return self._stamp_locked()

    def _stamp_locked(self):
        self._last_at = max(now_ms(), self._last_at + 1)
        return self._last_at

    # ---- the thread ----------------------------------------------------------------
    def start(self):
        if self._thread:
            return
        self._thread = threading.Thread(target=self._loop, name="fedtail-sync", daemon=True)
        self._thread.start()

    def stop(self, wait=5):
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(wait)

    def _loop(self):
        while not self._stop.is_set():
            self._round()
            woke = self._wake.wait(self.cfg["interval_seconds"])
            if self._stop.is_set():
                break
            if woke:
                self._wake.clear()
                self._stop.wait(DEBOUNCE)
        self._round(pull=False)  # what was marked last goes out before the exit

    def _round(self, pull=True):
        try:
            self.step(pull=pull)
        except Exception:  # noqa: BLE001 — sync must never take the window down
            log.exception("sync round failed")

    def step(self, pull=True):
        """One round: send this device's journal, take the others'. → (sent, got),
        or None when sync can't run (the reason is shown once and kept for status)."""
        with self._lock:
            self._trouble = ""  # a problem met this round (the round may go on past it)
            try:
                backend = self.backend()
                if backend is None:
                    return None
                key = self._key(backend)
                if key is None:
                    return None
                self._flush_drafts()
                sent = self._push(backend, key)
                got = self._pull(backend, key) if pull else 0
            except backends.BackendError as e:
                text = {"auth": _("sync_auth_refused"), "full": _("sync_full")}.get(
                    e.kind, _("sync_failed", why=str(e)))
                self._problem(e.kind, text)
                return None
            except crypto.CryptoMissing:
                self._problem("crypto", _("sync_no_crypto"))
                return None
            self.store.kv_set("sync.last", {"at": _iso(), "sent": sent, "got": got,
                                            "error": self._trouble})
            self.core.emit("sync_changed", None)
            if sent or got:
                log.info("sync: sent %d, got %d", sent, got)
            if not self._trouble:
                self._said.clear()  # working again: a new trouble is worth telling
            return sent, got

    def _problem(self, kind, text):
        self._trouble = text
        last = self.store.kv_get("sync.last") or {}
        self.store.kv_set("sync.last", {**last, "error": text, "error_at": _iso()})
        self.core.emit("sync_changed", None)
        if kind not in self._said:
            self._said.add(kind)
            log.warning("sync: %s", text)
            self.core.emit("error", text)

    # ---- where, and with what key ----------------------------------------------------
    def kind(self):
        return "folder" if self.cfg["folder"] else "server"

    def where(self):
        return self.cfg["folder"] or self.cfg["url"]

    def backend(self):
        if self.cfg["folder"]:
            return backends.FolderBackend(self.cfg["folder"])
        a = load_auth(auth_path(self.paths))
        if not a:
            self._problem("login", _("sync_login_first"))
            return None
        return backends.HttpBackend(self.cfg["url"], a["instance"], a["token"])

    def _key(self, backend):
        key = crypto.load_key(key_path(self.paths))
        if key:
            return key
        if not crypto.available():  # said before anything is made
            raise crypto.CryptoMissing("no cryptography")
        others, _cur, _more = backend.pull(None, self.device)
        if others:  # someone's journal is there already: its key, not a new one
            self._problem("key", _("sync_need_key"))
            return None
        key = crypto.new_key()
        crypto.save_key(key_path(self.paths), key)
        log.info("sync: a new key made (id %s): carry it to the other devices with "
                 "`fedtail sync key` → `fedtail sync join`", crypto.key_id(key).hex())
        return key

    # ---- out and in -----------------------------------------------------------------
    def _push(self, backend, key):
        sent = 0
        for _round in range(20):
            rows = self.store.sync_pending(BATCH_OPS)
            if not rows:
                break
            payload = {"v": 1, "d": self.device, "at": now_ms(), "ops": [op for _, op in rows]}
            backend.push(crypto.seal(key, payload), self.device)
            self.store.sync_sent(rows[-1][0])
            sent += len(rows)
        return sent

    def _pull(self, backend, key):
        if self.store.kv_get("sync.where") != backend.where:  # another store: from its start
            self.store.kv_set("sync.cursor", None)
            self.store.kv_set("sync.where", backend.where)
        cursor = self.store.kv_get("sync.cursor")
        mine = crypto.key_id(key)
        got = 0
        for _round in range(50):
            blobs, cursor, more = backend.pull(cursor, self.device)
            for blob in blobs:
                try:
                    if crypto.blob_key_id(blob) != mine:
                        self._problem("other_key", _("sync_other_key"))
                        continue
                    payload = crypto.unseal(key, blob)
                except crypto.BadBlob as e:
                    log.warning("sync: a blob skipped: %s", e)
                    continue
                if isinstance(payload, dict) and payload.get("d") != self.device:
                    got += self.apply(payload)
            self.store.kv_set("sync.cursor", cursor)
            if not more:
                break
        return got

    def apply(self, payload):
        """Another device's batch → this store. → how many ops it carried."""
        reads, threads, lanes, hidden, drafts, tiles = [], [], [], [], [], False
        device = str(payload.get("d") or "")
        seen = 0
        for op in payload.get("ops") or []:
            if not isinstance(op, dict):
                continue
            try:
                seen = max(seen, int(op.get("at") or 0))
            except (TypeError, ValueError):
                op["at"] = 0
            if isinstance(op.get("r"), list):
                if "read" in self.what:
                    reads += [str(i) for i in op["r"] if isinstance(i, (str, int))]
            elif isinstance(op.get("t"), str) and op.get("s") in THREAD_STATES:
                if "threads" in self.what and self.store.sync_newer(
                        f"t:{op['t']}", int(op.get("at") or 0), device, op["s"]):
                    threads.append((op["t"], op["s"]))
            elif op.get("k") in SETTINGS and "v" in op:
                if SETTINGS[op["k"]] in self.what and self._setting_ok(op["k"], op["v"]) and \
                        self.store.sync_newer(f"k:{op['k']}", int(op.get("at") or 0), device,
                                              json.dumps(op["v"])):
                    self.store.kv_set(op["k"], op["v"])
                    if op["k"] in LANE_KEYS:
                        lanes.append(op["k"])
                    else:
                        tiles = True
            elif isinstance(op.get("h"), list):
                if "activity" in self.what:
                    hidden += [tuple(str(x) for x in r) for r in op["h"]
                               if isinstance(r, list) and len(r) == 3]
            elif isinstance(op.get("dr"), str) and "v" in op:
                v = op["v"]
                if "drafts" in self.what and (v is None or isinstance(v, dict)) and \
                        self.store.sync_newer(f"d:{op['dr']}", int(op.get("at") or 0), device,
                                              json.dumps(v)):
                    self._apply_draft(op["dr"], v)
                    drafts.append(op["dr"])
        if reads:
            fresh = list(set(reads) - self.store.read_set(reads))
            if fresh:
                self.store.mark_read(fresh)
                self.core.emit("read_changed", fresh)
        for root, state in threads:
            try:
                self.core.apply_thread_state(root, state)
            except Exception as e:  # noqa: BLE001 — one gone thread mustn't stop the rest
                log.warning("sync: thread %s → %s: %s", root, state, e)
        if seen:  # what I do from now on is newer than anything I've seen, whatever
            with self._lock_at:  # the clocks of the devices say (a logical clock)
                self._last_at = max(self._last_at, min(seen, now_ms() + 86_400_000))
        if lanes:
            try:
                self.core.apply_lanes_state(lanes)
            except Exception as e:  # noqa: BLE001 — the rest of the batch is applied
                log.warning("sync: lanes %s: %s", lanes, e)
        if tiles:
            self.core.emit("tiles_changed", self.store.kv_get("pinned_tiles", []))
        if hidden and self.store.activity_hide_known(hidden):
            self.core.emit("activity_updated", None)
        if drafts:
            self.core.emit("drafts_changed", drafts)
        return len(reads) + len(threads) + len(lanes) + int(tiles) + len(hidden) + len(drafts)

    def _apply_draft(self, key, value):
        """Another device's version of a draft; this device's attachments for it stay."""
        if value is None:
            self.store.delete_draft(key)
            return
        mine = self.store.get_draft(key) or {}
        self.store.save_draft(key, {**value, "media": mine.get("media", [])})

    @staticmethod
    def _setting_ok(key, value):
        """Only the shapes app.py keeps: lists of ids or names; a list of tag groups;
        the lanes' settings (Core.LANE_RULES: a table of them)."""
        if key == "lane_rules":
            return isinstance(value, dict) and isinstance(value.get("custom", []), list) \
                and isinstance(value.get("enabled", []), list)
        if not isinstance(value, list):
            return False
        if key == "tag_groups":
            return all(isinstance(g, dict) for g in value)
        return all(isinstance(x, str) for x in value)

    # ---- for `fedtail sync status` ---------------------------------------------------
    def status(self):
        key = crypto.load_key(key_path(self.paths))
        a = load_auth(auth_path(self.paths))
        return {"backend": self.kind(),
                "where": self.where(),
                "login": a["instance"] if a else "",
                "device": self.device,
                "key": crypto.key_id(key).hex() if key else "",
                "pending": self.store.sync_pending_count(),
                "last": self.store.kv_get("sync.last") or {}}


# ---- the sync server's token: read:accounts only, never the main one -------------------

def login_start(api_class, instance):
    """Register the "fedtail sync" app on the account's server. → what login_finish
    needs, with the page where the user gets the code."""
    api = api_class(instance)
    app = api.register_app(scopes=SCOPES, name="fedtail sync")
    return {"instance": api.base, "client_id": app["client_id"],
            "client_secret": app["client_secret"],
            "url": api.authorize_url(app["client_id"], scopes=SCOPES)}


def login_finish(api_class, paths, pending, code):
    api = api_class(pending["instance"])
    token = api.get_token(pending["client_id"], pending["client_secret"], code, scopes=SCOPES)
    auth.save(auth_path(paths), {**{k: pending[k] for k in ("instance", "client_id",
                                                            "client_secret")},
                                 "token": token})


# ---- what `fedtail sync …` asks of a Core (app.py passes these through) -----------------

def shown_key(core):
    """The key as text, or None (not made yet)."""
    key = crypto.load_key(key_path(core.paths))
    return crypto.key_text(key) if key else None


def join(core, text):
    """Take the account's key from another device. → its id (hex). ValueError: not one."""
    key = crypto.key_from_text(text)
    crypto.save_key(key_path(core.paths), key)
    core.store.kv_set("sync.cursor", None)  # the journal from its start, with this key
    return crypto.key_id(key).hex()
