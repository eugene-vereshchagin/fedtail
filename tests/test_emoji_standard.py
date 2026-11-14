"""The standard (Unicode) emoji (core/emojis.py, post.emoji_standard): the picker's
"Standard" tab by group, the search by English words and short names (:smile:, :+1:), the
suggestions as one types `:smi` beside the server's own, and the web page's / phone's
emoji list carrying both."""

import unittest

from fedtail.core import config, emojis
from fedtail.frontends.common import compose as cc


class FakeView:
    def __init__(self, on=True, server=()):
        self.cfg, _w = config.validate({"post": {"emoji_standard": on}})
        self.server = list(server)

    def emoji_standard(self, words=""):
        return emojis.picker(words) if self.cfg["post"]["emoji_standard"] else []

    def emoji_standard_suggestions(self, prefix, limit=8):
        return emojis.suggestions(prefix, limit) if self.cfg["post"]["emoji_standard"] \
            and len(prefix) >= 2 else []

    def emoji_suggestions(self, word):
        return [(e["shortcode"], e) for e in self.server if e["shortcode"].startswith(word)]


class EmojiTest(unittest.TestCase):
    def test_every_one_once_and_real(self):
        got = emojis.every()
        chars = [e["char"].rstrip("️") for e in got]
        self.assertGreater(len(got), 1000)
        self.assertEqual(len(chars), len(set(chars)))
        self.assertEqual({e["group"] for e in got}, set(emojis.GROUPS))
        self.assertIn("😀", chars)
        self.assertNotIn("\U0001F394", chars)  # a heart ornament: a symbol, not an emoji
        self.assertNotIn("\U0001F3FB", chars)  # a skin tone: no emoji of its own
        self.assertIn("\U0001F321️", [e["char"] for e in got])  # text by default: VS16

    def test_short_names_people_know(self):
        def first(q):
            return emojis.search(q)[0]["char"]
        self.assertEqual(first("smile"), "😄")
        self.assertEqual(first(":smile:"), "😄")
        self.assertEqual(first("+1"), "👍")
        self.assertEqual(first("tada"), "🎉")
        self.assertIn("😉", [e["char"] for e in emojis.search("winking")])
        self.assertIn("😊", [e["char"] for e in emojis.search("smiling", 40)])
        self.assertEqual(emojis.suggestions("wink", 1), [("😉", "😉 :wink:")])
        for alias, char in emojis.ALIASES.items():  # every alias lands on a real emoji
            self.assertTrue(emojis.search(alias), alias)
            self.assertIn(char.rstrip("️"), [e["char"].rstrip("️")
                                                  for e in emojis.every()], alias)

    def test_picker_by_group_and_found(self):
        tabs = cc.emoji_standard(FakeView())
        self.assertEqual(len(tabs), len(cc.EMOJI_GROUPS))
        self.assertIn("😀", [e["char"] for e in tabs[0][1]])
        found = cc.emoji_standard(FakeView(), "cat")
        self.assertEqual(found[0][0], "")
        self.assertIn("🐱", [e["char"] for e in found[0][1]])
        self.assertEqual(cc.emoji_standard(FakeView(on=False)), [])

    def test_server_tab(self):
        items = [{"shortcode": "blobcat", "category": "Blobs"},
                 {"shortcode": "neko", "category": ""}]
        self.assertEqual([c for c, _e in cc.emoji_server(items)], ["Blobs", ""])
        self.assertEqual(cc.emoji_server(items, ":blob"), [("", items[:1])])
        self.assertEqual(cc.emoji_server(items, "zzz"), [])

    def test_typing_suggests_both(self):
        v = FakeView(server=[{"shortcode": "smilecat"}])
        got = cc.suggestions(v, ":", "smile")
        self.assertEqual(got[0], (":smilecat:", ":smilecat:"))  # the server's first
        self.assertIn(("😄", "😄 :smile:"), got)
        self.assertLessEqual(len(got), 8)
        self.assertEqual(cc.suggestions(FakeView(on=False), ":", "smile"), [])


if __name__ == "__main__":
    unittest.main()
