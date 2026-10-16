import unittest
from urllib.parse import unquote

from fedtail.core.links import in_app, looks_fediverse

from .fakes import BOB, status


class LinksTest(unittest.TestCase):
    def setUp(self):
        self.st = status("1", BOB)
        self.st["mentions"] = [{"id": "K", "url": "https://mastodon.ml/@kot",
                                "acct": "kot@mastodon.ml"}]

    def test_mentions_tags_and_fedi_links_stay_inside(self):
        html = ('<p><span class="h-card"><a href="https://mastodon.ml/@kot" '
                'class="u-url mention">@<span>kot</span></a></span> '
                '<a href="https://gts.example/tags/%D0%B8%D0%B3%D1%80%D1%8B" class="mention '
                'hashtag" rel="tag">#<span>игры</span></a> '
                '<a href="https://other.example/@ann/1234567">post</a> '
                '<a href="https://example.com/article">site</a></p>')
        out = in_app(html, self.st)
        self.assertIn('href="fedtail:account/K"', out)
        self.assertIn('href="fedtail:tag/%D0%B8%D0%B3%D1%80%D1%8B"', out)
        self.assertEqual(unquote("%D0%B8%D0%B3%D1%80%D1%8B"), "игры")
        self.assertIn('href="fedtail:resolve/https%3A%2F%2Fother.example%2F%40ann%2F1234567"',
                      out)
        self.assertIn('href="https://example.com/article"', out)  # an ordinary site stays

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
