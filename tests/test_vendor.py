"""The packages fedtail carries inside itself (fedtail/_vendor/, tools/vendor.py): each is
what VENDORED.toml says, its licence beside it, the files it doesn't need left out; ours
comes last on the path, so a copy in the system or from pip wins; a newer one on PyPI is
said (CI's nightly `vendored`)."""

import sys
import tomllib
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import vendor  # noqa: E402

from fedtail import _vendor  # noqa: E402


class VendoredTest(unittest.TestCase):
    def test_what_is_carried_is_what_the_list_says(self):
        items = tomllib.loads((_vendor.HERE / "VENDORED.toml").read_text("utf-8"))
        self.assertIn("textual-image", items)
        for name, it in items.items():
            with self.subTest(name=name):
                pkg = _vendor.HERE / it["package"]
                self.assertTrue((pkg / "__init__.py").is_file())
                self.assertTrue((pkg / "LICENSE.txt").is_file())  # LGPL: the text with it
                self.assertRegex(it["sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(it["version"], r"^\d+(\.\d+)+")
                self.assertFalse(list(pkg.rglob("*.jpg")))  # left out, as `dropped` says
                self.assertFalse((pkg / "demo").exists())

    def test_ours_comes_last(self):
        here = str(_vendor.HERE)
        with mock.patch.object(sys, "path", ["/a", "/b"]):
            _vendor.use()
            _vendor.use()
            self.assertEqual(sys.path, ["/a", "/b", here])

    def test_a_newer_version_is_said(self):
        self.assertGreater(vendor.version_key("0.14.10"), vendor.version_key("0.14.2"))
        self.assertGreater(vendor.version_key("1.0"), vendor.version_key("1.0rc1"))
        items = {"textual-image": {"version": "0.14.2"}}
        with mock.patch.object(vendor, "newest", lambda _n: "0.15.0"):
            self.assertEqual(vendor.check(items), [("textual-image", "0.14.2", "0.15.0")])
            self.assertEqual(vendor.main(["--check"]), 1)
        with mock.patch.object(vendor, "newest", lambda _n: "0.14.2"):
            self.assertEqual(vendor.check(items), [])


if __name__ == "__main__":
    unittest.main()
