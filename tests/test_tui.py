"""The terminal interface itself, driven headless by Textual's pilot. Skipped when
Textual isn't installed (CI installs it)."""

import unittest

try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ImportError:
    HAVE_TEXTUAL = False

from fedtail import i18n

from . import fakes, test_cli, test_cov_tui_host
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

    async def test_a_slow_server_is_tried_again(self):
        """The server not answering at the start: the windows say it and connect again
        in 20 s; the terminal only said it (23.11)."""
        from concurrent.futures import Future
        from unittest import mock

        from fedtail.frontends.tui.app import FedtailApp, LaneItem
        core, _w = self.make()
        core.me = None
        real = core.connect
        slow = Future()
        slow.set_exception(TimeoutError("Read timed out"))
        app = FedtailApp(core)
        core.cfg["net"]["retry_seconds"] = 0.2  # server.retry_seconds: the wait is the config's
        with mock.patch.object(core, "connect", side_effect=[slow, real()]) as conn:
            async with app.run_test(size=(120, 40)) as pilot:
                await self.wait(pilot, lambda: conn.call_count == 2)
                await self.wait(pilot, lambda: any(isinstance(i, LaneItem)
                                                   for i in app.query_one("#lanes").children))

    async def test_a_lane_is_read_as_it_opens(self):
        """read.mark_read = "on_open": the windows, the page and the phone read a lane as
        it opens; the terminal read only while scrolling (21.11)."""
        from fedtail.frontends.tui.app import FedtailApp, LaneItem
        core, w = self.make(read={"mark_read": "on_open"},
                            feed={"first_run_mark_read": False})
        for i in range(3):
            w.add(status(f"01{i}", BOB, minute=10 + i, text=f"post {i}", vis="public"),
                  home=True)
        core.poll_once()  # there when the lane opens
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.wait(pilot, lambda: any(isinstance(i, LaneItem)
                                               for i in app.query_one("#lanes").children))
            ids = [(None, {"id": f"01{i}"}) for i in range(3)]
            await self.wait(pilot, lambda: app.lane == "home" and not core.unread_ids(ids))

    async def test_new_posts_take_the_cursor_to_them(self):
        """feed.on_new = "jump_to_newest": the terminal goes to the newest end when new
        posts come, as the windows (it stood: 21.11)."""
        from textual.widgets import ListView

        from fedtail.frontends.tui.app import FedtailApp
        core, w = self.make(feed={"on_new": "jump_to_newest", "first_run_mark_read": False,
                                  "order": "oldest_first"})
        for i in range(3):
            w.add(status(f"02{i}", BOB, minute=20 + i, text=f"old {i}", vis="public"),
                  home=True)
        core.poll_once()
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.wait(pilot, lambda: app.lane == "home" and
                            len(app.query_one("#posts").children) >= 3)
            posts = app.query_one("#posts", ListView)
            posts.index = 0
            await pilot.pause(0.2)
            w.add(status("029", BOB, minute=29, text="the newest", vis="public"), home=True)
            core.poll_once()
            await self.wait(pilot, lambda: getattr(posts.highlighted_child, "key", None)
                            == "029")

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
            # j / k move, and reading on the way marks read (read.mark_read = on_scroll);
            # the lane settled first ("new below" may come a moment later: 1 of 4 runs)
            await pilot.pause(0.5)
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

    async def test_private_thread_frames_none(self):
        """The thread screen marks a private message as the lanes do (a frame), and none
        in a thread of private messages only (model.only_private)."""
        from textual.widgets import ListView

        from fedtail.frontends.tui.app import FedtailApp, ThreadScreen
        core, w = self.make()
        core.cfg["ui"]["direct_highlight"] = "frame"
        w.add(status("001", BOB, minute=1, text="open", vis="public"), home=True)
        w.add(status("002", ME, "001", "B", minute=2, text="dm", vis="direct"))
        w.add(status("010", BOB, minute=10, text="psst", vis="direct"), mention=True)
        w.add(status("011", ME, "010", "B", minute=11, text="ok", vis="direct"))
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            for sid, framed in (("002", ["002"]), ("011", [])):
                screen = ThreadScreen(sid)
                app.push_screen(screen)
                # this very screen, its two posts in (a slow runner: 12.11)
                await self.wait(pilot, lambda s=screen: app.screen is s and
                                len(s.query_one("#posts", ListView).children) == 2,
                                timeout=30)
                items = app.screen.query_one("#posts", ListView).children
                self.assertEqual([i.key for i in items if i.has_class("dm-frame")], framed)
                app.pop_screen()
                await pilot.pause(0.1)
            await pilot.press("q")

    async def test_thread_keys(self):
        """] / [ the next / previous top comment, - folds the branch and shows it again —
        pressed, as in Qt (common/postkeys); the terminal had no - (23.11)."""
        from textual.widgets import ListView

        from fedtail.frontends.tui.app import FedtailApp, ThreadScreen
        core, w = self.make()
        w.add(status("700", BOB, minute=1, text="root", vis="public"), home=True)
        for i, parent in ((1, "700"), (2, "700"), (3, "701"), (4, "700")):
            w.add(status(f"70{i}", BOB, parent, "B", minute=1 + i, text=f"c{i}"))
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            screen = ThreadScreen("700")
            app.push_screen(screen)
            await self.wait(pilot, lambda: app.screen is screen and
                            len(screen.query_one("#posts", ListView).children) == 5,
                            timeout=30)
            lv = screen.query_one("#posts", ListView)
            lv.index = 0
            at = lambda: lv.children[lv.index].key  # noqa: E731
            await pilot.press("right_square_bracket")
            self.assertEqual(at(), "701")
            await pilot.press("right_square_bracket")
            self.assertEqual(at(), "702")  # 703 (under 701) stepped over
            await pilot.press("left_square_bracket")
            self.assertEqual(at(), "701")
            deep = next(i for i in lv.children if i.key == "703")
            await pilot.press("minus")
            self.assertFalse(deep.display)
            await pilot.press("j")
            self.assertEqual(at(), "702")  # the folded one stepped over
            await pilot.press("k", "minus")
            self.assertTrue(deep.display)
            await pilot.press("q")

    async def test_thread_to_the_next_new_one(self):
        """NOTES/15, as the windows': N goes to the next comment new as the thread
        opened (the screen reads it whole at once), after the cursor."""
        from textual.widgets import ListView

        from fedtail.frontends.tui.app import FedtailApp, ThreadScreen
        core, w = self.make()
        w.add(status("700", BOB, minute=1, text="root", vis="public"), home=True)
        for i, parent in ((1, "700"), (2, "700"), (3, "701"), (4, "700")):
            w.add(status(f"70{i}", BOB, parent, "B", minute=1 + i, text=f"c{i}"))
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            core.mark_read(["701", "704"])  # 702, 703 new
            screen = ThreadScreen("700")
            app.push_screen(screen)
            await self.wait(pilot, lambda: app.screen is screen and
                            len(screen.query_one("#posts", ListView).children) == 5,
                            timeout=30)
            lv = screen.query_one("#posts", ListView)
            order = [i.key for i in lv.children]
            new = [k for k in order if k in ("702", "703")]
            lv.index = 0
            await pilot.pause(0.1)
            await pilot.press("N")
            await self.wait(pilot, lambda: lv.highlighted_child.key == new[0])
            await pilot.press("N")
            await self.wait(pilot, lambda: lv.highlighted_child.key == new[1])
            app.pop_screen()
            await pilot.press("q")

    async def test_a_lane_chosen_while_connecting_stays(self):
        """CI 18.11: a lane chosen once the sidebar is there, before connecting is done —
        the curtain (ui.start_lane = "none") drawn after it cleared it: Home stood empty."""
        from textual.widgets import ListView

        from fedtail.frontends.tui.app import FedtailApp, PostItem
        core, w = self.make(ui={"start_lane": "none"})
        w.add(status("001", BOB, minute=1, text="first", vis="public"), home=True)
        core.connect().result(timeout=10)
        core.poll_once()
        from unittest import mock
        real = FedtailApp.connected

        async def connected(self, me):  # the lane chosen in the middle of it
            await self.fill_lanes()
            await self.select_lane("home")
            await real(self, me)
        # no polling: its news would draw the lane again over the curtain and hide it
        with mock.patch.object(FedtailApp, "connected", connected), \
                mock.patch.object(core, "start_polling", lambda: None):
            app = FedtailApp(core)
            async with app.run_test(size=(120, 40)) as pilot:
                await self.wait(pilot, lambda: app.lane == "home" and any(
                    isinstance(x, PostItem)
                    for x in app.query_one("#posts", ListView).children), timeout=30)
                await pilot.pause(0.3)
                self.assertTrue(any(isinstance(x, PostItem)
                                    for x in app.query_one("#posts", ListView).children))
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
        shy = dict(fakes.acct("L", "shy@social.example"), locked=True,
                   created_at="2020-05-01T10:00:00.000Z")
        pic = status("003", shy, minute=3, text="look", vis="public")
        pic["media_attachments"] = [{"id": "m1", "type": "image",
                                     "url": "https://example.test/m1.png",
                                     "preview_url": "https://example.test/m1s.png"}]
        pic["pinned"] = True
        w.add(pic, home=True)
        w.featured["L"] = {"tags": [{"name": "cats", "statuses_count": 7}]}
        w.familiar["L"] = [BOB]
        w.act("a0", "follow", BOB, minute=1)  # history: the first fetch is seen
        app = FedtailApp(core)

        def no_network(url, elsewhere=""):  # the pictures: not fetched from example.test
            from concurrent.futures import Future
            f = Future()
            f.set_exception(OSError("no network in tests"))
            return f
        app.core.media_bytes = no_network

        def software(host):  # what their server runs: asked for the profile's own host
            from concurrent.futures import Future
            f = Future()
            f.set_result("GoToSocial 0.17" if host == "example.test" else "")
            return f
        app.core.server_software = software
        asked = []

        def from_origin(acc, cursor, have, resolve=False):  # their own server's posts
            from concurrent.futures import Future
            asked.append((acc.handle, cursor))
            f = Future()
            f.set_result(([], None))  # (nothing further back there either)
            return f
        app.core.older_from_origin = from_origin
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
            # the line about the person, the windows' and the page's (common/profile
            # .meta): locked, here since, what their server runs — the terminal said
            # only the counts (24.11)
            await self.wait(pilot, lambda: getattr(app.screen, "software", ""))
            about = str(app.screen.query_one("#about", Static).render())
            self.assertIn(i18n._("acc_locked"), about)
            self.assertIn("01.05.2020", about)
            self.assertIn("GoToSocial 0.17", about)
            # and what else a profile says there: whom of mine follows them, the tags
            # they put forward; their pinned post on top, marked, once
            await self.wait(pilot, lambda: "#cats" in str(
                app.screen.query_one("#about", Static).render()))
            about = str(app.screen.query_one("#about", Static).render())
            self.assertIn("@bob@social.example", about)
            rows = app.screen.query_one("#posts").children
            await self.wait(pilot, lambda: app.screen.pinned)
            await pilot.pause(0.2)
            rows = list(app.screen.query_one("#posts").children)
            self.assertEqual([r.entry.id for r in rows].count("003"), 1)
            self.assertEqual(rows[0].entry.id, "003")
            self.assertIn(i18n._("pinned"), str(rows[0].query_one(Static).render()))
            # M — more: my server has no older page, so their own server is asked
            # (feed.remote_profiles), once; then there is nothing further back
            await pilot.press("M")
            await self.wait(pilot, lambda: app.screen._older == "end")
            self.assertEqual(asked, [("shy@social.example", None)])
            await pilot.press("M")
            await pilot.pause(0.2)
            self.assertEqual(len(asked), 1)
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


    async def test_a_post_deleted_by_command_goes_from_the_screen(self):
        """D #id twice: the post deleted, and its row gone (it stayed till a redraw)."""
        from textual.widgets import Input

        from fedtail.frontends.tui.app import FedtailApp, LaneItem, PostItem
        core, w = self.make()
        w.add(status("001", ME, minute=1, vis="public", text="oops"), home=True)
        w.add(status("002", BOB, minute=2, vis="public"), home=True)
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            await self.wait(pilot, lambda: any(isinstance(i, LaneItem)
                                               for i in app.query_one("#lanes").children))

            def shown():
                return {getattr(getattr(i, "entry", None), "id", None)
                        for i in app.query_one("#posts").children if isinstance(i, PostItem)}
            await self.wait(pilot, lambda: "001" in shown())
            alias = core.short_ids([core.store.get_status("001")])["001"]
            cmd = app.query_one("#cmd", Input)
            for _ in range(2):  # asked first, then done
                cmd.focus()
                cmd.value = f"D #{alias}"
                await pilot.press("enter")
                await pilot.pause(0.2)
            await self.wait(pilot, lambda: "001" not in w.statuses)
            await self.wait(pilot, lambda: "001" not in shown())

    async def test_the_terminals_title_says_the_unread_number(self):
        """The windows put the unread number on the tray icon, the page into its tab;
        the terminal showed it nowhere (23.11): its window's title says "(N) FedTail" for
        the lanes window.icon_count chose, written by the terminal's own escape."""
        from fedtail.frontends.tui.app import FedtailApp, LaneItem
        core, w = self.make()
        core.cfg["ui"]["icon_count"] = ["all"]  # (the default counts the personal lanes)
        for i in range(1, 4):
            w.add(status(f"00{i}", BOB, minute=i, vis="public"), home=True)
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            wrote = []
            write = app._driver.write
            app._driver.write = lambda data: (wrote.append(data), write(data))[1]
            core.poll_once()
            await self.wait(pilot, lambda: any(isinstance(i, LaneItem)
                                               for i in app.query_one("#lanes").children))
            from fedtail.frontends.common import sidebar
            names = [i.lane for i in app.query_one("#lanes").children
                     if isinstance(i, LaneItem)]
            want = sidebar.icon_total(app.core, core.cfg, sidebar.counts(app.core, names))
            self.assertGreater(want, 0)
            await self.wait(pilot, lambda: app.window_title == f"({want}) FedTail")
            self.assertIn(f"\x1b]2;({want}) FedTail\x07", wrote)
            core.cfg["ui"]["icon_count"] = []  # nothing chosen: no number
            app.update_lane_counts()
            self.assertEqual(app.window_title, "FedTail")

    async def test_the_keys_are_the_configs(self):
        """[keys] and tui.keys: reply on a key of one's own, the command line on another
        — pressed, not called; the letters written in the screens no longer do it."""
        from textual.widgets import Input, ListView

        from fedtail.frontends.tui.app import FedtailApp, LaneItem, PostItem
        core, w = self.make()
        core.cfg["keys"]["reply"] = "a"
        core.cfg["tui"]["keys"] = ["command = g"]
        w.add(status("001", BOB, minute=1, vis="public", text="hello"), home=True)
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            await self.wait(pilot, lambda: any(isinstance(i, LaneItem)
                                               for i in app.query_one("#lanes").children))
            await self.wait(pilot, lambda: any(isinstance(i, PostItem)
                                               for i in app.query_one("#posts").children))
            posts = app.query_one("#posts", ListView)
            cmd = app.query_one("#cmd", Input)
            posts.focus()
            posts.index = next(i for i, x in enumerate(posts.children)
                               if isinstance(x, PostItem))
            await pilot.pause(0.2)
            await pilot.press("r")  # the letter written in the screen: no longer reply
            await pilot.pause(0.1)
            self.assertFalse(cmd.has_focus)
            await pilot.press("a")
            await self.wait(pilot, lambda: cmd.has_focus)
            self.assertTrue(cmd.value.startswith("#"))
            cmd.value = ""
            posts.focus()
            await pilot.pause(0.1)
            await pilot.press("g")
            await self.wait(pilot, lambda: cmd.has_focus)

    async def test_up_and_down_walk_the_lines_run_before(self):
        """↑ ↓ in the command line, the windows' (Qt and GTK alone had it, 23.11): typed
        and run by the keys, as a person does."""
        from textual.widgets import Input

        from fedtail.frontends.tui.app import FedtailApp, LaneItem
        core, w = self.make()
        w.add(status("001", BOB, minute=1, vis="public"), home=True)
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            await self.wait(pilot, lambda: any(isinstance(i, LaneItem)
                                               for i in app.query_one("#lanes").children))
            cmd = app.query_one("#cmd", Input)
            for line in ("#zzz1 one", "#zzz2 two"):
                cmd.focus()
                cmd.value = ""
                await pilot.press(*line.replace(" ", "\x00").split("\x00")[0], "space",
                                  *line.split(" ")[1])
                await pilot.press("enter")
                await self.wait(pilot, lambda: not cmd.disabled)
                cmd.value = ""
            cmd.focus()
            await pilot.press("up")
            self.assertEqual(cmd.value, "#zzz2 two")
            await pilot.press("up")
            self.assertEqual(cmd.value, "#zzz1 one")
            await pilot.press("down")
            self.assertEqual(cmd.value, "#zzz2 two")
            await pilot.press("down")
            self.assertEqual(cmd.value, "")  # past the last: an empty line again

    async def test_the_editor_keeps_its_draft_while_typing(self):
        """post.drafts_autosave: what is typed is kept a moment after the last key, not
        only on Esc — an SSH dropped lost it (21.11)."""
        from fedtail.frontends.tui.app import FedtailApp, LaneItem
        from fedtail.frontends.tui.screens import ComposeScreen
        core, w = self.make()
        w.add(status("001", BOB, minute=1, vis="public"), home=True)
        core.cfg["post"]["autosave_ms"] = 100
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            await self.wait(pilot, lambda: any(isinstance(i, LaneItem)
                                               for i in app.query_one("#lanes").children))
            app.query_one("#posts").focus()
            await pilot.press("w")
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            key = app.screen.key
            await pilot.press(*"half a thought")
            await self.wait(pilot, lambda: (core.get_draft(key) or {}).get(
                "text", "").endswith("half a thought"))

    async def test_files_pasted_as_paths_are_attached(self):
        """A file dropped on a terminal comes as a paste of its path: the editor attaches
        it (Qt and GTK take a pasted or dropped file; here it went into the text, 23.11).
        Words pasted stay words. The paste comes as the terminal sends it — an event."""
        from textual import events
        from textual.widgets import TextArea

        from fedtail.frontends.common.compose import pasted_files
        from fedtail.frontends.tui.app import FedtailApp, LaneItem
        from fedtail.frontends.tui.screens import ComposeScreen
        one, two = self.tmp / "кот 1.png", self.tmp / "b.png"
        for f in (one, two):
            f.write_bytes(b"png")
        self.assertEqual(pasted_files(f"'{one}'\nfile://{two}\n"), [str(one), str(two)])
        self.assertEqual(pasted_files(str(one).replace(" ", "\\ ")), [str(one)])
        for words in ("just words", "/no/such/file.png", f"{one} and more", "b.png", ""):
            self.assertEqual(pasted_files(words), [], words)
        core, w = self.make()
        w.add(status("001", BOB, minute=1, vis="public"), home=True)
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            await self.wait(pilot, lambda: any(isinstance(i, LaneItem)
                                               for i in app.query_one("#lanes").children))
            app.query_one("#posts").focus()
            await pilot.press("w")
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            editor = app.screen
            text = editor.query_one("#c-text", TextArea)
            text.focus()
            await pilot.pause(0.1)
            before = text.text  # (a reply: its "@bob " is there)
            app.post_message(events.Paste("pasted words"))  # as the terminal's driver does
            await self.wait(pilot, lambda: text.text.endswith("pasted words"))
            await pilot.pause(0.2)
            self.assertEqual(text.text, before + "pasted words")  # once
            self.assertEqual(editor.media, [])
            app.post_message(events.Paste(f"{one}\n{two}\n"))
            await self.wait(pilot, lambda: len(editor.media) == 2)
            self.assertEqual([m[0] for m in editor.media], [str(one), str(two)])
            self.assertEqual(text.text, before + "pasted words")  # the paths: not text

    async def test_the_editor_follows_its_switches(self):
        """post.cw_field, post.preview, post.schedule: the terminal's editor showed the
        warning's field, Ctrl+R and "Schedule" whatever they said (21.11). Driven by keys."""
        from textual.widgets import Input

        from fedtail.frontends.tui.app import FedtailApp, LaneItem
        from fedtail.frontends.tui.screens import ComposeScreen, MenuScreen
        core, w = self.make(post={"cw_field": False, "preview": False, "schedule": False})
        w.add(status("001", BOB, minute=1, vis="public"), home=True)
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            await self.wait(pilot, lambda: any(isinstance(i, LaneItem)
                                               for i in app.query_one("#lanes").children))
            app.query_one("#posts").focus()
            await pilot.press("w")
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            ed = app.screen
            self.assertFalse(ed.query_one("#c-cw", Input).display)  # behind Ctrl+O
            await pilot.press("ctrl+r")  # no preview
            await pilot.pause(0.2)
            self.assertIs(app.screen, ed)
            await pilot.press("ctrl+o")
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            words = [x[1] for x in app.screen.items if isinstance(x, tuple)]
            self.assertNotIn("when", words)  # no "Schedule"
            self.assertIn("cw", words)
            app.screen.dismiss("cw")  # "⚠ Warning": the field comes
            await self.wait(pilot, lambda: ed.query_one("#c-cw", Input).display)

    async def test_quote_as_a_link_where_quoting_is_not(self):
        """A server without quotes (GoToSocial, 23.11): . → "Quote as a link" — the
        editor with the post's address, the cursor on the line below it."""
        from textual.widgets import TextArea

        from fedtail.frontends.tui.app import FedtailApp, LaneItem
        from fedtail.frontends.tui.screens import ComposeScreen, MenuScreen
        core, w = self.make()
        w.add(status("001", BOB, minute=1, vis="public"), home=True)
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            await self.wait(pilot, lambda: any(isinstance(i, LaneItem)
                                               for i in app.query_one("#lanes").children))
            app.query_one("#posts").focus()
            await pilot.press("full_stop")
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            it = next(x[1] for x in app.screen.items
                      if isinstance(x, tuple) and x[0] == i18n._("quote_link"))
            app.screen.dismiss(it)
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            ta = app.screen.query_one(TextArea)
            self.assertEqual(ta.text, "https://example.test/s/001\n\n")
            self.assertEqual(ta.cursor_location, (2, 0))

    async def test_tab_completes_a_tag_in_the_editor(self):
        """Typed by keys as a person types: "#geo", the line under the text offers
        #georgia, Tab puts it in. The terminal's editor completed nothing (20.11); with
        nothing offered Tab still moves on."""
        from textual.widgets import Static, TextArea

        from fedtail.frontends.tui.app import FedtailApp, LaneItem
        from fedtail.frontends.tui.screens import ComposeScreen
        core, w = self.make()
        st = status("001", BOB, minute=1, text="#georgia", vis="public")
        st["tags"] = [{"name": "georgia"}]
        w.add(st, home=True)
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            await self.wait(pilot, lambda: any(isinstance(i, LaneItem)
                                               for i in app.query_one("#lanes").children))
            self.assertIsNone(core.store.tag_counts(compute=False))
            app.query_one("#posts").focus()
            await pilot.press("w")  # the editor (n is the one-line command line)
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            # opening the editor got ready what tags complete from
            await self.wait(pilot, lambda: core.store.tag_counts(compute=False))
            await pilot.press(*"hi #geo")
            line = app.screen.query_one("#c-suggest", Static)
            await self.wait(pilot, lambda: line.display)
            self.assertIn("#georgia", str(line.render()))
            ta = app.screen.query_one("#c-text", TextArea)
            await pilot.press("tab")
            self.assertTrue(ta.text.endswith("hi #georgia "), ta.text)
            self.assertFalse(line.display)
            await pilot.press("tab")  # nothing offered: the focus moves on, no tab typed
            self.assertTrue(ta.text.endswith("hi #georgia "), ta.text)
            self.assertIsNot(app.focused, ta)

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


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class TuiLongLaneTest(TmpDir, unittest.IsolatedAsyncioTestCase):
    """A lane of hundreds of posts: only a window of rows is built around where reading
    starts (all of them were, "from the start of time", 29.10); what scrolled over the
    screen is read, as in the windows — not only the post under the cursor."""
    make = test_cli.CliTest.make

    def setUp(self):
        TmpDir.setUp(self)
        i18n.setup("en")

    async def test_a_window_and_read_by_the_screen(self):
        import asyncio

        from textual.widgets import ListView

        from fedtail.frontends.tui.app import FedtailApp
        from fedtail.protocols.mastodon import adapter
        core, w = self.make(read={"mark_read": "on_scroll"},
                            feed={"order": "oldest_first", "first_run_mark_read": False})
        app = FedtailApp(core)
        big = [(f"{i:04d}", adapter.post(status(f"{i:04d}", BOB, minute=i % 59,
                                                vis="public", text=f"post number {i}"),
                                         "t")) for i in range(300)]
        app.core.entries = lambda lane: big if lane == "home" else []
        async with app.run_test(size=(120, 40)) as pilot:
            loop = asyncio.get_running_loop()
            end = loop.time() + 15
            while loop.time() < end and not app.lane:
                await pilot.pause(0.05)
            await app.select_lane("home")
            await pilot.pause(0.3)
            posts = app.query_one("#posts", ListView)
            n = len(app._rows)
            self.assertGreater(n, 250)
            self.assertLess(len(posts.children), 80)  # a window, not the lane
            # the wheel: what passes over the screen is read, the cursor where it was
            ids = [(None, {"id": f"{i:04d}"}) for i in range(300)]
            unread = len(core.unread_ids(ids))
            posts.scroll_to(y=posts.max_scroll_y // 2, animate=False)
            await pilot.pause(0.8)
            after = len(core.unread_ids(ids))
            self.assertLess(after, unread)
            # read through by the wheel, a few lines at a time: everything passed is read
            posts.scroll_to(y=0, animate=False)
            await pilot.pause(0.5)
            built = [it.entry.id for it in posts.children if hasattr(it, "entry")]
            while posts.scroll_y < posts.max_scroll_y:
                posts.scroll_to(y=posts.scroll_y + 5, animate=False)
                await pilot.pause(0.02)
            await pilot.pause(0.8)
            left = core.unread_ids([(None, {"id": i}) for i in built])
            self.assertEqual(sorted(left), [], "passed by the wheel, still unread")
            # the window grows as the cursor comes to its end
            posts.focus()
            before = len(posts.children)
            posts.index = len(posts.children) - 1
            await pilot.pause(0.3)
            self.assertGreaterEqual(len(posts.children), before)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class TuiCurtainTest(test_cov_tui_host.Base):
    async def test_the_curtain_and_where_a_lane_opens(self):
        """ui.start_lane = "none": the terminal opens on the curtain, as the windows do
        (it opened the lane of last time); Enter opens that lane — on the first new post
        under the card the reader stood at last, wherever that was (LaneModel.stood)."""
        from textual.widgets import ListView, Static

        from fedtail.frontends.tui.app import CURTAIN, FedtailApp
        core, w = self.make(ui={"start_lane": "none"}, feed={"page_size": 20})
        for i in range(1, 8):
            w.add(status(f"00{i}", BOB, minute=i, text=f"post {i}", vis="public"), home=True)
        core.set_state("lane", "home")
        core.set_state("stood.home", "003")  # read up to here in the window
        app = FedtailApp(core)
        async with app.run_test(size=(120, 40)) as pilot:
            core.poll_once()
            # the curtain's row with its words in (a slow runner: the row first, then
            # what's in it)
            await self.wait(pilot, lambda: any(getattr(i, "key", None) == CURTAIN
                                               and i.query(Static)
                                               for i in app.query_one("#posts").children),
                            what="the curtain")
            self.assertIsNone(app.lane)
            row = next(i for i in app.query_one("#posts").children
                       if getattr(i, "key", None) == CURTAIN)
            shown = str(row.query_one(Static).render())
            self.assertIn("Lanes closed", shown)
            app.query_one("#posts", ListView).focus()
            await pilot.press("enter")
            await self.wait(pilot, lambda: app.lane == "home", what="the lane")
            lv = app.query_one("#posts", ListView)
            # new posts under the place stood at: the first of them (13.11)
            await self.wait(pilot, lambda: getattr(lv.highlighted_child, "key", None)
                            == "004", what="the first new under the place stood at")
            # pictures come in above it: it stays on screen where it stood (they pushed
            # it down and away, the lane showing older posts, 29.10)
            from rich.text import Text

            from fedtail.frontends.tui.app import PostItem
            card = lv.highlighted_child
            for it in [c for c in lv.children if isinstance(c, PostItem)][:2]:
                app._picture_in(PostItem.set_picture, it, Text(("▀" * 10 + "\n") * 30))
            await pilot.pause(0.5)
            view = lv.content_region
            self.assertGreaterEqual(card.region.y, view.y)
            self.assertLessEqual(card.region.y + card.region.height, view.y + view.height)
            await pilot.press("q")
