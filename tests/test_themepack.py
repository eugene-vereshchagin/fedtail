"""A theme as a zip (frontends/themepack.py): out and back, the manual inside, the user's
own themes it rests on carried along, and an archive that can't harm the themes folder."""

import os
import tempfile
import unittest
import zipfile
from pathlib import Path

from fedtail.frontends import themefile, themepack


class ThemePackTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        old = os.environ.get("XDG_CONFIG_HOME")
        os.environ["XDG_CONFIG_HOME"] = str(self.tmp / "cfg")
        self.addCleanup(lambda: os.environ.__setitem__("XDG_CONFIG_HOME", old) if old
                        else os.environ.pop("XDG_CONFIG_HOME", None))
        self.themes = themefile.user_dir()
        self.themes.mkdir(parents=True)

    def zip(self, files, name="t.zip"):
        p = self.tmp / name
        with zipfile.ZipFile(p, "w") as z:
            for arc, data in files.items():
                z.writestr(arc, data)
        return p

    def test_builtin_out_renamed_and_back(self):
        # the author's round: take point off the phone, rename it, bring it back
        out = self.tmp / "point.zip"
        names = themepack.pack("point", out)
        self.assertIn("point.toml", names)
        self.assertTrue(any(n.startswith("point/icons/") for n in names))
        self.assertTrue(any(n.startswith("fonts/OpenSans") for n in names))
        with zipfile.ZipFile(out) as z:
            listed = z.namelist()
            ru = z.read("README.ru.md").decode()
            en = z.read("README.en.md").decode()
        self.assertIn("Переназвать", ru)
        self.assertIn("Rename it", en)
        self.assertNotIn("<!--", ru + en)
        self.assertNotIn("system.toml", listed)  # a built-in one it inherits: not carried
        # renamed: the file, its folder, the name inside
        renamed = {}
        with zipfile.ZipFile(out) as z:
            for n in listed:
                data = z.read(n)
                if n == "point.toml":
                    n, data = "mine.toml", data.replace(b'name = "Point"', b'name = "Mine"')
                elif n.startswith("point/"):
                    n = "mine/" + n[len("point/"):]
                renamed[n] = data
        got = themepack.unpack(self.zip(renamed, "mine.zip"))
        self.assertEqual(got["themes"], ["mine"])
        self.assertEqual(got["skipped"], [])
        self.assertIn("mine", themefile.available())
        theme, _w = themefile.load("mine")
        self.assertEqual(theme["name"], "Mine")
        self.assertEqual(theme["icon_dirs"][0], str(self.themes / "mine" / "icons"))
        self.assertTrue(all(Path(f).is_file() for f in theme["font"]["files"]))
        self.assertFalse((self.themes / "README.ru.md").exists())  # the manual stays out

    def test_own_parent_carried_along(self):
        (self.themes / "base.toml").write_text('name = "Base"\ninherit = "terminal"\n')
        (self.themes / "base" / "icons").mkdir(parents=True)
        (self.themes / "base" / "icons" / "reply.svg").write_text("<svg/>")
        (self.themes / "kid.toml").write_text('name = "Kid"\ninherit = "base"\n')
        names = themepack.pack("kid", self.tmp / "kid.zip")
        self.assertEqual(names, ["base.toml", "base/icons/reply.svg", "kid.toml"])
        self.assertEqual(themepack.themes_in(self.tmp / "kid.zip"), ["base", "kid"])

    def test_same_name_asked_then_replaced(self):
        (self.themes / "mine.toml").write_text('name = "Old"\n')
        (self.themes / "mine" / "icons").mkdir(parents=True)
        (self.themes / "mine" / "icons" / "gone.svg").write_text("<svg/>")
        z = self.zip({"mine.toml": 'name = "New"\n', "mine/icons/reply.svg": "<svg/>"})
        with self.assertRaises(themepack.PackError) as e:
            themepack.unpack(z)
        self.assertIn("mine", str(e.exception))
        self.assertIn("Old", (self.themes / "mine.toml").read_text())
        themepack.unpack(z, replace=True)
        self.assertIn("New", (self.themes / "mine.toml").read_text())
        self.assertFalse((self.themes / "mine" / "icons" / "gone.svg").exists())

    def test_zipped_with_its_folder(self):
        got = themepack.unpack(self.zip({"mine-theme/mine.toml": 'name = "M"\n',
                                         "mine-theme/mine/sounds/reply.wav": "RIFF"}))
        self.assertEqual(got["themes"], ["mine"])
        self.assertTrue((self.themes / "mine" / "sounds" / "reply.wav").is_file())

    def test_unsafe_and_wrong_archives(self):
        for files, words in (
                ({"../evil.toml": "x = 1"}, "out of the themes folder"),
                ({"/etc/evil.toml": "x = 1"}, "out of the themes folder"),
                ({"icons/a.svg": "<svg/>"}, "no theme"),
                ({"bad.toml": "= broken"}, "bad.toml"),
                ({"a b.toml": "x = 1"}, "name")):
            with self.subTest(files=list(files)):
                with self.assertRaises(themepack.PackError) as e:
                    themepack.unpack(self.zip(files))
                self.assertIn(words, str(e.exception))
        self.assertEqual(list(self.themes.iterdir()), [])  # nothing written
        not_zip = self.tmp / "x.zip"
        not_zip.write_text("hello")
        with self.assertRaises(themepack.PackError):
            themepack.unpack(not_zip)
        # other kinds of files: left out and said
        got = themepack.unpack(self.zip({"m.toml": 'name = "M"\n', "m/run.sh": "rm -rf ~"}))
        self.assertEqual(got["skipped"], ["m/run.sh"])
        self.assertFalse((self.themes / "m" / "run.sh").exists())

    def test_too_big(self):
        old = themepack.MAX_BYTES
        themepack.MAX_BYTES = 10
        self.addCleanup(setattr, themepack, "MAX_BYTES", old)
        with self.assertRaises(themepack.PackError):
            themepack.unpack(self.zip({"m.toml": 'name = "a long enough name"\n'}))

    def test_command_line(self):
        import contextlib
        import io

        from fedtail.__main__ import main
        out = self.tmp / "p.zip"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["--theme-export", "psi", str(out)]), 0)
            self.assertEqual(main(["--theme-import", str(out)]), 0)
        self.assertTrue((self.themes / "psi.toml").is_file())
        with contextlib.redirect_stdout(io.StringIO()), \
                contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(main(["--theme-import", str(out)]), 1)  # there: --replace
            self.assertIn("already there", err.getvalue())
            self.assertEqual(main(["--theme-import", str(out), "--replace"]), 0)

    def test_unknown_theme(self):
        with self.assertRaises(themepack.PackError):
            themepack.pack("no-such-theme", self.tmp / "x.zip")


if __name__ == "__main__":
    unittest.main()
