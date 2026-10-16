import unittest

try:
    from fedtail.frontends.qt.text import ZWSP, clean
except ImportError:  # no PySide6 here
    clean = None


@unittest.skipIf(clean is None, "PySide6 is not installed")
class CleanTest(unittest.TestCase):
    def test_long_link_text_is_shortened_href_kept(self):
        url = "https://freesoftwareextremist.com/objects/21d20787-5fba-491f-8c3e-0123456789ab"
        h = clean(f'<p>Продолжение: <a href="{url}">{url}</a></p>')
        self.assertIn(f'href="{url}"', h)
        self.assertRegex(h.replace(ZWSP, ""), r">freesoftwareextremist\.com/objects/21d2\w*…</a>")
        self.assertNotIn(">https://", h)

    def test_mastodon_short_links_untouched(self):
        h = clean('<a href="https://ex.org/a"><span class="invisible">https://</span>'
                  '<span class="">ex.org/a</span></a>')
        self.assertIn(">ex.org/a<", h.replace("<span>", "").replace("</span>", ""))

    def test_long_words_can_wrap_and_entities_survive(self):
        word = "x" * 70
        h = clean(f"<p>{word} &amp; &lt;b&gt; it's</p>")
        self.assertIn(ZWSP, h)
        self.assertEqual(h.replace(ZWSP, "").count("x"), 70)
        self.assertIn("&amp; &lt;b&gt; it's", h)

    def test_hostile_html_is_defused(self):
        h = clean('<p onclick="x()">hi<script>alert(1)</script><style>p{}</style>'
                  '<img src="file:///etc/passwd"><iframe src="https://x">in</iframe>'
                  '<a href="javascript:alert(1)">js</a> '
                  '<a href="fedtail:delete/123">tap me</a> '
                  '<a href="file:///home">f</a> <h1>BIG</h1><font size="9">f</font>'
                  '<table><tr><td>t</td></tr></table>'
                  '<a href="fedtail:account/42">@bob</a> <a href="https://ok.example/">ok</a>'
                  '<b style="font-size:90px">b</b></p>')
        for bad in ("script", "alert", "p{}", "90px", "onclick", "img", "iframe", "javascript",
                    "fedtail:delete", "file:", "<h1", "<font", "<table", "size"):
            self.assertNotIn(bad, h)
        for text in ("hi", "js", "tap me", "<p>BIG</p>", " t<", "<b>b</b>"):
            self.assertIn(text, h)
        self.assertIn('href="fedtail:account/42"', h)
        self.assertIn('href="https://ok.example/"', h)

    def test_entities_and_breaks_survive_sanitizing(self):
        from fedtail.frontends.qt.text import sanitize
        self.assertEqual(sanitize('<p>a &amp; b<br/>c &#39;d&#39; &lt;x&gt;</p>'),
                         "<p>a &amp; b<br>c &#x27;d&#x27; &lt;x&gt;</p>")


if __name__ == "__main__":
    unittest.main()


class SnippetBlocksTest(unittest.TestCase):
    def test_quote_and_paragraph_are_not_glued(self):
        from fedtail.core.model import snippet
        st = {"content": '<p><span class="h-card">@anna</span></p>'
                         "<blockquote><p>quote</p></blockquote><p>AO3</p><ul><li>Кто</li></ul>"}
        self.assertEqual(snippet(st), "@anna quote AO3 Кто")
