"""Small pure helpers, no server and no Qt: reading an outbox page by page, fedtail's
line in a private note."""

import unittest

from fedtail.core import replies
from fedtail.core.model import note_followed, note_text, note_with_followed
from fedtail.model.text import join_quote, quote_lines

PUB = "https://www.w3.org/ns/activitystreams#Public"
BASE = "https://far.example/outbox"


def create(n, to=(PUB,)):
    return {"type": "Create", "to": list(to), "object": f"https://far.example/n/{n}"}


class OutboxPageTest(unittest.TestCase):
    def docs(self):
        return {
            BASE: {"type": "OrderedCollection", "first": f"{BASE}?p=1"},
            f"{BASE}?p=1": {"type": "OrderedCollectionPage", "next": f"{BASE}?p=2",
                            "orderedItems": [create(5), create(4, to=["followers"])]},
            f"{BASE}?p=2": {"type": "OrderedCollectionPage",
                            "orderedItems": [{"type": "Announce", "to": [PUB],
                                              "object": "https://else.example/x"},
                                             create(3), create(2)]},
        }

    def test_pages_and_the_end(self):
        docs = self.docs()
        uris, nxt = replies.outbox_page(docs.get, BASE, limit=1)
        self.assertEqual(uris, ["https://far.example/n/5"])  # not followers-only
        self.assertEqual(nxt, f"{BASE}?p=2")
        uris, nxt = replies.outbox_page(docs.get, nxt, limit=10)
        self.assertEqual(uris, ["https://far.example/n/3", "https://far.example/n/2"])
        self.assertIsNone(nxt)  # no boosts, and that was the last page

    def test_skip_what_is_here(self):
        docs = self.docs()
        uris, _nxt = replies.outbox_page(docs.get, BASE, limit=10,
                                         skip={"https://far.example/n/5"})
        self.assertNotIn("https://far.example/n/5", uris)
        self.assertIn("https://far.example/n/3", uris)

    def test_broken_answers(self):
        self.assertEqual(replies.outbox_page(lambda u: None, BASE), ([], None))
        self.assertEqual(replies.outbox_page(lambda u: "html", BASE), ([], None))
        docs = {BASE: {"type": "OrderedCollection", "first": f"{BASE}?p=1"}}
        self.assertEqual(replies.outbox_page(docs.get, BASE), ([], None))  # page gone

    def test_newest_posts_keep_their_limit(self):
        docs = self.docs()
        self.assertEqual(replies.outbox_post_uris(docs.get, BASE, limit=2),
                         ["https://far.example/n/5", "https://far.example/n/3"])


class QuoteReplyTest(unittest.TestCase):
    def test_quote_lines(self):
        self.assertEqual(quote_lines("@bob @al@x.org Раз.\n\nДва.", strip_mentions=True),
                         "> Раз.\n>\n> Два.\n\n")
        self.assertEqual(quote_lines("@bob тут"), "> @bob тут\n\n")  # a selection: as is
        self.assertEqual(quote_lines("  "), "")
        self.assertEqual(quote_lines("a\u2029b", "» "), "» a\n» b\n\n")

    def test_join_quote(self):
        self.assertEqual(join_quote("", "> q"), "")
        self.assertEqual(join_quote("@bob@social.example ", "> q"), "\n")
        self.assertEqual(join_quote("ответ", "> q"), "\n\n")
        self.assertEqual(join_quote("ответ\n", "> q"), "\n")
        self.assertEqual(join_quote("ответ\n\n", "> q"), "")


class NoteLineTest(unittest.TestCase):
    def test_round_trip(self):
        self.assertIsNone(note_followed(""))
        self.assertIsNone(note_followed(None))
        n = note_with_followed("друг детства", "2026-10-18")
        self.assertEqual(n, "друг детства\n\n[fedtail followed 2026-10-18]")
        self.assertEqual(note_followed(n), "2026-10-18")
        self.assertEqual(note_text(n), "друг детства")
        # an empty note: just the line; editing keeps one line, never two
        self.assertEqual(note_with_followed("", "2026-10-18"), "[fedtail followed 2026-10-18]")
        self.assertEqual(note_with_followed(n, "2026-10-19").count("[fedtail"), 1)
        # taken out
        self.assertEqual(note_with_followed(n, None), "друг детства")

    def test_my_own_brackets_stay(self):
        n = "[мой тег] не путать"
        self.assertIsNone(note_followed(n))
        self.assertEqual(note_text(n), n)


