"""The in-app help and the "What's this?" hints, without a display: every page in both
languages, every link and anchor going somewhere real, every hint tied to a real string,
config key and help section, and no F1 anywhere."""

import re
import unittest
from pathlib import Path

from fedtail import i18n
from fedtail.core import config
from fedtail.frontends import helpdocs

ROOT = Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\(([^)\s]+)\)")


class HelpPagesTest(unittest.TestCase):
    def tearDown(self):
        i18n.setup("en")

    def test_the_same_pages_in_both_languages(self):
        ru = [p.name for p in helpdocs.pages("ru")]
        en = [p.name for p in helpdocs.pages("en")]
        self.assertEqual(ru, en)
        self.assertIn("ref/features", ru)
        self.assertIn("ref/config", ru)
        on_disk = sorted(f.stem for f in (ROOT / "fedtail/data/help/ru").glob("*.md"))
        self.assertEqual(sorted(n for n in ru if "/" not in n), on_disk,
                         "every page is in index.md, and every page in it exists")

    def test_every_link_goes_somewhere(self):
        for lang in helpdocs.LANGS:
            for p in helpdocs.pages(lang):
                text = helpdocs.page(lang, p.name)
                self.assertNotIn("<!-- include", text)
                self.assertNotIn("<details>", text)
                for link in LINK.findall(text):
                    t = helpdocs.resolve(link, lang, p.name)
                    where = f"{lang}/{p.name}: {link}"
                    if t.url:
                        self.assertTrue(t.url.startswith(("https://", "mailto:")), where)
                        continue
                    self.assertTrue(helpdocs.exists(lang, t.page), where)
                    if t.anchor:
                        anchors = [a for _, _, a in helpdocs.headings(lang, t.page)]
                        self.assertIn(t.anchor, anchors, where)

    def test_short_pages_lead_to_the_deep_dive(self):
        """Light reading: the topic pages end in links to the full feature list or the
        settings reference."""
        for lang, word in (("ru", "Подробно →"), ("en", "In detail →")):
            for name in ("reading", "search", "writing", "people", "notifications", "look",
                         "trouble", "command-line", "fediverse", "start"):
                self.assertIn(word, helpdocs.page(lang, name), f"{lang}/{name}")

    def test_resolve(self):
        r = helpdocs.resolve
        self.assertEqual(r("/docs/ru/features.md#ленты", "ru").page, "ref/features")
        self.assertEqual(r("/docs/ru/features.md#ленты", "ru").anchor, "ленты")
        self.assertTrue(r("/CHANGELOG.md", "en").url.endswith("/blob/main/CHANGELOG.md"))
        self.assertEqual(r("https://example.test/x", "en").url, "https://example.test/x")
        self.assertEqual(r("#lanes", "en", "ref/features").page, "ref/features")
        self.assertEqual(r("../reading.md", "en", "ref/features").page, "reading")
        self.assertEqual(r("ref/config.md", "en").page, "ref/config")
        self.assertIn("github.com", r("../../../../docs/DESIGN.md", "ru").url)
        self.assertEqual(helpdocs.language("de"), "en")

    def test_slug_like_github(self):
        self.assertEqual(helpdocs.slug("Что нового и что дальше"), "что-нового-и-что-дальше")
        self.assertEqual(helpdocs.slug("In a lane: Ctrl+F"), "in-a-lane-ctrlf")
        self.assertEqual(helpdocs.slug("`[ui]`"), "ui")

    def test_search(self):
        hits = helpdocs.search("ru", "шторка")
        self.assertTrue(hits)
        self.assertIn("reading", [p.name for p, _ in hits])
        self.assertEqual(helpdocs.search("en", "   "), [])
        self.assertEqual(helpdocs.search("en", "nosuchwordanywhere"), [])
        both = [p.name for p, _ in helpdocs.search("en", "curtain esc")]
        self.assertIn("reading", both)


class HintsTest(unittest.TestCase):
    def tearDown(self):
        i18n.setup("en")

    def test_the_same_hints_in_both_languages_and_real_keys(self):
        ru, en = helpdocs.hints("ru"), helpdocs.hints("en")
        self.assertEqual(sorted(ru), sorted(en))
        self.assertGreater(len(ru), 40)
        for lang, table in (("ru", ru), ("en", en)):
            strings = i18n.strings(lang)
            for key, h in table.items():
                self.assertIn(key, strings, f"{lang}: {key} is no interface string")
                self.assertTrue(h.get("text", "").strip(), f"{lang}: {key}")
                for opt in filter(None, (h.get("config") or "").split(",")):
                    sec, name = opt.strip().split(".")
                    self.assertIn(name, config.DEFAULTS.get(sec, {}), f"{lang}: {key}: {opt}")
                if h.get("help"):
                    page, _, anchor = h["help"].partition("#")
                    page = page[:-3] if page.endswith(".md") else page
                    self.assertTrue(helpdocs.exists(lang, page), f"{lang}: {key}: {page}")
                    if anchor:
                        anchors = [a for *_, a in helpdocs.headings(lang, page)]
                        self.assertIn(anchor, anchors, f"{lang}: {key}: {h['help']}")

    def test_found_by_the_tooltip_the_button_shows_anyway(self):
        i18n.setup("ru")
        self.assertEqual(helpdocs.hint_for("Ответить")[0], "reply")
        self.assertEqual(helpdocs.hint_for(i18n._("refresh") + " (F5)")[0], "refresh")
        lane = i18n._("tip_home") + " (Alt+2)\n" + i18n._("lane_codeword", name="home")
        self.assertEqual(helpdocs.hint_for(lane)[0], "tip_home")
        self.assertIsNone(helpdocs.hint_for("какая-то чужая подсказка"))
        self.assertEqual(helpdocs.hint_for("", key="cmd_tip")[0], "cmd_tip")
        i18n.setup("en")
        self.assertEqual(helpdocs.hint_for("Reply")[0], "reply")

    def test_hint_html(self):
        i18n.setup("en")
        key, h = helpdocs.hint_for("Reply")
        out = helpdocs.hint_html("Reply", h)
        self.assertIn("<b>Reply</b>", out)
        self.assertIn("post.reply_never_wider", out)
        self.assertIn("Writing", out)  # the help page by its title
        self.assertNotIn("<script", helpdocs.hint_html("<script>", h))


class NoF1Test(unittest.TestCase):
    def test_no_shortcut_on_f1(self):
        """F1 sits next to Esc: a missed Esc must not open anything."""
        for f in (ROOT / "fedtail" / "frontends").rglob("*.py"):
            src = f.read_text("utf-8")
            for bad in ('"F1"', "'F1'", "Key_F1", "HelpContents", "WhatsThis"):
                self.assertNotIn(bad, src, f"{f.name}: {bad}")


if __name__ == "__main__":
    unittest.main()
