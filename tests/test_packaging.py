"""The packages made from this repository (packaging/): what each takes from the one table
of dependencies (fedtail/deps.py), the files every package installs around the program,
the wheel's file list, the AppImage's own path, the Flatpak's pins, the Docker context."""

import re
import subprocess
import sys
import tomllib
import unittest
import xml.dom.minidom
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packaging"))

import arch  # noqa: E402
import desktop_files  # noqa: E402
import metainfo  # noqa: E402
import rpm  # noqa: E402

from fedtail import __version__, deps, sysenv  # noqa: E402
from fedtail.version import APP_ID  # noqa: E402


def tracked(prefix):
    try:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", prefix], capture_output=True,
                             text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.split()


class WheelTest(unittest.TestCase):
    def test_every_data_file_is_in_the_package(self):
        """pyproject.toml's package-data takes every file of fedtail/ that isn't Python
        (the lanes' icons were left out of pip's install: 44 files, 20.11)."""
        files = tracked("fedtail")
        if files is None:
            self.skipTest("no git checkout")
        conf = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
        patterns = conf["tool"]["setuptools"]["package-data"]["fedtail"]
        base = ROOT / "fedtail"
        taken = {str(p.relative_to(ROOT)) for pat in patterns for p in base.glob(pat)
                 if p.is_file()}
        left = [f for f in files if not f.endswith(".py") and f not in taken]
        self.assertEqual(left, [])


class TableTest(unittest.TestCase):
    def test_every_piece_has_its_names_everywhere(self):
        for n in deps.NEEDS:
            with self.subTest(n.key):
                self.assertTrue(n.deb and n.arch and n.rpm)

    def test_the_distributions_fields(self):
        for field in ("arch", "rpm"):
            needs, recommends, suggests = deps.dist_fields(field)
            every = [p for part in (needs, recommends, suggests) for p, _n in part]
            self.assertEqual(len(every), len(set(every)), field)  # each once
            self.assertEqual({p for n in deps.NEEDS for p in getattr(n, field).split()},
                             set(every), field)  # none lost
        names = [p for p, _n in deps.dist_fields("arch")[0]]
        self.assertIn("pyside6", names)  # the window comes with it
        self.assertNotIn("python-gobject", names)  # GTK doesn't: an optdepend

    def test_install_line_by_the_system(self):
        need = [n for n in deps.NEEDS if n.key in ("textual", "Enchant")]
        with mock.patch.object(deps, "debian_like", return_value=False), \
                mock.patch.object(deps, "arch_like", return_value=True):
            self.assertEqual(deps.install_line(need), "sudo pacman -S --needed python-textual "
                             "enchant hunspell-ru hunspell-en_us")
        with mock.patch.object(deps, "debian_like", return_value=False), \
                mock.patch.object(deps, "arch_like", return_value=False), \
                mock.patch.object(deps, "fedora_like", return_value=True):
            self.assertTrue(deps.install_line(need).startswith("sudo dnf install "
                                                               "python3-textual enchant2"))


