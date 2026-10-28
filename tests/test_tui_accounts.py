"""The terminal: spell checking in the editor (F7, core/spell.py) and going over to
another account (fedtail started anew with that profile, in this terminal). The
Textual parts are driven headless by its pilot; skipped without Textual."""

import unittest
from unittest import mock

from fedtail import i18n
from fedtail.core import spell

from .test_cov_tui_host import HAVE_TEXTUAL, Base
from .test_spell import FakeBackend


class RelaunchTest(unittest.TestCase):
    def test_the_process_is_replaced_with_the_other_profile(self):
        from fedtail.core import profiles
        from fedtail.frontends import tui
        lock = mock.Mock()
        with mock.patch.object(profiles, "command",
                               return_value=(["/usr/bin/python3", "-m", "fedtail",
                                              "--profile", "work"], None)), \
                mock.patch.object(profiles, "RUN_FLAGS", ["--layout", "split"]), \
                mock.patch("os.execv") as execv, mock.patch("os.chdir") as chdir:
            tui.relaunch("work", lock)
        argv = execv.call_args[0][1]
        self.assertEqual(execv.call_args[0][0], "/usr/bin/python3")
        self.assertEqual(argv[-6:], ["--profile", "work", "--ui", "tui", "--layout", "split"])
        lock.close.assert_called_once()  # this profile's lock let go first
        chdir.assert_not_called()


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class TuiSpellAccountsTest(Base):
    async def test_f7_puts_a_word_right(self):
        from fedtail.frontends.tui.screens import ComposeScreen, MenuScreen
        p = mock.patch.object(spell, "_backend", FakeBackend())
        p.start()
        self.addCleanup(p.stop)
        spell._checkers.clear()
        self.addCleanup(spell._checkers.clear)
        core, _w = self.make()
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            await pilot.press("w")
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            editor = app.screen
            await pilot.press(*"hello wrold")
            await pilot.press("f7")
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen),
                            what="the words")
            self.assertEqual(app.screen.m_title,
                             "abc " + i18n._("spell_wrong_n", n=1))
            app.screen.dismiss(app.screen.items[0][1])
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen) and
                            app.screen.m_title == "wrold", what="the suggestions")
            self.assertEqual(app.screen.items[0], ("world", ("put", "world")))
            app.screen.dismiss(("put", "world"))
            await self.wait(pilot, lambda: app.screen is editor)
            from textual.widgets import TextArea
            self.assertEqual(editor.query_one("#c-text", TextArea).text, "hello world")
            await self.wait(pilot, lambda: i18n._("spell_all_ok") in self.notes,
                            what="all right now")
            # a word of my own: into the dictionary, never marked again
            editor.query_one("#c-text", TextArea).load_text("fedtail")
            await pilot.press("f7")
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            app.screen.dismiss(app.screen.items[0][1])
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen) and
                            app.screen.m_title == "fedtail")
            app.screen.dismiss(("add", "fedtail"))
            await self.wait(pilot, lambda: self.notes.count(i18n._("spell_all_ok")) == 2)
            self.assertIn("fedtail", (core.paths.config_file.parent / "spelling.txt")
                          .read_text("utf-8"))

    async def test_the_formatting_buttons(self):
        """post.format_bar in the terminal: buttons over the text, the windows' rules."""
        from textual.widgets import Button, TextArea
        from textual.widgets.text_area import Selection

        from fedtail.frontends.tui.screens import ComposeScreen
        core, _w = self.make()
        core.cfg["post"]["format_bar"] = "on"
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            await pilot.press("w")
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            editor = app.screen
            ta = editor.query_one("#c-text", TextArea)
            ta.load_text("one\nsay hi")
            ta.selection = Selection((1, 4), (1, 6))
            editor.query_one("#fmt-bold", Button).press()
            await pilot.pause(0.1)
            self.assertEqual(ta.text, "one\nsay **hi**")
            self.assertEqual(ta.selected_text, "hi")
            editor.query_one("#fmt-quote", Button).press()
            await pilot.pause(0.1)
            self.assertEqual(ta.text, "one\n> say **hi**")
        core.cfg["post"]["format_bar"] = "off"
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            await pilot.press("w")
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            self.assertFalse(app.screen.query("#c-format"))

    async def test_no_dictionaries_said_so(self):
        from fedtail.frontends.tui.screens import ComposeScreen
        p = mock.patch.object(spell, "_backend", False)
        p.start()
        self.addCleanup(p.stop)
        core, _w = self.make()
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            await pilot.press("w")
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            await pilot.press("f7")
            await self.wait(pilot, lambda: i18n._("spell_unavailable") in self.notes)

    async def test_another_account_ends_the_app_for_a_new_start(self):
        core, _w = self.make()
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            app.open_thing({"profile": "work"})
            await pilot.pause(0.2)
        self.assertEqual(app.relaunch, "work")


if __name__ == "__main__":
    unittest.main()
