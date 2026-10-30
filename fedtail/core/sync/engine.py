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
  emptied draft goes everywhere. Its pictures travel beside the journal where the store
  keeps them (a fedtail-sync that says `media_kb`, or a folder): each sealed, named by a
  keyed hash (sent once, however often the draft is saved), fetched by the other devices
  into `sync_media/` of their profile; a sent or emptied draft takes its pictures off the
  store. Too big for the store, or one it dropped (it keeps the least used) — that
  picture stays on its own device, the rest goes.
* "activity" — notifications I dismissed from Activity (the server can't always forget
  them): hidden on every device. Like read marks, they only add up. And how far events
  are seen (kv "activity_seen", the sort of the newest seen — the server's time and id,
  the same on every device): it only goes forward, the furthest wins.
* "tiles" — which lanes the phone pins as tiles (kv "pinned_tiles", set through
  `Core.set_pinned_tiles`): one value, the newest wins.
* "lane_rules" (off by default: it writes config.toml) — the lanes themselves: which set
  (`lanes.preset`), which lanes and in what order (`lanes.enabled`), one's own lanes
  (`[[lanes.custom]]`), `lanes.posts_only`. One value (kv "lane_rules"), the newest wins;
  a device that gets it writes it into its config.toml and shows the lanes anew.

A journal only grows, so each device packs its own now and then (`_compact`): when what it
has sent since the last time is past COMPACT_BYTES and several times what a snapshot of it
all would be, it sends that snapshot — every newest-wins value with its own time and device,
the read marks of the newest posts, how far events are seen, what was dismissed — and has
the store drop its older blobs (a folder: its older files; a fedtail-sync that says
`compact`). A device that was away reads the snapshot instead of what it replaced: the
same state, but the read marks of posts older than the newest SNAPSHOT_READ.

What a device already knows when it first syncs under a key goes out once too (`_snapshot`):
the settings carried whole (not `lane_rules`), stamped time 0 so any real change anywhere
beats them; how
far events are seen; the user's read marks of the posts it keeps (the store's read_shared:
made here by hand or got from another device — never the first run's "all read", which
made a new phone mark the desktop's lanes read, 31.10). A device that joins later
gets the state, not only what changed after it came.

