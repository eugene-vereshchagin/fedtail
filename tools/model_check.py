"""Run the Mastodon adapter over every post a profile has stored, and say what it made.

    python3 tools/model_check.py [PROFILE]          # the main profile without a name

Read-only: the database is opened for reading and nothing is sent anywhere. Prints
how many posts, boosts and notifications went through, any that failed (with the
error and the post's id — no texts), and how often each part of the model came out
filled, so a server that names a field differently shows up as a 0 % next to it.
It also checks the adapter against the raw JSON: for the parts that matter, how many
posts carry them on the wire and how many came out in the model (a gap means the
adapter misreads this server), and which fields the server sends that the adapter
doesn't read at all (names only).

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


# what the adapter reads from a status, top level (anything else is listed as unread)
READ = {"id", "created_at", "edited_at", "in_reply_to_id", "in_reply_to_account_id",
        "sensitive", "spoiler_text", "visibility", "local_only", "language", "uri", "url",
        "replies_count", "reblogs_count", "favourites_count", "quotes_count", "favourited",
        "reblogged", "muted", "bookmarked", "pinned", "content", "reblog", "application",
        "account", "media_attachments", "mentions", "tags", "emojis", "card", "poll",
        "quote", "quote_id", "quote_approval", "interaction_policy", "filtered",
        "emoji_reactions", "pleroma", "text", "content_type"}

# raw key → does the model have it
ON_WIRE = {
    "card": lambda p: p.card is not None,
    "quote": lambda p: p.quote is not None,
    "quote_id": lambda p: p.quote is not None,
    "poll": lambda p: p.poll is not None,
    "emoji_reactions": lambda p: bool(p.reactions),
    "edited_at": lambda p: p.edited is not None,
    "filtered": lambda p: bool(p.filtered) or p.hidden,
    "spoiler_text": lambda p: bool(p.warning),
    "media_attachments": lambda p: bool(p.media),
    "text": lambda p: bool(p.source),
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
    unread = collections.Counter()
    wire, model = collections.Counter(), collections.Counter()
    took = 0.0
    for sid, data in db.execute("SELECT id, data FROM statuses"):
        raw = json.loads(data)
        if isinstance(raw.get("reblog"), dict):
            raw = raw["reblog"]  # stored by itself too, but count what the wrapper holds
        for key in raw:
            if key not in READ:
                unread[key] += 1
        try:
            t = time.perf_counter()
            got = adapter.post(json.loads(data))
            took += time.perf_counter() - t
        except Exception:  # noqa: BLE001 — that's what we're here to find
            failed.append((sid, traceback.format_exc(limit=3)))
            continue
        if isinstance(got, Share):
            count["shares"] += 1
            got = got.post
        count["posts"] += 1
        vis[got.visibility] += 1
        for key, test in ON_WIRE.items():
            if raw.get(key) or (key == "emoji_reactions"
                                and (raw.get("pleroma") or {}).get("emoji_reactions")):
                wire[key] += 1
                model[key] += bool(test(got))
        for key, test in FILLED.items():
            filled[key] += bool(test(got))
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
    print("on the wire → in the model:")
    for key in ON_WIRE:
        mark = "" if wire[key] == model[key] else "   <-- gap"
        print(f"  {key:18} {wire[key]:6} → {model[key]:6}{mark}")
    print("sent by the server, not read:",
          ", ".join(f"{k} {v}" for k, v in unread.most_common()) or "—")
    print(f"failed: {len(failed)}")
    for oid, tb in failed[:10]:
        print(f"--- {oid}\n{tb}")


if __name__ == "__main__":
    main()
