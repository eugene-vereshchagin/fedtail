"""Picture packs (frontends/iconpack.py): which file a picture comes from, inheriting,
the colours filled in, a theme's own pictures over its pack, yours over the built-in."""

import os
import tempfile
import unittest
from pathlib import Path

from fedtail.frontends import iconpack, themefile
from fedtail.frontends.palette import Color


class _Theme:
    def __init__(self, icon_set, icon_dirs=()):
        self.shape = {"icon_set": icon_set}
        self.icon_dirs = list(icon_dirs)


class IconPackTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = self._tmp.name
        iconpack.load.cache_clear()

    def tearDown(self):
        if self._old is None:
            os.environ.pop("XDG_CONFIG_HOME", None)
        else:
            os.environ["XDG_CONFIG_HOME"] = self._old
        iconpack.load.cache_clear()
        self._tmp.cleanup()

    def test_builtin_packs_have_every_picture(self):
        self.assertEqual(set(iconpack.available()) >= {"gloss", "qip", "agent", "flat", "psi"},
                         True)
        for name in iconpack.available():
            pack = iconpack.load(name)
            self.assertEqual(pack.warnings, [], name)
            for pic in iconpack.NAMES:
                self.assertIsNotNone(pack.find(pic), f"{name}: {pic}")

    def test_each_draws_its_own_way(self):
        accent = "#3daee9"
        gloss = iconpack.picture(iconpack.load("gloss"), "reply", accent)
        self.assertEqual(gloss.kind, "svg")
        self.assertIn(accent, gloss.text)
        self.assertNotIn("{c}", gloss.text)
        qip = iconpack.picture(iconpack.load("qip"), "send", accent)
        self.assertIn("#2fa82f", qip.text)  # QIP's: its own bright colour
        flat = iconpack.picture(iconpack.load("flat"), "emoji", accent)
        self.assertNotIn("url(#g)", flat.text)  # flat: no gradient, no shine
        self.assertNotIn('opacity=".35"', flat.text)
        agent = iconpack.load("agent")
        self.assertEqual(agent.find("status").parent.name, "agent")  # its own "@"
        self.assertEqual(agent.find("reply").parent.name, "gloss")  # the rest: inherited
        psi = iconpack.load("psi")
        self.assertEqual(iconpack.picture(psi, "reply", accent).kind, "png")
        self.assertEqual(psi.style, "flat")  # what Psi+ lacks comes flat
        self.assertTrue(iconpack.has_png(psi))
        # no SVG renderer: a pack's PNGs only
        self.assertIsNone(iconpack.picture(iconpack.load("gloss"), "reply", accent,
                                           svg_ok=False))

    def test_colours(self):
        c = Color.parse("#3daee9")
        text = iconpack.styled('<path fill="{c}" stroke="{d}"/><stop stop-color="{l}"/>',
                               "gloss", c)
        self.assertIn(c.name(), text)
        self.assertIn(c.darker(170).name(), text)
        self.assertIn(c.lighter(165).name(), text)

    def test_yours_and_a_themes_own(self):
        mine = Path(self._tmp.name) / "fedtail" / "icons" / "mine"
        mine.mkdir(parents=True)
        (mine / "pack.toml").write_text('name = "Mine"\ninherit = "qip"\n'
                                        '[colors]\nreply = "#123456"\n', "utf-8")
        (mine / "send.svg").write_text('<svg fill="{c}"/>', "utf-8")
        self.assertIn("mine", iconpack.available())
        pack = iconpack.load("mine")
        self.assertEqual(pack.style, "qip")  # inherited
        self.assertEqual(pack.find("send").parent, mine)
        self.assertIn("#123456", iconpack.picture(pack, "reply", "#000000").text)
        self.assertIn("#2fa82f", iconpack.picture(pack, "boost", "#000000").text)
        own = Path(self._tmp.name) / "own"
        own.mkdir()
        (own / "reply.png").write_bytes(b"\x89PNG")
        t = iconpack.for_theme(_Theme("mine", [str(own)]))
        self.assertEqual(iconpack.picture(t, "reply", "#000000").kind, "png")
        self.assertEqual(t.find("send").parent, mine)

    def test_unknown_pack_falls_back_and_says_so(self):
        pack = iconpack.load("no-such-pack")
        self.assertEqual(pack.name, "gloss")
        self.assertTrue(pack.warnings)
        themes = Path(self._tmp.name) / "fedtail" / "themes"
        themes.mkdir(parents=True)
        (themes / "odd.toml").write_text('inherit = "system"\n[shape]\nicon_set = "nope"\n',
                                         "utf-8")
        data, warnings = themefile.load("odd")  # a theme still loads, with a warning
        self.assertEqual(data["shape"]["icon_set"], "gloss")
        self.assertTrue(any("icon_set" in w for w in warnings))

    def test_copies_to_start_from(self):
        themefile.install_copies()
        root = Path(self._tmp.name) / "fedtail" / "icons"
        self.assertTrue((root / "builtin" / "qip" / "pack.toml").is_file())
        self.assertIn("reply", (root / "README.txt").read_text("utf-8"))
        self.assertNotIn("builtin", iconpack.available())


if __name__ == "__main__":
    unittest.main()
