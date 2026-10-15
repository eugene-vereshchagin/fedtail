"""Per-profile SQLite state: cached statuses, lane items, read marks, drafts.

One connection shared by all threads, serialised with a lock. Every
method is a short transaction, so contention is negligible.
"""

import json
import sqlite3
import threading
from datetime import UTC, datetime

SCHEMA_VERSION = 2

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
-- short local names for posts, like #k7q on Point: stable, never reused
CREATE TABLE IF NOT EXISTS aliases (
    n         INTEGER PRIMARY KEY AUTOINCREMENT,
    status_id TEXT NOT NULL UNIQUE
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


def now_iso():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sort_key(created_at, item_id):
    """Chronological key that also works across id formats (ULID / snowflake)."""
    return f"{created_at or ''}|{str(item_id).rjust(32, '0')}"


class Store:
    def __init__(self, path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA journal_mode=WAL")
        # bumped on every change, so callers can cache what they derive from the store
        self.items_version = {}
        self.status_version = 0
        self.db.execute("PRAGMA synchronous=NORMAL")
        with self.lock:
            self.db.executescript(SCHEMA)
            self._migrate()

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
        self.kv_set("schema", SCHEMA_VERSION)

    def close(self):
        with self.lock:
            self.db.close()

    def _tx(self):
        return _Tx(self)

    # ---- kv -------------------------------------------------------------------
    def kv_get(self, key, default=None):
        with self.lock:
            row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def kv_set(self, key, value):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO kv VALUES (?, ?)", (key, json.dumps(value)))

    # ---- statuses -------------------------------------------------------------
    def put_statuses(self, statuses):
        rows = []
        for st in statuses:
            for s in ([st["reblog"]] if st.get("reblog") else []) + [st]:
                rows.append((s["id"], json.dumps(s), s.get("created_at", ""),
                             s.get("in_reply_to_id"), (s.get("account") or {}).get("id")))
        with self._tx() as db:
            db.executemany("INSERT OR REPLACE INTO statuses (id, data, created_at, reply_to, "
                           "author) VALUES (?, ?, ?, ?, ?)", rows)
            self.status_version += 1

    def get_status(self, sid):
        with self.lock:
            row = self.db.execute("SELECT data FROM statuses WHERE id=?", (sid,)).fetchone()
        return json.loads(row[0]) if row else None

    def get_statuses(self, ids):
        ids = list(ids)
        out = {}
        with self.lock:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                marks = ",".join("?" * len(chunk))
                q = f"SELECT id, data FROM statuses WHERE id IN ({marks})"
                out.update({r[0]: json.loads(r[1]) for r in self.db.execute(q, chunk)})
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
        with self.lock:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                marks = ",".join("?" * len(chunk))
                q = (f"SELECT reply_to, data FROM statuses WHERE reply_to IN ({marks}) "
                     f"AND author = ? ORDER BY created_at")
                for pid, data in self.db.execute(q, chunk + [author_id]):
                    out.setdefault(pid, []).append(json.loads(data))
        return out

    def aliases(self, status_ids):
        """{status id: short alias}, giving new ones to ids that have none yet."""
        ids = list(dict.fromkeys(status_ids))
        out = {}
        with self._tx() as db:
            db.executemany("INSERT OR IGNORE INTO aliases (status_id) VALUES (?)",
                           [(i,) for i in ids])
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                marks = ",".join("?" * len(chunk))
                for sid, n in db.execute(
                        f"SELECT status_id, n FROM aliases WHERE status_id IN ({marks})", chunk):
                    out[sid] = alias_text(n)
        return out

    def by_alias(self, alias):
        n = alias_number(alias)
        if n is None:
            return None
        with self.lock:
            row = self.db.execute("SELECT status_id FROM aliases WHERE n=?", (n,)).fetchone()
        return row[0] if row else None

    def missing_set(self, ids):
        ids = list(ids)
        out = set()
        with self.lock:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                marks = ",".join("?" * len(chunk))
                q = f"SELECT status_id FROM missing WHERE status_id IN ({marks})"
                out.update(r[0] for r in self.db.execute(q, chunk))
        return out

    def is_missing(self, sid):
        with self.lock:
            return self.db.execute("SELECT 1 FROM missing WHERE status_id=?",
                                   (sid,)).fetchone() is not None

    # ---- source items ---------------------------------------------------------
    def put_items(self, source, entries):
        """entries: [(item_id, status, created_at)]. Returns ids that were new."""
        if not entries:
            return []
        self.put_statuses([st for _, st, _ in entries])
        new = []
        with self._tx() as db:
            for item_id, st, created in entries:
                cur = db.execute("INSERT OR IGNORE INTO items VALUES (?, ?, ?, ?)",
                                 (source, item_id, st["id"], sort_key(created, item_id)))
                if cur.rowcount:
                    new.append(item_id)
            if new:
                self._bump(source)
        return new

    def _bump(self, source):
        self.items_version[source] = self.items_version.get(source, 0) + 1

    def newest_item(self, source):
        with self.lock:
            row = self.db.execute("SELECT item_id FROM items WHERE source=? "
                                  "ORDER BY sort DESC LIMIT 1", (source,)).fetchone()
        return row[0] if row else None

    def oldest_item(self, source):
        with self.lock:
            row = self.db.execute("SELECT item_id FROM items WHERE source=? "
                                  "ORDER BY sort ASC LIMIT 1", (source,)).fetchone()
        return row[0] if row else None

    def count_items(self, source):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM items WHERE source=?",
                                   (source,)).fetchone()[0]

    def iter_items(self, source, chunk=200, max_rows=None):
        """Items newest → oldest, parsed lazily chunk by chunk."""
        offset = 0
        while max_rows is None or offset < max_rows:
            with self.lock:
                rows = self.db.execute(
                    "SELECT i.item_id, s.data FROM items i JOIN statuses s "
                    "ON s.id = i.status_id WHERE i.source=? ORDER BY i.sort DESC "
                    "LIMIT ? OFFSET ?", (source, chunk, offset)).fetchall()
            for r in rows:
                yield r[0], json.loads(r[1])
            if len(rows) < chunk:
                return
            offset += chunk

    def items(self, source, limit):
        """Newest `limit` items of a source, returned oldest → newest."""
        with self.lock:
            rows = self.db.execute(
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

    # ---- read marks -----------------------------------------------------------
    def mark_read(self, status_ids):
        with self._tx() as db:
            db.executemany("INSERT OR IGNORE INTO read VALUES (?)", [(i,) for i in status_ids])

    def read_set(self, status_ids):
        ids = list(status_ids)
        out = set()
        with self.lock:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                marks = ",".join("?" * len(chunk))
                q = f"SELECT status_id FROM read WHERE status_id IN ({marks})"
                out.update(r[0] for r in self.db.execute(q, chunk))
        return out

    # ---- drafts ---------------------------------------------------------------
    def save_draft(self, key, data):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO drafts VALUES (?, ?, ?)",
                            (key, json.dumps(data), now_iso()))

    def get_draft(self, key):
        with self.lock:
            row = self.db.execute("SELECT data FROM drafts WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def delete_draft(self, key):
        with self.lock:
            self.db.execute("DELETE FROM drafts WHERE key=?", (key,))

    def list_drafts(self):
        with self.lock:
            rows = self.db.execute("SELECT key, data, updated FROM drafts "
                                   "ORDER BY updated DESC").fetchall()
        return [(k, json.loads(d), u) for k, d, u in rows]


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
