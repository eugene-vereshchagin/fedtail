"""Per-profile SQLite state: cached statuses, lane items, read marks, drafts.

One connection shared by all threads, serialised with a lock. Every
method is a short transaction, so contention is negligible.
"""

import contextlib
import hashlib
import json
import logging
import sqlite3
import threading
import time
from datetime import UTC, datetime

log = logging.getLogger(__name__)
# the ids of the events fedtail writes into Activity itself (what I did: "I followed…"),
# never the server's: no fetch goes on from them, they count as nothing new
LOCAL_EVENT = "fedtail:"
# …and of those among them that are what I did myself: no unread number for them
MINE_EVENT = LOCAL_EVENT + "mine:"

SCHEMA_VERSION = 5
GC_CHUNK = 2000  # rows deleted, pages freed per short step of Store.gc

SCHEMA = """
CREATE TABLE IF NOT EXISTS statuses (
    id         TEXT PRIMARY KEY,
    data       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
-- an entry of a source: home/local/mine use status ids, mentions use notification ids
CREATE TABLE IF NOT EXISTS items (
    source    TEXT NOT NULL,
    item_id   TEXT NOT NULL,
    status_id TEXT NOT NULL,
    sort      TEXT NOT NULL,
    PRIMARY KEY (source, item_id)
);
CREATE INDEX IF NOT EXISTS items_sort ON items (source, sort);
CREATE TABLE IF NOT EXISTS read (
    status_id TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS missing (
    status_id TEXT PRIMARY KEY
);
CREATE TABLE IF NOT EXISTS drafts (
    key     TEXT PRIMARY KEY,
    data    TEXT NOT NULL,
    updated TEXT NOT NULL
);
-- short names for posts, like #k7q on Point. Before 0.18 a counter of this profile
-- (kept: names already given stay theirs); since, derived from the post's id
-- (short_ids: the full 8-character code, shown cut to 5 or more) — the same post has
-- the same name on every device of the account, without asking anyone
CREATE TABLE IF NOT EXISTS aliases (
    n         INTEGER PRIMARY KEY AUTOINCREMENT,
    status_id TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS short_ids (
    code      TEXT PRIMARY KEY,
    status_id TEXT NOT NULL
);
-- sync between devices (core/sync): what this device did and hasn't sent yet, and
-- when each thread's state was last set (and by which device) — the newest wins
CREATE TABLE IF NOT EXISTS sync_out (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    op  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sync_lww (
    key    TEXT PRIMARY KEY,
    at     INTEGER NOT NULL,
    device TEXT NOT NULL,
    value  TEXT NOT NULL
);
-- threads followed like on Point: new comments anywhere in them come to "Subscriptions"
CREATE TABLE IF NOT EXISTS subs (
    root_id       TEXT PRIMARY KEY,
    since         TEXT NOT NULL,     -- only comments newer than this are news
    last_activity TEXT NOT NULL,     -- quiet threads stop being checked after a while
    checked       TEXT NOT NULL DEFAULT '',
    auto          INTEGER NOT NULL DEFAULT 0
);
-- posts already known in a followed thread
CREATE TABLE IF NOT EXISTS sub_members (
    status_id TEXT PRIMARY KEY,
    root_id   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS sub_members_root ON sub_members (root_id);
-- threads the user left: automatic subscription never brings them back
CREATE TABLE IF NOT EXISTS unsubs (
    root_id TEXT PRIMARY KEY
);
-- threads muted here because the server can't (or as well): their mentions never come
CREATE TABLE IF NOT EXISTS quiet_threads (
    root_id TEXT PRIMARY KEY
);
-- posts known to be in a left or muted thread, to tell its new mentions by their parent
CREATE TABLE IF NOT EXISTS left_members (
    status_id TEXT PRIMARY KEY,
    root_id   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS left_members_root ON left_members (root_id);
-- favourites, boosts, new followers: who did what to which of my posts
CREATE TABLE IF NOT EXISTS activity (
    id         TEXT PRIMARY KEY,   -- notification id
    type       TEXT NOT NULL,
    account    TEXT NOT NULL,      -- JSON of who did it
    status_id  TEXT,
    sort       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS activity_sort ON activity (sort);
-- where a post first came into a source, as itself or boosted: a later boost of it is a
-- repeat (feed.repeat_boosts). item_id "" — it came boosted when already read.
CREATE TABLE IF NOT EXISTS first_seen (
    source  TEXT NOT NULL,
    real_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    PRIMARY KEY (source, real_id)
);
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


_B36 = "0123456789abcdefghijklmnopqrstuvwxyz"
_LETTERS = "abcdefghijklmnopqrstuvwxyz"


def alias_text(n):
    """1 → 'a00', 2 → 'a01', … 'zzz', then 'a000' …: a letter, then base-36."""
    k, length = n - 1, 3
    while k >= 26 * 36 ** (length - 1):
        k -= 26 * 36 ** (length - 1)
        length += 1
    head, rest = divmod(k, 36 ** (length - 1))
    tail = ""
    for _ in range(length - 1):
        rest, r = divmod(rest, 36)
        tail = _B36[r] + tail
    return _LETTERS[head] + tail


def alias_number(text):
    text = (text or "").lower().lstrip("#")
    if len(text) < 3 or text[0] not in _LETTERS or any(c not in _B36 for c in text):
        return None
    k = sum(26 * 36 ** (length - 1) for length in range(3, len(text)))
    v = _LETTERS.index(text[0])
    for c in text[1:]:
        v = v * 36 + _B36.index(c)
    return k + v + 1


SHORT_LEN = 5  # a derived name shows this many characters (more when two would clash)
CODE_LEN = 8   # what is kept: a letter and seven base-36 digits, 2·10¹² names


def short_code(status_id):
    """The post's derived name, full length: a letter, then base-36 digits of a hash of
    its id. Every device of an account knows a post by the same id, so by the same name.
    Its first SHORT_LEN characters are what a card shows; 5 is already longer than the
    counter's 3–4 ever reached, so old and new names never mix up."""
    v = int.from_bytes(hashlib.sha256(str(status_id).encode()).digest()[:12], "big")
    v, head = divmod(v, 26)
    tail = ""
    for _ in range(CODE_LEN - 1):
        v, r = divmod(v, 36)
        tail += _B36[r]
    return _LETTERS[head] + tail


def now_iso():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sort_key(created_at, item_id):
    """Chronological key that also works across id formats (ULID / snowflake)."""
    return f"{created_at or ''}|{str(item_id).rjust(32, '0')}"


