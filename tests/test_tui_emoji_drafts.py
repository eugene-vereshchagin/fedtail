"""The terminal editor: the emoji picker and "New draft" (set a draft aside)."""

from __future__ import annotations

import unittest

from fedtail import i18n

from .test_cov_tui_host import HAVE_TEXTUAL, Base


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class TuiEmojiDraftsTest(Base):
    async def open_editor(self, pilot, app):
        from fedtail.frontends.tui.screens import ComposeScreen
        await self.started(pilot, app)
        await pilot.press("w")
        await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
        return app.screen

    async def test_picker_standard_and_search(self):
        from textual.widgets import Button, Input, TextArea

        from fedtail.frontends.tui.screens import EmojiScreen
        core, w = self.make()
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            editor = await self.open_editor(pilot, app)
            editor.query_one("#c-emoji", Button).press()
            await self.wait(pilot, lambda: isinstance(app.screen, EmojiScreen))
            pick = app.screen
            await self.wait(pilot, lambda: pick.values["e-standard"])
            n = len(pick.values["e-standard"])
            self.assertGreater(n, 1000)  # every group, titles among them
            pick.query_one("#e-search", Input).value = "smile"
            await self.wait(pilot, lambda: len(pick.values["e-standard"]) < n)
            self.assertEqual(pick.values["e-standard"][0], "\U0001F604")
            await pilot.press("enter")
            await self.wait(pilot, lambda: app.screen is editor)
            self.assertEqual(editor.query_one("#c-text", TextArea).text,
                             "\U0001F604")

    async def test_picker_server_tab(self):
        from textual.widgets import TextArea

        from fedtail.frontends.tui.screens import EmojiScreen
        core, w = self.make()
        w.emoji = [{"shortcode": "blobcat", "category": "blobs", "url": "x"}]
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            editor = await self.open_editor(pilot, app)
            await pilot.press("ctrl+e")
            await self.wait(pilot, lambda: isinstance(app.screen, EmojiScreen))
            pick = app.screen
            await pilot.press("ctrl+right")
            await self.wait(pilot, lambda: ":blobcat: " in pick.values["e-server"])
            await pilot.press("enter")
            await self.wait(pilot, lambda: app.screen is editor)
            self.assertEqual(editor.query_one("#c-text", TextArea).text, ":blobcat: ")

    async def test_picker_server_empty_and_standard_off(self):
        from fedtail.frontends.tui.screens import EmojiScreen
        core, w = self.make()
        core.cfg["post"]["emoji_standard"] = False
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.open_editor(pilot, app)
            await pilot.press("ctrl+e")
            await self.wait(pilot, lambda: isinstance(app.screen, EmojiScreen))
            pick = app.screen
            self.assertNotIn("e-standard", pick.values)
            await self.wait(pilot, lambda: pick.server_items == [])
            box = pick.query_one("#e-server-list")
            self.assertIn(i18n._("emoji_server_none"), str(box.get_option_at_index(0).prompt))

    async def test_new_draft_sets_the_text_aside(self):
        from textual.widgets import Button, Static, TextArea
        core, w = self.make()
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            editor = await self.open_editor(pilot, app)
            await pilot.press(*"first thought")
            editor.query_one("#c-shelve", Button).press()
            await self.wait(pilot, lambda: editor.query_one("#c-text", TextArea).text == "")
            self.assertIn(i18n._("draft_shelved"),
                          str(editor.query_one("#c-hint", Static).render()))
            drafts = core.drafts()
            self.assertEqual(len(drafts), 1)
            self.assertTrue(drafts[0][0].startswith("new:"))
            self.assertEqual(drafts[0][1]["text"], "first thought")
            self.assertIsNone(core.get_draft("new"))
            await pilot.press("escape")  # empty and untouched: nothing kept under "new"
            await self.wait(pilot, lambda: app.screen is not editor)
            self.assertIsNone(core.get_draft("new"))

    async def test_no_shelve_button_when_off_or_for_a_reply(self):
        core, w = self.make()
        core.cfg["post"]["drafts_place"] = False
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            editor = await self.open_editor(pilot, app)
            self.assertEqual(len(editor.query("#c-shelve")), 0)
            self.assertEqual(len(editor.query("#c-emoji")), 1)

    async def test_drafts_open_brings_the_set_aside_one(self):
        from textual.widgets import TextArea
        core, w = self.make()
        core.store.save_draft("new:1a", {"text": "aside", "cw": "", "media": []})
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            from fedtail.frontends.tui.screens import ComposeScreen
            out = app.core.unshelve_draft("new:1a")
            app.host.compose(text="aside") if out == "new" else self.fail(out)
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            self.assertEqual(app.screen.query_one("#c-text", TextArea).text, "aside")
            self.assertEqual(app.screen.key, "new")


if __name__ == "__main__":
    unittest.main()
