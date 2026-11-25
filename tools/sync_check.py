"""The sync journal held against this profile's store: why the counts differ between devices.

    python3 tools/sync_check.py [PROFILE]          # the main profile without a name

Reads the whole journal from where `[sync]` says (a fedtail-sync server, a folder, WebDAV)
with the profile's key — GET only, nothing is sent, nothing changes there — and opens
state.db for reading. Prints, with no posts and no names (paste it into an issue):

* each device in the journal: its name, how many batches and when, what kinds of ops,
  how many read marks; a packed one (a snapshot) says so;
* this store: read marks of the other devices not applied here (a bug: they should be),
  the user's marks here that no journal holds any more (a device that comes or comes
  back now won't learn them), marks not sent yet;
* each lane's newest `feed.render_limit` entries: unread here, read and in the journal,
  read by the user but gone from the journal, read by fedtail itself (the first run,
  older history, my own posts — those never travel).
"""

import collections
import sqlite3
import sys
import tomllib
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fedtail.core import config, paths  # noqa: E402
from fedtail.core.sync import backends, crypto, engine  # noqa: E402

KINDS = {"r": "read", "t": "thread", "k": "setting", "as": "events seen", "h": "dismissed",
         "dr": "draft"}


def when(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%Y-%m-%d %H:%M") if ms else "?"


def open_backend(cfg, p):
    s = cfg["sync"]
    key = crypto.load_key(engine.key_path(p))
    if key is None:
        sys.exit("no sync key in this profile")
    if s["folder"]:
        return backends.FolderBackend(s["folder"]), key
    if s.get("webdav"):
        return backends.WebDavBackend(s["webdav"], s["webdav_user"],
                                      engine.load_webdav(p)), key
    if not s["url"]:
        sys.exit("sync is off in this profile")
    return backends.HttpBackend(s["url"], key, engine.load_invite(p)), key


def read_journal(backend, key):
    """→ [payload] of every batch sealed with this key, in the journal's order."""
    out, cursor, others = [], None, 0
    for _round in range(10_000):
        blobs, cursor, more = backend.pull(cursor, "")
        for blob in blobs:
            if crypto.is_escrow(blob):
                continue
            try:
                out.append(crypto.unseal(key, blob))
            except crypto.BadBlob:
                others += 1
        if not more:
            break
    if others:
        print(f"{others} blobs of another key (or broken) skipped")
    return out


def main(argv):
    p = paths.resolve(argv[0] if argv else None)
    with open(p.config_file, "rb") as f:  # config.load could write the file: not here
        cfg, _ = config.validate(tomllib.load(f))
    db = sqlite3.connect(f"file:{p.data_dir / 'state.db'}?mode=ro", uri=True)
    kv = dict(db.execute("SELECT key, value FROM kv WHERE key LIKE 'sync.%'"))
    me = (kv.get("sync.device") or "").strip('"')
    backend, key = open_backend(cfg, p)
    journal = read_journal(backend, key)

    print(f"# sync journal: {len(journal)} batches, this device {me}\n")
    marks = collections.defaultdict(set)
    devices = {}
    for b in journal:
        d = str(b.get("d") or "?")
        dev = devices.setdefault(d, {"name": "", "n": 0, "first": 0, "last": 0, "snap": 0,
                                     "ops": collections.Counter()})
        dev["name"] = b.get("n") or dev["name"]
        dev["n"] += 1
        at = int(b.get("at") or 0)
        dev["first"] = min(dev["first"] or at, at)
        dev["last"] = max(dev["last"], at)
        ops = b.get("ops") or []
        if any("by" in op for op in ops) or sum(len(op.get("r") or ()) for op in ops) >= 2000:
            dev["snap"] += 1
        for op in ops:
            kind = next((k for k in KINDS if k in op), "?")
            dev["ops"][KINDS.get(kind, kind)] += 1
            if kind == "r":
                marks[d].update(str(i) for i in op["r"])
    print("| device | name | batches | from | to | packed | read marks | ops |")
    print("|---|---|---|---|---|---|---|---|")
    for d, v in devices.items():
        ops = ", ".join(f"{k} {n}" for k, n in v["ops"].most_common())
        print(f"| {d}{' (here)' if d == me else ''} | {v['name'] or '—'} | {v['n']} | "
              f"{when(v['first'])} | {when(v['last'])} | {v['snap'] or ''} | "
              f"{len(marks[d])} | {ops} |")

    read = {r[0] for r in db.execute("SELECT status_id FROM read")}
    shared = {r[0] for r in db.execute("SELECT status_id FROM read_shared")}
    others = set().union(*(v for d, v in marks.items() if d != me)) if marks else set()
    everywhere = set().union(*marks.values()) if marks else set()
    pending = db.execute("SELECT COUNT(*) FROM sync_out").fetchone()[0]
    print(f"\nhere: {len(read)} read marks, {len(shared)} of them the user's (travel)")
    print(f"- the other devices' marks not applied here: {len(others - read)}"
          + ("  ← a bug" if others - read else ""))
    print(f"- the user's marks here that no journal holds: {len(shared - everywhere)}"
          " (a device joining or back from away won't learn them)")
    print(f"- ops waiting to go: {pending}; cursor {kv.get('sync.cursor')}; "
          f"last round {kv.get('sync.last')}")

    limit = cfg["feed"]["render_limit"]
    print(f"\n| lane (newest {limit}) | unread | read, in the journal | the user's, gone from "
          "the journal | fedtail's own |")
    print("|---|---|---|---|---|")
    for (src,) in db.execute("SELECT DISTINCT source FROM items ORDER BY source"):
        rows = db.execute("SELECT item_id, status_id FROM items WHERE source=? "
                          "ORDER BY sort DESC LIMIT ?", (src, limit)).fetchall()
        c = collections.Counter()
        for row in rows:
            ids = set(row)
            c["unread" if not ids & read else "journal" if ids & everywhere else
              "gone" if ids & shared else "own"] += 1
        print(f"| {src} | {c['unread']} | {c['journal']} | {c['gone']} | {c['own']} |")


if __name__ == "__main__":
    main(sys.argv[1:])
