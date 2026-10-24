"""The terminal commands (frontends/cli.py), the corners tests/test_cli.py leaves: colour
on a terminal, a boost, a reply, a direct post and pictures in a post's head, a lane by
a list's title, a lazy lane, tail over every lane, a reply to nothing, sync's failures,
not logged in, Ctrl+C."""

import io
import os
import threading
import time
from datetime import UTC, datetime, timedelta
from unittest import mock

from fedtail.core.view import View
from fedtail.frontends import cli
from fedtail.protocols.mastodon import adapter

from . import test_cli
from .fakes import BOB, ME, NEWS, status
from .test_core import TmpDir


class Tty(io.StringIO):
    def isatty(self):
        return True


class Stubborn(io.StringIO):
    def reconfigure(self, **_kw):
        raise ValueError("can't")


class CliCornersTest(TmpDir):
    make = test_cli.CliTest.make
    run_cli = test_cli.CliTest.run_cli

    def test_colour_on_a_terminal_and_no_color(self):
        self.assertTrue(cli.Out({"color": "auto"}, Tty()).color)
        with mock.patch.dict(os.environ, {"NO_COLOR": "1"}):
            self.assertFalse(cli.Out({"color": "auto"}, Tty()).color)
        self.assertFalse(cli.Out({"color": "never"}, Tty()).color)
        self.assertFalse(cli.Out({}, Stubborn()).color)  # a stream that can't reconfigure

    def test_when(self):
        self.assertEqual(cli._when(None), "?")
        now = datetime.now(UTC)
        self.assertRegex(cli._when(now), r"^\d\d:\d\d$")
        self.assertRegex(cli._when(now - timedelta(days=40)), r"^\d\d\.\d\d \d\d:\d\d$")

    def test_a_post_head_says_boost_reply_direct_and_pictures(self):
        core, _w = self.make()
        inner = status("001", BOB, "000", "N", minute=1, vis="direct", text="hello")
        inner["media_attachments"] = [{"type": "image", "url": "https://x/a.png"}]
        boost = status("002", NEWS, minute=2, text="")
        boost["reblog"] = inner
        out = io.StringIO()
        cli.print_post(cli.Out({}, out), View(core), adapter.post(boost), "a1", unread=True)
        head = out.getvalue().splitlines()[0]
        for mark in ("#a1", "@bob@social.example", "♻ @georgia_news", "↳", "✉", "•"):
            self.assertIn(mark, head)
        self.assertIn("1", out.getvalue().splitlines()[2])  # "[1 attachment]"
        nobody = dict(status("003", BOB, minute=3), account=dict(BOB, acct="", username=""))
        out = io.StringIO()
        cli.print_post(cli.Out({}, out), View(core), adapter.post(nobody), None)
        self.assertIn("@?", out.getvalue())

    def test_a_lane_by_a_lists_title_and_a_lazy_lane(self):
        core, w = self.make()
        w.lists["L1"] = {"title": "Друзья", "exclusive": False, "members": {"B"}}
        w.add(status("001", BOB, minute=1, text="for friends"), home=True)
        core.connect().result()
        core._refresh_lists()
        view = View(core)
        self.assertEqual(cli._lane_name(view, "друзья"), "list:L1")
        self.assertEqual(cli._lane_name(view, "list:Друзья"), "list:L1")
        self.assertEqual(cli._lane_name(view, "comments"), "replies")  # an old name
        w.local.append(status("009", NEWS, minute=9, text="local news"))
        got = self.run_cli(core, "show", "local", "--mark-read")
        self.assertIn("local news", got)
        view = View(core)
        self.assertEqual(view.unread(view.entries("local")), set())

    def test_tail_over_every_lane_marks_read(self):
        core, w = self.make(notify={"lanes": ["all"], "except": ["federated", "local"]})
        w.add(status("001", BOB, minute=1, text="old one"), home=True)
        core.connect().result()
        core.poll_once()
        out, stop = io.StringIO(), threading.Event()
        args = cli.parser().parse_args(["tail", "-n", "1", "--mark-read"])
        view = View(core)
        t = threading.Thread(target=cli.cmd_tail, args=(view, cli.Out({}, out), args, stop))
        t.start()
        try:
            deadline = time.monotonic() + 10
            while "old one" not in out.getvalue() and time.monotonic() < deadline:
                time.sleep(0.05)
            w.add(status("002", ME, minute=2, text="fresh one"), home=True)
            core.poll_now()
            while "fresh one" not in out.getvalue() and time.monotonic() < deadline:
                time.sleep(0.05)
            time.sleep(1.2)  # a round with nothing new: the wait goes on
        finally:
            stop.set()
            t.join(5)
        text = out.getvalue()
        self.assertIn("old one", text)  # -n 1: the last one of each first
        self.assertEqual(text.count("fresh one"), 1)  # once, though in two lanes
        tailing = next(x for x in text.splitlines() if "home" in x and "," in x)
        self.assertNotIn("federated", tailing)
        fresh = [x for x in view.entries("home") if x[1].id == "002"]
        self.assertTrue(fresh)
        self.assertEqual(view.unread(fresh), set())

    def test_tail_falls_back_to_home(self):
        core, _w = self.make()
        core.connect().result()
        view = View(core)
        view.cfg["cli"]["tail_lanes"] = ["no-such-lane"]
        stop = threading.Event()
        stop.set()
        out = io.StringIO()
        with mock.patch.object(type(core), "start_polling"):
            cli.cmd_tail(view, cli.Out({}, out), cli.parser().parse_args(["tail"]), stop)
        self.assertIn("home", out.getvalue())

    def test_reply_to_nothing(self):
        core, _w = self.make()
        with self.assertRaises(SystemExit) as e:
            self.run_cli(core, "post", "--reply", "#zzz/2", "text")
        self.assertIn("zzz", str(e.exception.code))

    def test_not_logged_in_and_ctrl_c(self):
        core, _w = self.make()
        core.paths.auth_file.unlink()
        with mock.patch.object(type(core), "logged_in", new_callable=mock.PropertyMock,
                               return_value=False):
            with self.assertRaises(SystemExit):
                self.run_cli(core, "lanes")
            with self.assertRaises(SystemExit):
                self.run_cli(core, "sync", "login")
        core, _w = self.make()
        with mock.patch.object(cli, "cmd_lanes", side_effect=KeyboardInterrupt):
            self.assertEqual(self.run_cli(core, "lanes"), "")

    def test_sync_now_that_fails(self):
        core, _w = self.make()
        view = View(core)
        st = {"backend": "folder", "where": "/x", "login": "", "device": "d", "key": "",
              "pending": 0, "last": {"error": "unreachable"}}
        with mock.patch.object(type(view), "sync_status", return_value=st, create=True), \
                mock.patch.object(type(view), "sync_now", return_value=None, create=True):
            out = io.StringIO()
            args = cli.parser().parse_args(["sync", "now"])
            cli.cmd_sync(view, cli.Out({}, out), args)
        self.assertIn("unreachable", out.getvalue())
