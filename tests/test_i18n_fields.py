"""No word of the interface may have a field named like _()'s own argument: `_("x",
key=…)` is "got multiple values for argument 'key'" — "Why is it here?" fell over on a
condition that didn't match (why_not_cond said {key})."""

import inspect
import re
import string
import unittest

from fedtail import i18n


class FieldsTest(unittest.TestCase):
    def test_no_field_named_like_the_lookup_argument(self):
        own = set(inspect.signature(i18n._).parameters) - {"kw"}
        bad = []
        for lang, words in i18n._STRINGS.items():
            for k, v in words.items():
                for text in v if isinstance(v, list) else [v]:
                    fields = {f for _l, f, _s, _c in string.Formatter().parse(text) if f}
                    fields = {re.split(r"[.\[]", f)[0] for f in fields}
                    bad += [f"{lang}:{k}:{{{f}}}" for f in fields & own]
        self.assertEqual(bad, [])

    def test_why_not_cond_says_its_reason(self):
        i18n.setup("en")
        self.assertIn("text", i18n._("why_not_cond", n=1, line="a = b", what="text"))


if __name__ == "__main__":
    unittest.main()
