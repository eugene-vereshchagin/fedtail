"""The phone's string resources: what Android's resource compiler refuses (28.10: a bare
apostrophe in "the key's QR code" failed the whole build) is caught here, on the desk,
and both languages have the same strings."""

import re
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

RES = Path(__file__).resolve().parent.parent / "android" / "app" / "src" / "main" / "res"
FILES = {"en": RES / "values" / "strings.xml", "ru": RES / "values-ru" / "strings.xml"}


def strings(path):
    return {e.get("name"): "".join(e.itertext()) for e in ET.parse(path).getroot()
            if e.tag == "string"}


class AndroidStringsTest(unittest.TestCase):
    def test_what_aapt_refuses(self):
        for lang, path in FILES.items():
            for name, text in strings(path).items():
                with self.subTest(lang=lang, name=name):
                    quoted = len(text) >= 2 and text[0] == text[-1] == '"'
                    if not quoted:
                        self.assertIsNone(re.search(r"(?<!\\)['\"]", text),
                                          "an apostrophe or quote unescaped: write \\' or \\\"")
                    self.assertIsNone(re.search(r"(?<!\\)@(?![a-z]+/)", text[:1]),
                                      "a leading @ is a reference: write \\@")

    def test_both_languages_have_the_same(self):
        # the app's name is one in every language: in values/ only
        self.assertEqual(set(strings(FILES["en"])) - {"app_name"}, set(strings(FILES["ru"])))


if __name__ == "__main__":
    unittest.main()
