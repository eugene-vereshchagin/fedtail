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
        self.assertEqual(i18n._("new_n", n=1), "1 новое")
        self.assertEqual(i18n._("new_n", n=3), "3 новых")
        self.assertEqual(i18n._("thread_info", n=2), "пост и 2 ответа")
        self.assertEqual(i18n._("thread_info", n=11), "пост и 11 ответов")
        self.assertEqual(i18n._("thread_info", n=21), "пост и 21 ответ")
        i18n.setup("xx")
        self.assertEqual(i18n._("thread_info", n=1), "post and 1 reply")


class VersionTest(unittest.TestCase):
    def test_compose(self):
        from fedtail.version import compose
        self.assertEqual(compose("0.2.0", 0, "abc"), "0.2.0")
        self.assertEqual(compose("0.3.0.dev0", 7, "abc"), "0.3.0.dev7+gabc")
        self.assertEqual(compose("0.2.0", 3, "abc"), "0.2.0+3.gabc")  # past it, not bumped


class CliTest(unittest.TestCase):
    def test_version(self):
        out = subprocess.run([sys.executable, "-m", "fedtail", "--version"], cwd=ROOT,
                             capture_output=True, text=True, check=True)
        self.assertIn("fedtail " + __version__.split(".dev")[0], out.stdout)

    def test_run_as_folder(self):
        out = subprocess.run([sys.executable, "fedtail", "--version"], cwd=ROOT,
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("fedtail " + __version__.split(".dev")[0], out.stdout)

    def test_install_desktop(self):
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, XDG_DATA_HOME=d)
            out = subprocess.run([sys.executable, "-m", "fedtail", "--install-desktop",
                                  "--profile", "croco"], cwd=ROOT, env=env,
                                 capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            entry = (Path(d) / "applications" / "fedtail-croco.desktop").read_text()
            self.assertIn("-m fedtail --profile croco", entry)
            self.assertIn(f"Path={ROOT}", entry)
            self.assertIn("Icon=fedtail", entry)
            svg = Path(d) / "icons/hicolor/scalable/apps/fedtail.svg"
            self.assertTrue(svg.read_text().startswith("<svg"))

    def test_bug_report_flag(self):
        import os
        import tarfile
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            env = dict(os.environ, HOME=d, XDG_DATA_HOME=d + "/data", XDG_CONFIG_HOME=d + "/cfg")
            out = subprocess.run([sys.executable, "-m", "fedtail", "--bug-report"], cwd=ROOT,
                                 env=env, capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            [archive] = Path(d).glob("fedtail-report-default-*.tar.gz")
            with tarfile.open(archive) as tar:
                self.assertIn("system.txt", tar.getnames())

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
