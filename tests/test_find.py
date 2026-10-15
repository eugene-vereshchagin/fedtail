import unittest

from fedtail.frontends.findtext import haystack, matches

POST = {
    "id": "1", "content": "<p>Лучший говорящий <b>куст</b> в мире! #игры</p>",
    "spoiler_text": "", "media_attachments": [{"description": "Ёжик в тумане"}],
    "account": {"display_name": "Lýra Selén", "acct": "lyraselen@stars.example"},
}
BOOST = {"id": "2", "reblog": POST, "account": {"display_name": "Арсен", "acct": "arsen"}}


class FindTest(unittest.TestCase):
    def test_words_any_order_any_case(self):
        h = haystack(POST, "adt")
        self.assertTrue(matches("КУСТ лучший", h))
        self.assertTrue(matches("#игры", h))
        self.assertTrue(matches("#adt", h))
        self.assertTrue(matches("@lyraselen", h))
        self.assertTrue(matches("ежик", h))  # ё = е, alt text counts
        self.assertFalse(matches("куст огурец", h))
        self.assertFalse(matches("   ", h))

    def test_booster_is_found_too(self):
        self.assertTrue(matches("арсен", haystack(BOOST)))
        self.assertTrue(matches("куст", haystack(BOOST)))


if __name__ == "__main__":
    unittest.main()
