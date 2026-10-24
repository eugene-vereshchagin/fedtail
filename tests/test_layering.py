"""Frontends read no protocol fields: they speak fedtail.model through core/view.py
(docs/en/dev/protocols.md, stage 2) — every file under frontends/."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "fedtail"

MOVED = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "frontends").rglob("*.py"))

# what only a Mastodon status or account has; the model says it differently
RAW = re.compile(r'"(reblog|spoiler_text|in_reply_to_id|in_reply_to_account_id|'
                 r'media_attachments|favourited|reblogged|favourites_count|reblogs_count|'
                 r'replies_count|display_name|acct|statuses_count|followers_count|'
                 r'following_count|preview_url|remote_url)"|/api/v\d|\.lane_entries\(|'
                 r'\.unread_ids\(|\.parent_of\(|\.account_statuses\(|core\.model import|'
                 r'\.store\.|\bstore\.get_status\(')


class LayeringTest(unittest.TestCase):
    def test_moved_frontends_read_no_protocol_fields(self):
        for rel in MOVED:
            text = (ROOT / rel).read_text(encoding="utf-8")
            hits = [f"{rel}:{n}: {line.strip()}" for n, line in enumerate(text.splitlines(), 1)
                    if RAW.search(line)]
            self.assertEqual(hits, [], "\n".join(hits))

    def test_shared_frontend_code_imports_no_toolkit(self):
        """frontends/common, palette.py, pango.py and the other shared modules are for
        every toolkit: none of them may import one (docs/en/dev/gtk.md, stage 0)."""
        toolkit = re.compile(r"^\s*(from|import)\s+(PySide6|gi\b|textual|shiboken)", re.M)
        shared = [p for p in (ROOT / "frontends").rglob("*.py")
                  if p.parent.name in ("frontends", "common")]
        self.assertTrue(any(p.parent.name == "common" for p in shared))
        for p in shared:
            self.assertIsNone(toolkit.search(p.read_text(encoding="utf-8")), p.name)

    def test_the_page_speaks_the_model(self):
        js = (ROOT / "data/web/app.js").read_text(encoding="utf-8")
        for word in ("favourited", "reblogged", "spoiler", "acct", "private"):
            self.assertNotRegex(js, rf"\.{word}\b", word)


if __name__ == "__main__":
    unittest.main()
