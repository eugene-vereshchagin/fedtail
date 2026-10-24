"""core/model.py at its edges: ids of different kinds, snippets of posts without words,
long-form objects in the shapes servers give them, and "is this the post I just sent"."""

import time
import unittest

from fedtail.core import model


class ModelEdgesTest(unittest.TestCase):
    def test_id_after(self):
        self.assertTrue(model.id_after("100", "99"))
        self.assertTrue(model.id_after("01HZZZZ", "9ZZZZ"))  # ULIDs of different lengths
        self.assertFalse(model.id_after("abc", "abd"))

    def test_snippet_without_words(self):
        self.assertEqual(model.snippet({"content": "", "spoiler_text": "spoiler"}), "spoiler")
        self.assertEqual(model.snippet({"content": "", "media_attachments": [{}, {}]}),
                         "[2 × media]")
        self.assertEqual(model.snippet({"content": "<p>" + "a" * 50 + "</p>"}, 10),
                         "a" * 9 + "…")

    def test_long_form_shapes(self):
        self.assertIsNone(model.long_form_of("nope"))
        self.assertIsNone(model.long_form_of({"type": "Person"}))
        got = model.long_form_of({"type": "Create", "object": {
            "type": ["Object", "Article"], "nameMap": {"ru": "Заголовок"},
            "url": [{"href": "https://x/a.json", "mediaType": "application/json"},
                    {"href": "https://x/a", "mediaType": "text/html"}],
            "location": [{"name": "Tbilisi", "address": {"addressLocality": "Tbilisi",
                                                         "addressCountry": "GE"}}]}})
        self.assertEqual(got["type"], "Article")
        self.assertEqual(got["name"], "Заголовок")
        self.assertEqual(got["url"], "https://x/a")
        self.assertEqual(got["location"], "Tbilisi, Tbilisi, GE")
        got = model.long_form_of({"type": ["Note"], "url": {"href": "https://x/n"},
                                  "location": "somewhere", "id": "https://x/id"})
        self.assertEqual((got["url"], got["location"]), ("https://x/n", "somewhere"))
        got = model.long_form_of({"type": "Event", "location": [], "url": []})
        self.assertEqual((got["url"], got["location"]), ("", ""))
        self.assertIsNone(model.long_form_of({"type": []}))

    def test_looks_sent(self):
        now = time.time()
        made = time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(now))
        st = {"id": "1", "created_at": made, "content": "<p>Привет, мир!</p>"}
        self.assertTrue(model.looks_sent(st, "привет мир", None, now))
        self.assertFalse(model.looks_sent(dict(st, created_at="garbage"), "привет", None, now))
        # a text with no words of three letters: compared whole
        self.assertTrue(model.looks_sent(dict(st, content="<p>ok</p>"), "ok", None, now))
        self.assertTrue(model.looks_sent(dict(st, content=""), "@bob", None, now))
        self.assertFalse(model.looks_sent(dict(st, content="<p>no</p>"), "ok", None, now))


if __name__ == "__main__":
    unittest.main()