class LongFormTest(unittest.TestCase):
    def test_article_and_event(self):
        from fedtail.core.model import long_form_of
        art = long_form_of({"type": "Create", "object": {
            "type": "Article", "id": "https://blog.example/p/1", "name": "Заголовок",
            "contentMap": {"ru": "<p>Весь текст</p>"},
            "url": [{"type": "Link", "mediaType": "text/html",
                     "href": "https://blog.example/hello"}]}})
        self.assertEqual((art["type"], art["name"], art["content"], art["url"]),
                         ("Article", "Заголовок", "<p>Весь текст</p>",
                          "https://blog.example/hello"))
        ev = long_form_of({"type": "Event", "id": "https://events.example/e/7",
                           "name": "Встреча", "startTime": "2026-11-01T18:00:00Z",
                           "location": {"type": "Place", "name": "Библиотека",
                                        "address": {"addressLocality": "Город"}}})
        self.assertEqual(ev["start"], "2026-11-01T18:00:00Z")
        self.assertEqual(ev["location"], "Библиотека, Город")
        self.assertEqual(ev["url"], "https://events.example/e/7")
        for junk in (None, "html", {"type": "Person"}, {"type": "Create"}):
            self.assertIsNone(long_form_of(junk))


def _docs_build():
    import importlib.util
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root / "tools"))
    spec = importlib.util.spec_from_file_location("docs_build", root / "tools" / "docs_build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class DocsBuildTest(unittest.TestCase):
    """tools/docs_build.py owns the generated docs: the feature list and comparison, the
    config reference, the generated parts and every include block."""

    @classmethod
    def setUpClass(cls):
        cls.mod = _docs_build()
        cls.files = cls.mod.build()

    def test_everything_is_up_to_date(self):
        """A changed feature, option, explanation or part — run python3 tools/docs_build.py."""
        stale = [str(p.relative_to(self.mod.ROOT)) for p, text in self.files.items()
                 if not p.exists() or p.read_text("utf-8") != text]
        self.assertEqual(stale, [], "out of date: python3 tools/docs_build.py")

    def test_both_languages_are_built(self):
        root = self.mod.ROOT
        for lang in ("ru", "en"):
            for name in ("features.md", "comparison.md", "config.md", "parts/whats-new.md"):
                self.assertIn(root / "docs" / lang / name, self.files, f"{lang}/{name}")
            self.assertIn("`media.prefetch`", self.files[root / "docs" / lang / "config.md"])
        self.assertIn("| Arts mode |", self.files[root / "docs" / "en" / "features.md"])
        self.assertIn("| Режим arts |", self.files[root / "docs" / "ru" / "features.md"])

    def test_config_reference_rows_are_the_options(self):
        """docs/<lang>/config.md lists every live option of the example once, the same
        rows in both languages. Prose that starts with "key = …" is not an option (the
        0.21.0 reference had rows in one language only, and the website refused it)."""
        import re
        import tomllib
        root = self.mod.ROOT
        rows = {}
        for lang in ("ru", "en"):
            text = self.files[root / "docs" / lang / "config.md"]
            rows[lang] = re.findall(r"^\| `([a-z_]+\.[a-z_]+)` \|", text, re.M)
            example = (root / "fedtail" / "data" / f"config.example.{lang}.toml").read_text(
                "utf-8")
            live = [f"{sec}.{key}" for sec, table in tomllib.loads(example).items()
                    if isinstance(table, dict) for key in table]
            self.assertEqual(sorted(rows[lang]), sorted(live), lang)
        self.assertEqual(rows["ru"], rows["en"])

    def test_config_keys_of_features_exist(self):
        """Every `section.key` in the config column of a feature fedtail has (or lacks)
        is a real option — planned and turned-down ones may name keys yet to be."""
        import re

        from fedtail.core import config
        for ch in self.mod.load_features():
            for f in ch.get("feature", []):
                if f["status"] not in ("has", "partly", "no"):
                    continue
                for lang in ("ru", "en"):
                    text = self.mod._t(f.get("config"), lang) or ""
                    for sec, key in re.findall(r"`([a-z_]+)\.([a-z_]+)", text):
                        # named as the file names it now (config.FILE_LAYOUT)
                        if sec in config.FILE_TABLES or sec in config.DEFAULTS:
                            self.assertIn((sec, key), config.INTERNAL,
                                          f"{f['id']}: {sec}.{key}")

    def test_sources_are_checked(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            Path(d, "01-x.toml").write_text(
                'id = "x"\ntitle.ru = "Икс"\ntitle.en = "X"\n\n[[feature]]\nid = "a"\n'
                'status = "has"\nname = "Без перевода"\n\n[[feature]]\nid = "a"\n'
                'status = "planned"\nsince = "0.1.0"\nname.ru = "Б"\n', "utf-8")
            with self.assertRaises(self.mod.DocsError) as e:
                self.mod.load_features(Path(d))
        msg = str(e.exception)
        self.assertIn("name is Russian", msg)
        self.assertIn("since — which version", msg)
        self.assertIn("the id is taken", msg)
        self.assertIn("since — only for what fedtail has", msg)
        self.assertIn("name has no en", msg)

    def test_includes(self):
        from pathlib import Path
        root = self.mod.ROOT
        text = "a\n<!-- include: parts/principles shift=1 -->\nSTALE\n<!-- /include -->\nb\n"
        out = self.mod.expand(text, root / "docs" / "en" / "x.md", {})
        self.assertNotIn("STALE", out)
        self.assertIn("Nothing jumps", out)
        self.assertTrue(out.endswith("<!-- /include -->\nb\n"))
        ru = self.mod.expand(text, root / "README.ru.md", {})
        self.assertIn("Ничего не дёргается", ru)
        with self.assertRaises(self.mod.DocsError):
            self.mod.expand(text, root / "docs" / "DESIGN.md", {})  # which language?
        self.assertEqual(self.mod.lang_of(root / "fedtail" / "data" / "help" / "ru" / "a.md"),
                         "ru")
        self.assertIsNone(self.mod.lang_of(Path(root / "docs" / "ARCHITECTURE.md")))


try:
    import PySide6  # noqa: F401
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


@unittest.skipUnless(HAVE_QT, "PySide6 is not installed")
class DecodeSideTest(unittest.TestCase):
    """A feed picture is decoded for its box, not at 1200 px."""

    class Lab:
        def __init__(self, dpr):
            self.dpr = dpr

        def devicePixelRatioF(self):
            return self.dpr

    def test_box_size(self):
        from fedtail.frontends.qt.card import _decode_side
        cfg = {"ui": {"image_decode": "box"}}
        # a 4000x3000 photo in a 560x420 box: 560 wide is enough, in steps of 100
        self.assertEqual(_decode_side(self.Lab(1.0), 560, 420, 4000, 3000, cfg), 600)
        # a HiDPI screen needs twice the pixels; never past 1200
        self.assertEqual(_decode_side(self.Lab(2.0), 560, 420, 4000, 3000, cfg), 1200)
        # filling a square cell with a wide picture: the short side reaches the box
        self.assertEqual(_decode_side(self.Lab(1.0), 150, 150, 3000, 1000, cfg), 500)
        # sizes unknown: room to spare
        self.assertEqual(_decode_side(self.Lab(1.0), 150, 230, None, None, cfg), 500)
        self.assertIsNone(_decode_side(self.Lab(1.0), 560, 420, 4000, 3000,
                                       {"ui": {"image_decode": "full"}}))


if __name__ == "__main__":
    unittest.main()
