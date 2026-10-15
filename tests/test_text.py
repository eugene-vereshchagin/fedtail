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


if __name__ == "__main__":
    unittest.main()
