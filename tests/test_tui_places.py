"""The terminal beyond lanes: a post's ⋯ menu (the windows' items, done the windows'
way), the ≡ menu, the places (common/places.py), a profile's buttons, the editor,
find in the lane. Driven headless by Textual's pilot; skipped without Textual."""

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


def pick(menu, label):
    """The value of a menu's item by its words."""
    return next(it[1] for it in menu.items if it != "-" and it[0] == label)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class TuiPlacesTest(TmpDir, unittest.IsolatedAsyncioTestCase):
    make = test_cli.CliTest.make

    def setUp(self):
        TmpDir.setUp(self)
        i18n.setup("en")

    async def wait(self, pilot, cond, timeout=10, what="condition"):
        import asyncio
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while loop.time() < end:
            await pilot.pause(0.05)
            try:
                if cond():
                    return True
            except Exception:  # noqa: BLE001 — not there yet
                pass
        self.fail(what + " not reached")

    async def start(self, pilot, app, core):
        from fedtail.frontends.tui.app import LaneItem
        core.poll_once()
        await self.wait(pilot, lambda: any(isinstance(i, LaneItem)
                                           for i in app.query_one("#lanes").children))
        await self.wait(pilot, lambda: app.lane is not None and
                        len(app.query_one("#posts").children) >= 1)

    async def to_post(self, pilot, app, sid):
        from textual.widgets import ListView
        await app.select_lane("home")
        await pilot.pause(0.2)
        posts = app.query_one("#posts", ListView)
        posts.focus()
        posts.index = [getattr(i, "entry", None) and i.entry.id for i in posts.children
                       ].index(sid)
        await pilot.pause(0.1)

    async def test_post_menu_profile_editor_places(self):
        from fedtail.frontends.tui.app import FedtailApp, ProfileScreen
        from fedtail.frontends.tui.screens import (
            ComposeScreen,
            ConfirmScreen,
            MenuScreen,
            PlaceScreen,
        )
        core, w = self.make()
        w.add(status("001", ME, minute=1, text="mine", vis="public"), home=True)
        w.add(status("002", BOB, minute=2, text="bob's", vis="public"), home=True)
        app = FedtailApp(core)
        async with app.run_test(size=(140, 48)) as pilot:
            await self.start(pilot, app, core)

            # ⋯ on bob's post: the windows' items; "Follow thread" done through the host
            await self.to_post(pilot, app, "002")
            await pilot.press("full_stop")
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen), what="⋯ menu")
            labels = app.screen.labels()
            self.assertIn(i18n._("sub_thread"), labels)
            self.assertIn(i18n._("add_to_list") + " …", labels)
            app.screen.dismiss(pick(app.screen, i18n._("sub_thread")))
            await self.wait(pilot, lambda: core.subscribed(w.statuses["002"]),
                            what="subscribed")

            # ⋯ → delete my post: "sure?" first, y deletes
            await self.to_post(pilot, app, "001")
            await pilot.press("full_stop")
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            app.screen.dismiss(pick(app.screen, i18n._("delete")))
            await self.wait(pilot, lambda: isinstance(app.screen, ConfirmScreen),
                            what="sure?")
            await pilot.press("y")
            await self.wait(pilot, lambda: "001" not in w.statuses, what="deleted")

            # a profile's buttons are the windows'; 1 — follow
            await self.to_post(pilot, app, "002")
            await pilot.press("p")
            await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen))
            await self.wait(pilot, lambda: app.screen.acc is not None)
            keys = [a.key for a in app.screen.buttons()]
            self.assertEqual(keys[0], "follow")
            self.assertIn("lists", keys)
            await pilot.press("1")
            await self.wait(pilot, lambda: "B" in w.following, what="followed")
            await pilot.press("escape")

            # the ≡ menu (g) lists the places; the silence place opens with its tabs
            await pilot.press("g")
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            self.assertIn(i18n._("silence_title") + " …", app.screen.labels())
            app.screen.dismiss(("place", "silence"))
            await self.wait(pilot, lambda: isinstance(app.screen, PlaceScreen) and
                            app.screen.page is not None, what="silence")
            self.assertEqual(app.screen.page.tab, "filters")
            await pilot.press("right_square_bracket")
            await self.wait(pilot, lambda: app.screen.page.tab == "muted", what="tab")
            await pilot.press("escape")

            # lists: a new one from the form
            app.open_thing({"page": "lists"})
            await self.wait(pilot, lambda: isinstance(app.screen, PlaceScreen) and
                            app.screen.page is not None, what="lists")
            from textual.widgets import Input
            app.screen.query_one("#form Input", Input).value = "Friends"
            await pilot.press("ctrl+s")
            await self.wait(pilot, lambda: any(x["title"] == "Friends"
                                               for x in w.lists.values()), what="list made")
            await pilot.press("escape")

            # the help: a Markdown page
            app.open_thing({"page": "help"})
            await self.wait(pilot, lambda: isinstance(app.screen, PlaceScreen) and
                            app.screen.page is not None, what="help")
            from textual.widgets import Markdown
            self.assertTrue(app.screen.query(Markdown))
            await pilot.press("escape")

            # the settings: a chapter as a form; Ctrl+S writes what changed into the file
            app.open_thing({"page": "settings"})
            await self.wait(pilot, lambda: isinstance(app.screen, PlaceScreen) and
                            app.screen.page is not None, what="settings")
            box = app.screen.form_widgets["ui.bookmark_button"]
            box.value = not box.value
            await pilot.press("ctrl+s")
            cfg_file = core.paths.config_file
            await self.wait(pilot, lambda: "bookmark_button = " + (
                "true" if box.value else "false") in cfg_file.read_text("utf-8"),
                what="settings saved")
            await pilot.press("escape")

            # the editor: w, text, Ctrl+S sends
            before = len(w.posted)
            await pilot.press("w")
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            await pilot.press(*"from the editor")
            await pilot.press("ctrl+s")
            await self.wait(pilot, lambda: len(w.posted) == before + 1, what="sent")
            self.assertIn("from the editor", w.posted[-1][0])

            # the editor's extras (Ctrl+O): a poll; then a picture with its description
            from fedtail.frontends.tui.screens import AskScreen
            await self.wait(pilot, lambda: not isinstance(app.screen, ComposeScreen))
            await pilot.press("w")
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            await pilot.press(*"choose")
            await pilot.press("ctrl+o")
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            app.screen.dismiss("poll")
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            await pilot.press(*"yes | no")
            await pilot.press("enter")
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen) and
                            app.screen.poll is not None, what="poll set")
            await pilot.press("ctrl+s")
            await self.wait(pilot, lambda: w.extras[-1]["poll"] is not None, what="poll sent")
            self.assertEqual(w.extras[-1]["poll"]["options"], ["yes", "no"])
            pic = self.tmp / "cat.png"
            pic.write_bytes(b"\x89PNG")
            await self.wait(pilot, lambda: not isinstance(app.screen, ComposeScreen))
            await pilot.press("w")
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            await pilot.press(*"look")
            await pilot.press("ctrl+o")
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            app.screen.dismiss("attach")
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            app.screen.query_one("#ask").value = str(pic)
            await pilot.press("enter")
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen) and
                            app.screen.q_title == i18n._("alt_title"), what="alt asked")
            await pilot.press(*"a cat")
            await pilot.press("enter")
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen) and
                            app.screen.media, what="attached")
            await pilot.press("ctrl+s")
            await self.wait(pilot, lambda: w.uploads and w.uploads[-1][1] == "a cat",
                            what="picture sent")

            # Ctrl+F: find in the lane
            await self.wait(pilot, lambda: not isinstance(app.screen, ComposeScreen))
            app.find("bob's")
            await pilot.pause(0.2)
            posts = app.query_one("#posts")
            self.assertEqual(posts.highlighted_child.entry.id, "002")


if __name__ == "__main__":
    unittest.main()
