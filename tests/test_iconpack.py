"""The pictures on the buttons (frontends/iconpack.py): the theme decides where they come
from ([shape] icons, ui.icons over it), its set lies next to it, what it lacks comes
from the themes it inherits, [pictures] from and the fallback; every built-in theme with
a set of its own has every picture without the fallback."""

import os
import tempfile
import unittest
from pathlib import Path

from fedtail.frontends import iconpack, themefile
from fedtail.frontends.palette import Color


class _Theme:
    def __init__(self, data):
        self.id = data["id"]
        self.shape = data["shape"]
        self.icon_dirs = data["icon_dirs"]
        self.pictures = data["pictures"]


def _theme(name):
    return _Theme(themefile.load(name)[0])


class IconPackTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._tmp.name

    def tearDown(self):
        if self._old is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._old
        self._tmp.cleanup()

    def test_who_has_what(self):
        want = {"system": "desktop", "debug": "desktop", "terminal": "words",
                "bnw": "words"}
        for name in themefile.available():
            data, _w = themefile.load(name)
            self.assertEqual(data["shape"]["icons"], want.get(name, "own"), name)

    def test_builtin_sets_are_whole(self):
        """No built-in theme with a set of its own needs the fallback."""
        self.assertEqual(sorted(p.stem for p in iconpack.FALLBACK_DIR.glob("*.svg")
                                if p.stem in iconpack.NAMES), sorted(iconpack.NAMES))
        for name in themefile.available():
            t = _theme(name)
            if t.shape["icons"] != "own":
                continue
            s = iconpack.for_theme(t)
            self.assertEqual(iconpack.missing(name, s), [], name)

    def test_each_draws_its_own_way(self):
        accent = "#3daee9"
        juick = iconpack.for_theme(_theme("juick"))
        gloss = iconpack.picture(juick, "reply", accent)
        self.assertEqual(gloss.kind, "svg")
        self.assertIn(accent, gloss.text)
        self.assertNotIn("{c}", gloss.text)
        qip = iconpack.for_theme(_theme("qip-modern"))  # qip-retro's set, borrowed
        self.assertIn("qip-retro", qip.find("send").parts)
        self.assertIn("#2fa82f", iconpack.picture(qip, "send", accent).text)
        blue = iconpack.for_theme(_theme("mra-blue"))
        self.assertEqual(blue.find("status").parent.parent.name, "mra")  # the Agent's @
        psi = iconpack.for_theme(_theme("psi"))
        self.assertEqual(iconpack.picture(psi, "reply", accent).kind, "png")
        self.assertNotIn("url(#g)", iconpack.picture(psi, "close", accent).text)  # flat
        self.assertTrue(iconpack.has_png(psi))
        self.assertIsNone(iconpack.picture(juick, "reply", accent, svg_ok=False))
        # a lane by its name; a picture left out: another stands in
        self.assertEqual(iconpack.lane_picture("list:12"), "list")
        self.assertEqual(juick.find("federated").stem, "public")

    def test_where_they_come_from(self):
        shape = {"icons": "own"}
        self.assertEqual(iconpack.mode({"ui": {"icons": "theme"}}, shape), "own")
        self.assertEqual(iconpack.mode({"ui": {"icons": "words"}}, shape), "words")
        self.assertEqual(iconpack.mode({"ui": {}}, {"icons": "desktop"}), "desktop")
        # the messengers' pictures: in the split layout, or anywhere with "additional"
        self.assertFalse(iconpack.shown("own", "send", split=False))
        self.assertTrue(iconpack.shown("own", "send", split=True))
        self.assertTrue(iconpack.shown("additional", "send", split=False))
        self.assertTrue(iconpack.shown("own", "reply", split=False))
        self.assertFalse(iconpack.shown("words", "menu", split=True))

    def test_colours(self):
        c = Color.parse("#3daee9")
        text = iconpack.styled('<path fill="{c}" stroke="{d}"/><stop stop-color="{l}"/>',
                               "gloss", c)
        self.assertIn(c.name(), text)
        self.assertIn(c.darker(170).name(), text)
        self.assertIn(c.lighter(165).name(), text)

    def test_a_theme_of_yours(self):
        themes = Path(self._tmp.name) / "fedtail" / "themes"
        own = themes / "mine" / "icons"
        own.mkdir(parents=True)
        (themes / "mine.toml").write_text(
            'inherit = "juick"\n[shape]\nicons = "own"\n[pictures]\nstyle = "qip"\n'
            '[pictures.colors]\nreply = "#123456"\n', "utf-8")
        (own / "send.svg").write_text('<svg fill="{c}"/>', "utf-8")
        t = _theme("mine")
        s = iconpack.for_theme(t)
        self.assertEqual(s.find("send").parent, own)
        self.assertIn("juick", s.find("boost").parts)  # what it lacks: the inherited
        self.assertIn("#123456", iconpack.picture(s, "reply", "#000000").text)
        self.assertEqual(iconpack.missing("mine", s), [])
        # a theme of an older version: icons = true / false, lane_icons, icon_set
        (themes / "old.toml").write_text('inherit = "system"\n[shape]\nicons = false\n'
                                         'lane_icons = true\nicon_set = "agent"\n', "utf-8")
        data, warnings = themefile.load("old")
        self.assertEqual(data["shape"]["icons"], "words")
        self.assertEqual(data["pictures"]["style"], "agent")
        self.assertEqual(warnings, [])
        # a set that lacks pictures: the fallback, and the log says which
        (themes / "bare.toml").write_text('inherit = "system"\n[shape]\nicons = "own"\n',
                                          "utf-8")
        bare = iconpack.for_theme(_theme("bare"))
        with self.assertLogs("fedtail.frontends.iconpack", "WARNING"):
            self.assertIn("reply", iconpack.missing("bare", bare))
        self.assertIsNotNone(iconpack.picture(bare, "reply", "#000000"))

    def test_copies_to_start_from(self):
        themefile.install_copies()
        root = Path(self._tmp.name) / "fedtail" / "themes" / "builtin"
        self.assertTrue((root / "mra" / "icons" / "status.svg").is_file())
        listing = (root / "PICTURES.txt").read_text("utf-8")
        for name in iconpack.NAMES:
            self.assertIn(name, listing)


