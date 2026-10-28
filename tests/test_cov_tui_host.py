"""The terminal's host (frontends/tui/host.py: what links, menus and profile buttons ask
for, done the terminal's way), its entry point (tui/__init__.py) and its pictures
without Pillow (tui/pictures.py). Driven headless by Textual's pilot; skipped without
Textual."""

import importlib
import io
import sys
import unittest
from concurrent.futures import Future
from unittest import mock

try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ImportError:
    HAVE_TEXTUAL = False

from fedtail import i18n

from . import test_cli
from .fakes import BOB, ME, status
from .test_core import TmpDir


def done(value=None, error=None):
    f = Future()
    if error is not None:
        f.set_exception(error)
    else:
        f.set_result(value)
    return f


class Base(TmpDir, unittest.IsolatedAsyncioTestCase):
    make = test_cli.CliTest.make

    def setUp(self):
        TmpDir.setUp(self)
        i18n.setup("en")
        p = mock.patch("webbrowser.open")
        self.browser = p.start()
        self.addCleanup(p.stop)

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

    def app_of(self, core):
        from fedtail.frontends.tui.app import FedtailApp
        app = FedtailApp(core)
        self.notes = []
        app.notify = lambda message, **_kw: self.notes.append(str(message))
        return app

    async def started(self, pilot, app):
        from fedtail.frontends.tui.app import LaneItem
        app.core.poll_once()
        await self.wait(pilot, lambda: any(isinstance(i, LaneItem)
                                           for i in app.query_one("#lanes").children),
                        what="lanes")
        await self.wait(pilot, lambda: app.lane is not None, what="a lane")
        # the poll's news may still be making the lane list anew: done before going on
        await self.wait(pilot, lambda: not getattr(app, "_lanes_busy", False),
                        what="the lane list made")


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class TuiHostTest(Base):
    async def test_host(self):
        from fedtail.frontends.tui.app import ProfileScreen, ThreadScreen
        from fedtail.frontends.tui.screens import (
            AskScreen,
            ComposeScreen,
            ConfirmScreen,
            PlaceScreen,
        )
        from fedtail.protocols.mastodon.adapter import account
        core, w = self.make()
        w.add(status("001", ME, minute=1, text="mine", vis="public"), home=True)
        w.add(status("002", BOB, "001", "ME", minute=2, text="bob's", vis="public"), home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            host, view = app.host, app.core
            self.assertIs(host.view, view)
            mine, bobs = view.by_id("001"), view.by_id("002")

            # call: ok, then the lane redrawn; an error said
            got = []
            host.call(done(5), ok=got.append)
            await self.wait(pilot, lambda: got == [5])
            errors = []
            app.show_error = errors.append
            host.call(done(error=RuntimeError("boom")))
            await self.wait(pilot, lambda: errors == ["boom"])
            host.status("hello")
            self.assertIn("hello", self.notes)

            # a question: yes runs it, no doesn't
            said = []
            host.confirm("Sure?", "really", lambda: said.append("yes"))
            await self.wait(pilot, lambda: isinstance(app.screen, ConfirmScreen))
            await pilot.press("y")
            await self.wait(pilot, lambda: said == ["yes"])
            host.confirm("Sure?", "really", lambda: said.append("again"))
            await self.wait(pilot, lambda: isinstance(app.screen, ConfirmScreen))
            await pilot.press("n")
            await self.wait(pilot, lambda: not isinstance(app.screen, ConfirmScreen))
            self.assertEqual(said, ["yes"])

            # a line: blank isn't an answer unless allowed
            answers = []
            host.ask_text("Name", "which?", answers.append, text="  ")
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            app.screen.dismiss("  ")
            await pilot.pause(0.1)
            host.ask_text("Name", "which?", answers.append, allow_empty=True)
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            app.screen.dismiss("")
            await self.wait(pilot, lambda: answers == [""])

            # the web only goes to the browser
            host.open_url("https://example.test/x")
            self.browser.assert_called_once_with("https://example.test/x")
            host.open_url("file:///etc/passwd")
            self.assertIn(i18n._("link_refused"), self.notes)
            host.open_url("")
            self.assertEqual(self.browser.call_count, 1)

            async def opened(fn, kind, check=None):
                fn()
                await self.wait(pilot, lambda: isinstance(app.screen, kind), what=str(fn))
                if check is not None:
                    self.assertTrue(check(app.screen))
                app.pop_screen()
                await pilot.pause(0.05)
            await opened(lambda: host.open_thread("002"), ThreadScreen)
            await opened(lambda: host.open_account("B"), ProfileScreen)
            for fn, name in ((lambda: host.open_tag("fedi"), "tag"),
                             (lambda: host.show_history(bobs), "history"),
                             (lambda: host.report(bobs), "report"),
                             (lambda: host.open_reactions(bobs, "favourited_by"), "reactions"),
                             (lambda: host.open_quotes(bobs), "quotes"),
                             (lambda: host.open_people(bobs.author, "followers"), "people"),
                             (host.edit_profile, "profile_edit"),
                             (lambda: host.open_lists(bobs.author), "list_of")):
                await opened(fn, PlaceScreen, lambda s, name=name: s.name_ == name)

            # a fediverse address: what my server finds, else the browser
            acc = account(BOB)
            for found, kind in ((acc, ProfileScreen), (bobs, ThreadScreen)):
                with mock.patch.object(type(view), "resolve", return_value=done(found)):
                    await opened(lambda: host.resolve_link("https://social.example/@bob"),
                                 kind)
            with mock.patch.object(type(view), "resolve", return_value=done(None)):
                host.resolve_link("https://social.example/@nobody")
                await self.wait(pilot, lambda: i18n._("resolve_browser") in self.notes)
            with mock.patch.object(type(view), "resolve",
                                   return_value=done(error=OSError("down"))):
                n = self.browser.call_count
                host.resolve_link("https://social.example/@down")
                await self.wait(pilot, lambda: self.browser.call_count == n + 1)

            # the handle, the alias, read up to
            host.copy_handle("bob@social.example")
            self.assertIn(i18n._("handle_copied", handle="@bob@social.example"), self.notes)
            host.put_alias("a3f")
            self.assertEqual(app.query_one("#cmd").value, "#a3f ")
            host.read_up_to("001")

            # the editor: an edit starts from the text as typed on the server
            host.compose(edit=mine)
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            self.assertIs(app.screen.edit, mine)
            app.pop_screen()
            await pilot.pause(0.05)
            d = mock.Mock(reply_to="002", text="again", warning="cw", visibility="public",
                          language="en", media=2)
            host.redrafted(d)
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            self.assertEqual(app.screen.reply_to.id, "002")
            self.assertIn(i18n._("redraft_media", n=2), self.notes)
            app.pop_screen()
            d = mock.Mock(reply_to=None, text="fresh", warning="", visibility="public",
                          language="", media=0)
            host.redrafted(d)
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            self.assertIsNone(app.screen.reply_to)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class TuiEntryTest(TmpDir):
    make = test_cli.CliTest.make

    def test_run_gives_the_code_and_closes_the_core(self):
        from fedtail.frontends import tui
        from fedtail.frontends.tui.app import FedtailApp
        core, _w = self.make()
        with mock.patch.object(FedtailApp, "run", lambda self: None), \
                mock.patch.object(type(core), "shutdown") as shut:
            self.assertEqual(tui.run(core, None, ["fedtail"]), 0)
            shut.assert_called_once()

        def ran(self):
            self._return_code = 3
        with mock.patch.object(FedtailApp, "run", ran), \
                mock.patch.object(FedtailApp, "return_code", 3, create=True), \
                mock.patch.object(type(core), "shutdown"):
            self.assertEqual(tui.run(core, None, ["fedtail"]), 3)


class NoPillowTest(unittest.TestCase):
    def test_without_pillow_there_are_no_pictures(self):
        try:
            import rich  # noqa: F401
        except ImportError:
            self.skipTest("rich is not installed")
        from fedtail.frontends.tui import pictures
        try:
            with mock.patch.dict(sys.modules, {"PIL": None}):
                importlib.reload(pictures)
                self.assertFalse(pictures.available())
                self.assertIsNone(pictures.blocks(b"\x89PNG", 10, 10))
        finally:
            importlib.reload(pictures)

    def test_a_decompression_bomb_isnt_drawn(self):
        try:
            import rich  # noqa: F401
            from PIL import Image
        except ImportError:
            self.skipTest("rich or Pillow is not installed")
        from fedtail.frontends.tui import pictures
        buf = io.BytesIO()
        Image.new("RGB", (100, 100)).save(buf, "PNG")
        with mock.patch.object(pictures, "MAX_PIXELS", 50):
            self.assertIsNone(pictures.blocks(buf.getvalue(), 10, 10))
        self.assertIsNotNone(pictures.blocks(buf.getvalue(), 10, 10))


if __name__ == "__main__":
    unittest.main()
