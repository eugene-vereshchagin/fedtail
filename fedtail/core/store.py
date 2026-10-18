"""Per-profile SQLite state: cached statuses, lane items, read marks, drafts.

One connection shared by all threads, serialised with a lock. Every
method is a short transaction, so contention is negligible.
"""

import json
import sqlite3
import threading
from datetime import UTC, datetime

SCHEMA_VERSION = 4

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


def now_iso():
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sort_key(created_at, item_id):
    """Chronological key that also works across id formats (ULID / snowflake)."""
    return f"{created_at or ''}|{str(item_id).rjust(32, '0')}"


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
        self._tags = None  # {lowercase name: [name as seen, how often]}, built on demand
        self._people = None  # {lowercase acct: [acct, display name, how often]}, the same way
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
        schema = self.kv_get("schema") or SCHEMA_VERSION
        if schema < 3:
            self._rename_lanes()
        if schema < 4:
            self._fill_first_seen()
        self.kv_set("schema", SCHEMA_VERSION)

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

    def close(self):
        with self.lock:
            self.db.close()

    def _tx(self):
        return _Tx(self)

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
        # a post of mine is read: I wrote it — from this client or any other, come by a
        # lane, a thread, a catch-up after a restart
        mine = [r[0] for r in rows if self.me_id and r[4] == self.me_id]
        with self._tx() as db:
            db.executemany("INSERT OR REPLACE INTO statuses (id, data, created_at, reply_to, "
                           "author) VALUES (?, ?, ?, ?, ?)", rows)
            if mine:
                db.executemany("INSERT OR IGNORE INTO read VALUES (?)", [(i,) for i in mine])
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
        with self.lock:
            for i in range(0, len(ids), 500):
                chunk = ids[i:i + 500]
                q = (f"SELECT real_id, item_id FROM first_seen WHERE source=? AND real_id IN "
                     f"({','.join('?' * len(chunk))})")
                out.update(self.db.execute(q, [source, *chunk]).fetchall())
        return out

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
            db.execute("INSERT OR IGNORE INTO subs (root_id, since, last_activity, checked, auto)"
                       " VALUES (?, ?, ?, '', ?)", (root_id, since, last_activity, int(auto)))
            db.executemany("INSERT OR IGNORE INTO sub_members VALUES (?, ?)",
                           [(m, root_id) for m in members])

    def sub_remove(self, root_id, remember=True):
        """Leave a thread: its comments vanish from the lane, and (remember)
        automatic subscription won't come back to it."""
        with self._tx() as db:
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
        with self.lock:
            row = self.db.execute("SELECT root_id FROM subs WHERE root_id=?",
                                  (status_id,)).fetchone() or \
                self.db.execute("SELECT m.root_id FROM sub_members m JOIN subs s "
                                "ON s.root_id = m.root_id WHERE m.status_id=?",
                                (status_id,)).fetchone()
        return row[0] if row else None

    def sub_left(self, root_id):
        with self.lock:
            return self.db.execute("SELECT 1 FROM unsubs WHERE root_id=?",
                                   (root_id,)).fetchone() is not None

    def subs_due(self, active_after, checked_before, limit):
        """Followed threads to look at now: alive lately, longest unchecked first."""
        with self.lock:
            rows = self.db.execute(
                "SELECT root_id, since, last_activity FROM subs WHERE last_activity > ? "
                "AND checked < ? ORDER BY checked ASC LIMIT ?",
                (active_after, checked_before, limit)).fetchall()
        return rows

    def sub_members(self, root_id):
        with self.lock:
            return {r[0] for r in self.db.execute(
                "SELECT status_id FROM sub_members WHERE root_id=?", (root_id,))}

    def sub_checked(self, root_id, checked, last_activity, members):
        with self._tx() as db:
            db.execute("UPDATE subs SET checked=?, last_activity=MAX(last_activity, ?) "
                       "WHERE root_id=?", (checked, last_activity, root_id))
            db.executemany("INSERT OR IGNORE INTO sub_members VALUES (?, ?)",
                           [(m, root_id) for m in members])

    def subs_count(self):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM subs").fetchone()[0]

    # ---- activity (favourites, boosts, follows) ------------------------------------
    def activity_put(self, notifications):
        """Returns the notifications that were new."""
        sts = [n["status"] for n in notifications if n.get("status")]
        if sts:
            self.put_statuses(sts)
        new = []
        with self._tx() as db:
            for n in notifications:
                acc = n.get("account") or {}
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
        return new

    def activity_delete(self, ids=None):
        """Some notifications gone from Activity (ids), or all of them (None)."""
        with self._tx() as db:
            if ids is None:
                db.execute("DELETE FROM activity")
            else:
                db.executemany("DELETE FROM activity WHERE id = ?", [(i,) for i in ids])
            self._bump("activity")

    def activity_newest(self):
        with self.lock:
            row = self.db.execute("SELECT id, sort FROM activity ORDER BY sort DESC LIMIT 1"
                                  ).fetchone()
        return (row[0], row[1]) if row else (None, "")

    def activity_recent(self, limit):
        """Newest first: [{id, type, account, status, created_at, sort}]."""
        with self.lock:
            rows = self.db.execute(
                "SELECT a.id, a.type, a.account, s.data, a.sort FROM activity a LEFT JOIN "
                "statuses s ON s.id = a.status_id ORDER BY a.sort DESC LIMIT ?",
                (limit,)).fetchall()
        return [{"id": r[0], "type": r[1], "account": json.loads(r[2]),
                 "status": json.loads(r[3]) if r[3] else None, "sort": r[4],
                 "created_at": r[4].split("|")[0]} for r in rows]

    def activity_count_after(self, sort):
        with self.lock:
            return self.db.execute("SELECT COUNT(*) FROM activity WHERE sort > ?",
                                   (sort,)).fetchone()[0]

    # ---- read marks -----------------------------------------------------------
    def mark_read(self, status_ids):
        with self._tx() as db:
            db.executemany("INSERT OR IGNORE INTO read VALUES (?)", [(i,) for i in status_ids])

    def mark_mine_read(self):
        """Every stored post of mine read (ones stored before this rule). How many."""
        if not self.me_id:
            return 0
        with self._tx() as db:
            cur = db.execute("INSERT OR IGNORE INTO read SELECT id FROM statuses "
                             "WHERE author = ?", (self.me_id,))
            return cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

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
