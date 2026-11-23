"""The config's [keys] (core/keys.py): a key read once and said in every toolkit's
words, what the posts' keys mean (common/postkeys.meaning), the terminal's keymap, and
F1 never a shortcut whatever the file says."""

import contextlib
import io
import unittest

from fedtail.core import config, keys
from fedtail.frontends.common import postkeys


def cfg(**over):
    c, _w = config.validate({"keys": over} if over else {})
    return c


class KeyTest(unittest.TestCase):
    def test_a_key_in_every_toolkits_words(self):
        for spec, words, qt, gtk, textual, web in (
                ("Ctrl+N", "Ctrl+N", "Ctrl+N", "<Control>n", "ctrl+n", "n"),
                ("shift+f3", "Shift+F3", "Shift+F3", "<Shift>F3", "shift+f3", "F3"),
                ("j", "j", "J", "j", "j", "j"),
                ("]", "]", "]", "bracketright", "right_square_bracket", "]"),
                ("-", "-", "-", "minus", "minus", "-"),
                ("Enter", "Enter", "Return", "Return", "enter", "Enter"),
                ("return", "Enter", "Return", "Return", "enter", "Enter"),
                ("PgDn", "PgDn", "PgDown", "Page_Down", "pagedown", "PageDown"),
                ("Ctrl++", "Ctrl++", "Ctrl++", "<Control>plus", "ctrl+plus", "+")):
            with self.subTest(spec=spec):
                k = keys.parse(spec)
                self.assertEqual((k.words(), k.qt(), k.gtk(), k.textual(), k.web()["key"]),
                                 (words, qt, gtk, textual, web))

    def test_what_is_no_key(self):
        for spec in ("", "Hyper+x", "Ctrl+", "Ctrl+Bogus"):
            with self.subTest(spec=spec), self.assertRaises(ValueError):
                keys.parse(spec)

    def test_several_keys_and_none(self):
        got, wrong = keys.read("o Enter")
        self.assertEqual([k.name for k in got], ["o", "enter"])
        self.assertEqual(wrong, [])
        self.assertEqual(keys.read(""), ([], []))
        self.assertEqual(keys.of(cfg(reply=""), "reply"), [])
        self.assertEqual(keys.hint(cfg(reply=""), "reply"), "")
        self.assertEqual(keys.hint(cfg(), "new_post"), " (Ctrl+N)")
        self.assertEqual(keys.words(cfg(), "open_thread"), "o, Enter")

    def test_f1_is_never_a_shortcut(self):
        """The principles' last line: F1 and Shift+F1 sit next to Esc."""
        c, warnings = config.validate({"keys": {"refresh": "F1 F5", "quit": "Shift+F1"}})
        self.assertEqual([k.name for k in keys.of(c, "refresh")], ["f5"])
        self.assertEqual(keys.of(c, "quit"), [])
        self.assertEqual(sum("F1" in w for w in warnings), 2)

    def test_the_config_says_what_is_wrong_and_starts(self):
        c, warnings = config.validate({"keys": {"like": "j", "boost": "Hyper+b"}})
        self.assertTrue(any("keys.like" in w and "next_post" in w for w in warnings))
        self.assertTrue(any("keys.boost" in w for w in warnings))
        self.assertEqual(keys.table(c)[keys.parse("j")], "next_post")  # the first keeps it
        self.assertEqual(set(config.DEFAULTS["keys"]), set(keys.ACTIONS))

    def test_events_of_the_toolkits(self):
        self.assertEqual(keys.from_gdk("bracketright"), keys.parse("]"))
        self.assertEqual(keys.from_gdk("KP_Enter"), keys.parse("Enter"))
        self.assertEqual(keys.from_gdk("n", ctrl=True), keys.parse("Ctrl+N"))
        self.assertEqual(keys.from_gdk("F3", shift=True), keys.parse("Shift+F3"))
        self.assertEqual(keys.from_qt("Return"), keys.parse("Enter"))
        self.assertEqual(keys.from_qt("J"), keys.parse("j"))
        self.assertEqual(keys.from_qt("]", shift=True), keys.parse("]"))  # typed with Shift
        self.assertEqual(keys.from_qt("F5"), keys.parse("F5"))


