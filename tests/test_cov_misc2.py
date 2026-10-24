"""Themes of one's own (themefile): broken files, borrowed pictures and sounds that
aren't there, wrong values, the copies kept in ~/.config; the icons' styles (iconpack);
the HTML cleaner's edge cases (richtext); the help's Markdown (mdhtml)."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fedtail.frontends import iconpack, mdhtml, richtext, themefile


class ThemeFileTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        p = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self._tmp.name})
        p.start()
        self.addCleanup(p.stop)
        self.dir = themefile.user_dir()
        self.dir.mkdir(parents=True)

    def theme(self, name, text):
        (self.dir / f"{name}.toml").write_text(text, "utf-8")

    def test_layouts_of_a_broken_theme_and_the_default(self):
        self.theme("broken", "layouts = [\n")
        self.assertEqual(themefile.layouts_of("broken"), themefile.LAYOUT_KINDS)
        self.theme("plain", 'name = "plain"\n')
        self.assertEqual(themefile.layouts_of("plain"), themefile.LAYOUT_KINDS)
        self.theme("odd", 'layouts = ["wide"]\n')
        self.assertEqual(themefile.layouts_of("odd"), themefile.LAYOUT_KINDS)
        with self.assertRaises(themefile.ThemeError):
            themefile.load("broken")

    def test_borrowed_sets_that_arent_there(self):
        self.theme("borrow", 'inherit = "system"\n[pictures]\nfrom = "nope"\n'
                             '[sound]\nfrom = "nope"\n')
        _t, warnings = themefile.load("borrow")
        self.assertTrue(any(w.startswith("pictures.from") for w in warnings))
        self.assertTrue(any(w.startswith("sound.from") for w in warnings))

    def test_font_files_of_a_copied_builtin_theme(self):
        self.theme("bad", 'inherit = "paper"\n[font]\nfiles = ["a.ttf", 3]\n')
        with self.assertRaisesRegex(themefile.ThemeError, "list of text"):
            themefile.load("bad")  # a number among the files: skipped, then refused
        self.theme("mine", 'inherit = "paper"\n[font]\n'
                           'files = ["fonts/none.ttf", "fonts/Arimo-Variable.ttf"]\n')
        t, _w = themefile.load("mine")
        # its own where it has one (or nothing built in by that name); else the built-in
        self.assertEqual(t["font"]["files"][-2:],
                         [str(self.dir / "fonts/none.ttf"),
                          str(themefile.BUILTIN_DIR / "fonts/Arimo-Variable.ttf")])

    def test_validate_says_what_is_wrong(self):
        ref = themefile.reference()
        bad = {"nonsense": {}, "pictures": {"colors": "red"}}
        self.assertIn("unknown section [nonsense]",
                      themefile.validate({"nonsense": {}}, ref))
        for theme, words in (
                ({"pictures": {"colors": "red"}}, "must be a table"),
                ({"pictures": {"colors": {"menu": "red"}}}, "use \"#rrggbb\""),
                ({"shape": {"debug": "yes"}}, "true/false"),
                ({"font": {k: 5 for k, v in ref["font"].items() if isinstance(v, str)}},
                 "must be text")):
            if not any(theme.values()) and theme is not bad:
                continue
            with self.assertRaisesRegex(themefile.ThemeError, words):
                themefile.validate(theme, ref)

    def test_builtin_fonts_without_the_folder(self):
        with mock.patch.object(themefile, "BUILTIN_DIR", Path(self._tmp.name) / "none"):
            self.assertEqual(themefile.builtin_fonts(), [])

    def test_install_copies(self):
        themefile._INSTALLED.clear()
        themefile.install_copies()
        target = self.dir / "builtin"
        self.assertTrue((target / "system.toml").exists())
        self.assertTrue((self.dir / "README.txt").exists())
        themefile.install_copies()  # once a run
        themefile._INSTALLED.clear()
        themefile.install_copies()  # again: every copy is current, nothing rewritten
        themefile._INSTALLED.clear()
        with mock.patch.object(Path, "mkdir", side_effect=OSError):
            themefile.install_copies()  # a read-only home: best effort, no error
        themefile._INSTALLED.clear()

    def test_copy_if_changed(self):
        src = Path(self._tmp.name) / "a.svg"
        dst = Path(self._tmp.name) / "b.svg"
        src.write_text("one")
        themefile._copy_if_changed(src, dst)
        self.assertEqual(dst.read_text(), "one")
        dst.write_text("own")  # the same size, newer: left alone
        themefile._copy_if_changed(src, dst)
        self.assertEqual(dst.read_text(), "own")


class Set:
    def __init__(self, path, style="flat", color=""):
        self.path, self.style, self.color = path, style, color

    def find(self, name, exts):
        return self.path

    def color_of(self, name):
        return ""


class IconPackTest(unittest.TestCase):
    SVG = ('<svg><rect fill="{c}" stroke="{d}"/><path stroke="{l}"/>'
           '<ellipse opacity=".35"/></svg>')

    def test_styles(self):
        sil = iconpack.styled(self.SVG, "silhouette", "#808080", "#ffffff")
        self.assertIn('stroke="#ffffff"', sil)  # lines cut out in the background
        agent = iconpack.styled(self.SVG, "agent", "#808080")
        self.assertIn('opacity=".6"', agent)
        # an outline as light as the page: made readable
        dark = iconpack.styled(self.SVG, "gloss", "#202020", "#101010")
        self.assertNotIn("#0b0b0b", dark)
        mid = iconpack.styled(self.SVG, "gloss", "#7f7f7f", "#404040")
        self.assertIn("stroke=", mid)

    def test_uses_set(self):
        self.assertTrue(iconpack.uses_set("own"))
        self.assertFalse(iconpack.uses_set("words"))

    def test_mark_missing_by_version(self):
        iconpack.mark_missing.cache_clear()
        self.addCleanup(iconpack.mark_missing.cache_clear)
        with mock.patch.dict(os.environ, {"FEDTAIL_MARK_MISSING": ""}), \
                mock.patch("fedtail.__version__", "0.19.0.dev3"):
            self.assertTrue(iconpack.mark_missing())
        iconpack.mark_missing.cache_clear()
        with mock.patch.dict(os.environ, {"FEDTAIL_MARK_MISSING": ""}), \
                mock.patch("fedtail.__version__", "0.19.0"):
            self.assertFalse(iconpack.mark_missing())

    def test_picture_unreadable_or_badly_coloured(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "menu.svg"
            iconpack.picture.cache_clear()
            self.assertIsNone(iconpack.picture(Set(p), "menu", "#336699"))  # not there
            p.write_text(self.SVG)
            with mock.patch.object(iconpack, "mark_missing", return_value=False):
                got = iconpack.picture(Set(p, color="not a colour"), "bell", "#336699")
            self.assertIn("#336699", got.text)  # the accent instead
            iconpack.picture.cache_clear()


class RichTextTest(unittest.TestCase):
    def test_dropped_and_odd_tags(self):
        html = ('<p>a<script>x<script>y</script>z</script>b<img src=x/>'
                '<unknown>c</unknown><br/></p>')
        got = richtext.sanitize(html)
        self.assertNotIn("x", got.replace("<br>", ""))
        self.assertIn("a", got)
        self.assertIn("b", got)
        self.assertIn("c", got)
        self.assertEqual(richtext.sanitize("x<style>p{}</style><hr/>ok"), "x<br>ok")
        # inside a dropped element nothing counts: tags, lone tags, their ends
        self.assertEqual(richtext.sanitize("a<object><b>x</b><br/><p>y</p></object>b"), "ab")

    def test_names_dates_links(self):
        acc = mock.Mock(name="", username="", handle="<bob>")
        acc.name = ""
        self.assertEqual(richtext.display_name(acc), "&lt;bob&gt;")
        months = "jan feb mar apr may jun jul aug sep oct nov dec".split()
        self.assertEqual(richtext.when("nonsense", months), "")
        self.assertEqual(richtext.when("2001-02-03T10:00:00Z", months)[-4:], "2001")
        from datetime import UTC, datetime
        now = datetime.now(UTC).replace(microsecond=0).isoformat()
        self.assertIn(":", richtext.when(now, months))
        a = richtext.link("tag", "c&c", "#c", color="#f00", bold=True)
        self.assertIn("color:#f00;font-weight:700;", a)
        self.assertIn("fedtail:tag/c&amp;c", a)


class MarkdownTest(unittest.TestCase):
    def test_code_lists_and_quotes(self):
        md = ("text\n```\n<b>code</b>\n```\n- one\n  goes on\n- two\n\n"
              "> quoted\n> more\nafter")
        got = mdhtml.markdown_html(md)
        self.assertIn("<pre><code>&lt;b&gt;code&lt;/b&gt;</code></pre>", got)
        self.assertIn("<li>one goes on</li>", got)
        self.assertIn("<blockquote>quoted more</blockquote>", got)


if __name__ == "__main__":
    unittest.main()
