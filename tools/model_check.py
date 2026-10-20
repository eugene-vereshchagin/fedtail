"""Run the Mastodon adapter over every post a profile has stored, and say what it made.

    python3 tools/model_check.py [PROFILE]          # the main profile without a name

Read-only: the database is opened for reading and nothing is sent anywhere. Prints
how many posts, boosts and notifications went through, any that failed (with the
error and the post's id — no texts), and how often each part of the model came out
filled, so a server that names a field differently shows up as a 0 % next to it.
Paste the output into an issue or a message: it holds no posts and no names.
"""

import collections
import json
import sqlite3
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fedtail.core import paths  # noqa: E402
from fedtail.model import Share  # noqa: E402
from fedtail.protocols.mastodon import adapter  # noqa: E402

FILLED = {
    "text": lambda p: bool(p.text), "warning": lambda p: bool(p.warning),
    "created": lambda p: p.created is not None, "edited": lambda p: p.edited is not None,
    "reply_to": lambda p: p.reply_to is not None, "media": lambda p: bool(p.media),
    "media.alt": lambda p: any(m.alt for m in p.media),
    "media.size": lambda p: any(m.width for m in p.media),
    "poll": lambda p: p.poll is not None, "card": lambda p: p.card is not None,
    "quote": lambda p: p.quote is not None,
    "quote.post": lambda p: p.quote is not None and p.quote.post is not None,
    "mentions": lambda p: bool(p.mentions), "tags": lambda p: bool(p.tags),
    "emojis": lambda p: bool(p.emojis), "reactions": lambda p: bool(p.reactions),
    "policy": lambda p: p.policy is not None, "local_only": lambda p: p.local_only,
    "lang": lambda p: bool(p.lang), "app": lambda p: bool(p.app),
    "filtered": lambda p: bool(p.filtered), "author.handle": lambda p: bool(p.author.handle),
    "author.avatar": lambda p: bool(p.author.avatar_static),
    "author.created": lambda p: p.author.created is not None,
    "author.fields": lambda p: bool(p.author.fields),
}


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else None
    db_path = paths.resolve(name).db_file
    if not db_path.exists():
        sys.exit(f"no database at {db_path}")
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    count = collections.Counter()
    filled = collections.Counter()
    vis = collections.Counter()
    failed = []
    t = time.perf_counter()
    for sid, data in db.execute("SELECT id, data FROM statuses"):
        try:
            got = adapter.post(json.loads(data))
        except Exception:  # noqa: BLE001 — that's what we're here to find
            failed.append((sid, traceback.format_exc(limit=3)))
            continue
        if isinstance(got, Share):
            count["shares"] += 1
            got = got.post
        count["posts"] += 1
        vis[got.visibility] += 1
        for key, test in FILLED.items():
            filled[key] += bool(test(got))
    took = time.perf_counter() - t
    kinds = collections.Counter()
    for nid, type_, acc, _sid in db.execute("SELECT id, type, account, status_id FROM activity"):
        try:
            a = adapter.activity({"id": nid, "type": type_, "account": json.loads(acc)})
            kinds[a.kind] += 1
        except Exception:  # noqa: BLE001
            failed.append((nid, traceback.format_exc(limit=3)))
    n = max(1, count["posts"])
    print(f"posts {count['posts']} (boosts {count['shares']}), "
          f"{took * 1e6 / n:.0f} µs each; notifications {sum(kinds.values())}")
    print("visibility:", dict(vis))
    print("activity kinds:", dict(kinds))
    print("filled:")
    for key in FILLED:
        print(f"  {key:16} {filled[key] * 100 / n:5.1f} %")
    print(f"failed: {len(failed)}")
    for oid, tb in failed[:10]:
        print(f"--- {oid}\n{tb}")


if __name__ == "__main__":
    main()
