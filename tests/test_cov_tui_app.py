"""The terminal application (frontends/tui/app.py) beyond tests/test_tui.py: every key
of the lane and of the menus, the ≡ menu's items, the lane's choices, the command line's
every answer, Activity and follow requests, a thread and a profile, logging in, the
pictures in the lane and full screen, and calls from other threads. Driven headless by
Textual's pilot; skipped without Textual."""

import asyncio
import io
import threading
import types
import unittest
from unittest import mock

try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ImportError:
    HAVE_TEXTUAL = False

try:
    from PIL import Image
except ImportError:
    Image = None

from fedtail import i18n
from fedtail.core.app import Core

from . import fakes
from .fakes import BOB, ME, NEWS, status
from .test_cov_tui_host import Base, done


def png(colour=(200, 0, 0)):
    buf = io.BytesIO()
    Image.new("RGB", (40, 20), colour).save(buf, "PNG")
    return buf.getvalue()


def with_picture(st, kind="image", preview=True, url=True):
    st["media_attachments"] = [{"type": kind, "id": "m" + st["id"],
                                "url": f"https://example.test/{st['id']}.png" if url else None,
                                "preview_url": f"https://example.test/{st['id']}_s.png"
                                if preview else None,
                                "remote_url": None, "description": "alt words"}]
    return st


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class AppKeysTest(Base):
    async def test_keys_menus_and_the_command_line(self):
        from textual.widgets import Input, ListView

        from fedtail.frontends.tui.app import PostItem, ProfileScreen, ThreadScreen
        from fedtail.frontends.tui.screens import (
            AskScreen,
            ComposeScreen,
            MenuScreen,
            PlaceScreen,
        )
        core, w = self.make(tui={"pictures": "off"})
        w.add(status("001", ME, minute=1, text="my own post", vis="public"), home=True)
        w.add(with_picture(status("002", BOB, minute=2, text="bob with a cat", vis="public")),
              home=True)
        w.add(status("003", BOB, minute=3, text="news of the day", vis="public"),
              home=True)
        app = self.app_of(core)
        errors = []
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            app.show_error = errors.append
            view = app.core
            posts = app.query_one("#posts", ListView)
            await self.wait(pilot, lambda: len([x for x in posts.children
                                                if isinstance(x, PostItem)]) == 3)

            def to(sid):
                posts.focus()
                posts.index = [getattr(x, "entry", None) and x.entry.id
                               for x in posts.children].index(sid)

            async def back():
                app.pop_screen()
                await pilot.pause(0.05)

            # v: the pictures, or "none"
            to("003")
            app.action_pictures()
            self.assertIn(i18n._("tui_no_pictures"), self.notes)
            to("002")
            with mock.patch.object(type(view), "media_bytes", return_value=done(b"")):
                app.action_pictures()
                await self.wait(pilot, lambda: type(app.screen).__name__ == "PictureScreen")
            await back()

            # b boosts (public), m bookmarks, o opens in the browser (the web only)
            app.action_boost()
            await self.wait(pilot, lambda: w.statuses["002"].get("reblogged"))
            await pilot.pause(0.2)  # the lane drawn again after the boost
            to("002")
            app.action_bookmark()
            await self.wait(pilot, lambda: w.statuses["002"].get("bookmarked"))
            await pilot.pause(0.2)
            to("002")
            app.action_browser()
            self.assertEqual(self.browser.call_count, 1)
            with mock.patch("fedtail.frontends.tui.app.openable", return_value=False):
                app.action_browser()
            self.assertIn(i18n._("link_refused"), self.notes)
            # w: the editor, answering the post under the cursor
            app.action_editor()
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            self.assertEqual(app.screen.reply_to.id, "002")
            await back()

            # the ⋯ menu's items, done
            st = view.by_id("002")
            labels = [x[0] for x in app.post_menu_items(st) if x != "-"]
            self.assertTrue(labels)
            self.assertNotEqual(app.post_menu_items(st)[-1], "-")
            item = types.SimpleNamespace
            app.do_menu_item(st, item(kind="open", url="https://example.test/x"))
            self.assertEqual(self.browser.call_count, 2)
            app.copy_to_clipboard = mock.Mock(side_effect=RuntimeError("no OSC 52"))
            app.do_menu_item(st, item(kind="copy", text="the text"))
            self.assertIn(i18n._("web_copied") + ": the text", self.notes)
            app.do_menu_item(st, item(kind="link", url="https://example.test/tags/x"))
            await pilot.pause(0.1)
            while app.screen is not app.screen_stack[0]:
                await back()
            for kind, place in (("lists", "list_of"), ("long_form", "long_form"),
                                ("translate", "translate")):
                app.do_menu_item(st, item(kind=kind, data=st.author))
                await self.wait(pilot, lambda place=place: isinstance(app.screen,
                                                                      PlaceScreen) and
                                app.screen.name_ == place)
                await back()
            app.do_menu_item(st, item(kind="quote_reply"))
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            quoted = app.screen.query_one("#c-text").text
            self.assertIn("> bob with a cat", quoted)
            self.assertNotIn("<p>", quoted)  # the words, not the post's HTML
            await back()
            app.do_menu_item(st, item(kind="something else"))  # not the terminal's

            # ≡: its items; a place opens, an action runs, Esc closes
            app.action_main_menu()
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            app.screen.dismiss(None)
            await pilot.pause(0.05)
            app.action_main_menu()
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            app.screen.dismiss(("place", "search"))
            await self.wait(pilot, lambda: isinstance(app.screen, PlaceScreen))
            await back()
            app.action_main_menu()
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            app.screen.dismiss(("do", "refresh"))
            await self.wait(pilot, lambda: i18n._("refresh") in self.notes)
            await app.menu_do("editor")
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            await back()
            await app.menu_do("my_profile")
            await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen))
            await back()
            with mock.patch("fedtail.diag.bug_report", return_value="/tmp/report.tgz"), \
                    mock.patch("fedtail.diag.log_stats"):
                await app.menu_do("bug_report")
            self.assertTrue(any("/tmp/report.tgz" in n for n in self.notes))
            with mock.patch("fedtail.diag.bug_report", side_effect=OSError("disk full")), \
                    mock.patch("fedtail.diag.log_stats"):
                await app.menu_do("bug_report")
            self.assertIn("disk full", str(errors[-1]))
            await app.menu_do("logs")
            app.sounds = mock.Mock(test=lambda: "beep")
            await app.menu_do("test_sound")
            self.assertIn("beep", self.notes)
            with mock.patch("fedtail.diag.dump_stacks") as stacks:
                await app.menu_do("stacks")
            stacks.assert_called_once()
            await app.menu_do("all_read")
            app.action_search()
            await self.wait(pilot, lambda: isinstance(app.screen, PlaceScreen) and
                            app.screen.name_ == "search")
            await back()

            # Ctrl+F: find in the lane; again: the next one; nothing found: said
            app.action_find()
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            app.screen.dismiss(None)
            await pilot.pause(0.05)
            app.action_find()
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            app.screen.dismiss("news")
            await self.wait(pilot, lambda: getattr(app, "_found", None))
            self.assertEqual(posts.highlighted_child.entry.id, "003")
            app.action_find()  # the same lane: the next (the only) one
            self.assertEqual(app._found["at"], 0)
            app.find("no such words at all")  # kept for D / E: none in the lane
            self.assertEqual(app._found["hits"], [])

            # keys of the lane list and the command line
            cmd_line = app.query_one("#cmd", Input)
            app.action_new()
            await self.wait(pilot, lambda: cmd_line.has_focus)
            app.action_escape()
            await self.wait(pilot, lambda: posts.has_focus)
            app.action_escape()  # the command line not focused: nothing
            app.action_command()
            await self.wait(pilot, lambda: cmd_line.has_focus)
            posts.focus()
            await self.wait(pilot, lambda: posts.has_focus)
            app.action_switch()
            lanes = app.query_one("#lanes", ListView)
            await self.wait(pilot, lambda: lanes.has_focus)
            at = lanes.index
            app.action_cursor_down()
            app.action_cursor_up()
            self.assertEqual(lanes.index, at)
            app.action_switch()
            await self.wait(pilot, lambda: posts.has_focus)
            app.action_to_lanes()
            await self.wait(pilot, lambda: lanes.has_focus)
            names = app._lane_names()
            lanes.index = [getattr(i, "lane", None) for i in lanes.children].index("local")
            app.action_to_posts()
            await self.wait(pilot, lambda: app.lane == "local")
            await app.action_lane_number(1)
            self.assertEqual(app.lane, names[0])
            await app.action_lane_number(99)
            await app.action_lane_step(-1)
            self.assertEqual(app.lane, names[-1])
            with mock.patch.object(type(app), "_lane_names", return_value=[]):
                await app.action_lane_step(1)
            await app.select_lane("home")
            app.action_request(True)  # not a request under the cursor: nothing
            app.action_all_read()
            await self.wait(pilot, lambda: not view.unread_count("home"))

            # where things lead
            app.open_thing(None)
            app.open_thing({"thread": "002"})
            await self.wait(pilot, lambda: isinstance(app.screen, ThreadScreen))
            # Tab in a thread: as usual; the command line there takes "#alias "
            app.action_switch()
            app.put_in_command_line("#abc ")
            self.assertEqual(app.screen.query_one("#cmd", Input).value, "#abc ")
            await back()
            app.open_thing({"account": "B"})
            await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen))
            await back()
            app.open_thing({"url": "https://example.test/y"})
            self.assertEqual(self.browser.call_args[0][0], "https://example.test/y")
            self.assertEqual(app.date_words(None), "")
            self.assertIsInstance(app.thread_screen("1"), ThreadScreen)

            # read up to here; a post not in the lane; no lane
            app.read_up_to("no-such")
            lane, app.lane = app.lane, None
            app.read_up_to("002")
            app.lane = lane
            app.read_up_to("002")

            # the post keys the places use
            changed = []
            where = mock.Mock(status_changed=changed.append)
            app.post_fav(st, where)
            app.post_boost(st, where)
            app.post_bookmark(st, where)
            await self.wait(pilot, lambda: len(changed) == 3)
            app.post_boost(view.by_id("001") if False else
                           types.SimpleNamespace(**{}) if False else st)
            private = fakes.status("009", BOB, minute=9, vis="private")
            w.add(private, home=True)
            view.poll_once()
            n = len(changed)
            app.post_boost(view.by_id("009"), where)  # followers only: not boosted
            await pilot.pause(0.1)
            self.assertEqual(len(changed), n)
            app.post_fav(st)
            await pilot.pause(0.1)

            # the command line's answers
            cmd = app.query_one("#cmd", Input)

            async def line(text):
                cmd.value = text
                await app.run_line(cmd, app)
                await pilot.pause(0.1)
            await line("   ")
            self.assertTrue(posts.has_focus)
            await line("?")
            self.assertIn(i18n._("cmd_help"), self.notes)
            await line("#zzz9 hi")
            self.assertIn(i18n._("cmd_no_post", alias="zzz9"), self.notes)
            short = view.short_ids([view.by_id("001"), st])
            await line(f"#{short['002']}")
            await self.wait(pilot, lambda: isinstance(app.screen, ThreadScreen))
            await back()
            await line("@bob@social.example")
            await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen))
            await back()
            await line(f"S #{short['002']}")
            await self.wait(pilot, lambda: cmd.value == "")
            before = len(w.posted)
            await line(f"#{short['002']} a reply")
            await self.wait(pilot, lambda: len(w.posted) == before + 1)
            await line(f"D #{short['001']}")  # asks first: the line stays
            await self.wait(pilot, lambda: cmd.value == f"D #{short['001']}")
            await line(f"D #{short['001']}")
            await self.wait(pilot, lambda: "001" not in w.statuses)
            with mock.patch.object(app.cmds, "run",
                                   return_value=(done(error=OSError("down")), None)):
                await line("anything")
            await self.wait(pilot, lambda: "down" in str(errors[-1]))
            self.assertFalse(cmd.disabled)
            with mock.patch.object(app.cmds, "run", return_value=(done(object()), "went")):
                await line("anything")
            await self.wait(pilot, lambda: "went" in self.notes)
            app.copy_to_clipboard = None
            app.copy_text("x")
            await app.menu_do("nothing known")
            app.exit = mock.Mock()
            await app.menu_do("quit")
            app.exit.assert_called_once()

    async def test_lane_choices_and_the_start(self):
        from fedtail.frontends.tui.screens import MenuScreen
        core, w = self.make(tui={"pictures": "off"})
        w.add(with_picture(status("001", BOB, minute=1, text="a cat", vis="public")),
              home=True)
        w.add(status("002", BOB, minute=2, text="words", vis="public"), home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            m = app.lane_model("home")

            async def choose(pick):
                app.action_lane_choices()
                await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
                menu = app.screen
                value = next(v for x in menu.items if x != "-"
                             for label, v, *_hint in [x] if pick(label, v))
                menu.dismiss(value)
                await pilot.pause(0.1)
            await choose(lambda _l, v: v == ("filter", "posts"))
            self.assertEqual(m.current_filter(), "posts")
            self.assertIn(i18n._("posts_only"), str(app.query_one("#title").render()))
            await choose(lambda _l, v: v == ("filter", "all"))
            if m.conversations_offered():
                await choose(lambda _l, v: v == ("conv", True))
                self.assertTrue(m.conversations())
                self.assertIn(i18n._("conv_mode"), app.lane_choice_words(m))
                await choose(lambda _l, v: v == ("conv", False))
            had = "image" in m.media.wanted
            await choose(lambda _l, v: v == ("media", "image"))
            self.assertNotEqual("image" in m.media.wanted, had)
            await choose(lambda _l, v: v == ("media", "boosts"))
            await choose(lambda _l, v: v == ("media", "reset"))
            app.action_lane_choices()
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            app.screen.dismiss(None)
            await pilot.pause(0.05)
            await app.select_lane("activity") if "activity" in app._lane_names() else None
            lane, app.lane = app.lane, None
            app.action_lane_choices()  # no lane: no menu
            await app.refresh_posts()
            app.lane = lane
            self.assertNotIsInstance(app.screen, MenuScreen)

            # where reading starts
            e = [(None, types.SimpleNamespace(id=x)) for x in "abc"]
            cfg = app.core.cfg["feed"]
            cfg["order"], cfg["start_at"] = "oldest_first", "first_unread"
            self.assertEqual(app._start_index(e, set()), 2)
            self.assertEqual(app._start_index(e, {"b", "c"}), 1)
            cfg["order"] = "newest_first"
            self.assertEqual(app._start_index(e, {"a", "b"}), 1)
            cfg["start_at"] = "newest"
            self.assertEqual(app._start_index(e, {"b"}), 0)
            cfg["order"], cfg["start_at"] = "oldest_first", "first_unread"

            # a lane the list doesn't have yet: the list drawn anew
            with mock.patch.object(app, "fill_lanes", wraps=app.fill_lanes) as fill:
                await app.lanes_updated({"list:new": []})
                fill.assert_called_once()
            app._redraw_pending = True
            await app.lanes_updated({app.lane: []})  # a redraw on its way: counts only
            app._redraw_pending = False
            # the highlight of something that isn't a post
            app.on_list_view_highlighted(mock.Mock(list_view=mock.Mock(id="lanes")))
            from fedtail.frontends.tui.app import PostItem
            post_item = PostItem(app.core.by_id("001"), "x")
            with mock.patch.object(type(app), "screen_stack", new_callable=mock.PropertyMock,
                                   return_value=[]):  # the app closing: nothing to do
                app.on_list_view_highlighted(mock.Mock(list_view=app.query_one("#posts"),
                                                       item=post_item))

    async def test_on_scroll_reads_a_whole_conversation(self):
        from textual.widgets import ListView

        from fedtail.frontends.tui.app import PostItem
        core, w = self.make(read={"mark_read": "on_scroll"}, tui={"pictures": "off"})
        w.add(status("001", BOB, minute=1, text="one", vis="public"), home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            posts = app.query_one("#posts", ListView)
            item = next(x for x in posts.children if isinstance(x, PostItem))
            with mock.patch.object(app.lane_model("home"), "read",
                                   return_value=["001", "x"]):
                app.on_list_view_highlighted(mock.Mock(list_view=posts, item=item))
            self.assertEqual(app.core.unread_count("home"), 0)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class ActivityRequestsTest(Base):
    async def test_activity_and_requests(self):
        from textual.widgets import ListView

        from fedtail.frontends.tui.app import (
            ActivityItem,
            ProfileScreen,
            RequestItem,
            ThreadScreen,
        )
        core, w = self.make(lanes={"enabled": ["home", "activity", "requests"]},
                            feed={"order": "newest_first"}, tui={"pictures": "off"})
        mine = w.add(status("001", ME, minute=1, text="my post", vis="public"), home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            posts = app.query_one("#posts", ListView)
            # nothing yet: said so
            await app.select_lane("activity")
            await self.wait(pilot, lambda: i18n._("activity_none") in str(
                posts.children[0].query_one("Static").render()))
            await app.select_lane("requests")
            await self.wait(pilot, lambda: i18n._("no_requests") in str(
                posts.children[0].query_one("Static").render()))

            w.act("a1", "favourite", BOB, mine, minute=5)
            w.act("a2", "follow", NEWS, minute=6)
            w.requests.append(fakes.acct("Q", "quinn@example.org"))
            app.core.poll_once()
            await app.select_lane("activity")
            await self.wait(pilot, lambda: len([x for x in posts.children
                                                if isinstance(x, ActivityItem)]) == 2)
            kinds = {x.activity.kind: i for i, x in enumerate(posts.children)}
            self.assertEqual(posts.index, 0)  # newest first: the newest at the top
            posts.index = kinds["like"]
            self.assertEqual(app.current().id, "001")  # a like: the post it is about
            app.action_profile()
            await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen))
            app.pop_screen()
            await pilot.pause(0.05)
            await app.on_list_view_selected(mock.Mock(list_view=posts,
                                                      item=posts.children[kinds["like"]]))
            await self.wait(pilot, lambda: isinstance(app.screen, ThreadScreen))
            app.pop_screen()
            await pilot.pause(0.05)
            await app.on_list_view_selected(mock.Mock(list_view=posts,
                                                      item=posts.children[kinds["follow"]]))
            await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen))
            app.pop_screen()
            await pilot.pause(0.05)
            # a new one while on screen: redrawn, the cursor kept
            posts.index = kinds["follow"]
            await app.other_updated("activity_updated")
            await app.other_updated("activity_seen")  # this lane being looked at
            await app.other_updated("requests_updated")  # not on screen: counts

            await app.select_lane("requests")
            await self.wait(pilot, lambda: isinstance(posts.children[0], RequestItem))
            app.action_profile()
            await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen))
            app.pop_screen()
            await pilot.pause(0.05)
            await app.on_list_view_selected(mock.Mock(list_view=posts,
                                                      item=posts.children[0]))
            await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen))
            app.pop_screen()
            await pilot.pause(0.05)
            await app.other_updated("requests_updated")
            app.action_request(True)
            await self.wait(pilot, lambda: "✔ @quinn@example.org" in self.notes)
            # Enter on a lane: the lane, then its posts
            lanes = app.query_one("#lanes", ListView)
            home = next(x for x in lanes.children if getattr(x, "lane", "") == "home")
            await app.on_list_view_selected(mock.Mock(list_view=lanes, item=home))
            self.assertEqual(app.lane, "home")
            posts.index = 0
            await app.on_list_view_selected(mock.Mock(list_view=posts,
                                                      item=posts.children[0]))
            await self.wait(pilot, lambda: isinstance(app.screen, ThreadScreen))
            await pilot.pause(0.3)  # its highlights handled before the app closes


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class ThreadProfileTest(Base):
    async def test_thread_and_profile(self):
        from textual.widgets import Input, ListView

        from fedtail.frontends.tui.app import ProfileScreen, ThreadScreen
        core, w = self.make(tui={"pictures": "off"})
        root = w.add(status("001", BOB, minute=1, text="the root", vis="public"), home=True)
        w.add(status("002", ME, root["id"], "B", minute=2, text="my answer", vis="public"),
              home=True)
        w.add(status("003", BOB, "002", "ME", minute=3, text="deeper", vis="public"),
              home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            app.push_screen(ThreadScreen("003"))
            await self.wait(pilot, lambda: isinstance(app.screen, ThreadScreen) and
                            len(app.screen.query_one("#posts").children) == 3)
            t = app.screen
            lv = t.query_one("#posts", ListView)
            await self.wait(pilot, lambda: lv.index == 2, what="the post asked for")
            self.assertTrue(str(lv.children[2].text).startswith("  "))  # nested: indented
            t.action_command()
            cmd = t.query_one("#cmd", Input)
            await self.wait(pilot, lambda: cmd.has_focus)
            before = len(w.posted)
            alias = app.core.short_ids([app.core.by_id("003")])["003"]
            cmd.value = f"#{alias} from the thread"
            await t.on_input_submitted(Input.Submitted(cmd, cmd.value))
            await self.wait(pilot, lambda: len(w.posted) == before + 1)
            t.status_changed(None)
            t.action_reply()
            self.assertTrue(cmd.value.startswith("#"))
            t.action_post_menu()
            await pilot.pause(0.1)
            app.pop_screen()
            await pilot.pause(0.05)
            app.pop_screen()
            await pilot.pause(0.05)

            # someone's profile: the note, the fields, follows me, the buttons 1…9
            bob = dict(BOB, note="<p>about bob</p>", statuses_count=3,
                       fields=[{"name": "site", "value": "<a href='x'>x.test</a>"}])
            rel = {"id": "B", "following": True, "followed_by": True, "note": "my note"}
            with mock.patch.object(fakes.FakeApi, "get", return_value=bob), \
                    mock.patch.object(fakes.FakeApi, "relationship", create=True,
                                      return_value=rel):
                app.push_screen(ProfileScreen("B"))
                await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen) and
                                app.screen.acc is not None and app.screen.rel is not None)
            p = app.screen
            about = str(p.query_one("#about").render())
            for words in ("about bob", "site", "x.test", i18n._("acc_follows_you")):
                self.assertIn(words, about)
            await self.wait(pilot, lambda: len(p.query_one("#posts").children) >= 1)
            await p.on_input_submitted(Input.Submitted(p.query_one("#cmd", Input), ""))
            p.action_command()
            await self.wait(pilot, lambda: p.query_one("#cmd", Input).has_focus)
            p.action_button(99)  # no such button
            acts = p.buttons()
            self.assertTrue(acts)
            with mock.patch("fedtail.frontends.common.profile.do") as do:
                p.action_button(1)
                do.assert_called_once()
                changed = do.call_args[0][5]
                changed(None)
                changed(p.rel)
            p.status_changed(None)
            # Enter on a post of the profile: its thread
            plv = p.query_one("#posts", ListView)
            plv.index = 0
            await app.on_list_view_selected(mock.Mock(list_view=plv, item=plv.children[0]))
            await self.wait(pilot, lambda: isinstance(app.screen, ThreadScreen))
            app.pop_screen()
            await pilot.pause(0.05)
            app.pop_screen()
            await pilot.pause(0.05)

            # my own profile asks no relationship; one that fails to load says why
            app.push_screen(ProfileScreen(app.core.me.id))
            await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen) and
                            app.screen.acc is not None)
            self.assertIsNone(app.screen.rel)
            app.pop_screen()
            await pilot.pause(0.05)
            with mock.patch.object(type(app.core), "account",
                                   return_value=done(error=OSError("gone"))):
                app.push_screen(ProfileScreen("Z"))
                await self.wait(pilot, lambda: "gone" in str(
                    app.screen.query_one("#about").render()))
                self.assertEqual(app.screen.buttons(), [])
                app.screen.show_about()


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class LoginTest(Base):
    async def test_logging_in(self):
        from textual.widgets import Input

        from fedtail.frontends.tui.app import LoginScreen
        core, _w = self.make()
        core.paths.auth_file.unlink()
        app = self.app_of(core)
        view = app.core
        calls = []
        with mock.patch.object(type(view), "begin_login", create=True,
                               side_effect=lambda s: (calls.append(s),
                                                      done("https://x.test/oauth"))[1]), \
                mock.patch.object(type(view), "finish_login", create=True,
                                  side_effect=lambda c: (calls.append(c), done(None))[1]), \
                mock.patch.object(Core, "connect", return_value=done(None)), \
                mock.patch.object(Core, "logged_in", new_callable=mock.PropertyMock,
                                  return_value=False):
            async with app.run_test(size=(100, 30)) as pilot:
                await self.wait(pilot, lambda: isinstance(app.screen, LoginScreen))
                s = app.screen
                field = s.query_one("#answer", Input)
                s.on_input_submitted(Input.Submitted(field, "   "))  # nothing typed
                s.on_input_submitted(Input.Submitted(field, "x.test"))
                await self.wait(pilot, lambda: s.step == "code")
                self.browser.assert_called_with("https://x.test/oauth")
                self.assertIn("x.test/oauth", str(s.query_one("#url").render()))
                s.on_input_submitted(Input.Submitted(field, "CODE"))
                await self.wait(pilot, lambda: not isinstance(app.screen, LoginScreen))
                self.assertEqual(calls, ["x.test", "CODE"])
                from fedtail.frontends.tui.app import LaneItem
                await self.wait(pilot, lambda: any(isinstance(i, LaneItem) for i in
                                                   app.query_one("#lanes").children))
        self.browser.side_effect = RuntimeError("no browser")
        app = self.app_of(core)
        with mock.patch.object(Core, "logged_in", new_callable=mock.PropertyMock,
                               return_value=False):
            async with app.run_test(size=(100, 30)) as pilot:
                await self.wait(pilot, lambda: isinstance(app.screen, LoginScreen))
                app.screen.got_url("https://x.test/oauth")  # no browser: the link stays
                self.assertEqual(app.screen.step, "code")


