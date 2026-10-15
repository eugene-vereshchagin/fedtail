import re
import subprocess
import sys
import unittest
from pathlib import Path

from fedtail import __version__, i18n

ROOT = Path(__file__).resolve().parent.parent


class I18nTest(unittest.TestCase):
    def test_languages_have_same_keys(self):
        self.assertEqual(i18n.keys("ru"), i18n.keys("en"))

    def test_every_used_key_exists(self):
        used = set()
        prefixes = set()
        for f in (ROOT / "fedtail").rglob("*.py"):
            text = f.read_text("utf-8")
            used |= set(re.findall(r'\b_\("([a-z_0-9]+)"', text))
            prefixes |= set(re.findall(r'\b_\("([a-z]+_)"\s*\+', text))
        known = i18n.keys("en")
        concrete = {k for k in used if k not in prefixes}
        self.assertEqual(concrete - known, set())
        for p in prefixes:
            self.assertTrue(any(k.startswith(p) for k in known), p)

    def test_months(self):
        i18n.setup("ru")
        self.assertEqual(len(i18n.months()), 12)
        self.assertEqual(i18n._("unread_n", n=3), "новых: 3")
        i18n.setup("xx")
        self.assertEqual(i18n._("unread_n", n=3), "unread: 3")


class CliTest(unittest.TestCase):
    def test_version(self):
        out = subprocess.run([sys.executable, "-m", "fedtail", "--version"], cwd=ROOT,
                             capture_output=True, text=True, check=True)
        self.assertIn(__version__, out.stdout)

    def test_update_config_flag(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "c.toml"
            cfg.write_text('[ui]\ntheme = "terminal"\n')
            out = subprocess.run([sys.executable, "-m", "fedtail", "-c", str(cfg), "-d", d,
                                  "--update-config"], cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("ui.actions", out.stdout)
            self.assertTrue((Path(d) / "c.toml.bak").exists())
            self.assertTrue((Path(d) / "config.example.toml").exists())
            self.assertIn("#actions", cfg.read_text())

    def test_bad_config_is_explained(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "c.toml"
            cfg.write_text('[feed]\norder = "sideways"\n')
            out = subprocess.run([sys.executable, "-m", "fedtail", "-c", str(cfg), "-d", d],
                                 cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(out.returncode, 2)
            self.assertIn("feed.order", out.stderr)


if __name__ == "__main__":
    unittest.main()
