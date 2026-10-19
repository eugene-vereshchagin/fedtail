import unittest

# the sanitizer has no Qt in it: these run everywhere, with or without PySide6
from fedtail.frontends.richtext import ZWSP, clean


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
        from fedtail.frontends.richtext import sanitize
        self.assertEqual(sanitize('<p>a &amp; b<br/>c &#39;d&#39; &lt;x&gt;</p>'),
                         "<p>a &amp; b<br>c &#x27;d&#x27; &lt;x&gt;</p>")

    def test_inside_links_cannot_wrap_other_things(self):
        # fedtail:resolve/ is a web address found through my server: never a file (on
        # Windows file://host/share hands the login's hash to that host), a script or a
        # share; the other inside links take an id, not a path into the API
        for href in ("fedtail:resolve/file:///etc/passwd",
                     "fedtail:resolve/file:///home/u/.local/share/fedtail/default/auth.json",
                     "fedtail:resolve/file://attacker.example/share/x.png",
                     "fedtail:resolve/javascript:alert(1)",
                     "fedtail:resolve/JavaScript:alert(1)",
                     "fedtail:resolve/data:text/html,hi",
                     "fedtail:resolve/smb://attacker.example/share",
                     "fedtail:resolve/&#x66;ile:///etc/passwd",
                     "fedtail:resolve/file%3A%2F%2F%2Fetc%2Fpasswd",
                     "fedtail:account/1/follow", "fedtail:account/1%2Ffollow",
                     "fedtail:thread/1/../../accounts/2/follow", "fedtail:thread/1?x",
                     "Fedtail:delete/1", "fedtail:boost/1", "fedtail:account/",
                     "https://ok.example/\x01", "smb://attacker.example/share"):
            out = clean(f'<a href="{href}">кот</a>')
            self.assertNotIn("href", out, href)
            self.assertIn("кот", out)

    def test_inside_links_that_only_go_somewhere_stay(self):
        for href in ("fedtail:resolve/https%3A%2F%2Fsocial.example%2F%40a",
                     "fedtail:resolve/https://social.example/@a",
                     "fedtail:account/42", "fedtail:thread/110", "fedtail:tag/linux",
                     "mailto:a@b.example", "magnet:?xt=urn:btih:abc"):
            self.assertIn(f'href="{href}"', clean(f'<a href="{href}">x</a>'))
        # the scheme as fedtail reads it (the window compares it as written)
        self.assertIn('href="fedtail:account/42"', clean('<a href="Fedtail:Account/42">x</a>'))

    def test_link_query_is_not_decoded_twice(self):
        # &not= &copy= &para= are also old HTML entities: decoding the parser's result
        # once more turned ?a=1&not=2 into ?a=1¬=2
        href = "https://x.example/p?a=1&amp;not=2&amp;copy=3&amp;para=4"
        self.assertIn('href="https://x.example/p?a=1&amp;not=2&amp;copy=3&amp;para=4"',
                      clean(f'<a href="{href}">x</a>'))


class LinkPolicyTest(unittest.TestCase):
    def test_openable_is_the_web_and_post_links_only(self):
        from fedtail.frontends.richtext import openable
        for ok in ("https://a.example/", "HTTP://a.example", "mailto:a@b.example",
                   "xmpp:a@b.example", "gemini://g.example/", "magnet:?xt=1"):
            self.assertTrue(openable(ok), ok)
        for bad in ("file:///etc/passwd", "file://attacker.example/share/x",
                    "\\\\attacker.example\\share", "smb://attacker.example/s",
                    "javascript:alert(1)", "data:text/html,x", "fedtail:delete/1",
                    "-help", "", None, "https://a.example/\n", "C:\\Windows\\x.exe"):
            self.assertFalse(openable(bad), bad)

    def test_tooltips_show_someone_elses_words_as_written(self):
        from fedtail.frontends.richtext import plain_tip
        tip = plain_tip('<img src="file://attacker.example/s/x.png"> a & b\nnext')
        self.assertTrue(tip.startswith("<qt>"))  # rich on purpose, so Qt doesn't guess
        self.assertNotIn("<img", tip)
        self.assertIn("&lt;img", tip)
        self.assertIn("a &amp; b<br>next", tip)
        self.assertEqual(plain_tip(""), "")
        self.assertEqual(plain_tip(None), "")

    def test_history_warning_is_text(self):
        from fedtail.frontends.richtext import history_html
        h = history_html([{"created_at": "", "content": "<p>v1</p>",
                           "spoiler_text": '<img src="file://attacker.example/s/x.png">'
                                           '<a href="fedtail:delete/1">x</a>'},
                          {"created_at": "", "content": "<p>v2</p>"}], lambda _iso: "")
        self.assertNotIn("<img", h)
        self.assertNotIn('href="fedtail:delete', h)
        self.assertIn("&lt;img", h)
        self.assertIn("<p>v1</p>", h)
        self.assertEqual(h.count("<hr>"), 1)


