"""The terminal's parts of the windows' parity that need no screen: notifications from a
terminal (termcaps.notifier / osc, tui/notify.py) and a poll in words (tui/model.py).
termcaps needs nothing; the rest is skipped without Textual (it brings rich)."""

import io
import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import mock

from fedtail import i18n
from fedtail.frontends.tui import termcaps

try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ImportError:
    HAVE_TEXTUAL = False


def caps(name="?", display=False, tmux=False):
    return termcaps.Caps(name, None, display, tmux)


class NotifierChoiceTest(unittest.TestCase):
    def test_desktop_first_then_the_terminal_then_none(self):
        found = {"notify-send": "/usr/bin/notify-send"}.get
        self.assertEqual(termcaps.notifier(caps("kitty", display=True), found),
                         ("notify-send", "/usr/bin/notify-send"))
        nothing = lambda _n: None  # noqa: E731
        self.assertEqual(termcaps.notifier(caps("kitty"), nothing), ("osc", "99"))
        self.assertEqual(termcaps.notifier(caps("foot", display=True), nothing),
                         ("osc", "777"))
        self.assertEqual(termcaps.notifier(caps("iTerm.app"), nothing), ("osc", "9"))
        self.assertEqual(termcaps.notifier(caps("kitty", tmux=True), nothing),
                         ("none", None))  # tmux eats the code
        self.assertEqual(termcaps.notifier(caps("VTE"), nothing), ("none", None))

    def test_escape_codes_cleaned(self):
        k = termcaps.osc("99", "a;b\x07", "body\n")
        self.assertTrue(k.startswith("\x1b]99;i=1:d=0;ab\x1b\\"))
        self.assertIn("p=body;body\x1b\\", k)
        self.assertEqual(termcaps.osc("777", "t", "b"), "\x1b]777;notify;t;b\x1b\\")
        self.assertEqual(termcaps.osc("9", "t", "b"), "\x1b]9;t: b\x1b\\")

    def test_summary_says_where_notifications_go(self):
        lines = termcaps.summary({"TERM": "xterm-kitty"}, lambda _n: None, "linux")
        self.assertIn("notifications: osc", lines)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class NotifierTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")
        self.notes = []
        self.app = SimpleNamespace(
            core=SimpleNamespace(cfg={"notify": {}}, lane_title=lambda n: n),
            lane="home", notify=lambda m, **_k: self.notes.append(str(m)))
        self.app.screen = self.app.screen_stack0 = object()
        self.app.screen_stack = [self.app.screen]

    def make(self, env, which=lambda _n: None, out=None):
        from fedtail.frontends.tui import notify
        with mock.patch.object(termcaps.shutil, "which", which):
            return notify.Notifier(self.app, env, which, out)

    def test_nowhere_says_so(self):
        n = self.make({"TERM": "linux"})
        self.assertEqual(n.backend, "none")
        self.assertEqual(n.test(), i18n._("notify_nothing"))

    def test_the_terminal_code_and_what_is_due(self):
        from fedtail.frontends import notifytext
        out = io.StringIO()
        n = self.make({"TERM": "xterm-kitty"}, out=out)
        self.assertIn("osc", n.test())
        self.assertIn("\x1b]99;", out.getvalue())
        self.assertTrue(n.on_screen("home"))
        self.assertFalse(n.on_screen("local"))
        note = notifytext.Note("t", "b", "home")
        with mock.patch.object(notifytext, "due", return_value=[note]) as due:
            n.notify([("home", None, None)])
        self.assertEqual(due.call_args.args[3], n.on_screen)
        self.assertEqual(out.getvalue().count("\x1b]99;i=1:d=0;t"), 1)

    def test_notify_send_and_a_failure(self):
        n = self.make({"TERM": "xterm", "DISPLAY": ":0"},
                      which=lambda name: "/bin/" + name)
        self.assertEqual(n.backend, "notify-send")
        from fedtail.frontends.tui import notify
        with mock.patch.object(notify.subprocess, "Popen") as popen:
            self.assertIn("notify-send", n.test())
        self.assertEqual(popen.call_args.args[0][0], "/bin/notify-send")
        with mock.patch.object(notify.subprocess, "Popen", side_effect=OSError("gone")):
            n.test()
        self.assertIn("gone", self.notes[-1])


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class PollWordsTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_poll_line(self):
        from fedtail.frontends.tui.model import _via, poll_line
        poll = SimpleNamespace(voters=3, votes=5, expired=False, multiple=True,
                               expires=datetime(2099, 1, 1, tzinfo=UTC))
        line = poll_line(poll, lambda d: "then")
        self.assertIn(i18n._("poll_people", n=3), line)
        self.assertIn(i18n._("poll_until", when="then"), line)
        self.assertIn(i18n._("poll_multiple"), line)
        closed = SimpleNamespace(voters=None, votes=5, expired=True, multiple=True,
                                 expires=None)
        self.assertEqual(poll_line(closed), i18n._("poll_votes", n=5) + " · " +
                         i18n._("poll_closed"))
        self.assertEqual(_via(SimpleNamespace(), None), "")  # a core without via
        self.assertEqual(_via(SimpleNamespace(via=lambda e: "@me@there"), None),
                         "@me@there")


if __name__ == "__main__":
    unittest.main()
