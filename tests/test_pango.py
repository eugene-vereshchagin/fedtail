"""frontends/pango.py: post HTML as Pango markup (checked by Pango itself when it's here)."""

import re
import unittest

from fedtail.frontends.pango import markup

try:
    import gi
    gi.require_version("Pango", "1.0")
    from gi.repository import Pango
    HAVE_PANGO = True
except (ImportError, ValueError):
    HAVE_PANGO = False

SAMPLES = [
    "<p>one</p><p>two</p>",
    '<p>hi <a href="https://x.test/a?b=1&amp;c=2">link</a> &amp; &lt;tag&gt;</p>',
    "<p>line<br>next<br/>third</p>",
    "<blockquote><p>quoted <b>bold</b></p><p>more</p></blockquote><p>after</p>",
    "<ul><li>a</li><li>b<ol><li>x</li><li>y</li></ol></li></ul>",
    "<pre><code>a  b\n  c</code></pre>",
    "<p><b>unclosed <i>both",
    '<p><a href="javascript:alert(1)">bad</a> <script>x</script></p>',
    '<p><span class="h-card"><a href="https://m.test/@a">@<span>a</span></a></span></p>',
    "<p>it's \"quoted\"</p>",
]


class PangoTest(unittest.TestCase):
    def test_paragraphs_and_breaks(self):
        self.assertEqual(markup("<p>one</p><p>two</p>"), "one\n\ntwo")
        self.assertEqual(markup("<p>a<br>b</p>"), "a\nb")
        self.assertEqual(markup("<p>  lots   of\n space </p>"), "lots of space")

    def test_escaping_and_links(self):
        m = markup('<p>x &amp; <a href="https://e.test/?a=1&amp;b=2">y</a></p>')
        self.assertEqual(m, 'x &amp; <a href="https://e.test/?a=1&amp;b=2">y</a>')

    def test_bad_links_lose_their_href(self):
        m = markup('<p><a href="javascript:alert(1)">bad</a></p>')
        self.assertNotIn("javascript", m)
        self.assertIn("bad", m)

    def test_quote_and_lists(self):
        self.assertEqual(markup("<blockquote><p>q</p></blockquote><p>a</p>"),
                         "<i>▎ q</i>\n\na")
        self.assertEqual(markup("<p>before</p><blockquote><p>q</p></blockquote>"),
                         "before\n\n<i>▎ q</i>")
        self.assertEqual(markup("<ul><li>a</li><li>b</li></ul>"), "• a\n• b")
        self.assertEqual(markup("<ol><li>a</li><li>b</li></ol>"), "1. a\n2. b")

    def test_simple_tags(self):
        self.assertEqual(markup("<p><strong>b</strong> <em>i</em> <del>s</del> <code>c</code>"
                                "</p>"), "<b>b</b> <i>i</i> <s>s</s> <tt>c</tt>")

    @unittest.skipUnless(HAVE_PANGO, "no Pango here")
    def test_pango_accepts_every_sample(self):
        for html in SAMPLES:
            m = markup(html)
            try:
                # <a> is Gtk.Label's own, the rest must be Pango's
                Pango.parse_markup(re.sub(r"</?a\b[^>]*>", "", m), -1, "\0")
            except Exception as e:  # noqa: BLE001
                self.fail(f"{html!r} → {m!r}: {e}")


if __name__ == "__main__":
    unittest.main()