class StrikeTildesTest(unittest.TestCase):
    def test_struck_where_meant(self):
        from fedtail.frontends.richtext import clean, strike_tildes
        h = "<p>свой ~~плагин~~ тропу</p>"
        self.assertEqual(strike_tildes(h), "<p>свой <s>плагин</s> тропу</p>")
        self.assertIn("<s>плагин</s>", clean(h, markup=True))
        self.assertNotIn("<s>", clean(h))  # off: as it came
        self.assertEqual(strike_tildes("<p>~~два слова~~!</p>"), "<p><s>два слова</s>!</p>")
        for keep in ("<p>a~~b~~c</p>", "<p>~~ пробел ~~</p>", "<p>~~~ три ~~~</p>",
                     '<p><a href="https://x.example/~~a~~">~~a~~</a></p>',
                     "<pre><code>x = ~~y~~</code></pre>", "<p>~ одна ~</p>"):
            self.assertEqual(strike_tildes(keep), keep)


class SnippetBlocksTest(unittest.TestCase):
    def test_quote_and_paragraph_are_not_glued(self):
        from fedtail.core.model import snippet
        st = {"content": '<p><span class="h-card">@anna</span></p>'
                         "<blockquote><p>quote</p></blockquote><p>AO3</p><ul><li>Кто</li></ul>"}
        self.assertEqual(snippet(st), "@anna quote AO3 Кто")


class EmojiTest(unittest.TestCase):
    def test_shortcodes_become_pictures_outside_tags(self):
        from fedtail.frontends.richtext import emojify
        emojis = [{"shortcode": "blobcat", "url": "https://s/blobcat.gif",
                   "static_url": "https://s/blobcat.png"},
                  {"shortcode": "nope", "url": "https://s/nope.png"}]
        have = {"https://s/blobcat.png": "/tmp/cache/abc"}
        h, missing = emojify('<a title=":blobcat:">hi :blobcat: and :nope: and :other:</a>',
                             emojis, 18, have.get)
        from pathlib import Path
        self.assertIn(f'src="{Path("/tmp/cache/abc").resolve().as_uri()}"', h)
        self.assertIn('width="18"', h)
        self.assertIn('title=":blobcat:">hi <img', h)  # not inside the tag's attribute
        self.assertIn(":nope:", h)
        self.assertIn(":other:", h)
        self.assertEqual(missing, ["https://s/nope.png"])
        self.assertEqual(emojify("plain", [], 18, have.get), ("plain", []))


class NoEmojiTest(unittest.TestCase):
    """feed.emoji = false: no emoji at all in the feed."""

    def test_unicode_and_server_emoji_go_text_and_app_glyphs_stay(self):
        from fedtail.frontends.richtext import strip_emoji
        h = strip_emoji('<a title=":blob: 🔥">hi 🔥🔥 there 👨‍👩‍👧 ok ❤️ ⚠ ↔ '
                        'warn 🇬🇪 1️⃣ x :blob: y</a>', [{"shortcode": "blob"}])
        self.assertEqual(h, '<a title=":blob: 🔥">hi there ok ⚠ ↔ warn x y</a>')

    def test_unlisted_shortcode_alone_goes_but_times_stay(self):
        from fedtail.frontends.richtext import strip_emoji
        self.assertEqual(strip_emoji("must die :bloberika_wtf_knife:"), "must die ")
        self.assertEqual(strip_emoji("at 10:30:00, a:b:c"), "at 10:30:00, a:b:c")


class LooksSentTest(unittest.TestCase):
    def test_words_parent_and_time(self):
        import time

        from fedtail.core.model import looks_sent
        now = time.time()
        made = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now))
        st = {"id": "1", "in_reply_to_id": "50", "created_at": made,
              "content": '<p><span class="h-card"><a href="x">@<span>Linda</span></a></span> '
                         "потому что <strong>тонкий</strong> слой в раковине</p>"}
        text = "@Linda-chan@juick.com потому что **тонкий** слой в раковине"
        self.assertTrue(looks_sent(st, text, "50", now))
        self.assertFalse(looks_sent(st, text, None, now))  # another parent
        self.assertFalse(looks_sent(st, "совсем другие слова тут", "50", now))
        self.assertFalse(looks_sent(st, text, "50", now + 3600))  # made long before


if __name__ == "__main__":
    unittest.main()
