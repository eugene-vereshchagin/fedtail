"""The rest of the small modules, case by case: Pango markup from HTML and Markdown
(pango), the desktop notifications' words (notifytext), a theme's sounds when the theme
is broken (soundpack), help pages that aren't there (helpdocs), a frontend that can't be
loaded, the menu entry (desktop), the version from git or a build (version), the
interface's language from the environment (i18n), and the model's text helpers."""

import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from fedtail import i18n
from fedtail.frontends import notifytext, pango
from fedtail.model import Mention, Ref
from fedtail.model import text as mtext
from fedtail.protocols.mastodon import adapter

from .fakes import BOB, status

_ = i18n._


class PangoTest(unittest.TestCase):
    def test_pre_quote_and_lone_tags(self):
        got = pango.markup("<p>a<br/>b</p><pre>x &lt; y</pre><b>bold</b>", sanitized=True)
        self.assertIn("<tt>x &lt; y</tt>", got)
        self.assertIn("<b>bold</b>", got)
        self.assertIn("a\nb", got)
        open_quote = pango.markup("<blockquote><p>q</p>", sanitized=True)  # never closed
        self.assertIn(pango.QUOTE_MARK.strip(), open_quote)
        self.assertEqual(pango.markup("<p></p>", sanitized=True), "")
        self.assertEqual(pango.markup("a</b>", sanitized=True), "a")  # an end of nothing
        self.assertEqual(pango.markup("<b>never closed", sanitized=True),
                         "<b>never closed</b>")  # closed at the end: Pango wants it
        b = pango._Builder()
        b._put("")  # nothing to add: nothing added
        self.assertEqual(b.result(), "")

    def test_markdown_quotes_and_unclosed_code(self):
        got = pango.markdown("> said\n```\ncode <here>")
        self.assertIn("<i>" + pango.QUOTE_MARK + "said</i>", got)
        self.assertTrue(got.endswith("<tt>code &lt;here&gt;</tt>"))


class NotifyTextTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_due(self):
        view = mock.Mock()
        view.model_of = lambda items: items
        notes = [notifytext.Note("t", "b", "home"), notifytext.Note("t", "b", "replies")]
        cfg = {"enabled": True, "privacy": "full", "when_focused": False}
        self.assertEqual(notifytext.due(view, [], cfg, lambda lane: False), [])
        with mock.patch.object(notifytext, "build", return_value=notes):
            self.assertEqual(notifytext.due(view, [1], dict(cfg, enabled=False),
                                            lambda lane: False), [])
            with self.assertLogs("fedtail", "INFO"):
                got = notifytext.due(view, [1], cfg, lambda lane: lane == "home")
            self.assertEqual([n.lane for n in got], ["replies"])

    def test_many_posts_say_how_many_more(self):
        posts = [adapter.post(status(str(i), BOB, minute=i, text=f"p{i}")) for i in range(5)]
        note = notifytext._note("home", posts, "full")
        self.assertIn(_("notify_more", n=2).strip(), note.body)


class SoundsHelpLoadTest(unittest.TestCase):
    def test_a_broken_theme_has_no_sounds(self):
        from fedtail.frontends import soundpack
        soundpack._scheme_of.cache_clear()
        self.addCleanup(soundpack._scheme_of.cache_clear)
        with self.assertLogs("fedtail", "WARNING"):
            s = soundpack._scheme_of("no-such-theme")
        self.assertEqual(s.source, "none")

    def test_a_help_page_not_there(self):
        from fedtail.frontends import helpdocs
        self.assertIsNone(helpdocs.page("en", "no-such-page"))

    def test_a_frontend_that_cant_load(self):
        from fedtail import frontends
        err = ImportError("No module named 'PySide6'")
        import io
        with mock.patch.object(sys, "stderr", io.StringIO()), \
                mock.patch.object(frontends.importlib, "import_module", side_effect=err):
            with self.assertRaises(SystemExit) as e:
                frontends.load("qt")
        self.assertEqual(e.exception.code, 3)
        other = ImportError("No module named 'mine'")
        with mock.patch.object(frontends.importlib, "import_module", side_effect=other):
            with self.assertRaises(ImportError):
                frontends.load("qt")


class DesktopTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        env = {"XDG_DATA_HOME": str(Path(self._tmp.name) / "data"),
               "XDG_CONFIG_HOME": str(Path(self._tmp.name) / "cfg"),
               "XDG_DATA_DIRS": str(Path(self._tmp.name) / "none")}
        p = mock.patch.dict(os.environ, env)
        p.start()
        self.addCleanup(p.stop)
        from fedtail import desktop
        self.d = desktop

    def test_the_one_file_build_runs_itself(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            text = self.d.entry_text("work")
        self.assertIn(f'Exec="{sys.executable}" --profile work', text)
        self.assertNotIn("Path=", text)

    def test_install_tells_the_desktop(self):
        with mock.patch.object(self.d.shutil, "which", lambda n: "/usr/bin/" + n), \
                mock.patch.object(self.d.subprocess, "run") as run:
            entry, _icon = self.d.install("work")
        cmds = [c[0][0][0] for c in run.call_args_list]
        self.assertEqual(cmds, ["xdg-mime", "update-desktop-database", "gtk-update-icon-cache",
                                "kbuildsycoca6", "kbuildsycoca5"])
        self.assertTrue(entry.is_file())
        with mock.patch.object(self.d.shutil, "which", return_value=None):
            self.assertIsNone(self.d.ensure("work"))  # all in place: nothing to do
        self.assertFalse(self.d._ours(entry.parent))  # a folder: not an entry of ours
        self.assertEqual(self.d._remove_own("nobody"), [])
        self.assertIsNone(self.d.system_entry())

    def test_windows_and_mac(self):
        with mock.patch.object(self.d.os, "name", "nt"), \
                mock.patch.object(self.d, "_windows_install", return_value=("E", "I")):
            self.assertEqual(self.d.install("work"), ("E", "I"))
            self.assertIsNone(self.d.ensure("work"))


class VersionTest(unittest.TestCase):
    def setUp(self):
        from fedtail import version
        self.v = version
        version.info.cache_clear()
        self.addCleanup(version.info.cache_clear)

    def test_a_build_says_its_own(self):
        build = types.ModuleType("fedtail._build")
        build.BUILD, build.COMMIT, build.DATE = "1.2.3", "abc", "2026-01-01"
        with mock.patch.dict(sys.modules, {"fedtail._build": build}):
            self.assertEqual(self.v.info(), {"version": "1.2.3", "commit": "abc",
                                             "date": "2026-01-01"})

    def test_from_git(self):
        answers = {"rev-parse": "abc1234", "log": "2026-10-24", "status": "",
                   "describe": "v0.18.0-7-gabc1234"}
        with mock.patch.object(self.v, "_git", lambda *a: answers[a[0]]), \
                mock.patch.object(self.v.shutil, "which", return_value="/usr/bin/git"):
            got = self.v.info()
        self.assertIn("abc1234", got["version"])
        self.assertEqual(got["commit"], "abc1234")
        self.v.info.cache_clear()
        with mock.patch.object(self.v, "_git", side_effect=ValueError), \
                mock.patch.object(self.v.shutil, "which", return_value="/usr/bin/git"):
            self.assertEqual(self.v.info()["commit"], "")


class LanguageTest(unittest.TestCase):
    def test_detect(self):
        with mock.patch.dict(os.environ, {"LC_ALL": "", "LC_MESSAGES": "", "LANG": "ru_RU"}):
            self.assertEqual(i18n.detect(), "ru")
        with mock.patch.dict(os.environ, {"LC_ALL": "", "LC_MESSAGES": "", "LANG": ""}), \
                mock.patch.object(i18n.locale, "getlocale", side_effect=ValueError):
            self.assertEqual(i18n.detect(), "en")


class ModelTextTest(unittest.TestCase):
    def test_snippets(self):
        warned = adapter.post(dict(status("1", BOB, text=""), content="",
                                   spoiler_text="cw words"))
        self.assertEqual(mtext.snippet(warned), "cw words")
        pic = dict(status("2", BOB, text=""), content="")
        pic["media_attachments"] = [{"id": "m", "type": "image", "url": "https://x/a.png"}]
        self.assertEqual(mtext.snippet(adapter.post(pic)), "[1 × media]")
        self.assertEqual(mtext.snippet_html("<p>" + "word " * 50 + "</p>", 20)[-1], "…")
        self.assertEqual(mtext.without_quote_fallback(None), "")

    def test_tag_stuffing_without_links_stays(self):
        html = "<p>#a #b #c #d #e</p>"
        self.assertEqual(mtext.collapse_tag_stuffing(html), html)

    def test_bots_by_name(self):
        acc = adapter.account(dict(BOB, bot=False))
        self.assertTrue(mtext.is_bot(acc, ["@bob@social.example"]))
        self.assertFalse(mtext.is_bot(acc))

    def test_held_back_without_a_post(self):
        h = adapter.held_back({"id": "R", "account": {"id": "A", "acct": "a"},
                               "last_status": "gone"})
        self.assertIsNone(h.last)

    def test_refs_and_mentions(self):
        r = Ref("mastodon", "work", "7")
        self.assertEqual(str(r), "mastodon:work:7")
        self.assertEqual(Mention(r, "a@b").id, "7")


if __name__ == "__main__":
    unittest.main()
