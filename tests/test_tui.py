"""The terminal interface itself, driven headless by Textual's pilot. Skipped when
Textual isn't installed (CI installs it)."""

import unittest

try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ImportError:
    HAVE_TEXTUAL = False

from fedtail import i18n

from . import test_cli
from .fakes import BOB, ME, status
from .test_core import TmpDir


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class TuiTest(TmpDir, unittest.IsolatedAsyncioTestCase):
    make = test_cli.CliTest.make

    def setUp(self):
        TmpDir.setUp(self)
        i18n.setup("en")

    async def wait(self, pilot, cond, timeout=10):
        import asyncio
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while loop.time() < end:
            await pilot.pause(0.05)
            if cond():
                return True
        self.fail("condition not reached")

    async def test_lanes_posts_keys_and_commands(self):
        from textual.widgets import Input, ListView

        from fedtail.frontends.tui.app import FedtailApp, LaneItem, PostItem, ThreadScreen
        core, w = self.make(read={"mark_read": "on_scroll"})
        mine = w.add(status("001", ME, minute=1, text="my post", vis="public"), home=True)
        w.add(status("002", BOB, mine["id"], "ME", minute=2, text="a reply to me"),
              home=True, mention=True)
        w.add(status("003", BOB, minute=3, text="something else", vis="public"), home=True)
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            await self.wait(pilot, lambda: any(isinstance(i, LaneItem)
                                               for i in app.query_one("#lanes").children))
            await self.wait(pilot, lambda: app.lane is not None and
                            len(app.query_one("#posts").children) >= 2)
            posts = app.query_one("#posts", ListView)
            self.assertTrue(all(isinstance(i, PostItem) for i in posts.children))
            # j / k move, and reading on the way marks read (read.mark_read = on_scroll)
            posts.focus()
            posts.index = 0
            await pilot.press("j")
            await pilot.pause(0.1)
            self.assertEqual(posts.index, 1)
            seen = posts.highlighted_child.status["id"]
            self.assertNotIn(seen, core.unread_ids([(None, posts.highlighted_child.status)]))
            await pilot.press("k")
            await pilot.pause(0.1)
            self.assertEqual(posts.index, 0)

            # f likes the post under the cursor
            await pilot.press("f")
            target = posts.highlighted_child.status["id"]
            await self.wait(pilot, lambda: w.statuses[target].get("favourited"))

            # r puts "#alias " in the command line; Enter sends the reply
            await pilot.press("r")
            cmd = app.query_one("#cmd", Input)
            self.assertTrue(cmd.has_focus)
            self.assertTrue(cmd.value.startswith("#"))
            before = len(w.posted)
            await pilot.press(*"thanks")
            await pilot.press("enter")
            await self.wait(pilot, lambda: len(w.posted) == before + 1)
            self.assertIn("thanks", w.posted[-1][0])
            self.assertEqual(w.posted[-1][2], target)

            # Enter on a post: its thread; Esc: back
            posts.focus()
            await pilot.press("enter")
            await self.wait(pilot, lambda: isinstance(app.screen, ThreadScreen))
            await self.wait(pilot, lambda: len(app.screen.query_one("#posts").children) >= 1)
            await pilot.press("escape")
            await self.wait(pilot, lambda: not isinstance(app.screen, ThreadScreen))

            # another lane from the list
            lanes = app.query_one("#lanes", ListView)
            names = [i.lane for i in lanes.children]
            self.assertIn("comments", names)
            await app.select_lane("comments")
            await self.wait(pilot, lambda: any("a reply to me" in i.status["content"]
                                               for i in app.query_one("#posts").children))

            # x: the whole lane read
            await pilot.press("x")
            await self.wait(pilot, lambda: core.unread_count("comments") == 0)

            # a bad command says so, a plain line is a post
            cmd.focus()
            cmd.value = "#zzz9 hi"
            await pilot.press("enter")
            await pilot.pause(0.2)
            self.assertEqual(cmd.value, "#zzz9 hi")  # not sent, kept for fixing
            cmd.value = "hello from the terminal"
            before = len(w.posted)
            await pilot.press("enter")
            await self.wait(pilot, lambda: len(w.posted) == before + 1)
            await pilot.press("escape")
            await pilot.press("q")

    async def test_login_screen_without_token(self):
        from fedtail.core import auth
        from fedtail.frontends.tui.app import FedtailApp, LoginScreen
        core, _w = self.make()
        auth.forget(core.paths.auth_file)
        core.auth = None
        app = FedtailApp(core)
        async with app.run_test(size=(100, 30)) as pilot:
            await self.wait(pilot, lambda: isinstance(app.screen, LoginScreen))
            await pilot.press("escape")


if __name__ == "__main__":
    unittest.main()
