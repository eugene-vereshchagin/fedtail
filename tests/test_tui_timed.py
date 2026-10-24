"""The terminal's choose() (how long a mute lasts, posts only or not), the profile's
switch between posts, posts and replies, media, and "Hide this post" in the ⋯ menu.
Driven headless by Textual's pilot; skipped without Textual."""

import unittest

from fedtail import i18n

from .fakes import BOB, ME, status
from .test_cov_tui_host import HAVE_TEXTUAL, Base


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class TuiTimedTest(Base):
    async def test_choose_mute_profile_switch_hide(self):
        from fedtail.frontends.common import actions
        from fedtail.frontends.tui.app import ProfileScreen
        from fedtail.frontends.tui.screens import ChooseScreen
        core, w = self.make()
        w.add(status("001", ME, minute=1, text="mine", vis="public"), home=True)
        w.add(status("002", BOB, "001", "ME", minute=2, text="bob's", vis="public"),
              home=True)
        w.add(status("003", BOB, minute=3, text="own post", vis="public"))
        pic = w.add(status("004", BOB, minute=4, text="a picture", vis="public"))
        pic["media_attachments"] = [{"id": "m1", "type": "image", "url": "https://x/p.png"}]
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            host = app.host

            # choose: Enter on an answer gives (key, ticked); t ticks; Esc — nothing
            got = []
            host.choose("Mute", "how long?", [(0, "ever"), (3600, "hour")],
                        lambda k, t: got.append((k, t)), check="posts only")
            await self.wait(pilot, lambda: isinstance(app.screen, ChooseScreen))
            self.assertEqual(app.screen.labels(), ["ever", "hour"])
            await pilot.press("t")
            await pilot.press("j")
            await pilot.press("enter")
            await self.wait(pilot, lambda: got == [(3600, True)])
            host.choose("Mute", "", [(0, "ever")], lambda k, t: got.append((k, t)))
            await self.wait(pilot, lambda: isinstance(app.screen, ChooseScreen))
            await pilot.press("t")  # no box: nothing to tick
            await pilot.press("escape")
            await self.wait(pilot, lambda: not isinstance(app.screen, ChooseScreen))
            self.assertEqual(got, [(3600, True)])

            # the post menu's Mute: asked how long, then muted that long
            app.links.open("fedtail:mute/002")
            await self.wait(pilot, lambda: isinstance(app.screen, ChooseScreen))
            await pilot.press("j")
            await pilot.press("enter")
            await self.wait(pilot, lambda: "B" in w.mute_terms)
            self.assertEqual(w.mute_terms["B"], {"duration": 3600, "notifications": True})
            core.mute("B", False).result()

            # Hide this post: in the menu where the server can
            p = app.core.by_id("002")  # the View: the model's Post, as menus take it
            ctx = actions.Ctx(cfg=core.cfg, me_id=app.core.me.id, supports=core.supports)
            self.assertIn("fedtail:hidepost/002",
                          [i.url for i in actions.menu(p, ctx) if i.kind == "link"])

            # the profile: posts first (feed.profile_show), s — posts and replies, media
            app.push_screen(ProfileScreen("B"))
            await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen))
            prof = app.screen

            def keys():
                return sorted(x.key for x in prof.query_one("#posts").children)
            await self.wait(pilot, lambda: keys() == ["003", "004"], what="posts only")
            self.assertEqual(prof.show, "posts")
            self.assertIn("[" + i18n._("profile_show_posts") + "]", prof.posts_head())
            await pilot.press("s")
            await self.wait(pilot, lambda: keys() == ["002", "003", "004"], what="all")
            await pilot.press("s")
            await self.wait(pilot, lambda: keys() == ["004"], what="media")
            await pilot.press("s")
            self.assertEqual(prof.show, "posts")


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class TuiHelpHistoryTest(Base):
    async def test_help_back_and_forward(self):
        from fedtail.frontends.tui.screens import PlaceScreen
        core, _w = self.make()
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            app.push_screen(PlaceScreen("help", "index"))
            await self.wait(pilot, lambda: getattr(app.screen, "name_", "") == "help")
            first = app.screen
            self.assertIsNot(first.check_action("help_back", ()), True)  # nothing before
            first._help_fwd().clear()
            app.push_screen(PlaceScreen("help", "keys"))
            await self.wait(pilot, lambda: app.screen is not first)
            self.assertTrue(app.screen.check_action("help_back", ()))
            await pilot.press("alt+left")
            await self.wait(pilot, lambda: app.screen is first)
            self.assertEqual(app.help_forward_pages, [("keys", "")])
            self.assertTrue(first.check_action("help_forward", ()))
            await pilot.press("alt+right")
            await self.wait(pilot, lambda: getattr(app.screen, "arg", "") == "keys")
            self.assertEqual(app.help_forward_pages, [])
            self.assertFalse(PlaceScreen("lists").check_action("help_back", ()))


if __name__ == "__main__":
    unittest.main()