class PackagesTest(unittest.TestCase):
    def test_pkgbuild(self):
        text = arch.pkgbuild("0" * 64)
        self.assertIn(f"pkgver={__version__}\n", text)
        depends = re.search(r"^depends=\((.*)\)$", text, re.M).group(1)
        self.assertIn("'pyside6'", depends)
        self.assertIn("'hicolor-icon-theme'", depends)
        self.assertIn("  'gtk4: ", text)  # an optdepend, with what it gives
        self.assertIn("/releases/download/v$pkgver/fedtail-$pkgver.tar.gz", text)
        self.assertIn("python packaging/desktop_files.py", text)
        local = arch.pkgbuild("1" * 64, "fedtail-x.tar.gz")
        self.assertIn('source=("fedtail-x.tar.gz")', local)

    def test_spec(self):
        self.assertEqual(rpm.rpm_version("0.23.6.dev0"), "0.23.6~dev0")
        self.assertEqual(rpm.rpm_version("0.23.6"), "0.23.6")
        text = rpm.spec(version="1.2.3")
        self.assertIn("Version:        1.2.3\n", text)
        self.assertIn("Requires:       python3-pyside6\n", text)
        self.assertIn("Recommends:     python3-cryptography\n", text)
        self.assertIn("Suggests:       gtk4\n", text)
        self.assertNotIn("sqlite-libs", text)  # Python's own pulls it
        self.assertIn("%autosetup -n fedtail-1.2.3", text)
        self.assertIn("/releases/download/v1.2.3/fedtail-1.2.3.tar.gz", text)
        long = [x for x in text.split("%description", 1)[1].split("%prep")[0].splitlines()
                if len(x) > 79]
        self.assertEqual(long, [])  # rpmlint: description-line-too-long

    def test_menu_entry(self):
        """`fedtail` on the PATH, whatever profile the building machine calls its main
        one; the GTK window as its action."""
        with mock.patch("fedtail.core.paths.main_profile", return_value="work"), \
                mock.patch.object(desktop_files, "main_profile", return_value="work"):
            text = desktop_files.entry(icon=APP_ID)
        self.assertIn("\nExec=fedtail\n", text)
        self.assertIn("\nExec=fedtail --ui gtk\n", text)
        self.assertIn(f"\nIcon={APP_ID}\n", text)
        self.assertNotIn("Path=", text)
        self.assertNotIn("--profile", text)

    def test_metainfo(self):
        changelog = ("## What's next\n\n* soon\n\n## 1.2.0 — 2026-01-02\n\n* a\n\n"
                     "## 1.1.0 — 2025-12-01\n")
        text = metainfo.text(changelog)
        doc = xml.dom.minidom.parseString(text.encode())
        self.assertEqual(doc.getElementsByTagName("id")[0].firstChild.data, APP_ID)
        got = [(r.getAttribute("version"), r.getAttribute("date"))
               for r in doc.getElementsByTagName("release")]
        self.assertEqual(got, [("1.2.0", "2026-01-02"), ("1.1.0", "2025-12-01")])
        launch = doc.getElementsByTagName("launchable")[0].firstChild.data
        self.assertEqual(launch, f"{APP_ID}.desktop")
        self.assertIn('xml:lang="ru"', text)
        metainfo.text()  # the real CHANGELOG reads


class AppImageTest(unittest.TestCase):
    def test_the_image_starts_itself_again(self):
        """Inside an AppImage the program's own folder is a mount that goes when it
        exits: a restart and a menu entry name the .AppImage file."""
        with mock.patch.object(sysenv, "FROZEN", True), \
                mock.patch.dict("os.environ", {"APPIMAGE": __file__}):
            self.assertEqual(sysenv.own_binary(), __file__)
        with mock.patch.object(sysenv, "FROZEN", True), \
                mock.patch.dict("os.environ", {"APPIMAGE": ""}):
            self.assertEqual(sysenv.own_binary(), sys.executable)
        with mock.patch.object(sysenv, "FROZEN", False), \
                mock.patch.dict("os.environ", {"APPIMAGE": __file__}):
            self.assertEqual(sysenv.own_binary(), sys.executable)  # not ours: as it was
        from fedtail.core import profiles
        with mock.patch.object(sys, "frozen", True, create=True), \
                mock.patch.object(sysenv, "FROZEN", True), \
                mock.patch.dict("os.environ", {"APPIMAGE": __file__}):
            self.assertEqual(profiles.command("work")[0], [__file__, "--profile", "work"])


class FilesTest(unittest.TestCase):
    def test_flatpak_pins(self):
        text = (ROOT / "packaging/flatpak" / f"{APP_ID}.yml").read_text("utf-8")
        self.assertIn(f"\nid: {APP_ID}\n", text)
        urls = re.findall(r"^\s+url: (\S+)$", text, re.M)
        sums = re.findall(r"^\s+sha256: ([0-9a-f]{64})$", text, re.M)
        self.assertTrue(urls)
        self.assertEqual(len(urls), len(sums))  # each file with its sha256
        self.assertIn("--icon " + APP_ID, text)  # Flatpak's icon is named as the app

    def test_docker_context_holds_nothing_else(self):
        """The image is built from the package alone: no notes, profiles or builds of
        the checkout go into the build context."""
        lines = [x.strip() for x in (ROOT / ".dockerignore").read_text("utf-8").splitlines()
                 if x.strip() and not x.startswith("#")]
        self.assertEqual(lines[0], "*")
        allowed = {x[1:] for x in lines if x.startswith("!")}
        self.assertEqual(allowed, {"fedtail/", "pyproject.toml", "README.md", "LICENSE",
                                   "packaging/docker/"})


if __name__ == "__main__":
    unittest.main()
