"""The terminal commands (fedtail show / tail / post / read / lanes)."""

import io
import threading
import time

from fedtail import __main__ as entry
from fedtail.core import auth, config, paths
from fedtail.core.app import Core
from fedtail.frontends import cli

from . import fakes
from .fakes import BOB, FakeApi, status
from .test_core import TmpDir


class CliTest(TmpDir):
    def make(self, **over):
        FakeApi.world = fakes.World()
        user = {"feed": {"first_run_mark_read": False, "page_size": 3}, "ui": {"language": "en"}}
        for k, v in over.items():
            user.setdefault(k, {}).update(v)
        cfg, _ = config.validate(user)
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        self.addCleanup(core.shutdown)
        return core, FakeApi.world

    def run_cli(self, core, *argv):
        out = io.StringIO()
        cli.run(core, list(argv), stream=out)
        return out.getvalue()

    def test_show_prints_posts_with_aliases(self):
        core, w = self.make()
        w.add(status("001", BOB, minute=1, text="hello there"), home=True)
        w.add(status("002", BOB, minute=2, text="second"), home=True)
        got = self.run_cli(core, "show", "home")
        self.assertIn("@bob@social.example", got)
        self.assertIn("hello there", got)
        self.assertLess(got.index("hello there"), got.index("second"))  # oldest first
        self.assertRegex(got, r"#[0-9a-z]+ ")
        self.assertNotIn("\033[", got)  # not a terminal: no colour

    def test_show_n_unread_and_mark_read(self):
        core, w = self.make()
        for i in range(1, 4):
            w.add(status(f"00{i}", BOB, minute=i, text=f"post{i}"), home=True)
        got = self.run_cli(core, "show", "home", "-n", "1")
        self.assertIn("post3", got)
        self.assertNotIn("post1", got)
        core2, _w = self._again(core)
        self.run_cli(core2, "read", "home")
        core3, _w = self._again(core2)
        self.assertNotIn("post", self.run_cli(core3, "show", "home", "--unread"))

    def _again(self, core):
        """A second run of the command, as from the shell: a new Core on the same data."""
        c = Core(core.cfg, core.paths, api_class=FakeApi)
        c._origin_json = lambda url: None
        self.addCleanup(c.shutdown)
        return c, FakeApi.world

    def test_cw_hidden_unless_expand(self):
        core, w = self.make(ui={"expand_cw": False, "arts_mode": False})
        st = status("001", BOB, minute=1, text="the spoiler")
        st["spoiler_text"] = "careful"
        w.add(st, home=True)
        got = self.run_cli(core, "show", "home")
        self.assertIn("careful", got)
        self.assertNotIn("the spoiler", got)
        core2, w = self.make(ui={"expand_cw": True, "arts_mode": False})
        w.add(st, home=True)
        self.assertIn("the spoiler", self.run_cli(core2, "show", "home"))
        # arts mode opens it whatever expand_cw says
        core3, w = self.make(ui={"expand_cw": False, "arts_mode": True})
        w.add(st, home=True)
        self.assertIn("the spoiler", self.run_cli(core3, "show", "home"))

    def test_max_lines_and_color(self):
        core, w = self.make(cli={"max_lines": 1, "color": "always"})
        w.add(status("001", BOB, minute=1, text="one<br>two<br>three"), home=True)
        got = self.run_cli(core, "show", "home")
        self.assertIn("\033[", got)
        self.assertNotIn("three", got)
        self.assertIn("…", got)

    def test_post_and_reply(self):
        core, w = self.make()
        w.add(status("001", BOB, minute=1, vis="public"), home=True)
        got = self.run_cli(core, "show", "home")
        alias = got.split()[0]  # "#a3f"
        core2, w = self._again(core)
        out = self.run_cli(core2, "post", "--reply", alias, "-v", "unlisted", "a reply")
        self.assertIn("sent", out)
        self.assertEqual(w.posted[-1][1:3], ("unlisted", "001"))

    def test_post_from_stdin_and_empty(self):
        core, w = self.make()
        args = cli.parser().parse_args(["post", "-"])
        core.connect().result()
        cli.cmd_post(core, cli.Out({}, io.StringIO()), args, stdin=io.StringIO("from a pipe\n"))
        self.assertIn("from a pipe", w.posted[-1][0])
        with self.assertRaises(SystemExit):
            cli.cmd_post(core, cli.Out({}, io.StringIO()), args, stdin=io.StringIO("  "))

    def test_unknown_lane_names_the_known(self):
        core, _w = self.make()
        with self.assertRaises(SystemExit) as e:
            self.run_cli(core, "show", "nosuch")
        self.assertIn("home", str(e.exception.code))

    def test_lanes_lists_counts(self):
        core, w = self.make()
        w.add(status("001", BOB, minute=1), home=True)
        got = self.run_cli(core, "lanes")
        line = next(x for x in got.splitlines() if x.startswith("home "))
        self.assertTrue(line.rstrip().endswith("1"))

    def test_tail_prints_what_arrives(self):
        core, w = self.make()
        w.add(status("001", BOB, minute=1, text="old one"), home=True)
        core.connect().result()
        core.poll_once()
        out, stop = io.StringIO(), threading.Event()
        args = cli.parser().parse_args(["tail", "home"])
        t = threading.Thread(target=cli.cmd_tail, args=(core, cli.Out({}, out), args, stop))
        t.start()
        try:
            time.sleep(0.3)
            w.add(status("002", BOB, minute=2, text="fresh one"), home=True)
            core.poll_now()
            deadline = time.monotonic() + 10
            while "fresh one" not in out.getvalue() and time.monotonic() < deadline:
                time.sleep(0.05)
        finally:
            stop.set()
            t.join(5)
        self.assertIn("fresh one", out.getvalue())
        self.assertNotIn("old one", out.getvalue())

    def test_disabled_and_entry_args(self):
        args = entry.parse_args(["-p", "x", "show", "replies", "-n", "5"])
        self.assertEqual((args.profile, args.command, args.rest), ("x", "show",
                                                                 ["replies", "-n", "5"]))
        self.assertIsNone(entry.parse_args([]).command)
