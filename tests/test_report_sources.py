"""Sources of lanes of rules from the competitors' report (feeds.md §2.1): an account's
posts filtered by its server, search, RSS feeds, a lane of tags in one request, and the
"network" and "strangers' mentions" lanes of the extra set."""

import unittest
from types import SimpleNamespace

from fedtail.core import atoms, presets, rss, sources, taggroups

RSS2 = b"""<?xml version="1.0"?>
<rss version="2.0"><channel><title>Tbilisi notes</title><link>https://blog.example/</link>
<item><title>Old town &amp; sulfur baths</title><link>https://blog.example/baths</link>
<description>&lt;p&gt;A walk &lt;b&gt;through&lt;/b&gt; Abanotubani.&lt;/p&gt;</description>
<pubDate>Mon, 26 Oct 2026 10:00:00 +0400</pubDate><guid>baths</guid></item>
<item><title>Kazbegi in snow</title><link>https://blog.example/kazbegi</link>
<pubDate>Tue, 27 Oct 2026 09:00:00 +0000</pubDate></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Release notes</title>
<link rel="alternate" href="https://code.example/"/>
<entry><title>v1.2</title><link rel="alternate" href="https://code.example/v1.2"/>
<id>tag:code.example,2026:v1.2</id><updated>2026-10-25T12:00:00Z</updated>
<summary>Faster &amp; smaller.</summary></entry></feed>"""


class Spy:
    """An API that remembers what it was asked."""

    def __init__(self):
        self.asked = []

    def __getattr__(self, name):
        def call(*a, **kw):
            self.asked.append((name, a, kw))
            return [{"id": "1", "created_at": "2026-10-27T10:00:00.000Z",
                     "tags": [{"name": "linux"}], "content": "<p>#linux</p>"}]
        return call


class AccountSourceTest(unittest.TestCase):
    def test_flags_go_to_the_server(self):
        self.assertEqual(sources.account_parts("7/posts/media/tag:#linux"),
                         ("7", {"posts", "media"}, "linux"))
        with self.assertRaises(ValueError):
            sources.account_parts("7/whatever")
        api = Spy()
        src = sources.prefixed_source(api, "account:7/posts/noboosts/tag:linux")
        src.fetch(limit=20)
        name, args, kw = api.asked[-1]
        self.assertEqual((name, args[0]), ("account_statuses", "7"))
        self.assertEqual((kw["exclude_replies"], kw["exclude_reblogs"], kw["only_media"],
                          kw["tagged"]), (True, True, False, "linux"))
        pinned = sources.prefixed_source(api, "account:7/pinned")
        self.assertTrue(pinned.fetch(limit=20))
        self.assertEqual(api.asked[-1][0], "pinned")
        self.assertEqual(pinned.fetch(limit=20, max_id="1"), [])  # one page, no older
        self.assertIsNone(sources.prefixed_source(api, "account:7/nonsense"))

    def test_search_and_rss(self):
        api = Spy()
        sources.prefixed_source(api, "search:openwrt router").fetch(limit=20, min_id="5")
        self.assertEqual(api.asked[-1][0], "search_statuses")
        self.assertEqual(api.asked[-1][1][0], "openwrt router")
        got = []
        src = sources.prefixed_source(api, "rss:https://blog.example/feed",
                                      rss=lambda url: got.append(url) or [{"id": "rss-1"}])
        self.assertEqual(src.fetch(limit=10), [{"id": "rss-1"}])
        self.assertEqual(got, ["https://blog.example/feed"])
        self.assertIsNone(sources.prefixed_source(api, "rss:https://x.example/f"))  # no rss()


class TagsOnceTest(unittest.TestCase):
    def test_the_group_in_one_request(self):
        asked = []

        def tag_timeline(tag, **kw):
            asked.append((tag, kw))
            return [{"id": "1", "created_at": "x", "tags": [{"name": "linux"}],
                     "content": "<p>#linux</p>"},
                    {"id": "2", "created_at": "y", "tags": [{"name": "spam"}],
                     "content": "<p>#spam</p>"}]
        spec = {"any": ["linux", "debian"], "none": ["spam"]}
        got = taggroups.fetch_once(tag_timeline, spec, limit=40)
        self.assertEqual(len(asked), 1)
        tag, kw = asked[0]
        self.assertEqual({tag, *kw["any[]"]}, {"linux", "debian"})
        self.assertEqual(kw["none[]"], ["spam"])
        self.assertEqual([st["id"] for st in got], ["1"])  # still checked here
        src = sources.tag_group_source(SimpleNamespace(tag_timeline=tag_timeline), spec, True)
        src.fetch(limit=40)
        self.assertEqual(len(asked), 2)


class RssTest(unittest.TestCase):
    def test_rss2_items_are_posts(self):
        got = rss.parse(RSS2, "https://blog.example/feed")
        self.assertEqual(len(got), 2)
        newest, older = got
        self.assertIn("Kazbegi", newest["content"])
        self.assertTrue(rss.is_rss(newest))
        self.assertEqual(older["url"], "https://blog.example/baths")
        self.assertIn("<b>Old town &amp; sulfur baths</b>", older["content"])
        self.assertIn("A walk through Abanotubani.", older["content"])
        self.assertNotIn("<p>A walk", older["content"].split("</b>")[1].replace(
            "<p>A walk through", ""))  # the feed's own tags are out
        self.assertEqual(older["created_at"], "2026-10-26T06:00:00.000Z")
        self.assertEqual(older["account"]["display_name"], "Tbilisi notes")
        self.assertEqual(older["card"]["url"], "https://blog.example/baths")
        again = rss.parse(RSS2, "https://blog.example/feed")
        self.assertEqual([s["id"] for s in again], [s["id"] for s in got])  # stable ids

    def test_atom_and_rubbish(self):
        [entry] = rss.parse(ATOM, "https://code.example/feed.atom")
        self.assertEqual(entry["url"], "https://code.example/v1.2")
        self.assertIn("Faster &amp; smaller.", entry["content"])
        self.assertEqual(rss.parse(b"<html>no</html>", "https://x.example/"), [])
        self.assertEqual(rss.parse(b"not xml at all <", "https://x.example/"), [])

    def test_a_feed_item_lives_only_here(self):
        from fedtail import i18n
        from fedtail.core.app import Core
        i18n.setup("en")
        item = rss.parse(RSS2, "https://blog.example/feed")[0]
        with self.assertRaises(ValueError) as e:
            Core._on_server(item)
        self.assertIn("RSS", str(e.exception))
        Core._on_server({"id": "103"})  # a server's post: nothing said


class ExtraLanesTest(unittest.TestCase):
    def test_network_and_strangers(self):
        extra = {t["name"]: t for t in presets.extra()}
        for name in ("network", "stranger_mentions"):
            rule = atoms.Rule.parse(extra[name])
            self.assertEqual(rule.warnings, [], name)
        self.assertEqual(extra["network"]["any"], [{"author": "remote"}])


if __name__ == "__main__":
    unittest.main()
