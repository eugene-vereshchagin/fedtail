"""Frontends moved to fedtail.model read no protocol fields (docs/PROTOCOLS.md, stage 2).

The Qt frontend moves file by file; when the last one is in, the list goes and the
test covers frontends/ as a whole.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "fedtail"

MOVED = ["frontends/cli.py", "frontends/tui/model.py", "frontends/tui/app.py",
         "frontends/web/server.py",
         # Qt, as it moves: the post card and what it opens
         "frontends/qt/card.py", "frontends/qt/viewer.py", "frontends/qt/player.py",
         "frontends/qt/find.py", "frontends/qt/social.py", "frontends/qt/feed.py",
         "frontends/qt/compose.py", "frontends/qt/cmdline.py"]

# what only a Mastodon status or account has; the model says it differently
RAW = re.compile(r'"(reblog|spoiler_text|in_reply_to_id|in_reply_to_account_id|'
                 r'media_attachments|favourited|reblogged|favourites_count|reblogs_count|'
                 r'replies_count|display_name|acct|statuses_count|followers_count|'
                 r'following_count|preview_url|remote_url)"|/api/v\d|\.lane_entries\(|'
                 r'\.unread_ids\(|\.parent_of\(|\.account_statuses\(|core\.model import')


class LayeringTest(unittest.TestCase):
    def test_moved_frontends_read_no_protocol_fields(self):
        for rel in MOVED:
            text = (ROOT / rel).read_text(encoding="utf-8")
            hits = [f"{rel}:{n}: {line.strip()}" for n, line in enumerate(text.splitlines(), 1)
                    if RAW.search(line)]
            self.assertEqual(hits, [], "\n".join(hits))

    def test_the_page_speaks_the_model(self):
        js = (ROOT / "data/web/app.js").read_text(encoding="utf-8")
        for word in ("favourited", "reblogged", "spoiler", "acct", "private"):
            self.assertNotRegex(js, rf"\.{word}\b", word)


if __name__ == "__main__":
    unittest.main()