HIDDEN_KEEP = 2000  # notifications hidden by hand, remembered
GROUPS_KEEP = 2000  # the server's notification groups: key → the row standing for it


class Store:
    def __init__(self, path):
        self.me_id = None  # set once connected: my own posts go in as read
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA journal_mode=WAL")
        # bumped on every change, so callers can cache what they derive from the store
        self.items_version = {}
        self.status_version = 0
        self.read_version = 0  # bumped by every read mark (Core caches unread counts by it)
        # every read mark, in memory: the sidebar counts every lane after each read mark
        # and asking SQLite for thousands of ids each time froze the window (413 ms on a
        # real profile); None — read from the table at the next question
        self._read = None
        self._tags = None  # {lowercase name: [name as seen, how often]}, built on demand
        self._people = None  # {lowercase acct: [acct, display name, how often]}, the same way
        # reads have a connection of their own: WAL lets them go on while a poll writes, so
        # the window asking for a lane's posts never waits for a round's transaction (the
        # freezes on the store's lock); a read inside a write stays on the writer's own
        self._rdb = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._rdb.execute("PRAGMA busy_timeout=5000")
        self._rlock = threading.RLock()
        self.db.execute("PRAGMA synchronous=NORMAL")
        # a new file frees its pages as it goes (an old one is converted in _migrate)
        self.db.execute("PRAGMA auto_vacuum=INCREMENTAL")
        with self.lock:
            self.db.executescript(SCHEMA)
            self._migrate()
        self._private(path)

    @staticmethod
    def _private(path):
        """The database holds direct messages and what was read: the owner's only, like
        auth.json — not left to the umask (0644) and the folder's 0700 alone."""
        import os
        if os.name == "nt":
            return
        for p in (str(path), f"{path}-wal", f"{path}-shm"):
            try:
                os.chmod(p, 0o600)
            except OSError:
                pass

    def _migrate(self):
        """Bring an older state.db up to date in place; never loses data."""
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(statuses)")}
        if "reply_to" not in cols:  # v2: who answers whom, for "you replied"
            self.db.execute("ALTER TABLE statuses ADD COLUMN reply_to TEXT")
            self.db.execute("ALTER TABLE statuses ADD COLUMN author TEXT")
            self.db.execute(
                "UPDATE statuses SET reply_to = json_extract(data, '$.in_reply_to_id'), "
                "author = json_extract(data, '$.account.id')")
        self.db.execute("CREATE INDEX IF NOT EXISTS statuses_reply_to ON statuses (reply_to)")
        # my own posts, found fast: my direct messages go into "Direct" (app._carry_my_direct)
        self.db.execute("CREATE INDEX IF NOT EXISTS statuses_author ON statuses (author)")
        if "touched" not in cols:  # v5: when a post was last stored, for gc()'s grace time
            self.db.execute("ALTER TABLE statuses ADD COLUMN touched TEXT NOT NULL DEFAULT ''")
            self.db.execute("UPDATE statuses SET touched=?", (now_iso(),))
        schema = self.kv_get("schema") or SCHEMA_VERSION
        if schema < 3:
            self._rename_lanes()
        if schema < 4:
            self._fill_first_seen()
        self.kv_set("schema", SCHEMA_VERSION)
        if self.db.execute("PRAGMA auto_vacuum").fetchone()[0] != 2:
            # once: an older file learns to give freed pages back (gc() → incremental_vacuum)
            log.info("store: converting to incremental vacuum (once; may take a while)")
            self.db.execute("PRAGMA auto_vacuum=INCREMENTAL")
            self.db.execute("VACUUM")

    def _fill_first_seen(self):
        """v4: for what is stored already, the oldest entry of each post in a source
        is its first coming (inserted oldest first: OR IGNORE keeps that one)."""
        self.db.execute(
            "INSERT OR IGNORE INTO first_seen (source, real_id, item_id) "
            "SELECT i.source, COALESCE(json_extract(s.data, '$.reblog.id'), s.id), i.item_id "
            "FROM items i JOIN statuses s ON s.id = i.status_id ORDER BY i.sort ASC")

    def _rename_lanes(self):
        """v3: lanes got the names they show ("people" is "home"…); what the window
        remembered about them — the lane open, the columns, the choices over a lane —
        follows them."""
        from .lanes import RENAMED, canonical
        lane = self.kv_get("ui.lane")
        if lane in RENAMED:
            self.kv_set("ui.lane", canonical(lane))
        cols = self.kv_get("ui.columns")
        if isinstance(cols, list):
            self.kv_set("ui.columns", [canonical(x) for x in cols])
        for kind in ("unread_only", "conversations", "posts_only"):
            for old, new in RENAMED.items():
                value = self.kv_get(f"ui.{kind}.{old}")
                if value is not None:
                    self.kv_set(f"ui.{kind}.{new}", value)
                    self.db.execute("DELETE FROM kv WHERE key=?", (f"ui.{kind}.{old}",))

    closed = False  # after close(): what still comes (a late event) knows to stop

    def close(self):
        with self.lock, self._rlock:
            self.closed = True
            self.db.close()
            self._rdb.close()

    def _tx(self):
        return _Tx(self)

    @contextlib.contextmanager
    def _reading(self):
        """The connection to read from: the writer's own inside its lock (its rows not
        committed yet), else the readers' — no waiting for a write going on."""
        if self.lock._is_owned():
            yield self.db
            return
        with self._rlock:
            yield self._rdb

    def diag_counts(self):
        """Row counts and the file size, for the stats line."""
        with self.lock:
            q = self.db.execute
            out = {"statuses": q("SELECT COUNT(*) FROM statuses").fetchone()[0],
                   "items": q("SELECT COUNT(*) FROM items").fetchone()[0],
                   "read": q("SELECT COUNT(*) FROM read").fetchone()[0],
                   "activity": q("SELECT COUNT(*) FROM activity").fetchone()[0],
                   "subs": q("SELECT COUNT(*) FROM subs").fetchone()[0]}
            page = q("PRAGMA page_count").fetchone()[0] * q("PRAGMA page_size").fetchone()[0]
        out["db_mb"] = round(page / 1024 / 1024, 1)
        return out

    def size_mb(self):
        """What the data takes in the file, MB (free pages not counted)."""
        with self.lock:
            q = self.db.execute
            pages = q("PRAGMA page_count").fetchone()[0] - q("PRAGMA freelist_count").fetchone()[0]
            return pages * q("PRAGMA page_size").fetchone()[0] / 1024 / 1024

    def item_sources(self):
        with self._reading() as db:
            return [r[0] for r in db.execute("SELECT DISTINCT source FROM items")]

    def gc(self, keep_activity=3000, grace_hours=48, drop_read=False):
        """Forget what nothing points at any more, so the file doesn't grow for ever.

        A post stays while a lane, a followed thread, an activity entry or a reply
        draft points at it, while it is mine, while a kept post boosts, quotes or answers
        it (up the whole thread), and for grace_hours after it was last stored (a thread
        or a profile open on screen). A post that goes is fetched again when needed.
        drop_read: also read marks of posts no longer stored (under size pressure only:
        an old post boosted again then shows as unread). Short ids are never forgotten.
        Returns {what: rows removed}."""
        cutoff = datetime.fromtimestamp(datetime.now(UTC).timestamp() - grace_hours * 3600,
                                        UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        out = {}
        with self._tx() as db:
            out["activity"] = db.execute(
                "DELETE FROM activity WHERE id NOT IN "
                "(SELECT id FROM activity ORDER BY sort DESC LIMIT ?)",
                (max(0, keep_activity),)).rowcount
            out["sub_members"] = db.execute(
                "DELETE FROM sub_members WHERE root_id NOT IN (SELECT root_id FROM subs)"
            ).rowcount
            out["left_members"] = db.execute(
                "DELETE FROM left_members WHERE root_id NOT IN (SELECT root_id FROM unsubs "
                "UNION SELECT root_id FROM quiet_threads)").rowcount
            db.execute("CREATE TEMP TABLE IF NOT EXISTS gc_keep (id TEXT PRIMARY KEY)")
            db.execute("DELETE FROM gc_keep")
            for q, args in (
                    ("SELECT status_id FROM items", ()),
                    ("SELECT status_id FROM sub_members", ()),
                    ("SELECT root_id FROM subs", ()),
                    ("SELECT status_id FROM activity WHERE status_id IS NOT NULL", ()),
                    ("SELECT substr(key, 7) FROM drafts WHERE key LIKE 'reply:%'", ()),
                    ("SELECT id FROM statuses WHERE author = ?", (self.me_id or "",)),
                    ("SELECT id FROM statuses WHERE touched >= ?", (cutoff,))):
                db.execute(f"INSERT OR IGNORE INTO gc_keep {q}", args)
            # what kept posts lead to: the boosted post, the quoted one, the parent —
            # level by level (a whole thread up), each level from the posts the last one
            # added only; each post's JSON parsed once per level (one row, five columns)
            db.execute("CREATE TEMP TABLE IF NOT EXISTS gc_front (id TEXT PRIMARY KEY)")
            db.execute("DELETE FROM gc_front")
            db.execute("INSERT INTO gc_front SELECT id FROM gc_keep")
            leads = ("WITH f AS MATERIALIZED (SELECT json_extract(s.data, '$.reblog.id', "
                     "'$.quote.quoted_status_id', '$.quote.quoted_status.id', '$.quote_id') "
                     "AS j, s.reply_to AS r FROM statuses s JOIN gc_front g ON g.id = s.id) "
                     "SELECT DISTINCT v FROM (SELECT r AS v FROM f UNION ALL "
                     "SELECT e.value FROM f, json_each(f.j) AS e) "
                     "WHERE v IS NOT NULL AND v NOT IN (SELECT id FROM gc_keep)")
            while True:
                found = [r[0] for r in db.execute(leads).fetchall()]
                if not found:
                    break
                db.execute("DELETE FROM gc_front")
                db.executemany("INSERT OR IGNORE INTO gc_front VALUES (?)", [(i,) for i in found])
                db.executemany("INSERT OR IGNORE INTO gc_keep VALUES (?)", [(i,) for i in found])
        # then away in short transactions: a first gc on a year-old file deletes
        # hundreds of MB, and the window must not wait for all of it. A post stored
        # meanwhile is newer than the cutoff, so it stays.
        out["statuses"] = 0
        while True:
            with self._tx() as db:
                n = db.execute(
                    "DELETE FROM statuses WHERE rowid IN (SELECT rowid FROM statuses "
                    "WHERE touched < ? AND id NOT IN (SELECT id FROM gc_keep) LIMIT ?)",
                    (cutoff, GC_CHUNK)).rowcount
            out["statuses"] += n
            if n < GC_CHUNK:
                break
            time.sleep(0.005)  # the lock isn't fair: let a waiting reader in between
        with self._tx() as db:
            db.execute("DELETE FROM gc_keep")
            db.execute("DELETE FROM gc_front")
            out["missing"] = db.execute(
                "DELETE FROM missing WHERE status_id NOT IN "
                "(SELECT reply_to FROM statuses WHERE reply_to IS NOT NULL)").rowcount
            out["kv"] = db.execute(
                "DELETE FROM kv WHERE key LIKE 'replies_checked:%' AND substr(key, 17) "
                "NOT IN (SELECT id FROM statuses)").rowcount
            if drop_read:
                out["read"] = db.execute(
                    "DELETE FROM read WHERE status_id NOT IN (SELECT id FROM statuses)"
                ).rowcount
                self._read = None
            if out["statuses"]:
                self.status_version += 1
            if out["activity"]:
                self._bump("activity")
        while True:  # freed pages back to the system, a slice at a time
            with self.lock:
                if not self.db.execute("PRAGMA freelist_count").fetchone()[0]:
                    break
                # one page per row stepped: fetchall(), or it frees just the first
                self.db.execute(f"PRAGMA incremental_vacuum({GC_CHUNK // 4})").fetchall()
            time.sleep(0.005)
        with self.lock:
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return out

    # ---- kv -------------------------------------------------------------------
    def kv_get(self, key, default=None):
        with self._reading() as db:
            row = db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def kv_set(self, key, value):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, json.dumps(value)))

    # ---- statuses -------------------------------------------------------------
    def put_statuses(self, statuses):
        rows = []
        touched = now_iso()
        for st in statuses:
            for s in ([st["reblog"]] if st.get("reblog") else []) + [st]:
                rows.append((s["id"], json.dumps(s), s.get("created_at", ""),
                             s.get("in_reply_to_id"), (s.get("account") or {}).get("id"),
                             touched))
        # a post of mine is read: I wrote it — from this client or any other, come by a
        # lane, a thread, a catch-up after a restart
        mine = [r[0] for r in rows if self.me_id and r[4] == self.me_id]
        with self._tx() as db:
            # the same posts as stored (a followed thread read again, a lane's overlap):
            # no new version — every lane's cache (app.lane_entries) keys on it, and
            # dropping them each round made the sidebar's counts read the store in the
            # GUI thread, waiting on the poll's lock (the night of 22.10: 0.3–0.6 s)
            old = {}
            for i in range(0, len(rows), 500):
                part = [r[0] for r in rows[i:i + 500]]
                marks = ",".join("?" * len(part))
                old.update(db.execute(f"SELECT id, data FROM statuses WHERE id IN ({marks})",
                                      part))
            changed = any(old.get(r[0]) != r[1] for r in rows)
            db.executemany("INSERT OR REPLACE INTO statuses (id, data, created_at, reply_to, "
                           "author, touched) VALUES (?, ?, ?, ?, ?, ?)", rows)
            if mine:
                db.executemany("INSERT OR IGNORE INTO read VALUES (?)", [(i,) for i in mine])
                if self._read is not None:
                    self._read.update(mine)
            if changed:
                self.status_version += 1
            if self._tags is not None:
                for st in statuses:
                    for t in (st.get("reblog") or st).get("tags") or ():
                        self._count_tag(t.get("name"))
            if self._people is not None:
                for st in statuses:
                    self._count_people(st.get("reblog") or st)

    def _count_tag(self, name):
        if not name:
            return
        seen = self._tags.setdefault(name.casefold(), [name, 0])
        seen[1] += 1
        if seen[0] == seen[0].lower() and name != name.lower():
            seen[0] = name  # #GeorgiaNews over #georgianews when somebody wrote it so

    def _count_people(self, s):
        acc = s.get("account") or {}
        self._count_person(acc.get("acct"), acc.get("display_name"))
        for m in s.get("mentions") or ():
            self._count_person(m.get("acct"), None)

    def _count_person(self, acct, name):
        if not acct:
            return
        seen = self._people.setdefault(acct.casefold(), [acct, "", 0])
        seen[2] += 1
        if name:
            seen[1] = name

    def people_counts(self, compute=True):
        """Who posts and who gets mentioned in the stored posts, how often — for
        completing @names while writing. Built once, then kept up to date."""
        with self.lock:
            if self._people is None and compute:
                self._people = {}
                q = ("SELECT json_extract(data, '$.account.acct'), "
                     "json_extract(data, '$.account.display_name'), "
                     "json_extract(data, '$.mentions') FROM statuses")
                for acct, name, mentions in self.db.execute(q):
                    self._count_person(acct, name)
                    for m in json.loads(mentions or "[]") or ():
                        self._count_person(m.get("acct"), None)
            return self._people

    def tag_counts(self, compute=True):
        """Hashtags of every stored post, how often each is used — for completing
        a tag while writing. Built once (one pass over the store), then kept up
        to date as posts come. compute=False: None until it's built."""
        with self.lock:
            if self._tags is None and compute:
                self._tags = {}
                q = ("SELECT json_extract(t.value, '$.name') FROM statuses, "
                     "json_each(statuses.data, '$.tags') AS t")
                for (name,) in self.db.execute(q):
                    self._count_tag(name)
            return self._tags

    def get_status(self, sid):
        with self._reading() as db:
            row = db.execute("SELECT data FROM statuses WHERE id=?", (sid,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_statuses(self, ids):
        ids = list(ids)
        out = {}
        with self._reading() as db:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                marks = ",".join("?" * len(chunk))
                q = f"SELECT id, data FROM statuses WHERE id IN ({marks})"
                out.update({r[0]: json.loads(r[1]) for r in db.execute(q, chunk)})
        return out

    def delete_status(self, sid):
        with self._tx() as db:
            db.execute("DELETE FROM statuses WHERE id=?", (sid,))
            db.execute("DELETE FROM items WHERE status_id=?", (sid,))
            self.status_version += 1

    def mark_missing(self, sid):
        with self.lock:
            self.db.execute("INSERT OR IGNORE INTO missing VALUES (?)", (sid,))

    def replies_by(self, parent_ids, author_id):
        """{parent id: [replies by author, oldest first]}"""
        ids = list(parent_ids)
        out = {}
        with self._reading() as db:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                marks = ",".join("?" * len(chunk))
                q = (f"SELECT reply_to, data FROM statuses WHERE reply_to IN ({marks}) "
                     f"AND author = ? ORDER BY created_at")
                for pid, data in db.execute(q, chunk + [author_id]):
                    out.setdefault(pid, []).append(json.loads(data))
        return out

    def aliases(self, status_ids):
        """{status id: short alias}. A post named by the old counter keeps that name;
        any other gets its derived one (short_code), remembered so it can be looked up
        — cut to SHORT_LEN, or longer while another known post shares the beginning."""
        ids = list(dict.fromkeys(status_ids))
        out = {}
        with self._tx() as db:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                marks = ",".join("?" * len(chunk))
                for sid, n in db.execute(
                        f"SELECT status_id, n FROM aliases WHERE status_id IN ({marks})", chunk):
                    out[sid] = alias_text(n)
            codes = {sid: short_code(sid) for sid in ids if sid not in out}
            db.executemany("INSERT OR IGNORE INTO short_ids VALUES (?, ?)",
                           [(c, sid) for sid, c in codes.items()])
            for sid, code in codes.items():
                n = SHORT_LEN
                while n < CODE_LEN and db.execute(
                        "SELECT COUNT(*) FROM short_ids WHERE code >= ? AND code < ?",
                        (code[:n], code[:n] + "~")).fetchone()[0] > 1:
                    n += 1
                out[sid] = code[:n]
        return out

    def by_alias(self, alias):
        """The post behind a name: an old counter name (3–4 characters) or the beginning
        of a derived one (5 and more). Where a beginning fits several posts, the newest
        stored one — the card itself shows them longer."""
        text = (alias or "").lower().lstrip("#")
        if len(text) < SHORT_LEN:
            n = alias_number(text)
            if n is None:
                return None
            with self._reading() as db:
                row = db.execute("SELECT status_id FROM aliases WHERE n=?", (n,)).fetchone()
            return row[0] if row else None
        if len(text) > CODE_LEN or any(c not in _B36 for c in text):
            return None
        with self._reading() as db:
            row = db.execute(
                "SELECT k.status_id FROM short_ids k LEFT JOIN statuses s ON s.id = k.status_id "
                "WHERE k.code >= ? AND k.code < ? ORDER BY s.created_at DESC LIMIT 1",
                (text, text + "~")).fetchone()
        return row[0] if row else None

    def missing_set(self, ids):
        ids = list(ids)
        out = set()
        with self._reading() as db:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                marks = ",".join("?" * len(chunk))
                q = f"SELECT status_id FROM missing WHERE status_id IN ({marks})"
                out.update(r[0] for r in db.execute(q, chunk))
        return out

    def is_missing(self, sid):
        with self._reading() as db:
            return db.execute("SELECT 1 FROM missing WHERE status_id=?",
                                   (sid,)).fetchone() is not None

    # ---- source items ---------------------------------------------------------
    def put_items(self, source, entries):
        """entries: [(item_id, status, created_at)]. Returns ids that were new."""
        if not entries:
            return []
        self.put_statuses([st for _, st, _ in entries])
        new = []
        with self._tx() as db:
            # oldest first: where a post came in first is where it stays
            for item_id, st, created in sorted(entries, key=lambda e: sort_key(e[2], e[0])):
                cur = db.execute("INSERT OR IGNORE INTO items VALUES (?, ?, ?, ?)",
                                 (source, item_id, st["id"], sort_key(created, item_id)))
                if cur.rowcount:
                    new.append(item_id)
                self._first_seen(db, source, item_id, st)
            if new:
                self._bump(source)
        return new

    @staticmethod
    def _first_seen(db, source, item_id, st):
        real_id = (st.get("reblog") or st)["id"]
        if st.get("reblog") and db.execute("SELECT 1 FROM read WHERE status_id=?",
                                           (real_id,)).fetchone():
            item_id = ""  # read already (in a thread, another lane): a boost brings it again
        db.execute("INSERT OR IGNORE INTO first_seen VALUES (?, ?, ?)",
                   (source, real_id, item_id))

    def first_seen(self, source, real_ids):
        """{real id: the item it first came as in this source ("" — read already)}."""
        ids = list(dict.fromkeys(real_ids))
        out = {}
        with self._reading() as db:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                q = (f"SELECT real_id, item_id FROM first_seen WHERE source=? AND real_id IN "
                     f"({','.join('?' * len(chunk))})")
                out.update(db.execute(q, [source, *chunk]).fetchall())
        return out

    def _bump(self, source):
        self.items_version[source] = self.items_version.get(source, 0) + 1

    # items put in by fedtail itself (my direct messages in the mentions stream: "mine:"
    # + the post's id) are no place in the server's list to page from
    LOCAL_ITEM = "mine:%"

    def newest_item(self, source):
        """The server's id to ask for newer ones from (None — nothing of its yet)."""
        with self._reading() as db:
            row = db.execute("SELECT item_id FROM items WHERE source=? "
                                  "AND item_id NOT LIKE ? ORDER BY sort DESC LIMIT 1",
                                  (source, self.LOCAL_ITEM)).fetchone()
        return row[0] if row else None

    def oldest_item(self, source):
        with self._reading() as db:
            row = db.execute("SELECT item_id FROM items WHERE source=? "
                                  "AND item_id NOT LIKE ? ORDER BY sort ASC LIMIT 1",
                                  (source, self.LOCAL_ITEM)).fetchone()
        return row[0] if row else None

    def threads_with_news(self):
        """Roots of followed threads with an unread reply in them (the Subscriptions
        stream): for "threads with news"."""
        with self._reading() as db:
            return {r[0] for r in db.execute(
                "SELECT DISTINCT m.root_id FROM items i JOIN sub_members m "
                "ON m.status_id = i.status_id WHERE i.source = 'subs' "
                "AND i.status_id NOT IN (SELECT status_id FROM read)")}

    def held_in(self, sources, status_ids):
        """Which of these statuses one of these streams holds."""
        ids, sources = list(dict.fromkeys(status_ids)), sorted(set(sources))
        if not ids or not sources:
            return set()
        out = set()
        with self._reading() as db:
            for i in range(0, len(ids), 400):
                part = ids[i:i + 400]
                out |= {r[0] for r in db.execute(
                    f"SELECT DISTINCT status_id FROM items WHERE source IN "
                    f"({','.join('?' * len(sources))}) AND status_id IN "
                    f"({','.join('?' * len(part))})", [*sources, *part])}
        return out

    def drop_held(self, source, others):
        """Take out of `source` what one of `others` holds (Unsorted, once a lane has it)."""
        others = sorted(set(others) - {source})
        if not others:
            return 0
        with self._tx() as db:
            cur = db.execute(
                f"DELETE FROM items WHERE source=? AND status_id IN (SELECT status_id FROM "
                f"items WHERE source IN ({','.join('?' * len(others))}))", [source, *others])
            if cur.rowcount:
                self._bump(source)
            return cur.rowcount

    def held_by(self, prefix, status_ids):
        """Which of these statuses some stream whose name starts with `prefix` holds."""
        ids = list(dict.fromkeys(status_ids))
        if not ids:
            return set()
        out = set()
        with self._reading() as db:
            for i in range(0, len(ids), 500):
                part = ids[i:i + 500]
                marks = ",".join("?" * len(part))
                out |= {r[0] for r in db.execute(
                    f"SELECT DISTINCT status_id FROM items WHERE source LIKE ? "
                    f"AND status_id IN ({marks})", [prefix + "%", *part])}
        return out

    def count_items(self, source):
        with self._reading() as db:
            return db.execute("SELECT COUNT(*) FROM items WHERE source=?",
                                   (source,)).fetchone()[0]

    def iter_items(self, source, chunk=200, max_rows=None):
        """Items newest → oldest, parsed lazily chunk by chunk. Each chunk starts where
        the last one ended (sort, item_id), not at an OFFSET: going deep into a big
        source stays linear instead of re-walking everything before each chunk."""
        done, last = 0, None
        base = ("SELECT i.item_id, s.data, i.sort FROM items i JOIN statuses s "
                "ON s.id = i.status_id WHERE i.source=? ")
        order = "ORDER BY i.sort DESC, i.item_id DESC LIMIT ?"
        while max_rows is None or done < max_rows:
            with self._reading() as db:
                if last is None:
                    rows = db.execute(base + order, (source, chunk)).fetchall()
                else:
                    rows = db.execute(base + "AND (i.sort, i.item_id) < (?, ?) " + order,
                                           (source, last[0], last[1], chunk)).fetchall()
            for r in rows:
                yield r[0], json.loads(r[1])
            if len(rows) < chunk:
                return
            done += chunk
            last = (rows[-1][2], rows[-1][0])

    def items(self, source, limit):
        """Newest `limit` items of a source, returned oldest → newest."""
        with self._reading() as db:
            rows = db.execute(
                "SELECT i.item_id, s.data FROM items i JOIN statuses s ON s.id = i.status_id "
                "WHERE i.source=? ORDER BY i.sort DESC LIMIT ?", (source, limit)).fetchall()
        return [(r[0], json.loads(r[1])) for r in reversed(rows)]

    def prune(self, source, keep):
        with self._tx() as db:
            cur = db.execute(
                "DELETE FROM items WHERE source=? AND item_id NOT IN "
                "(SELECT item_id FROM items WHERE source=? ORDER BY sort DESC LIMIT ?)",
                (source, source, keep))
            if cur.rowcount:
                self._bump(source)
            # what came is remembered far longer than the lane is kept: an old post
            # boosted again a month later is still a repeat
            db.execute("DELETE FROM first_seen WHERE source=? AND rowid NOT IN "
                       "(SELECT rowid FROM first_seen WHERE source=? "
                       "ORDER BY rowid DESC LIMIT ?)", (source, source, keep * 10))

    # ---- thread subscriptions ----------------------------------------------------
    def sub_add(self, root_id, since, last_activity, auto, members):
        with self._tx() as db:
            if not auto:
                db.execute("DELETE FROM unsubs WHERE root_id=?", (root_id,))
                db.execute("DELETE FROM quiet_threads WHERE root_id=?", (root_id,))
                db.execute("DELETE FROM left_members WHERE root_id=?", (root_id,))
            db.execute("INSERT OR IGNORE INTO subs (root_id, since, last_activity, checked, auto)"
                       " VALUES (?, ?, ?, '', ?)", (root_id, since, last_activity, int(auto)))
            db.executemany("INSERT OR IGNORE INTO sub_members VALUES (?, ?)",
                           [(m, root_id) for m in members])

    def sub_remove(self, root_id, remember=True, members=()):
        """Leave a thread: its comments vanish from the lane, and (remember)
        automatic subscription won't come back to it; its posts (those followed and
        `members`) are kept as the left thread's, to know its later mentions."""
        with self._tx() as db:
            if remember:
                db.execute("INSERT OR REPLACE INTO left_members SELECT status_id, root_id "
                           "FROM sub_members WHERE root_id=?", (root_id,))
                db.executemany("INSERT OR REPLACE INTO left_members VALUES (?, ?)",
                               [(m, root_id) for m in {root_id, *members}])
            cur = db.execute("DELETE FROM items WHERE source='subs' AND status_id IN "
                             "(SELECT status_id FROM sub_members WHERE root_id=?)", (root_id,))
            if cur.rowcount:
                self._bump("subs")
            db.execute("DELETE FROM sub_members WHERE root_id=?", (root_id,))
            db.execute("DELETE FROM subs WHERE root_id=?", (root_id,))
            if remember:
                db.execute("INSERT OR IGNORE INTO unsubs VALUES (?)", (root_id,))

    def sub_root_of(self, status_id):
        """The followed thread a post belongs to, or None."""
        with self._reading() as db:
            row = db.execute("SELECT root_id FROM subs WHERE root_id=?",
                                  (status_id,)).fetchone() or \
                db.execute("SELECT m.root_id FROM sub_members m JOIN subs s "
                                "ON s.root_id = m.root_id WHERE m.status_id=?",
                                (status_id,)).fetchone()
        return row[0] if row else None

    def quiet_set(self, root_id, on=True):
        """Mute a thread here (its mentions are dropped), or let it speak again."""
        with self._tx() as db:
            if on:
                db.execute("INSERT OR IGNORE INTO quiet_threads VALUES (?)", (root_id,))
            else:
                db.execute("DELETE FROM quiet_threads WHERE root_id=?", (root_id,))

    def quiet_roots(self, left_too=False):
        """Roots of threads whose mentions don't come: muted here, and (left_too) left."""
        q = "SELECT root_id FROM quiet_threads"
        if left_too:
            q += " UNION SELECT root_id FROM unsubs"
        with self._reading() as db:
            return {r[0] for r in db.execute(q)}

    def left_root_of(self, status_ids):
        """The left or muted thread one of these posts is known to be in, or None."""
        ids = [i for i in status_ids if i]
        if not ids:
            return None
        marks = ",".join("?" * len(ids))
        with self._reading() as db:
            row = db.execute(
                f"SELECT root_id FROM left_members WHERE status_id IN ({marks})", ids
            ).fetchone()
        return row[0] if row else None

    def left_add(self, root_id, status_ids):
        with self._tx() as db:
            db.executemany("INSERT OR REPLACE INTO left_members VALUES (?, ?)",
                           [(i, root_id) for i in status_ids if i])

    def drop_items_by(self, source, author_id):
        """Take someone's posts and boosts out of a lane's source (Home, after I stop
        following them: the server's Home forgets them too). → how many went."""
        with self._tx() as db:
            cur = db.execute("DELETE FROM items WHERE source=? AND status_id IN "
                             "(SELECT id FROM statuses WHERE author=?)", (source, author_id))
            if cur.rowcount:
                self._bump(source)
            return cur.rowcount

    def authors_in(self, source, limit=2000):
        """Whose posts (or boosts) a source holds, the freshest first."""
        with self._reading() as db:
            return [r[0] for r in db.execute(
                "SELECT s.author FROM items i JOIN statuses s ON s.id = i.status_id "
                "WHERE i.source = ? AND s.author IS NOT NULL GROUP BY s.author "
                "ORDER BY MAX(i.sort) DESC LIMIT ?", (source, limit))]

    def drop_items_of_thread(self, source, root_id):
        """Take a muted thread's posts out of a lane (mentions: they came before)."""
        with self._tx() as db:
            cur = db.execute("DELETE FROM items WHERE source=? AND status_id IN "
                             "(SELECT status_id FROM left_members WHERE root_id=?)",
                             (source, root_id))
            if cur.rowcount:
                self._bump(source)
            return cur.rowcount

    def sub_left(self, root_id):
        with self._reading() as db:
            return db.execute("SELECT 1 FROM unsubs WHERE root_id=?",
                                   (root_id,)).fetchone() is not None

    def subs_due(self, active_after, checked_before, limit):
        """Followed threads to look at now: alive lately, longest unchecked first."""
        with self._reading() as db:
            rows = db.execute(
                "SELECT root_id, since, last_activity, checked FROM subs WHERE last_activity > ? "
                "AND checked < ? ORDER BY checked ASC LIMIT ?",
                (active_after, checked_before, limit)).fetchall()
        return rows

    def sub_members(self, root_id):
        with self._reading() as db:
            return {r[0] for r in db.execute(
                "SELECT status_id FROM sub_members WHERE root_id=?", (root_id,))}

    def sub_checked(self, root_id, checked, last_activity, members):
        with self._tx() as db:
            db.execute("UPDATE subs SET checked=?, last_activity=MAX(last_activity, ?) "
                       "WHERE root_id=?", (checked, last_activity, root_id))
            db.executemany("INSERT OR IGNORE INTO sub_members VALUES (?, ?)",
                           [(m, root_id) for m in members])

    def subs_count(self):
        with self._reading() as db:
            return db.execute("SELECT COUNT(*) FROM subs").fetchone()[0]

    # ---- activity (favourites, boosts, follows) ------------------------------------
    def activity_put(self, notifications):
        """Returns the notifications that were new."""
        sts = [n["status"] for n in notifications if n.get("status")]
        if sts:
            self.put_statuses(sts)
        new = []
        hidden = self.kv_get("activity_hidden", {}) or {}
        hidden_groups = self.kv_get("activity_hidden_groups", {}) or {}
        groups = self.kv_get("activity_groups", {}) or {}
        groups_before = dict(groups)
        with self._tx() as db:
            for n in notifications:
                if n["id"] in hidden:  # hidden here by hand: it stays hidden
                    continue
                group = n.get("_group")
                key = (group or {}).get("key") or ""
                if key and key in hidden_groups:  # …and so does a hidden group
                    continue
                acc = n.get("account") or {}
                if group:
                    # the server's group: one row, the newest; the row it had before goes
                    acc = dict(acc, _group=group)
                    old = groups.get(key)
                    if old and old != n["id"]:
                        db.execute("DELETE FROM activity WHERE id = ?", (old,))
                    if key:
                        groups[key] = n["id"]
                # the server's own notices carry their details: kept with the account
                notice = n.get("event") or n.get("relationship_severance_event") or \
                    n.get("moderation_warning")
                if notice:
                    acc = dict(acc, _notice=notice)
                cur = db.execute(
                    "INSERT OR IGNORE INTO activity VALUES (?, ?, ?, ?, ?)",
                    (n["id"], n["type"], json.dumps(acc),
                     (n.get("status") or {}).get("id"), sort_key(n.get("created_at"), n["id"])))
                if cur.rowcount:
                    new.append(n)
            if new:
                self._bump("activity")
        if groups != groups_before:
            if len(groups) > GROUPS_KEEP:  # the oldest groups are long gone from the screen
                groups = dict(list(groups.items())[-GROUPS_KEEP:])
            self.kv_set("activity_groups", groups)
        return new

    def activity_group_of(self, nid):
        """The server's group key of this Activity row, or "" (not a group)."""
        with self._reading() as db:
            row = db.execute("SELECT account FROM activity WHERE id = ?",
                                  (nid,)).fetchone()
        if not row:
            return ""
        try:
            return ((json.loads(row[0]) or {}).get("_group") or {}).get("key") or ""
        except (ValueError, AttributeError):
            return ""

    def activity_delete(self, ids=None):
        """Some notifications gone from Activity (ids), or all of them (None)."""
        with self._tx() as db:
            if ids is None:
                db.execute("DELETE FROM activity")
                db.execute("DELETE FROM kv WHERE key = 'activity_groups'")
            else:
                db.executemany("DELETE FROM activity WHERE id = ?", [(i,) for i in ids])
            self._bump("activity")

    def activity_hide(self, ids):
        """Notifications gone from Activity for good, while the server keeps them (it can't
        dismiss one): remembered, so the next fetch doesn't bring them back.
        → [(id, sort, group key or "")] of the ones that were here (for sync)."""
        with self._reading() as db:
            rows = db.execute(
                f"SELECT id, sort FROM activity WHERE id IN ({','.join('?' * len(ids))})",
                list(ids)).fetchall() if ids else []
        hidden = self.kv_get("activity_hidden", {}) or {}
        hidden.update(dict(rows))
        # a server's group comes back under a new id with its next notification: hidden
        # by its key too
        keys = {k: sort for k, sort in ((self.activity_group_of(i), sort) for i, sort in rows)
                if k}
        if keys:
            hg = self.kv_get("activity_hidden_groups", {}) or {}
            hg.update(keys)
            if len(hg) > HIDDEN_KEEP:
                hg = dict(sorted(hg.items(), key=lambda kv: kv[1])[-HIDDEN_KEEP:])
            self.kv_set("activity_hidden_groups", hg)
        if len(hidden) > HIDDEN_KEEP:  # the oldest go: the server won't send them again
            hidden = dict(sorted(hidden.items(), key=lambda kv: kv[1])[-HIDDEN_KEEP:])
        self.kv_set("activity_hidden", hidden)
        groups = {i: self.activity_group_of(i) for i, _sort in rows}
        self.activity_delete(ids)
        return [(i, sort, groups.get(i, "")) for i, sort in rows]

    def activity_hide_known(self, items):
        """Notifications another device dismissed (core/sync): [(id, sort, group key)] —
        remembered as hidden here too, and gone from Activity if they are in it.
        → whether anything was here to go."""
        if not items:
            return False
        hidden = self.kv_get("activity_hidden", {}) or {}
        hg = self.kv_get("activity_hidden_groups", {}) or {}
        keys = set()
        for nid, sort, key in items:
            hidden[nid] = max(hidden.get(nid, ""), sort)
            if key:
                hg[key] = max(hg.get(key, ""), sort)
                keys.add(key)
        if len(hidden) > HIDDEN_KEEP:
            hidden = dict(sorted(hidden.items(), key=lambda kv: kv[1])[-HIDDEN_KEEP:])
        if len(hg) > HIDDEN_KEEP:
            hg = dict(sorted(hg.items(), key=lambda kv: kv[1])[-HIDDEN_KEEP:])
        self.kv_set("activity_hidden", hidden)
        self.kv_set("activity_hidden_groups", hg)
        ids = {nid for nid, _s, _k in items}
        with self._reading() as db:
            rows = db.execute("SELECT id, account FROM activity").fetchall()
        gone = []
        for nid, acc in rows:
            if nid in ids:
                gone.append(nid)
            elif keys:
                try:
                    k = ((json.loads(acc) or {}).get("_group") or {}).get("key")
                except (ValueError, AttributeError):
                    k = None
                if k in keys:
                    gone.append(nid)
        if gone:
            self.activity_delete(gone)
        return bool(gone)

    def activity_newest(self, server=False):
        """(id, sort) of the newest notification fetched — hidden ones count: the next
        fetch goes on from there. server: the server's own only — not the events fedtail
        writes itself (LOCAL_EVENT ids: "I followed…"), no cursor for the server."""
        where = f"WHERE id NOT LIKE '{LOCAL_EVENT}%' " if server else ""
        with self._reading() as db:
            row = db.execute(f"SELECT id, sort FROM activity {where}ORDER BY sort DESC "
                             "LIMIT 1").fetchone()
        best = (row[0], row[1]) if row else (None, "")
        for nid, sort in (self.kv_get("activity_hidden", {}) or {}).items():
            if sort > best[1] and not (server and str(nid).startswith(LOCAL_EVENT)):
                best = (nid, sort)
        return best

    def activity_recent(self, limit):
        """Newest first: [{id, type, account, status, created_at, sort}]."""
        with self._reading() as db:
            rows = db.execute(
                "SELECT a.id, a.type, a.account, s.data, a.sort FROM activity a LEFT JOIN "
                "statuses s ON s.id = a.status_id ORDER BY a.sort DESC LIMIT ?",
                (limit,)).fetchall()
        return [{"id": r[0], "type": r[1], "account": json.loads(r[2]),
                 "status": json.loads(r[3]) if r[3] else None, "sort": r[4],
                 "created_at": r[4].split("|")[0]} for r in rows]

    def activity_count_after(self, sort):
        """Notifications after this sort — what I did myself (MINE_EVENT) isn't news."""
        with self._reading() as db:
            return db.execute("SELECT COUNT(*) FROM activity WHERE sort > ? AND id NOT LIKE ?",
                              (sort, MINE_EVENT + "%")).fetchone()[0]

    # ---- read marks -----------------------------------------------------------
    def mark_read(self, status_ids):
        with self._tx() as db:
            ids = list(status_ids)
            db.executemany("INSERT OR IGNORE INTO read VALUES (?)", [(i,) for i in ids])
            if self._read is not None:
                self._read.update(ids)
            self.read_version += 1

    def my_direct_outside(self, source, limit=200):
        """My direct messages stored (however they came: sent from here, a thread, my
        posts, a conversation) that the source has no item of yet: [status], newest
        first."""
        if not self.me_id:
            return []
        with self._reading() as db:
            rows = db.execute(
                "SELECT data FROM statuses s WHERE s.author = ? "
                "AND json_extract(s.data, '$.visibility') = 'direct' "
                "AND NOT EXISTS (SELECT 1 FROM items i WHERE i.source = ? "
                "AND i.status_id = s.id) ORDER BY s.created_at DESC LIMIT ?",
                (self.me_id, source, limit)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def mark_mine_read(self):
        """Every stored post of mine read (ones stored before this rule). How many."""
        if not self.me_id:
            return 0
        with self._tx() as db:
            cur = db.execute("INSERT OR IGNORE INTO read SELECT id FROM statuses "
                             "WHERE author = ?", (self.me_id,))
            self._read = None
            self.read_version += 1
            return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

    def account_of(self, acc_id):
        """Someone's account as one of their stored posts has it (None: no post of
        theirs here)."""
        with self._reading() as db:
            row = db.execute("SELECT data FROM statuses WHERE author=? LIMIT 1",
                                  (acc_id,)).fetchone()
        return json.loads(row[0]).get("account") if row else None

    def read_set(self, status_ids):
        """Which of these posts are read (from memory: the table once a run)."""
        with self.lock:
            if self._read is None:
                self._read = {r[0] for r in self.db.execute("SELECT status_id FROM read")}
            known = self._read
            return {i for i in status_ids if i in known}

    # ---- drafts ---------------------------------------------------------------
    def save_draft(self, key, data):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO drafts VALUES (?, ?, ?)",
                            (key, json.dumps(data), now_iso()))

    def get_draft(self, key):
        with self._reading() as db:
            row = db.execute("SELECT data FROM drafts WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def delete_draft(self, key):
        with self.lock:
            self.db.execute("DELETE FROM drafts WHERE key=?", (key,))

    def list_drafts(self):
        with self._reading() as db:
            rows = db.execute("SELECT key, data, updated FROM drafts "
                                   "ORDER BY updated DESC").fetchall()
        return [(k, json.loads(d), u) for k, d, u in rows]

    # ---- sync between devices (core/sync) ------------------------------------------
    def sync_record(self, op):
        """One thing this device did, to be sent to the others."""
        with self.lock:
            self.db.execute("INSERT INTO sync_out (op) VALUES (?)",
                            (json.dumps(op, separators=(",", ":")),))

    def sync_pending(self, limit=500):
        """[(seq, op)] not sent yet, oldest first."""
        with self._reading() as db:
            rows = db.execute("SELECT seq, op FROM sync_out ORDER BY seq LIMIT ?",
                                   (limit,)).fetchall()
        return [(seq, json.loads(op)) for seq, op in rows]

    def sync_sent(self, upto):
        with self.lock:
            self.db.execute("DELETE FROM sync_out WHERE seq <= ?", (upto,))

    def sync_pending_count(self):
        with self._reading() as db:
            return db.execute("SELECT COUNT(*) FROM sync_out").fetchone()[0]

    def sync_newer(self, key, at, device, value):
        """Last-writer-wins: keep (at, device, value) under `key` if it is newer than
        what is there. True when it was (the caller then applies `value`)."""
        with self._tx() as db:
            row = db.execute("SELECT at, device FROM sync_lww WHERE key=?", (key,)).fetchone()
            if row and (row[0], row[1]) >= (at, device):
                return False
            db.execute("INSERT OR REPLACE INTO sync_lww VALUES (?, ?, ?, ?)",
                       (key, at, device, value))
            return True


class _Tx:
    def __init__(self, store):
        self.store = store

    def __enter__(self):
        self.store.lock.acquire()
        try:
            self.store.db.execute("BEGIN")
        except BaseException:
            self.store.lock.release()  # never leave the lock held on a failed BEGIN
            raise
        return self.store.db

    def __exit__(self, exc_type, *_):
        try:
            self.store.db.execute("ROLLBACK" if exc_type else "COMMIT")
        finally:
            self.store.lock.release()
