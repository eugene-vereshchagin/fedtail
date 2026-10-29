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


class SecretsTest(unittest.TestCase):
    """The config's secrets — an API key, a proxy's or a WebDAV address's password — go
    into neither the log nor the bug report as they are."""

    def tearDown(self):  # whatever a test did, no proxy is left for the next ones
        import os
        for name in config._PROXY_VARS:
            self.assertNotIn("proxy.example", os.environ.get(name, ""))

    TEXT = ('[feed]\ntranslate_key = "sk-live-123"\ntranslate_url = "https://t.example"\n'
            '[net]\nproxy = "socks5h://me:hunter2@proxy.example:1080"\n'
            '[sync]\nwebdav = "https://bob:pw@dav.example/fedtail"\n')

    def test_the_text_and_the_options(self):
        got = diag.redact_config(self.TEXT)
        for secret in ("sk-live-123", "hunter2", "me:", "bob:pw"):
            self.assertNotIn(secret, got)
        self.assertIn('translate_key = "***"', got)
        self.assertIn("socks5h://***@proxy.example:1080", got)
        self.assertIn('translate_url = "https://t.example"', got)  # the rest as it is
        self.assertEqual(diag.redact_config('translate_key = ""\n'), 'translate_key = ""\n')
        cfg, _w = config.validate({"feed": {"translate_key": "sk-live-123"},
                                   "net": {"proxy": "http://me:hunter2@p.example:3128"}})
        opts = diag.changed_options(cfg)
        self.assertEqual(opts["feed.translate_key"], "***")
        self.assertEqual(opts["net.proxy"], "http://***@p.example:3128")
        self.assertEqual(diag.redact({"translate_key": "x", "l": ["ftp://a:b@h"]}),
                         {"translate_key": "***", "l": ["ftp://***@h"]})

    def test_not_in_the_log_nor_the_report(self):
        import tarfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            p = paths.resolve("t", config=str(Path(d) / "c.toml"), data=str(Path(d) / "data"))
            p.config_file.write_text(self.TEXT, "utf-8")
            import tomllib  # validate, not load: load puts net.proxy into the environment
            cfg, _w = config.validate(tomllib.loads(self.TEXT))
            with mock.patch.object(diag, "is_on", return_value=True), \
                    self.assertLogs("fedtail", logging.INFO) as got:
                diag.debug_context(p, cfg, "qt")
            text = "\n".join(got.output)
            for secret in ("sk-live-123", "hunter2", "bob:pw"):
                self.assertNotIn(secret, text)
            out = diag.bug_report(p, d, cfg)
            with tarfile.open(out) as tar:
                kept = tar.extractfile("config.toml").read().decode()
                self.assertIn("system.txt", tar.getnames())
            for secret in ("sk-live-123", "hunter2", "bob:pw"):
                self.assertNotIn(secret, kept)
            self.assertIn("proxy.example", kept)


if __name__ == "__main__":
    unittest.main()