if __name__ == "__main__":
    unittest.main()


class MissingInRedTest(unittest.TestCase):
    """A development version: what a theme's set lacks comes from the fallback in red —
    the theme's gaps seen at once; its own pictures as they are."""

    def test_red_from_the_fallback_only(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"FEDTAIL_MARK_MISSING": "1"}):
            iconpack.mark_missing.cache_clear()
            iconpack.picture.cache_clear()
            try:
                bare = iconpack.Set(dirs=(str(iconpack.FALLBACK_DIR),))
                pic = iconpack.picture(bare, "reply", "#336699")
                self.assertIn(iconpack.MISSING_RED, pic.text)
                own = iconpack.for_theme(type("T", (), {
                    "icon_dirs": [str(themefile.BUILTIN_DIR / "point" / "icons")],
                    "pictures": {"style": "silhouette", "color": "#a29b94"}})())
                self.assertNotIn(iconpack.MISSING_RED,
                                 iconpack.picture(own, "reply", "#336699").text)
            finally:
                iconpack.mark_missing.cache_clear()
                iconpack.picture.cache_clear()


class ThemesByLayoutTest(unittest.TestCase):
    """ui.themes_by_layout: the messengers' themes offered for the split layout only;
    "auto" — on in releases, off in development versions."""

    def test_offered_by_layout(self):
        def offered(layout, mode, keep=()):
            return themefile.for_layout({"ui": {"layout": layout, "themes_by_layout": mode}},
                                        keep)
        self.assertEqual(themefile.layouts_of("mra-blue"), ("split",))  # its own word
        self.assertIn("qip-retro", offered("split", "on"))
        self.assertNotIn("qip-retro", offered("single", "on"))
        self.assertIn("qip-retro", offered("single", "on", keep=("qip-retro",)))  # on now
        self.assertIn("nord", offered("single", "on"))
        self.assertIn("qip-retro", offered("single", "off"))
        from unittest import mock
        # "auto": every theme in a development version, the layout's ones in a release
        with mock.patch("fedtail.__version__", "0.19.0.dev3"):
            self.assertEqual(themefile.by_layout({"ui": {}}), False)
        with mock.patch("fedtail.__version__", "0.19.0"):
            self.assertEqual(themefile.by_layout({"ui": {}}), True)


class LaneLibraryTest(unittest.TestCase):
    """The lanes' library (data/icons/lanes, tools/lane_pictures.py): every picture a
    lane may wear is drawn, named in both languages, and found through any theme."""

    def test_every_picture_is_there(self):
        from fedtail import i18n
        from fedtail.core import atoms
        have = {p.stem for p in iconpack.LANES_DIR.glob("*.svg")}
        self.assertEqual(have, set(atoms.LANE_LIBRARY))
        for lang in ("ru", "en"):
            i18n.setup(lang)
            for name in atoms.LANE_ICONS:
                self.assertNotEqual(i18n._("pic_" + name), "pic_" + name, (lang, name))
        i18n.setup("en")
        for theme in ("point", "juick", "qip-retro", "nord", "system"):
            pset = iconpack.for_theme(_theme(theme))
            for name in atoms.LANE_ICONS:
                pic = iconpack.picture(pset, name, "#3366cc", bg="#ffffff")
                self.assertIsNotNone(pic, (theme, name))
                if pic.kind == "svg":
                    self.assertNotRegex(pic.text, r"\{[cldo]\}", (theme, name))

    def test_lanes_wear_their_own(self):
        self.assertEqual(iconpack.lane_picture("important"), "important")  # not a star:
        self.assertEqual(iconpack.lane_picture("commented"), "commented")  # Point's is one
        self.assertEqual(iconpack.lane_picture("custom:x", "mountain"), "mountain")
        self.assertEqual(iconpack.lane_picture("custom:x", "nope"), "list")
        self.assertEqual(iconpack.lane_picture("home", object()), "home")  # not a name

    def test_silhouette_keeps_what_lies_outside(self):
        text = (iconpack.LANES_DIR / "sun.svg").read_text("utf-8")
        out = iconpack.styled(text, "silhouette", "#c0392b", "#ffffff")
        self.assertIn('stroke="#c0392b"', out)  # the rays: the shape's colour, not cut out
