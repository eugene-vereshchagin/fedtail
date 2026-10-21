"""A dev version's log holds what a bug report would add (diag.debug_context)."""

import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fedtail import diag
from fedtail.core import config, paths


class DebugContextTest(unittest.TestCase):
    def test_log_holds_the_report(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            p = paths.resolve("t", config=str(Path(d) / "c.toml"), data=str(Path(d) / "data"))
            p.config_file.write_text('[ui]\ntheme = "point"\n', "utf-8")
            cfg, _w = config.validate({"ui": {"theme": "point"}})
            with mock.patch.object(diag, "is_on", return_value=True), \
                    self.assertLogs("fedtail", logging.INFO) as got:
                diag.debug_context(p, cfg, "gtk")
            text = "\n".join(got.output)
            self.assertIn("frontend gtk", text)
            self.assertIn("python", text)
            self.assertIn('"ui.theme": "point"', text)
            self.assertIn('theme = "point"', text)  # the config file itself
            with mock.patch.object(diag, "is_on", return_value=False):
                with self.assertNoLogs("fedtail", logging.INFO):
                    diag.debug_context(p, cfg, "qt")

    def test_changed_options(self):
        cfg, _w = config.validate({})
        self.assertEqual(diag.changed_options(cfg), {})
        cfg, _w = config.validate({"feed": {"order": "newest_first"}})
        self.assertEqual(diag.changed_options(cfg), {"feed.order": "newest_first"})


if __name__ == "__main__":
    unittest.main()
