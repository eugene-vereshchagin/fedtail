"""The terminal interface itself, driven headless by Textual's pilot. Skipped when
Textual isn't installed (CI installs it)."""

import unittest

try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ImportError:
    HAVE_TEXTUAL = False

from fedtail import i18n

from . import fakes, test_cli
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
            # posts, and "new below" where reading stood (Textual 8 draws it by the time
            # this looks; 2.x a moment later)
            from fedtail.frontends.common.lane import SEPARATOR
            self.assertTrue(all(isinstance(i, PostItem) or getattr(i, "key", None) == SEPARATOR
                                for i in posts.children))
            # j / k move, and reading on the way marks read (read.mark_read = on_scroll)
            posts.focus()
            posts.index = 0
            await pilot.press("j")  # the next post — over "new below", if it stands between
            await pilot.pause(0.1)
            # counted after the move: "new below" may have come in meanwhile (2.x)
            kids = list(posts.children)
            second = next(i for i, x in enumerate(kids) if i > 0 and isinstance(x, PostItem))
            self.assertEqual(posts.index, second)
            seen = posts.highlighted_child.entry.id
            self.assertNotIn(seen, core.unread_ids([(None, {"id": seen})]))
            await pilot.press("k")
            await pilot.pause(0.1)
            self.assertEqual(posts.index, 0)

            # f likes the post under the cursor
            await pilot.press("f")
            target = posts.highlighted_child.entry.id
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

            # p: the author's profile, with their posts; F follows
            from fedtail.frontends.tui.app import ProfileScreen
            posts.focus()
            posts.index = [getattr(i, "entry", None) and i.entry.id
                           for i in posts.children].index("003")
            await pilot.press("p")
            await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen))
            await self.wait(pilot, lambda: len(app.screen.query_one("#posts").children) >= 1)
            await pilot.press("F")
            await self.wait(pilot, lambda: "B" in w.following)
            await pilot.press("escape")
            await self.wait(pilot, lambda: not isinstance(app.screen, ProfileScreen))

            # another lane from the list
            names = app._lane_names()  # the lanes, the section headings left out
            self.assertIn("replies", names)
            await app.select_lane("replies")
            await self.wait(pilot, lambda: any("a reply to me" in i.entry.text
                                               for i in app.query_one("#posts").children))

            # x: the whole lane read
            await pilot.press("x")
            await self.wait(pilot, lambda: core.unread_count("replies") == 0)

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

    async def test_new_posts_while_another_screen_is_on_top(self):
        """A poll lands while a thread is open (or the composer, after sending): the
        lanes live on the main screen, and the update must find them there."""
        from textual.widgets import ListView

        from fedtail.frontends.tui.app import FedtailApp, LaneItem, ThreadScreen
        core, w = self.make()
        w.add(status("001", BOB, minute=1, text="first", vis="public"), home=True)
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            await self.wait(pilot, lambda: app.lane is not None and
                            len(app.query_one("#posts").children) >= 1)
            main = app.screen
            posts = app.query_one("#posts", ListView)
            posts.focus()
            posts.index = 0
            await pilot.pause(0.1)
            await pilot.press("enter")
            await self.wait(pilot, lambda: isinstance(app.screen, ThreadScreen))
            # a new lane appears (a fresh list) and the open lane gets a post
            w.add(status("002", BOB, minute=2, text="second", vis="public"), home=True)
            before = len(main.query_one("#posts", ListView).children)
            await pilot.pause(0.1)
            core.poll_once()
            await self.wait(pilot, lambda: len(main.query_one("#posts", ListView).children)
                            > before)
            self.assertTrue(any(isinstance(i, LaneItem)
                                for i in main.query_one("#lanes", ListView).children))
            await pilot.press("escape")
            await pilot.press("q")

    async def test_lane_keys_profile_activity_requests(self):
        """[ / ] and digits switch lanes, h / j / l walk the lane list; the profile's
        header stays on screen; Activity and Requests have rows; v opens pictures."""
        from textual.widgets import ListView, Static

        from fedtail.frontends.tui.app import (
            EventItem,
            FedtailApp,
            PictureScreen,
            ProfileScreen,
        )
        core, w = self.make(lanes={"enabled": ["home", "replies", "activity", "requests"]})
        mine = w.add(status("001", ME, minute=1, text="my post", vis="public"), home=True)
        pic = status("003", BOB, minute=3, text="look", vis="public")
        pic["media_attachments"] = [{"id": "m1", "type": "image",
                                     "url": "https://example.test/m1.png",
                                     "preview_url": "https://example.test/m1s.png"}]
        w.add(pic, home=True)
        w.act("a0", "follow", BOB, minute=1)  # history: the first fetch is seen
        app = FedtailApp(core)

        def no_network(url):  # the pictures: not fetched from example.test
            from concurrent.futures import Future
            f = Future()
            f.set_exception(OSError("no network in tests"))
            return f
        app.core.media_bytes = no_network
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            w.act("a1", "favourite", BOB, st=mine, minute=5)
            w.requests.append(fakes.acct("Q", "quinn@example.org"))
            core.poll_once()
            await self.wait(pilot, lambda: app.lane is not None)
            # the first rounds drawn before a key comes (under a loaded machine a key
            # pressed mid-redraw went to the lane being replaced)
            await self.wait(pilot, lambda: not getattr(app, "_redraw_pending", False))
            await pilot.pause(0.3)
            names = app._lane_names()
            first = app.lane
            await pilot.press("right_square_bracket")
            await self.wait(pilot, lambda: app.lane == names[(names.index(first) + 1)
                                                              % len(names)])
            await pilot.press("1")
            await self.wait(pilot, lambda: app.lane == names[0])
            await pilot.press("h")
            lanes = app.query_one("#lanes", ListView)
            self.assertTrue(lanes.has_focus)
            before = lanes.index
            await pilot.press("j")
            await pilot.pause(0.1)
            self.assertEqual(lanes.index, before + 1)
            while not hasattr(lanes.highlighted_child, "lane"):  # a section's heading
                await pilot.press("j")
                await pilot.pause(0.05)
            target = lanes.highlighted_child.lane
            await pilot.press("l")
            await self.wait(pilot, lambda: app.lane == target)

            await app.select_lane("activity")  # a lane like any other, its rows events
            await self.wait(pilot, lambda: any(isinstance(i, EventItem)
                                               for i in app.query_one("#posts").children))
            await app.select_lane("requests")
            await self.wait(pilot, lambda: any(isinstance(i, EventItem) and i.parts.answers
                                               for i in app.query_one("#posts").children))
            posts = app.query_one("#posts", ListView)
            posts.focus()
            posts.index = 0
            await pilot.press("a")  # the request's "approve"
            await self.wait(pilot, lambda: not w.requests)

            await app.select_lane("home")
            await self.wait(pilot, lambda: len(app.query_one("#posts").children) >= 2)
            posts = app.query_one("#posts", ListView)
            posts.focus()
            posts.index = [getattr(i, "entry", None) and i.entry.id
                           for i in posts.children].index("003")
            await pilot.press("p")
            await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen))
            await self.wait(pilot, lambda: len(app.screen.query_one("#posts").children) >= 1)
            await pilot.pause(0.2)
            title = app.screen.query_one("#title", Static)
            self.assertEqual(title.region.y, 0)  # the header is still at the top
            self.assertGreater(title.region.height, 0)
            await pilot.press("escape")
            await self.wait(pilot, lambda: not isinstance(app.screen, ProfileScreen))
            await pilot.press("v")
            await self.wait(pilot, lambda: isinstance(app.screen, PictureScreen))
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


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class MarkupTest(unittest.IsolatedAsyncioTestCase):
    async def test_words_are_shown_not_read_as_markup(self):
        """A post's words in a dialog (deleting it: "Sure? «…»") are text, not Textual
        markup: "[/b]" broke the dialog, "[@click=app.quit]" was an action."""
        from textual.app import App
        from textual.widgets import Static

        from fedtail.frontends.tui.screens import ConfirmScreen

        text = "a [/b] and [@click=app.quit]quit[/] [b]x"
        app = App()
        async with app.run_test() as pilot:
            app.push_screen(ConfirmScreen("[/i] title", text))
            await pilot.pause(0.1)
            shown = str(app.screen.query_one("#q-text", Static).render())
            self.assertIn("[/b]", shown)
            self.assertIn("[@click=app.quit]", shown)
            await pilot.press("n")
            await pilot.pause(0.05)
            self.assertTrue(app.is_running)