Sync is on when it has a place to meet: `sync.url` (a fedtail-sync server: the journal
is the key's — an id and a secret derived from it; the first device makes the journal with
the invite code the server's admin gave, kept in the data folder, `sync_invite.json`),
`sync.folder`, or `sync.webdav` (a WebDAV folder spoken directly — `sync.webdav_user`, the
password in the profile's data folder, `sync_webdav.json`, never in the config). Nothing
set — no sync, and nothing is recorded.

Recording works without the sync thread (`fedtail read …` in a terminal, the window
closed): the journal is in the store; whichever process of the profile runs the thread
sends it. The thread (`fedtail-sync`, started with polling) sends and fetches every
`sync.interval_seconds`, and a few seconds after something was recorded.

The key: in a folder or WebDAV the first device makes one when the store is empty, and
says so in the log; a device without a key facing someone's journal stops and asks for
`fedtail sync join`. On a server the journal is found by the key, so there is nothing to
look at without one: the key is made only when asked (`fedtail sync first`, the window's
"this is my first device") or taken (`join`, the password).
"""

import json
import logging
import os
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

from ...i18n import _
from .. import auth
from . import backends, crypto

log = logging.getLogger(__name__)

THREAD_STATES = ("sub", "left", "muted")
# the drafts' pictures that travel: what a fediverse server takes as an attachment
MEDIA_EXTS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".heic", ".mp4", ".webm",
              ".mov", ".mp3", ".ogg", ".oga", ".opus", ".wav", ".flac", ".m4a")
WHAT = ("read", "threads", "lanes", "drafts", "activity", "tiles",
        "lane_rules", "people")  # = config.SYNC_WHAT
# kv values carried whole (the newest wins) → the switch that lets them travel; app.py
# records them where they change
SETTINGS = {"list_order": "lanes", "tag_groups": "lanes", "pinned_tiles": "tiles",
            "lane_rules": "lane_rules",
            # my own names for people, those kept out of Home (sync.people)
            "people_aliases": "people", "people.hidden_home": "people",
            "people_colors": "people"}
PEOPLE_KEYS = tuple(k for k, w in SETTINGS.items() if w == "people")
LANE_KEYS = tuple(k for k, w in SETTINGS.items() if w in ("lanes", "lane_rules"))
READ_CHUNK = 1000   # ids in one recorded op
BATCH_OPS = 400     # ops in one sealed blob
DEBOUNCE = 3        # seconds after a mark before sending: scrolling marks in bursts
COMPACT_BYTES = 1024 * 1024  # this device's journal past this → packed into a snapshot
COMPACT_GAIN = 4    # … and only when it is this many times the snapshot


def wanted(cfg):
    """Is sync on? It is when it has somewhere to go."""
    s = cfg.get("sync") or {}
    return bool(s.get("url") or s.get("folder") or s.get("webdav"))


def now_ms():
    return int(time.time() * 1000)


def _iso():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def key_path(paths):
    return paths.data_dir / "sync.key"


def invite_path(paths):
    return paths.data_dir / "sync_invite.json"


def load_invite(paths):
    """The sync server's invite code kept here, or ""."""
    try:
        data = json.loads(invite_path(paths).read_text("utf-8"))
    except (OSError, ValueError):
        return ""
    return data.get("code") if isinstance(data, dict) and isinstance(data.get("code"), str) \
        else ""


def save_invite(paths, code):
    code = str(code or "").strip()
    if not code:
        invite_path(paths).unlink(missing_ok=True)
        return
    auth.save(invite_path(paths), {"code": code})


def webdav_path(paths):
    return paths.data_dir / "sync_webdav.json"


def load_webdav(paths):
    """The WebDAV password kept here, or ""."""
    try:
        data = json.loads(webdav_path(paths).read_text("utf-8"))
    except (OSError, ValueError):
        return ""
    return data.get("password") if isinstance(data, dict) and \
        isinstance(data.get("password"), str) else ""


def save_webdav(paths, password):
    """Readable by its owner only, as auth.json; "" — forgotten."""
    f = webdav_path(paths)
    if not password:
        f.unlink(missing_ok=True)
        return
    auth.save(f, {"password": password})  # the one way a secret file is written here


def media_dir(paths):
    """Where the other devices' pictures of drafts are kept here."""
    return Path(paths.data_dir) / "sync_media"


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
        # a round, and every change of the key: a round mustn't make a key of its own
        # while the window takes or makes one (two keys, one kept, the other sealing)
        self._lock = threading.RLock()
        self._thread = None
        self._said = set()  # problems shown to the user this run (each once)
        self._trouble = ""
        self._last_at = 0  # stamps strictly rise: two changes in one ms keep their order
        self._drafts = {}  # draft key → when it changed: sent at the next round, once
        self._media_at = None  # (backend, key) while a round runs: the drafts' pictures
        self._lock_at = threading.Lock()  # guards both

    def _device(self):
        """This device's id in the journal. It is bound to where it was made (the
        machine's name and the profile's folder): a profile copied to another computer
        (28.10: Linux's onto a Windows VM) makes an id of its own there — two devices
        under one id take each other's journal for their own and never see it."""
        d = self.store.kv_get("sync.device")
        here = self._here()
        # an id from before 0.22 has no place of its own yet: made anew once (cheap — the
        # journal is read again from its start, every op in it can be taken twice)
        if d and self.store.kv_get("sync.device_at") != here:
            log.info("sync: a new device id here (the profile was made elsewhere, or by an "
                     "older fedtail); the journal read from its start")
            d = None
            self.store.kv_set("sync.cursor", None)
            self.store.kv_set("sync.snapshot", None)  # what this one knows goes out too
        if not d:
            d = uuid.uuid4().hex[:16]
            self.store.kv_set("sync.device", d)
        self.store.kv_set("sync.device_at", here)
        return d

    def _here(self):
        import hashlib
        import platform
        where = f"{platform.node()}\0{Path(self.paths.data_dir).resolve()}"
        return hashlib.sha256(where.encode()).hexdigest()[:16]

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

    def record_activity_seen(self, mark):
        """Events seen here up to this sort (Core.mark_activity_seen)."""
        if "activity" in self.what and mark:
            self.store.sync_record({"as": str(mark)})
            self._wake.set()

    def record_activity(self, hidden):
        """Notifications dismissed here: [(id, sort, group key or "")]."""
        if "activity" not in self.what:
            return
        rows = [[str(i), str(s or ""), str(g or "")] for i, s, g in hidden if i]
        if rows:
            self.store.sync_record({"h": rows})
            self._wake.set()

    def _flush_drafts(self, backend=None, key=None):
        with self._lock_at:
            dirty, self._drafts = self._drafts, {}
        for dkey, at in dirty.items():
            d = self.store.get_draft(dkey)
            value = None
            if d:
                value = {k: v for k, v in d.items() if k != "media"}
                refs = self._send_media(backend, key, d.get("media") or ())
                if refs:
                    value["media_refs"] = refs
                if not refs and not any(value.get(k) for k in ("text", "cw", "poll")):
                    continue  # only pictures that can't travel: nothing for another device
                self._draft_refs(dkey, [r["ref"] for r in refs])
            else:
                self._drop_media(backend, self._draft_refs(dkey, []))
            self.store.sync_newer(f"d:{dkey}", at, self.device, json.dumps(value))
            self.store.sync_record({"dr": dkey, "v": value, "at": at})

    SNAPSHOT_READ = 5000  # read marks of the newest posts kept, sent with the snapshot

    def _snapshot(self, key, where=""):
        """Once per key: what this device knows already goes into the journal — so a
        device joining later gets the state, not only the changes made after it came."""
        # once per key and per store: a journal moved (another server, protocol 2's
        # journals by key) gets what this device knows again
        kid = crypto.key_id(key).hex() + (f" {where}" if where else "")
        if self.store.kv_get("sync.snapshot") == kid:
            return
        for k, switch in SETTINGS.items():
            value = self.store.kv_get(k)
            # not the lanes themselves: they write the other device's config.toml, and a
            # device joining mustn't have its lanes replaced by what it merely met there
            if k != "lane_rules" and switch in self.what and value not in (None, [], {}):
                # time 0: any device's real change beats it; between snapshots alone the
                # device id decides, the same everywhere
                self.store.sync_record({"k": k, "v": value, "at": 0})
        if "activity" in self.what:
            self.record_activity_seen(self.store.kv_get("activity_seen"))
        if "read" in self.what:
            self.record_read(self.store.recent_read(self.SNAPSHOT_READ))
        self.store.kv_set("sync.snapshot", kid)
        log.info("sync: what this device knows sent once for key %s", kid)

    # ---- the drafts' pictures ------------------------------------------------------
    MEDIA_SENT_KEEP = 500  # names this device put on the store: not put again

    def _send_media(self, backend, key, media):
        """This device's pictures of a draft onto the store (each once) → their refs:
        [{"ref", "ext", "desc", "focus"}] — the ones that can't go (too big, gone from
        the disk, a store without pictures) are left out."""
        if backend is None or key is None or not media:
            return []
        try:
            kb = backend.media_kb()
        except backends.BackendError:
            kb = 0
        if not kb:
            return []
        sent = list(self.store.kv_get("sync.media_sent") or ())
        refs = []
        for m in media:
            m = list(m) if isinstance(m, (list, tuple)) else [m]
            path = Path(str(m[0])) if m else None
            ext = path.suffix.lower() if path else ""
            try:
                if path is None or ext not in MEDIA_EXTS or path.stat().st_size > kb * 1024:
                    continue
                data = path.read_bytes()
            except OSError:
                continue
            name = crypto.media_name(key, data)
            if name not in sent:
                try:
                    backend.media_put(name, crypto.seal_media(key, data))
                except backends.BackendError as e:
                    log.info("sync: a picture of a draft not sent: %s", e)
                    continue
                sent.append(name)
            refs.append({"ref": name, "ext": ext, "desc": str(m[1] if len(m) > 1 else ""),
                         "focus": m[2] if len(m) > 2 else None})
        self.store.kv_set("sync.media_sent", sent[-self.MEDIA_SENT_KEEP:])
        return refs

    def _draft_refs(self, dkey, names):
        """The pictures a draft has on the store now (kv "sync.draft_media"); → the ones it
        had before that no draft has any more (to take off the store)."""
        table = dict(self.store.kv_get("sync.draft_media") or {})
        before = set(table.get(dkey) or ())
        if names:
            table[dkey] = list(names)
        else:
            table.pop(dkey, None)
        self.store.kv_set("sync.draft_media", table)
        still = {n for v in table.values() for n in v}
        return sorted(before - still)

    def _drop_media(self, backend, names):
        if not names:
            return
        sent = [n for n in self.store.kv_get("sync.media_sent") or () if n not in names]
        self.store.kv_set("sync.media_sent", sent)
        for name in names:
            f = next(media_dir(self.paths).glob(name + ".*"), None) \
                if media_dir(self.paths).is_dir() else None
            if f is not None:
                f.unlink(missing_ok=True)
            if backend is not None:
                try:
                    backend.media_delete(name)
                except (backends.BackendError, ValueError) as e:
                    log.info("sync: a picture not taken off the store: %s", e)

    def _fetch_media(self, refs):
        """Another device's pictures of a draft → [[path, desc, focus]] here (fetched into
        sync_media/ once); those the store no longer has, or that don't open, left out."""
        backend, key = self._media_at or (None, None)
        out = []
        folder = media_dir(self.paths)
        for r in refs if isinstance(refs, list) else ():
            if not isinstance(r, dict):
                continue
            name, ext = str(r.get("ref") or ""), str(r.get("ext") or "")
            if not backends._MEDIA_NAME.match(name) or ext not in MEDIA_EXTS:
                continue
            f = folder / (name + ext)
            if not f.exists():
                if backend is None:
                    continue
                try:
                    blob = backend.media_get(name)
                    data = crypto.unseal_media(key, blob) if blob else None
                except (backends.BackendError, crypto.BadBlob) as e:
                    log.info("sync: a picture of a draft not fetched: %s", e)
                    continue
                if data is None or crypto.media_name(key, data) != name:
                    continue  # gone from the store, or not the picture its name says
                folder.mkdir(parents=True, exist_ok=True)
                tmp = f.with_name("." + f.name + ".part")
                tmp.write_bytes(data)
                os.replace(tmp, f)
            item = [str(f), str(r.get("desc") or "")]
            if r.get("focus") is not None:
                item.append(r["focus"])
            out.append(item)
        return out

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
                if self.kind() == "server":  # the journal is found by the key
                    key = crypto.load_key(key_path(self.paths))
                    if key is None:
                        self._problem("key", _("sync_need_key_server"))
                        return None
                    backend = self.backend(key)
                else:
                    backend = self.backend()
                    if backend is None:
                        return None
                    key = self._key(backend)
                    if key is None:
                        return None
                self._snapshot(key, backend.where)
                self._media_at = (backend, key)  # for the drafts' pictures, this round
                self._flush_drafts(backend, key)
                sent = self._push(backend, key)
                got = self._pull(backend, key) if pull else 0
                if pull:
                    self._compact(backend, key)
            except backends.BackendError as e:
                text = {"auth": _("sync_auth_refused"), "full": _("sync_full"),
                        "invite": _("sync_invite_needed")}.get(
                    e.kind, _("sync_failed", why=str(e)))
                self._problem(e.kind, text)
                return None
            except crypto.CryptoMissing:
                self._problem("crypto", _("sync_no_crypto"))
                return None
            finally:
                self._media_at = None
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
        # its kind too: the window's place goes back to the step that mends it (an invite
        # code wanted → "where", where the code is typed)
        self.store.kv_set("sync.last", {**last, "error": text, "error_at": _iso(),
                                        "error_kind": kind})
        self.core.emit("sync_changed", None)
        if kind not in self._said:
            self._said.add(kind)
            log.warning("sync: %s", text)
            self.core.emit("error", text)

    # ---- where, and with what key ----------------------------------------------------
    def kind(self):
        return "folder" if self.cfg["folder"] else (
            "webdav" if self.cfg.get("webdav") else "server")

    def where(self):
        return self.cfg["folder"] or self.cfg.get("webdav") or self.cfg["url"]

    def backend(self, key=None):
        """Where the journal is. A server: the journal of `key` (this device's when None),
        or — no key here — one that answers only what needs no journal (the key under a
        password)."""
        if self.cfg["folder"]:
            return backends.FolderBackend(self.cfg["folder"])
        if self.cfg.get("webdav"):
            password = load_webdav(self.paths)
            if not password or not self.cfg.get("webdav_user"):
                self._problem("login", _("sync_webdav_login_first"))
                return None
            return backends.WebDavBackend(self.cfg["webdav"], self.cfg["webdav_user"],
                                          password)
        key = key or crypto.load_key(key_path(self.paths))
        return backends.HttpBackend(self.cfg["url"], key, load_invite(self.paths))

    def _key(self, backend):
        key = crypto.load_key(key_path(self.paths))
        if key:
            return key
        if not crypto.available():  # said before anything is made
            raise crypto.CryptoMissing("no cryptography")
        others, _cur, _more = backend.pull(None, self.device)
        for blob in others:
            if crypto.is_escrow(blob):
                self._keep_escrow(blob)
        if [b for b in others if not crypto.is_escrow(b)]:
            # someone's journal is there already: its key, not a new one — from another
            # device, or out of the journal with the password if it was put there
            self._problem("key", _("sync_need_key_pass") if self.store.kv_get("sync.escrow")
                          else _("sync_need_key"))
            return None
        key = crypto.new_key()
        crypto.save_key(key_path(self.paths), key)
        log.info("sync: a new key made (id %s): carry it to the other devices with "
                 "`fedtail sync key` → `fedtail sync join`", crypto.key_id(key).hex())
        return key

    def _who(self):
        """The fediverse account, "user@host": what makes the key under a password one
        person's on a server (crypto.escrow_id). ValueError before a login."""
        from ..merged import full_handle
        who = full_handle(self.core).lstrip("@")
        if "@" not in who:
            raise ValueError("log in to the account first")
        return who

    def _keep_escrow(self, blob):
        import base64
        self.store.kv_set("sync.escrow", base64.b64encode(bytes(blob)).decode())

    def find_escrow(self, password=None):
        """The key-under-a-password blob: the one seen, else looked for in the journal
        from its start (a server: asked under the id the password makes — None without
        one). → bytes or None."""
        import base64
        if self.kind() == "server":
            if not password:
                return None
            return backends.HttpBackend(self.cfg["url"]).escrow_get(
                crypto.escrow_id(password, self.cfg["url"], self._who()))
        got = self.store.kv_get("sync.escrow")
        if got:
            return base64.b64decode(got)
        backend = self.backend()
        if backend is None:
            return None
        cursor = None
        for _round in range(200):
            blobs, cursor, more = backend.pull(cursor, self.device)
            found = [b for b in blobs if crypto.is_escrow(b)]
            if found:
                self._keep_escrow(found[-1])
                return bytes(found[-1])
            if not more:
                break
        return None

    def put_escrow(self, password):
        """This device's key into the journal, sealed by the password."""
        key = crypto.load_key(key_path(self.paths))
        if key is None:
            raise ValueError("no key")
        backend = self.backend()
        if backend is None:
            raise RuntimeError(_("sync_webdav_login_first"))
        blob = crypto.escrow_seal(key, password)
        if self.kind() == "server":  # under an id the password makes: found by it alone
            backend.escrow_put(crypto.escrow_id(password, self.cfg["url"], self._who()), blob)
        else:
            backend.push(blob, self.device)
        self._keep_escrow(blob)

    # ---- out and in -----------------------------------------------------------------
    def _push(self, backend, key):
        sent = 0
        for _round in range(20):
            rows = self.store.sync_pending(BATCH_OPS)
            if not rows:
                break
            payload = {"v": 1, "d": self.device, "at": now_ms(), "ops": [op for _, op in rows]}
            blob = crypto.seal(key, payload)
            backend.push(blob, self.device)
            self._grew(len(blob))
            self.store.sync_sent(rows[-1][0])
            sent += len(rows)
        return sent

    def _grew(self, n):
        """How much this device has put into the journal since it was last packed."""
        self.store.kv_set("sync.mine_bytes", int(self.store.kv_get("sync.mine_bytes") or 0) + n)

    def state_ops(self):
        """Everything this device knows that travels, as ops — the snapshot a packed
        journal is replaced by. Each newest-wins value keeps its own time and the device
        that set it ("by"), so the snapshot never beats a newer change anywhere."""
        ops = []
        kinds = {"t": "threads", "d": "drafts"}
        for k, at, dev, value in self.store.sync_lww_rows():
            kind, _sep, name = k.partition(":")
            try:
                v = json.loads(value) if kind in ("k", "d") else value
            except ValueError:
                continue
            if kind == "k":
                if SETTINGS.get(name) in self.what:
                    ops.append({"k": name, "v": v, "at": at, "by": dev})
            elif kinds.get(kind) in self.what:
                ops.append({"t": name, "s": v, "at": at, "by": dev} if kind == "t" else
                           {"dr": name, "v": v, "at": at, "by": dev})
        if "activity" in self.what:
            if self.store.kv_get("activity_seen"):
                ops.append({"as": str(self.store.kv_get("activity_seen"))})
            rows = [list(r) for r in self.store.activity_hidden_rows()]
            ops += [{"h": rows[i:i + READ_CHUNK]} for i in range(0, len(rows), READ_CHUNK)]
        if "read" in self.what:
            ids = [str(i) for i in self.store.recent_read(self.SNAPSHOT_READ)]
            ops += [{"r": ids[i:i + READ_CHUNK]} for i in range(0, len(ids), READ_CHUNK)]
        return ops

    def _compact(self, backend, key):
        """This device's journal packed, when that is worth it (see the top). → how many
        old blobs went, or 0."""
        mine = int(self.store.kv_get("sync.mine_bytes") or 0)
        can = getattr(backend, "can_compact", None)
        if mine < COMPACT_BYTES or not can or not can():
            return 0
        ops = self.state_ops()
        blobs = [crypto.seal(key, {"v": 1, "d": self.device, "at": now_ms(),
                                   "ops": ops[i:i + BATCH_OPS]})
                 for i in range(0, len(ops), BATCH_OPS)]
        size = sum(map(len, blobs))
        if not blobs or mine < size * COMPACT_GAIN:
            return 0
        first = None
        for blob in blobs:
            at = backend.push(blob, self.device)
            first = at if first is None else first
        self.store.kv_set("sync.mine_bytes", size)
        if not first:  # the store didn't say where it went: the old ones stay
            return 0
        gone = backend.compact(self.device, first)
        log.info("sync: this device's journal packed: %d old blobs gone, %d KB → %d KB",
                 gone, mine // 1024, size // 1024)
        return gone

    def _pull(self, backend, key):
        if self.store.kv_get("sync.where") != backend.where:  # another store: from its start
            self.store.kv_set("sync.cursor", None)
            self.store.kv_set("sync.where", backend.where)
        cursor = self.store.kv_get("sync.cursor")
        mine = crypto.key_id(key)
        got = 0
        for _round in range(50):
            blobs, cursor, more = backend.pull(cursor, self.device)
            left = set(self.store.kv_get("sync.left_keys") or ())
            for blob in blobs:
                if crypto.is_escrow(blob):  # the key under a password: kept, for a new device
                    self._keep_escrow(blob)
                    continue
                try:
                    kid = crypto.blob_key_id(blob)
                    if kid != mine:
                        if kid.hex() not in left:  # a key let go of on purpose: silent
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
        people = False
        seen_to = None  # how far events are seen elsewhere, when further than here
        sender = str(payload.get("d") or "")
        seen = 0
        for op in payload.get("ops") or []:
            if not isinstance(op, dict):
                continue
            try:
                seen = max(seen, int(op.get("at") or 0))
            except (TypeError, ValueError):
                op["at"] = 0
            # a snapshot carries values other devices set: each with its own
            by = op.get("by")
            device = by if isinstance(by, str) and by else sender
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
                    elif op["k"] in PEOPLE_KEYS:
                        people = True
                    else:
                        tiles = True
            elif isinstance(op.get("as"), str):
                if "activity" in self.what and op["as"] > (self.store.kv_get("activity_seen")
                                                           or ""):
                    self.store.kv_set("activity_seen", op["as"])
                    seen_to = op["as"]
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
            # every one of them the user's (somewhere): carried on in this device's
            # snapshots too, even the ones read here already by fedtail itself
            self.store.mark_read(reads, shared=True)
            if fresh:
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
        if people:
            changed = getattr(self.core, "_people_changed", None)
            if changed is not None:
                changed()
        if hidden and self.store.activity_hide_known(hidden):
            self.core.emit("activity_updated", None)
        if drafts:
            self.core.emit("drafts_changed", drafts)
        if seen_to:
            self.core.emit("activity_seen", seen_to)
        return len(reads) + len(threads) + len(lanes) + int(tiles) + len(hidden) + \
            len(drafts) + int(bool(seen_to))

    def _apply_draft(self, key, value):
        """Another device's version of a draft, with its pictures fetched; one without
        pictures of its own keeps this device's ones for it."""
        if value is None:
            self.store.delete_draft(key)
            self._drop_media(None, self._draft_refs(key, []))  # our copies of its pictures
            return
        value = dict(value)
        refs = value.pop("media_refs", None)
        mine = self.store.get_draft(key) or {}
        media = self._fetch_media(refs) if refs else []
        self.store.save_draft(key, {**value, "media": media or mine.get("media", [])})
        if refs:
            self._draft_refs(key, [str(r.get("ref")) for r in refs if isinstance(r, dict)])

    @staticmethod
    def _setting_ok(key, value):
        """Only the shapes app.py keeps: lists of ids or names; a list of tag groups;
        the lanes' settings (Core.LANE_RULES: a table of them)."""
        if key == "lane_rules":
            return isinstance(value, dict) and isinstance(value.get("custom", []), list) \
                and isinstance(value.get("enabled", []), list)
        if key in ("people_aliases", "people_colors"):
            return isinstance(value, dict) and all(isinstance(k, str) and isinstance(v, str)
                                                   for k, v in value.items())
        if not isinstance(value, list):
            return False
        if key == "tag_groups":
            return all(isinstance(g, dict) for g in value)
        return all(isinstance(x, str) for x in value)

    # ---- for `fedtail sync status` ---------------------------------------------------
    def status(self):
        key = crypto.load_key(key_path(self.paths))
        login = "invite" if load_invite(self.paths) else ""
        if self.kind() == "webdav":
            login = self.cfg.get("webdav_user", "") if load_webdav(self.paths) else ""
        return {"backend": self.kind(),
                "where": self.where(),
                "login": login,
                "device": self.device,
                "key": crypto.key_id(key).hex() if key else "",
                "pending": self.store.sync_pending_count(),
                "last": self.store.kv_get("sync.last") or {}}


# ---- what `fedtail sync …` asks of a Core (app.py passes these through) -----------------

def shown_key(core):
    """The key as text, or None (not made yet)."""
    key = crypto.load_key(key_path(core.paths))
    return crypto.key_text(key) if key else None


def _key_lock(core):
    """The lock a round holds (Sync._lock): changing the key waits for the round."""
    import contextlib
    sync = getattr(core, "sync", None)
    return sync._lock if sync is not None else contextlib.nullcontext()


def _take(core, key):
    """This device's key from now on: the journal read from its start with it; the key
    it had before (if any) let go of — its old blobs pass silently."""
    with _key_lock(core):
        return _take_locked(core, key)


def _take_locked(core, key):
    old = crypto.load_key(key_path(core.paths))
    if old is not None and old != key:
        left = list(core.store.kv_get("sync.left_keys") or [])
        if crypto.key_id(old).hex() not in left:
            core.store.kv_set("sync.left_keys", (left + [crypto.key_id(old).hex()])[-20:])
    crypto.save_key(key_path(core.paths), key)
    core.store.kv_set("sync.cursor", None)  # the journal from its start, with this key
    return crypto.key_id(key).hex()


def join(core, text):
    """Take the account's key from another device. → its id (hex). ValueError: not one."""
    return _take(core, crypto.key_from_text(text))


def take_escrow(core, password):
    """The key out of the journal with its password. → its id. ValueError: no such
    blob in the journal; BadBlob: the password is wrong."""
    sync = core.sync
    blob = sync.find_escrow(password) if sync is not None else None
    if blob is None:
        raise ValueError("no key in the journal")
    return _take(core, crypto.escrow_open(blob, password))


def first_key(core):
    """The first device of the account: its key made now. ValueError when the journal
    holds another device's entries already (then this one joins, it doesn't start)."""
    sync = core.sync
    if sync is None:
        raise RuntimeError("sync is off")
    with sync._lock:  # the round can't make its own meanwhile
        return _first_key_locked(core, sync)


def _first_key_locked(core, sync):
    if crypto.load_key(key_path(core.paths)) is not None:
        return crypto.key_id(crypto.load_key(key_path(core.paths))).hex()
    if not crypto.available():
        raise crypto.CryptoMissing("no cryptography")
    if sync.kind() != "server":  # a server's journals are found by their keys: nothing
        backend = sync.backend()  # to look at before there is one
        if backend is None:
            raise RuntimeError(_("sync_webdav_login_first"))
        blobs, _cur, _more = backend.pull(None, sync.device)
        if [b for b in blobs if not crypto.is_escrow(b)]:
            raise ValueError("a journal is there already")
    return _take(core, crypto.new_key())


def fresh_key(core):
    """A new key for the account (the old one isn't at hand): the journal's blobs of the
    other key are let go of — they pass silently from now on. → the new key's id."""
    sync = core.sync
    left = list(core.store.kv_get("sync.left_keys") or [])
    if sync is not None and sync.kind() != "server":  # a server: a new key, a new journal
        backend = sync.backend()
        cursor = None
        for _round in range(200) if backend is not None else ():
            blobs, cursor, more = backend.pull(cursor, sync.device)
            for b in blobs:
                if not crypto.is_escrow(b):
                    try:
                        kid = crypto.blob_key_id(b).hex()
                    except crypto.BadBlob:
                        continue
                    if kid not in left:
                        left.append(kid)
            if not more:
                break
    core.store.kv_set("sync.left_keys", left[-20:])
    core.store.kv_set("sync.escrow", None)  # it held the old key
    return _take(core, crypto.new_key())
