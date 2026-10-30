import unittest
from urllib.parse import unquote

from fedtail.core.links import in_app, looks_fediverse

from .fakes import BOB, status


class LinksTest(unittest.TestCase):
    def setUp(self):
        self.st = status("1", BOB)
        self.st["mentions"] = [{"id": "K", "url": "https://kot.example/@kot",
                                "acct": "kot@kot.example"}]

    def test_mentions_tags_and_fedi_links_stay_inside(self):
        html = ('<p><span class="h-card"><a href="https://kot.example/@kot" '
                'class="u-url mention">@<span>kot</span></a></span> '
                '<a href="https://gts.example/tags/%D0%B8%D0%B3%D1%80%D1%8B" class="mention '
                'hashtag" rel="tag">#<span>игры</span></a> '
                '<a href="https://other.example/@ann/1234567">post</a> '
                '<a href="https://example.com/article">site</a></p>')
        out = in_app(html, self.st)
        self.assertIn('href="fedtail:account/K"', out)
        # the tag carries its post's author: a click may open it as they write it
        self.assertIn('href="fedtail:tag/%D0%B8%D0%B3%D1%80%D1%8B%20by%3AB"', out)
        self.assertEqual(unquote("%D0%B8%D0%B3%D1%80%D1%8B%20by%3AB"), "игры by:B")
        self.assertIn('href="fedtail:resolve/https%3A%2F%2Fother.example%2F%40ann%2F1234567"',
                      out)
        self.assertIn('href="https://example.com/article"', out)  # an ordinary site stays

    def test_every_servers_hashtags_stay_inside(self):
        """Each server marks a tag its own way; one not recognised went to the other
        server's web page, which asked to log in (29.10)."""
        cases = [
            ('<a href="https://p.example/tag/linux" rel="tag">#linux</a>', None),  # Pleroma
            ('<a href="https://k.example/tags/linux">#linux</a>', None),            # Misskey
            ('<a href="https://f.example/search?tag=linux">#linux</a>', None),      # Friendica
            ('<a href="https://x.example/whatever/1">#linux</a>', ["linux"]),       # by the list
            ('<a href="https://x.example/tags/linux" class="u-url">#Linux</a>', None),
        ]
        for html, tags in cases:
            out = in_app(html, {}, tags=tags)
            self.assertIn("fedtail:tag/", out, html)
            self.assertIn('title="', out)  # the address kept to see
        # a site's own tag page with other words is the site's
        out = in_app('<a href="https://blog.example/tag/linux">my notes</a>', {})
        self.assertNotIn("fedtail:", out)
        # the post's own tags (a raw status)
        st = dict(status("2", BOB), tags=[{"name": "игры", "url": "https://x.example/t/1"}])
        out = in_app('<a href="https://x.example/t/1">#игры</a>', st)
        self.assertIn("fedtail:tag/%D0%B8%D0%B3%D1%80%D1%8B", out)

    def test_unknown_mention_is_resolved(self):
        out = in_app('<a href="https://x.example/@zed" class="u-url mention">@zed</a>', {})
        self.assertIn("fedtail:resolve/", out)

    def test_shapes(self):
        for url in ("https://m.example/@u", "https://m.example/@u/110000",
                    "https://g.example/@u/statuses/01HXYZ", "https://g.example/users/u",
                    "https://a.example/notice/AbC", "https://k.example/notes/9xyz"):
            self.assertTrue(looks_fediverse(url), url)
        for url in ("https://example.com/", "https://example.com/blog/post-1",
                    "ftp://m.example/@u"):
            self.assertFalse(looks_fediverse(url), url)


if __name__ == "__main__":
    unittest.main()


class MediaLinkTest(unittest.TestCase):
    """30.10: "1 attachment was not downloaded … 0ba3a335ab822c8c.mp4 (error: file size
    limit reached)" — the server leaves the clip's link in the text, and it went to the
    browser. A link to a video or sound file goes to the interface's own player
    (media.links_in_player), the browser when off or where there's none."""

    def test_the_player_or_the_browser(self):
        import types

        from fedtail.frontends.common import links as L
        self.assertEqual(L.media_link("https://f.example/a/0ba3.mp4"), "video")
        self.assertEqual(L.media_link("https://f.example/s.OPUS?x=1"), "audio")
        self.assertEqual(L.media_link("https://f.example/page.html"), "")
        self.assertEqual(L.media_link("file:///etc/x.mp4"), "")  # the web only
        cfg = {"ui": {"links_in_player": True}}
        played, opened = [], []
        host = types.SimpleNamespace(play_link=played.append, open_url=opened.append)
        links = L.Links(types.SimpleNamespace(cfg=cfg), host)
        links.open("https://f.example/a/0ba3.mp4")
        self.assertEqual([(m.kind, m.url) for m in played],
                         [("video", "https://f.example/a/0ba3.mp4")])
        links.open("https://f.example/page")
        self.assertEqual(opened, ["https://f.example/page"])
        cfg["ui"]["links_in_player"] = False
        links.open("https://f.example/a/0ba3.mp4")
        self.assertEqual(opened[-1], "https://f.example/a/0ba3.mp4")
        cfg["ui"]["links_in_player"] = True
        bare = L.Links(types.SimpleNamespace(cfg=cfg),
                       types.SimpleNamespace(open_url=opened.append))  # no player there
        bare.open("https://f.example/b.mp3")
        self.assertEqual(opened[-1], "https://f.example/b.mp3")
