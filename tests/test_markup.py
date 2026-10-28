"""The editor's formatting buttons (frontends/common/markup.py): every format put on and
taken off, with and without a selection, at the edges of the text, and the positions an
editor counting in UTF-16 needs."""

import unittest

from fedtail.frontends.common import markup
from fedtail.frontends.common.markup import Edit, apply


def sel(text):
    """'a [b] c' → ('a b c', 2, 3): brackets mark the selection, '|' the cursor."""
    if "|" in text:
        i = text.index("|")
        return text.replace("|", ""), i, i
    s = text.index("[")
    e = text.index("]") - 1
    return text.replace("[", "", 1).replace("]", "", 1), s, e


def shown(edit):
    t = edit.text
    if edit.start == edit.end:
        return t[:edit.start] + "|" + t[edit.start:]
    return t[:edit.start] + "[" + t[edit.start:edit.end] + "]" + t[edit.end:]


class InlineTest(unittest.TestCase):
    def check(self, name, before, after):
        self.assertEqual(shown(apply(name, *sel(before))), after)

    def test_on_and_off(self):
        self.check("bold", "say [hi] there", "say **[hi]** there")
        self.check("bold", "say **[hi]** there", "say [hi] there")
        self.check("italic", "say [hi]", "say *[hi]*")
        self.check("italic", "say *[hi]*", "say [hi]")
        self.check("strike", "[no]", "~~[no]~~")
        self.check("strike", "~~[no]~~", "[no]")
        self.check("code", "run [ls]", "run `[ls]`")
        self.check("code", "run `[ls]`", "run [ls]")

    def test_selected_with_its_marks(self):
        self.check("bold", "say [**hi**]", "say [hi]")
        self.check("italic", "[*hi*]", "[hi]")
        self.check("strike", "[~~x~~]", "[x]")

    def test_bold_and_italic_tell_each_other_apart(self):
        self.check("italic", "**[hi]**", "***[hi]***")  # bold stays, italic added
        self.check("bold", "*[hi]*", "***[hi]***")
        self.check("italic", "***[hi]***", "**[hi]**")
        self.check("bold", "***[hi]***", "*[hi]*")
        self.check("bold", "[*hi*]", "**[*hi*]**")  # italic selected whole: bold around it

    def test_no_selection_puts_the_cursor_between(self):
        self.check("bold", "a |b", "a **|**b")
        self.check("bold", "a **|**b", "a |b")
        self.check("code", "|", "`|`")

    def test_spaces_at_the_edges_stay_out(self):
        self.check("bold", "a[ word ]b", "a **[word]** b")
        self.check("italic", "[  ]", "  *|*")

    def test_code_of_several_lines_is_a_block(self):
        self.assertEqual(shown(apply("code", *sel("x\n[a\nb]\ny"))),
                         "x\n```\n[a\nb]\n```\ny")
        self.assertEqual(shown(apply("code", *sel("x [a\nb] y"))), "x \n```\n[a\nb]\n```\n y")
        self.assertEqual(shown(apply("code", *sel("[```\na\nb\n```]"))), "[a\nb]")

    def test_the_order_of_start_and_end_and_out_of_range(self):
        self.assertEqual(apply("bold", "hi", 2, 0), Edit("**hi**", 2, 4))
        self.assertEqual(apply("bold", "hi", -5, 99), Edit("**hi**", 2, 4))

    def test_unknown(self):
        with self.assertRaises(KeyError):
            apply("blink", "x", 0, 1)


class LineTest(unittest.TestCase):
    def check(self, name, before, after):
        self.assertEqual(shown(apply(name, *sel(before))), after)

    def test_quote_and_list_on_every_line_touched(self):
        self.check("quote", "x\n[a\nb]\ny", "x\n[> a\n> b]\ny")
        self.check("list", "a[b\nc]d", "[- ab\n- cd]")
        self.check("list", "[- a\n- b]", "[a\nb]")
        self.check("quote", "[> a\n>\n> b]", "[a\n\nb]")

    def test_empty_lines_inside_stay_empty(self):
        self.check("list", "[a\n\nb]", "[- a\n\n- b]")

    def test_mixed_lines_get_it_all(self):
        self.check("quote", "[> a\nb]", "[> > a\n> b]")

    def test_the_cursor_rides_with_its_line(self):
        self.check("quote", "ab|c", "> ab|c")
        self.check("quote", "> ab|c", "ab|c")
        self.check("list", "|", "- |")
        self.check("list", "- |", "|")

    def test_a_selection_ending_at_a_line_break_takes_that_line_only(self):
        self.check("list", "[a\n]b", "[- a]\nb")


class LinkTest(unittest.TestCase):
    def test_words_become_the_link_the_address_selected(self):
        e = apply("link", *sel("see [docs] now"))
        self.assertEqual(shown(e), "see [docs]([https://]) now")

    def test_an_address_becomes_the_address(self):
        e = apply("link", *sel("[https://x.org/a]"))
        self.assertEqual(shown(e), "[|](https://x.org/a)")

    def test_nothing_selected(self):
        self.assertEqual(shown(apply("link", *sel("|"))), "[]([https://])")


class RestTest(unittest.TestCase):
    def test_shown_by_the_flag(self):
        self.assertTrue(markup.shown({"post": {"format_bar": "auto"}}, True))
        self.assertFalse(markup.shown({"post": {"format_bar": "auto"}}, False))
        self.assertTrue(markup.shown({"post": {"format_bar": "on"}}, False))
        self.assertFalse(markup.shown({"post": {"format_bar": "off"}}, True))
        self.assertTrue(markup.shown({}, True))
        self.assertFalse(markup.shown(None, False))

    def test_tips_and_names(self):
        b = markup.BY_NAME["bold"]
        self.assertEqual(markup.tip(b, "Bold"), "Bold (Ctrl+B)")
        self.assertEqual(markup.tip(markup.BY_NAME["strike"], "Strike"), "Strike")
        self.assertEqual([f.name for f in markup.FORMATS],
                         ["bold", "italic", "strike", "code", "link", "quote", "list"])

    def test_every_tip_has_its_words(self):
        from fedtail import i18n
        for lang in ("ru", "en"):
            i18n.setup(lang)
            for f in markup.FORMATS:
                self.assertNotEqual(i18n._(f.tip), f.tip, (lang, f.tip))
        i18n.setup("en")

    def test_utf16_positions(self):
        t = "a😀b"
        self.assertEqual(markup.utf16(t, 2), 3)
        self.assertEqual(markup.from_utf16(t, 3), 2)
        self.assertEqual(markup.from_utf16(t, 2), 2)  # inside the pair: after it
        self.assertEqual(markup.from_utf16(t, 99), 3)
        self.assertEqual(markup.from_utf16(t, 0), 0)


if __name__ == "__main__":
    unittest.main()