@unittest.skipUnless(HAVE_TEXTUAL and Image is not None, "Textual or Pillow is missing")
class PicturesTest(Base):
    async def test_pictures_in_the_lane_and_full_screen(self):
        from textual.widgets import ListView

        from fedtail.frontends.tui import app as app_mod
        from fedtail.frontends.tui.app import PictureScreen, PostItem
        core, w = self.make(tui={"pictures": "inline", "picture_rows": 4})
        w.add(with_picture(status("001", BOB, minute=1, text="cat", vis="public")),
              home=True)
        w.add(with_picture(status("002", BOB, minute=2, text="video", vis="public"),
                           kind="video", preview=False), home=True)
        w.add(with_picture(status("003", BOB, minute=3, text="gone", vis="public")),
              home=True)
        app = self.app_of(core)
        view = app.core
        answers = {"https://example.test/001_s.png": png(),
                   "https://example.test/001.png": png((0, 0, 200)),
                   "https://example.test/003_s.png": None}

        def media_bytes(_self, url):
            got = answers.get(url, b"")
            return done(error=OSError("refused")) if got is None else done(got)
        with mock.patch.object(type(view), "media_bytes", media_bytes):
            async with app.run_test(size=(120, 40)) as pilot:
                await self.started(pilot, app)
                posts = app.query_one("#posts", ListView)
                await self.wait(pilot, lambda: any(getattr(x, "has_picture", False)
                                                   for x in posts.children),
                                what="a picture drawn")
                self.assertTrue(app._picture_failed)  # the refused one: said once
                n = len(app._pictures)
                await app.refresh_posts()  # drawn again: from the cache
                self.assertEqual(len(app._pictures), n)
                app._pictures.update({(str(i), 0, 0): None for i in range(401)})
                answers["https://example.test/001_s.png"] = png((0, 200, 0))
                app._pictures.pop(("https://example.test/001_s.png", 16, 4), None)
                await app.refresh_posts()
                await self.wait(pilot, lambda: len(app._pictures) <= 2)
                detached = PostItem(view.by_id("001"), "x")
                app._put_picture(detached, "drawn")  # not on screen: left alone
                self.assertFalse(detached.has_picture)
                detached.set_picture(None)

                # full screen: ← → through them, the original, the video's still
                media = list(view.by_id("001").media) + list(view.by_id("002").media) + \
                    list(view.by_id("003").media)
                s = PictureScreen(media)
                app.push_screen(s)
                await self.wait(pilot, lambda: app.screen is s)
                await self.wait(pilot, lambda: "▀" in str(s.query_one("#pic").render()))
                self.assertIn("1", str(s.query_one("#pic-title").render()))
                s.action_original()
                self.browser.assert_called_with("https://example.test/001.png")
                s.action_step(1)
                await self.wait(pilot, lambda: "▶" in str(s.query_one("#pic").render()))
                s.action_step(1)
                await self.wait(pilot, lambda: i18n._("tui_picture_failed", err="")
                                .split("{")[0][:8] in str(s.query_one("#pic").render()))
                answers["https://example.test/003.png"] = b"not a picture"
                answers["https://example.test/003_s.png"] = b"not a picture"
                s.action_step(-1)
                s.action_step(1)
                await pilot.pause(0.2)
                s._put(99, "stale")  # an answer for a picture no longer shown
                with mock.patch.object(app_mod.pictures, "available", return_value=False):
                    s.show()
                    self.assertEqual(str(s.query_one("#pic").render()), i18n._("tui_no_pil"))
                one = PictureScreen(media[:1])
                one.action_step(1)  # one picture: nowhere to step
                self.assertEqual(one.at, 0)
                app.pop_screen()
                await pilot.pause(0.05)
            # no pictures in the lane when the setting is off or Pillow is missing
            app.core.cfg["tui"]["pictures"] = "key"
            app.load_pictures([])


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class ThreadsTest(Base):
    async def test_calls_from_other_threads_and_the_start(self):
        core, _w = self.make(tui={"theme": "no-such-theme", "sound": "off"})
        app = self.app_of(core)
        instance = mock.Mock()
        app._instance = instance
        async with app.run_test(size=(100, 30)) as pilot:
            await self.started(pilot, app)
            instance.listen.assert_called_once()
            self.assertIsNone(app.sounds)
            instance.listen.call_args[0][0]("show")  # another start: nothing to do here
            got = []
            t = threading.Thread(target=app.in_ui, args=(got.append, "from a thread"))
            t.start()
            t.join()
            await self.wait(pilot, lambda: got == ["from a thread"])
            app.in_ui(got.append, "here")
            await self.wait(pilot, lambda: got[-1] == "here")
            loop = app._ui_loop
            with mock.patch.object(loop, "call_soon_threadsafe",
                                   side_effect=RuntimeError("closed")):
                t = threading.Thread(target=app.in_ui, args=(got.append, "lost"))
                t.start()
                t.join()
            app._ui_loop = None
            t = threading.Thread(target=app.in_ui, args=(got.append, "lost"))
            t.start()
            t.join()
            app._ui_loop = loop
            await pilot.pause(0.1)
            self.assertNotIn("lost", got)
            app.show_error("x" * 400)
            # a core future that fails without a handler: said as an error
            errors = []
            app.show_error = errors.append
            app.later(done(error=ValueError("bad")))
            await self.wait(pilot, lambda: errors == ["bad"])
            from concurrent.futures import Future
            f = Future()
            app.later(f, ok=got.append)
            f.cancel()
            await pilot.pause(0.05)
            # an answer arriving as the app closes (no screens left): dropped quietly
            with mock.patch.object(type(app), "screen_stack", new_callable=mock.PropertyMock,
                                   return_value=[]):
                app.later(done("closing"), ok=got.append)
                await pilot.pause(0.1)
            self.assertNotIn("closing", got)
        app._run_in_ui(got.append, ("after",))  # not running any more: dropped
        self.assertNotIn("after", got)

    async def test_connect_failure_and_the_sound(self):
        core, _w = self.make(tui={"sound": "bell"})
        app = self.app_of(core)
        errors = []
        app.show_error = errors.append
        with mock.patch.object(Core, "connect",
                               return_value=done(error=OSError("no network"))):
            async with app.run_test(size=(100, 30)) as pilot:
                await self.wait(pilot, lambda: errors)
                self.assertIn("no network", errors[0])
                self.assertIsNotNone(app.sounds)
                with mock.patch.object(app.sounds, "play") as play:
                    app.play_sound("mention")
                    play.assert_called_once_with("mention", focused=False)
                await asyncio.sleep(0)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class EdgesTest(Base):
    def test_render_and_an_older_textual(self):
        from fedtail.frontends.tui import app as app_mod
        from fedtail.frontends.tui.model import Shown
        t = app_mod.render(Shown(head=[("who", "@bob")], above=[("boost", "♻ boosted")]))
        self.assertEqual(t.plain, "♻ boosted\n@bob")
        real_input = app_mod.Input

        def old_input(*a, **kw):
            if "select_on_focus" in kw:
                raise TypeError("unexpected keyword")
            return real_input(*a, **kw)
        with mock.patch.object(app_mod, "Input", old_input):
            self.assertEqual(app_mod._cmd_line().id, "cmd")

    async def test_edges(self):
        from textual.css.query import NoMatches
        from textual.widgets import Input, ListView

        from fedtail.frontends.common import actions
        from fedtail.frontends.tui.app import PostItem, ThreadScreen
        core, w = self.make(tui={"pictures": "off"})
        w.add(status("001", BOB, minute=1, text="one", vis="public"), home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            posts = app.query_one("#posts", ListView)
            await self.wait(pilot, lambda: any(isinstance(x, PostItem)
                                               for x in posts.children))
            st = app.core.by_id("001")
            # r on an empty list: nothing; the places' r: "#alias " in the line
            with mock.patch.object(type(app), "current", return_value=None):
                app.action_reply()
            app.post_reply(st)
            self.assertTrue(app.query_one("#cmd", Input).value.startswith("#"))
            with mock.patch.object(type(app.core), "short_ids", return_value={}):
                app.post_reply(st)
            self.assertEqual(app.query_one("#cmd", Input).value, "")
            # a ⋯ menu that would end in a line: the line goes
            sep = types.SimpleNamespace(kind="separator")
            item = types.SimpleNamespace(kind="copy", label="Copy", text="x")
            with mock.patch.object(actions, "menu", return_value=[item, sep, sep]):
                self.assertEqual([x[0] for x in app.post_menu_items(st)], ["Copy"])
            # the lanes not built: j / k move the posts
            with mock.patch.object(type(app), "_main", side_effect=NoMatches("none")):
                self.assertFalse(app._lanes_focused())
                await app.refresh_posts()  # the app closing: nothing to draw on
            # a conversation view: offered, on and off
            m = app.lane_model("home")
            with mock.patch.object(m, "conversations_offered", return_value=True), \
                    mock.patch.object(m, "conversations", return_value=True), \
                    mock.patch.object(m, "set_conversations") as setc:
                self.assertIn(i18n._("conv_mode"), app.lane_choice_words(m))
                app.action_lane_choices()
                await self.wait(pilot, lambda: type(app.screen).__name__ == "MenuScreen")
                labels = app.screen.labels()
                self.assertTrue(any(i18n._("conv_mode") in x for x in labels))
                app.screen.dismiss(("conv", False))
                await pilot.pause(0.1)
                setc.assert_called_once_with(False)
            # where the cursor starts when the lane can't say
            with mock.patch.object(m, "start_key", return_value="no-such-key"):
                await app.refresh_posts(first=True)
            self.assertEqual(posts.index, 0)
            # an answer for a screen closed meanwhile is dropped
            t = ThreadScreen("001")
            app.push_screen(t)
            await self.wait(pilot, lambda: app.screen is t)
            app.pop_screen()
            await pilot.pause(0.05)
            got = []
            t.later(done("late"), ok=got.append)
            await pilot.pause(0.1)
            self.assertEqual(got, [])

    async def test_a_picture_that_wont_draw(self):
        if Image is None:
            self.skipTest("Pillow is not installed")
        from textual.widgets import ListView
        core, w = self.make(tui={"pictures": "inline"})
        w.add(with_picture(status("001", BOB, minute=1, text="cat", vis="public")),
              home=True)
        app = self.app_of(core)
        with mock.patch.object(type(app.core), "media_bytes",
                               lambda _s, url: done(b"not a picture")):
            async with app.run_test(size=(120, 40)) as pilot:
                await self.started(pilot, app)
                await pilot.pause(0.3)
                posts = app.query_one("#posts", ListView)
                self.assertFalse(any(getattr(x, "has_picture", False)
                                     for x in posts.children))
                self.assertEqual(app._pictures, {})


if __name__ == "__main__":
    unittest.main()