class MeaningTest(unittest.TestCase):
    def test_the_authors_keys(self):
        c = cfg()
        for spec, what in (("j", ("walk", 1)), ("k", ("walk", -1)), ("r", ("act", "reply")),
                           ("f", ("act", "fav")), ("b", ("act", "boost")),
                           ("m", ("act", "bookmark")), ("o", ("act", "thread")),
                           ("Enter", ("act", "thread")), ("]", ("top", 1)),
                           ("[", ("top", -1)), ("-", ("fold", None))):
            self.assertEqual(postkeys.meaning(c, keys.parse(spec)), what, spec)
        self.assertIsNone(postkeys.meaning(c, keys.parse("x")))
        self.assertIsNone(postkeys.meaning(c, keys.parse("Ctrl+N")))  # the window's

    def test_ones_own_keys(self):
        c = cfg(next_post="n Down", reply="Ctrl+R", like="")
        self.assertEqual(postkeys.meaning(c, keys.parse("n")), ("walk", 1))
        self.assertEqual(postkeys.meaning(c, keys.parse("Down")), ("walk", 1))
        self.assertIsNone(postkeys.meaning(c, keys.parse("j")))
        self.assertEqual(postkeys.meaning(c, keys.parse("Ctrl+R")), ("act", "reply"))
        self.assertIsNone(postkeys.meaning(c, keys.parse("r")))
        self.assertIsNone(postkeys.meaning(c, keys.parse("f")))  # like: no key at all

    def test_post_keys_off_means_none_of_them(self):
        c = cfg()
        c["ui"]["post_keys"] = False
        self.assertIsNone(postkeys.meaning(c, keys.parse("j")))

    def test_the_pages_own_keys_by_name(self):
        c, warnings = config.validate({"web": {"keys": ["new = c Ctrl+M", "bogus = x",
                                                        "quote = F1", "nonsense"]}})
        self.assertEqual(sum("web.keys" in w for w in warnings), 3)
        rows = {(r["action"], r["key"], r["ctrl"]) for r in keys.page_table(c)}
        self.assertIn(("new", "c", False), rows)
        self.assertIn(("new", "m", True), rows)
        self.assertNotIn("quote", {r[0] for r in rows})  # F1: never, so no key at all
        self.assertIn(("refresh", "r", False), rows)  # (Shift+R: shift told apart)
        # a key of the posts wins over the page's own on the same key
        c2, _w = config.validate({"web": {"keys": ["new = j"]}})
        self.assertNotIn("new", {r["action"] for r in keys.page_table(c2)})

    def test_the_pages_table(self):
        c = cfg(reply="Ctrl+R")
        table = keys.web_table(c, keys.POSTS)
        self.assertIn({"action": "reply", "key": "r", "ctrl": True, "alt": False,
                       "shift": False}, table)
        self.assertNotIn("new_post", {row["action"] for row in table})  # the browser's own


class TerminalKeymapTest(unittest.TestCase):
    def setUp(self):
        try:
            from fedtail.frontends.tui import app, keymap
        except ImportError:
            self.skipTest("no Textual here")
        self.app, self.keymap = app, keymap

    def test_every_binding_has_a_name(self):
        from textual.binding import Binding
        for cls in self.app.SCREENS:
            for b in cls.__dict__.get("BINDINGS", ()):
                self.assertIsInstance(b, Binding)
                self.assertTrue(b.id, f"{cls.__name__}: {b.key}")
        known = self.keymap.ids(*self.app.SCREENS)
        for bid in self.keymap.FROM_KEYS:
            self.assertIn(bid, known)

    def test_the_posts_keys_follow_the_config_and_tui_keys_go_over(self):
        c = cfg(reply="a", next_comment="n")
        c["tui"]["keys"] = ["quit = Ctrl+Q", "command = g Ctrl+L", "nonsense",
                            "no_such = x", "refresh = F1"]
        known = self.keymap.ids(*self.app.SCREENS)
        with self.assertLogs("fedtail.frontends.tui.keymap", level="WARNING") as logs:
            got = self.keymap.keymap(c, known)
        self.assertEqual(got["reply"], "a")
        self.assertEqual(got["top_comment(1)"], "n")
        self.assertEqual(got["cursor_down"], "j")
        self.assertEqual(got["quit"], "ctrl+q")
        self.assertEqual(got["command"], "g,ctrl+l")
        self.assertNotIn("no_such", got)
        self.assertNotIn("refresh", got)  # F1: never
        self.assertEqual(len(logs.output), 3)

    def test_the_command_lists_them(self):
        from fedtail.__main__ import _keys
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(_keys(cfg(reply="a")), 0)
        text = out.getvalue()
        self.assertRegex(text, r"new_post\s+Ctrl\+N")
        self.assertRegex(text, r"\n  reply\s+a\n")
        self.assertRegex(text, r"\n  quit\s+")


class NewSwitchesTest(unittest.TestCase):
    """What the audit of 23.11 found nailed in, now settings."""

    def test_a_failed_connect_is_tried_again_when_the_config_says(self):
        from fedtail.frontends.common.connecting import AGAIN_SECONDS, trouble
        self.assertEqual(trouble("ReadTimeout: slow")["again"], AGAIN_SECONDS)
        c, _w = config.validate({"server": {"retry_seconds": 45}})
        self.assertEqual(trouble("ReadTimeout: slow", c)["again"], 45)
        self.assertTrue(trouble("HTTP 401: no", c)["relogin"])
        with self.assertRaises(config.ConfigError):
            config.validate({"server": {"retry_seconds": 1}})


if __name__ == "__main__":
    unittest.main()
