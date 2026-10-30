"""The terminal caught up with the windows (docs/src/parity.toml): a poll to vote in, the
editor's preview and extras, the thread's head, the sidebar's sections, the find bar's
keys, "to the new", older posts, the Debugging submenu, a picture saved. Driven
headless by Textual's pilot; skipped without Textual."""

import os
import unittest
from types import SimpleNamespace
from unittest import mock

try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ImportError:
    HAVE_TEXTUAL = False

from fedtail import i18n

from .fakes import BOB, ME, acct, status
from .test_cov_tui_host import Base, done

_ = i18n._


def with_poll(i, author, multiple=False, expired=False, voted=False, minute=1):
    st = status(i, author, minute=minute, vis="public", text=f"poll {i}")
    st["poll"] = {"id": "p" + i, "expires_at": "2099-01-01T00:00:00.000Z",
                  "expired": expired, "multiple": multiple, "votes_count": 3,
                  "voters_count": 2, "voted": voted, "own_votes": [0] if voted else [],
                  "options": [{"title": "yes", "votes_count": 2},
                              {"title": "", "votes_count": 1},
                              {"title": "maybe", "votes_count": 0}], "emojis": []}
    return st


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class PollTest(Base):
    async def test_vote_results_refresh(self):
        from fedtail.frontends.tui.app import PostItem
        from fedtail.frontends.tui.more import PollScreen
        from fedtail.frontends.tui.screens import MenuScreen
        core, w = self.make()
        w.add(with_poll("001", BOB), home=True)
        w.add(with_poll("002", BOB, multiple=True, minute=2), home=True)
        w.add(status("003", BOB, minute=3, text="no poll"), home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            posts = app.query_one("#posts")
            await self.wait(pilot, lambda: len(posts.children) >= 3, what="posts")

            def to(i):
                posts.focus()
                posts.index = next(n for n, it in enumerate(posts.children)
                                   if isinstance(it, PostItem) and it.entry.id == i)
            # the card says it in words
            first = next(it for it in posts.children if getattr(it, "entry", None) and
                         it.entry.id == "001")
            self.assertIn(_("tui_poll"), str(first.text))
            to("003")
            await pilot.press("u")  # no poll: nothing
            await pilot.pause(0.1)
            self.assertNotIsInstance(app.screen, PollScreen)

            to("001")
            await pilot.press("u")
            await self.wait(pilot, lambda: isinstance(app.screen, PollScreen), what="poll")
            scr = app.screen
            self.assertTrue(scr.open_ended())
            labels = [str(t) for t in scr.lines()]
            self.assertIn(_("poll_option", n=2), labels[1])
            self.assertTrue(labels[0].startswith("○"))
            await pilot.press("r")  # the results before voting
            await pilot.pause(0.1)
            self.assertIn("%", str(scr.lines()[0]))
            await pilot.press("r")
            await pilot.press("j")
            await pilot.press("k")
            await pilot.press("j")
            await pilot.press("enter")  # nothing ticked: the highlighted one
            await self.wait(pilot, lambda: w.statuses["001"]["poll"]["voted"], what="voted")
            self.assertEqual(w.statuses["001"]["poll"]["own_votes"], [1])
            await self.wait(pilot, lambda: _("poll_voted") in self.notes, what="said")
            await self.wait(pilot, lambda: not scr.open_ended(), what="closed for me")
            await pilot.press("space")  # voted: ticks nothing
            await pilot.press("enter")
            self.assertEqual(scr.picked, set())
            await pilot.press("u")  # fresh counts
            await pilot.pause(0.2)
            scr.failed(RuntimeError("nope"))
            self.assertFalse(scr.sending)
            await pilot.press("escape")
            await self.wait(pilot, lambda: not isinstance(app.screen, PollScreen))

            # several may be picked: from the ⋯ menu
            to("002")
            app.action_post_menu()
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen), what="⋯")
            item = app.screen.items[0]
            self.assertIn(_("poll_vote"), item[0])
            app.screen.dismiss(item[1])
            await self.wait(pilot, lambda: isinstance(app.screen, PollScreen), what="poll 2")
            scr = app.screen
            await pilot.press("space")
            await pilot.press("j")
            await pilot.press("space")
            await pilot.press("j")
            await pilot.press("space")
            await pilot.press("space")  # ticked twice: off
            self.assertEqual(scr.picked, {0, 1})
            self.assertTrue(str(scr.lines()[0]).startswith("☑"))
            scr.sending = True
            await scr.action_vote()  # one vote at a time
            scr.sending = False
            await pilot.press("enter")
            await self.wait(pilot, lambda: w.statuses["002"]["poll"]["voted"], what="voted 2")
            self.assertEqual(w.statuses["002"]["poll"]["own_votes"], [0, 1])
            await pilot.press("escape")

    async def test_a_closed_poll_and_my_own(self):
        from fedtail.frontends.tui.more import PollScreen
        core, w = self.make()
        w.add(with_poll("001", BOB, expired=True), home=True)
        w.add(with_poll("002", ME, minute=2), home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            await self.wait(pilot, lambda: len(app.query_one("#posts").children) >= 2)
            for i in ("001", "002"):
                st = app.core.by_id(i)
                app.push_screen(PollScreen(st))
                await self.wait(pilot, lambda: isinstance(app.screen, PollScreen))
                self.assertFalse(app.screen.open_ended())
                self.assertIn("(", str(app.screen.lines()[0]))  # the counts shown
                await app.screen.action_vote()
                await app.screen.changed(None)  # no post back: the old one stays
                app.pop_screen()
                await pilot.pause(0.05)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class EditorTest(Base):
    async def test_count_preview_language_discard_alt(self):
        from textual.widgets import Input, Static, TextArea

        from fedtail.frontends.tui.more import PreviewScreen
        from fedtail.frontends.tui.screens import (
            AskScreen,
            ComposeScreen,
            ConfirmScreen,
            MenuScreen,
        )
        core, w = self.make()
        w.add(status("001", BOB, minute=1, text="hello"), home=True)
        app = self.app_of(core)
        pic = self.tmp / "cat.png"
        pic.write_bytes(b"\x89PNG not really")
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            scr = ComposeScreen()
            app.push_screen(scr)
            await self.wait(pilot, lambda: app.screen is scr, what="editor")
            ta = scr.query_one("#c-text", TextArea)
            ta.text = "about #lowercasetag"
            await pilot.pause(0.1)
            count = str(scr.query_one("#c-count", Static).render())
            self.assertIn("/ 500", count)
            self.assertIn("#lowercasetag", count)  # the CamelCase hint
            ta.text = "w" * (scr.show_count().limit + 1)  # over the limit
            await pilot.pause(0.1)
            self.assertTrue(scr.show_count().over)
            ta.text = "one\n---\ntwo"  # a chain
            await pilot.pause(0.1)
            self.assertEqual(scr.show_count().parts, 2)

            # Ctrl+R: the preview, Markdown or not
            await pilot.press("ctrl+r")
            await self.wait(pilot, lambda: isinstance(app.screen, PreviewScreen))
            self.assertIn(_("chain_count", n=scr.show_count().parts),
                          str(app.screen.query_one("#pv-title", Static).render()))
            await pilot.press("escape")
            await self.wait(pilot, lambda: app.screen is scr)
            app.push_screen(PreviewScreen("**b**", "a warning", True, 1, 2))
            await self.wait(pilot, lambda: isinstance(app.screen, PreviewScreen))
            self.assertIn(_("preview_media", n=2),
                          str(app.screen.query_one("#pv-title", Static).render()))
            await pilot.press("enter")
            await self.wait(pilot, lambda: app.screen is scr)

            async def extras(value):
                scr.action_extras()
                await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
                self.assertIn(value, [it[1] for it in app.screen.items if it != "-"])
                app.screen.dismiss(value)
                await pilot.pause(0.05)

            # another language, typed
            await extras("lang")
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            app.screen.dismiss("EO")
            await self.wait(pilot, lambda: scr.query_one("#c-lang", Input).value == "eo")
            scr._language("not a code!")
            self.assertEqual(scr.query_one("#c-lang", Input).value, "eo")

            # a picture without a description: asked before it goes
            ta.text = "a cat"
            scr.media = [(str(pic), "")]
            scr.action_send()
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen), what="alt?")
            self.assertIn(_("alt_missing", n=1), app.screen.m_title)
            app.screen.dismiss("describe")
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            app.screen.dismiss("a grey cat")
            await self.wait(pilot, lambda: scr.media[0][1] == "a grey cat")
            scr.media.append((str(pic), ""))
            scr.action_send()
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            app.screen.dismiss(None)  # neither: stays
            await pilot.pause(0.05)
            self.assertIs(app.screen, scr)
            scr.action_send()
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            app.screen.dismiss("send")
            await self.wait(pilot, lambda: app.screen is not scr, what="sent")
            self.assertTrue(scr.alt_ok)

            # post.lang_check: another language than the post's — asked, switched, sent
            app.core.cfg["post"]["lang_check"] = True
            scr = ComposeScreen()
            app.push_screen(scr)
            await self.wait(pilot, lambda: app.screen is scr)
            scr.query_one("#c-text", TextArea).text = (
                "გამარჯობა მეგობრებო, დღეს თბილისში ძალიან ლამაზი ამინდია და ქალაქი სავსეა")
            scr.query_one("#c-lang", Input).value = "en"
            scr.action_send()
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen), what="lang?")
            app.screen.dismiss("switch")
            await self.wait(pilot, lambda: app.screen is not scr, what="sent")
            # the editor has gone with its fields: what reached the server says it
            await self.wait(pilot, lambda: w.languages[-1:] == ["ka"], what="sent as ka")
            app.core.cfg["post"]["lang_check"] = False

            # discard, asked first
            scr = ComposeScreen()
            app.push_screen(scr)
            await self.wait(pilot, lambda: app.screen is scr)
            scr.query_one("#c-text", TextArea).text = "never mind"
            await extras("discard")
            await self.wait(pilot, lambda: isinstance(app.screen, ConfirmScreen))
            app.screen.dismiss(False)
            await self.wait(pilot, lambda: app.screen is scr)
            await extras("discard")
            await self.wait(pilot, lambda: isinstance(app.screen, ConfirmScreen))
            app.screen.dismiss(True)
            await self.wait(pilot, lambda: app.screen is not scr, what="discarded")

            # an edit: its pictures stay, said so; no other language offered
            st = app.core.by_id("001")
            scr = ComposeScreen(edit=st, text="hello")
            app.push_screen(scr)
            await self.wait(pilot, lambda: app.screen is scr)
            self.assertIn(_("edit_media_kept"),
                          str(scr.query_one("#c-hint", Static).render()))

            # all accounts in one window: a reply from the other one is said
            scr.reply_to, scr.from_first = st, "main"
            scr.accounts = [("main", "me@a.example"), ("other", "me@b.example")]
            ev = SimpleNamespace(select=SimpleNamespace(id="c-from"), value="other")
            scr.on_select_changed(ev)
            self.assertIn("me@b.example", str(scr.query_one("#c-count", Static).render()))
            scr.on_select_changed(SimpleNamespace(select=SimpleNamespace(id="c-from"),
                                                  value="main"))
            self.assertEqual(str(scr.query_one("#c-count", Static).render()), "")
            scr.on_select_changed(SimpleNamespace(select=SimpleNamespace(id="c-vis"),
                                                  value="x"))


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class ThreadHeadTest(Base):
    async def test_my_answer_shows_in_the_open_thread(self):
        """Sent from the editor or anywhere: the thread on screen takes my answer in at
        once (the core's "arrived"), as the windows do — it showed only opened anew."""
        from fedtail.frontends.tui.app import ThreadScreen
        core, w = self.make()
        w.add(status("010", BOB, minute=1, text="the root"), home=True)
        w.add(status("011", BOB, "010", "B", minute=2, text="a reply"), home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            scr = ThreadScreen("011")
            app.push_screen(scr)
            await self.wait(pilot, lambda: len(scr.query_one("#posts").children) == 2)
            app.core.post("me too", "private", reply_to="011")
            await self.wait(pilot, lambda: len(scr.query_one("#posts").children) == 3,
                            what="my answer in the thread")

    async def test_a_thread_that_comes_after_its_screen_went(self):
        """CI, 30.10: the thread's answer came while its screen had no title (gone, or
        not drawn yet) — NoMatches took the test down. It draws nothing then."""
        from fedtail.frontends.tui.app import ThreadScreen
        core, w = self.make()
        w.add(status("010", BOB, minute=1, text="the root"), home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            scr = ThreadScreen("010")
            app.push_screen(scr)
            await self.wait(pilot, lambda: len(scr.query_one("#posts").children) == 1)
            items = core.thread("010").result()
            scr.query_one("#title").remove()
            await pilot.pause()
            await scr.fill(items)  # no title: quietly nothing

    async def test_count_cw_follow_via_home(self):
        from textual.widgets import Static

        from fedtail.frontends.tui.app import ThreadScreen
        core, w = self.make(ui={"expand_cw": False, "arts_mode": False})
        carol = acct("C", "carol@other.example")
        root = status("010", BOB, minute=1, text="the root")
        root["spoiler_text"] = "spoilers"
        w.add(root, home=True)
        w.add(status("011", carol, "010", "B", minute=2, text="a reply"), home=True)
        w.add(status("012", BOB, "011", "C", minute=3, text="deeper"), home=True)
        w.following.add("B")
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            scr = ThreadScreen("011")
            app.push_screen(scr)
            await self.wait(pilot, lambda: len(scr.query_one("#posts").children) == 3)
            title = scr.query_one("#title", Static)
            self.assertIn(_("thread_info", n=2), scr.info)
            self.assertIn(_("cw_all_show"), scr.info)
            await self.wait(pilot, lambda: _("thread_via_home", names="@bob")
                            in str(title.render()), what="via home")
            texts = [str(it.text) for it in scr.query_one("#posts").children]
            self.assertIn(_("came_from"), texts[1])
            self.assertNotIn("the root", texts[0])  # behind its warning
            await pilot.press("c")
            await self.wait(pilot, lambda: "the root" in str(
                scr.query_one("#posts").children[0].text), what="every CW open")
            self.assertIn(_("cw_all_hide"), scr.info)
            self.assertIn(_("cw_all_tip"), self.notes)

            await pilot.press("s")
            await self.wait(pilot, lambda: app.core.subscribed(scr.root),
                            what="followed")
            await self.wait(pilot, lambda: "✓" in scr.info, what="said in the title")
            scr.via_home([BOB])  # subscribed: the reason isn't needed
            await pilot.press("s")
            await self.wait(pilot, lambda: _("unsubbed") in self.notes, what="unfollowed")

            many = [SimpleNamespace(handle=f"p{i}@x") for i in range(5)]
            await self.wait(pilot, lambda: not app.core.subscribed(app.core.by_id("010")))
            await pilot.pause(0.2)
            scr.via_home(many)
            self.assertIn(_("and_more", n=2), str(title.render()))
            scr.via_home([])
            scr.root = None
            scr.action_follow_thread()  # nothing loaded: nothing to follow


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class SidebarAndFindTest(Base):
    async def test_sections_fold(self):
        from fedtail.frontends.tui.app import GroupItem, LaneItem
        core, w = self.make()
        w.add(status("001", BOB, minute=1), home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            lanes = app.query_one("#lanes")
            heads = [it for it in lanes.children if isinstance(it, GroupItem)]
            self.assertTrue(heads)
            head = heads[-1]
            under = len([it for it in lanes.children if isinstance(it, LaneItem)])
            lanes.focus()
            lanes.index = list(lanes.children).index(head)
            await pilot.press("enter")
            await self.wait(pilot, lambda: len([it for it in lanes.children if isinstance(
                it, LaneItem)]) < under, what="folded")
            again = next(it for it in lanes.children if isinstance(it, GroupItem) and
                         it.group == head.group)
            self.assertTrue(again.folded)
            self.assertTrue(str(again.label.render()).startswith("▸"))
            self.assertIs(lanes.highlighted_child, again)  # where it was
            await app.fold_group(again)
            await self.wait(pilot, lambda: len([it for it in lanes.children if isinstance(
                it, LaneItem)]) == under, what="unfolded")
            self.assertEqual(GroupItem._text("t", True, 3).plain, "▸ T 3")

    async def test_find_keys_deeper_everywhere(self):
        from fedtail.frontends.tui.app import PostItem
        from fedtail.frontends.tui.screens import AskScreen, MenuScreen
        core, w = self.make(feed={"order": "newest_first"})
        for i in range(1, 6):
            w.add(status(f"00{i}", BOB, minute=i, text=f"needle {i}" if i % 2 else
                         "hay"), home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            posts = app.query_one("#posts")
            await self.wait(pilot, lambda: len(posts.children) >= 3, what="posts")
            app.action_find()
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            self.assertIn("N — " + _("find_prev"), app.screen.question)
            app.screen.dismiss("needle")
            await self.wait(pilot, lambda: getattr(app, "_found", None))
            hits = app._found["hits"]
            self.assertGreaterEqual(len(hits), 2)
            self.assertEqual(posts.index, hits[0])
            await pilot.press("N")  # back round to the last
            self.assertEqual(posts.index, hits[-1])
            await pilot.press("ctrl+f")
            self.assertEqual(posts.index, hits[0])
            posts.focus()
            await pilot.press("escape")  # the find closed
            self.assertIsNone(app._found)
            self.assertIn(_("find_close"), self.notes)
            app.action_find_prev()  # nothing found: nothing
            app.action_find_deeper()

            # nothing here: kept for D and E
            app.find("zzz")
            self.assertEqual(app._found["hits"], [])
            app.action_find_prev()
            for res in ({"total": 0, "more": False}, {"total": 1, "more": False}):
                app.core.deep_find = lambda _l, _q, r=res: done(r)
                app.action_find_deeper()
                await pilot.pause(0.1)
            self.assertIn(_("find_archive_none"), self.notes)
            app.core.deep_find = lambda _l, _q: done({"total": 1, "more": True})
            app.action_find_deeper()
            await pilot.pause(0.3)  # found again after the lane grew: none still
            self.assertEqual(app._found["query"], "zzz")

            # E: every lane
            app.core.find_everywhere = lambda _q: done([])
            app.action_find_everywhere()
            await pilot.pause(0.1)
            self.assertIn(_("find_none_anywhere"), self.notes)
            app.core.find_everywhere = lambda _q: done([
                {"lane": "no-such-lane", "status_id": "001", "index": 0, "item": None},
                {"lane": "home", "status_id": "003", "index": 50, "item": None},
                {"lane": "home", "status_id": "gone", "index": 1, "item": None}])
            app.action_find_everywhere()
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen), what="hits")
            self.assertEqual(len(app.screen.items), 2)
            app.screen.dismiss(app.screen.items[0][1])
            await self.wait(pilot, lambda: getattr(posts.highlighted_child, "entry", None)
                            and posts.highlighted_child.entry.id == "003", what="shown")
            app.action_find_everywhere()  # the find was closed by the lane: asked anew
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            app.screen.dismiss(None)
            await pilot.pause(0.05)

            # J: to the first new one (newest first: the lowest unread)
            unread = app.core.unread([it.entry for it in posts.children
                                  if isinstance(it, PostItem)])
            app.action_to_new()
            if unread:
                self.assertIn(posts.highlighted_child.entry.id, unread)
            app.core.mark_read([it.entry for it in posts.children if isinstance(it, PostItem)])
            app.action_to_new()
            self.assertIn(_("to_new_tip") + ": —", self.notes)

            # j past the last (newest first): older ones from the server
            posts.focus()
            posts.index = len(posts.children) - 1
            app.core.load_older = lambda _n: done(0)
            app.action_cursor_down()
            await self.wait(pilot, lambda: _("no_older") in self.notes, what="no older")
            app.core.load_older = lambda _n: done(2)
            await app.action_older()
            await app.select_lane("activity")
            await app.action_older()  # not a lane of posts: nothing

    async def test_older_on_top_and_the_lane_menu(self):
        from fedtail.frontends.tui.screens import MenuScreen
        core, w = self.make()
        for i in range(1, 4):
            w.add(status(f"00{i}", BOB, minute=i), home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            posts = app.query_one("#posts")
            await self.wait(pilot, lambda: len(posts.children) >= 3)
            asked = []
            app.core.load_older = lambda n: asked.append(n) or done(0)
            posts.focus()
            posts.index = 0
            app.action_cursor_up()  # oldest first: older ones above
            await self.wait(pilot, lambda: asked == ["home"], what="older asked")
            app.action_lane_choices()
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            menu = app.screen
            i = next(n for n, it in enumerate(menu.items)
                     if it != "-" and it[1] == ("new", None))
            self.assertEqual(menu.hint_of(i), _("to_new_tip"))
            self.assertEqual(menu.hint_of(99), "")
            menu.query_one("#menu").index = i
            await pilot.pause(0.05)
            self.assertTrue(menu.query_one("#menu-hint").display)
            menu.dismiss(("new", None))
            await pilot.pause(0.1)

            # all accounts in one window: the account that got it, on the card and menu
            app.core.via = lambda _e: "@me@b.example"
            await app.refresh_posts()
            await self.wait(pilot, lambda: "⇄ @me@b.example" in str(
                posts.children[0].text), what="via on the card")
            posts.index = 0
            app.action_post_menu()
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            self.assertEqual(app.screen.hint_of(0), _("via_tip", acct="@me@b.example"))
            app.screen.dismiss(None)
            await pilot.pause(0.05)

            # the preview of plain text
            from fedtail.frontends.tui.more import PreviewScreen
            app.push_screen(PreviewScreen("plain *text*"))
            await self.wait(pilot, lambda: isinstance(app.screen, PreviewScreen))
            self.assertIn(_("preview_plain"), str(app.screen.query_one("#pv-title").render()))
            await pilot.press("escape")


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class DebugAndSaveTest(Base):
    async def test_debug_menu(self):
        from fedtail import diag
        from fedtail.frontends.tui.screens import MenuScreen
        core, w = self.make()
        app = self.app_of(core)
        copied = []
        app.copy_text = copied.append
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            app.action_main_menu()
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            self.assertIn(("do", "debug"), [it[1] for it in app.screen.items if it != "-"])
            app.screen.dismiss(("do", "debug"))
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen) and
                            app.screen.m_title == _("debug_menu"), what="≡ Debugging")
            # the full snapshot first, everything of debugging in one place (29.10)
            self.assertEqual(app.screen.items[0][1], ("bug_report", None))
            self.assertIn(("place", "log"), [it[1] for it in app.screen.items if it != "-"])
            self.assertTrue(any("Textual" in x for x in app.screen.labels()))
            app.screen.dismiss(("corner", None))
            await self.wait(pilot, lambda: copied and "Textual" in copied[-1])

            await app.debug_do("notify")
            self.assertTrue(self.notes[-1])
            with mock.patch.object(diag, "full_snapshot", return_value=self.tmp / "r.tar.gz"):
                await app.menu_do("bug_report")
            self.assertIn("r.tar.gz", self.notes[-1])
            with mock.patch.dict(os.environ, {"VISUAL": "", "EDITOR": ""}):
                app.open_file("/tmp/x.toml")
            self.assertEqual(copied[-1], "/tmp/x.toml")
            ran = []
            app.run_outside = lambda argv: ran.append(argv) or True
            with mock.patch.dict(os.environ, {"VISUAL": "nano -w", "EDITOR": ""}):
                app.open_file("/tmp/y.toml")  # the editor, the terminal handed over
            self.assertEqual(ran, [["nano", "-w", "/tmp/y.toml"]])
            self.assertFalse(app.merged())
            await app.debug_do("merge")
            self.assertTrue(app.merged())
            await app.debug_do("merge")
            self.assertFalse(app.merged())
            app.notifier.notify([])

    async def test_save_a_picture(self):
        from fedtail.frontends.tui.app import PictureScreen
        save = self.tmp / "saved"
        core, w = self.make(ui={"save_dir": str(save)})
        st = status("001", BOB, minute=1, text="a picture")
        st["media_attachments"] = [{"id": "m1", "type": "image",
                                    "url": "https://img.example/cat.png",
                                    "preview_url": "https://img.example/cats.png"}]
        w.add(st, home=True)
        app = self.app_of(core)
        errors = []
        app.show_error = lambda e: errors.append(str(e))
        app.core.media_bytes = lambda url: done(b"\x89PNG data")
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            media = app.core.by_id("001").media
            app.push_screen(PictureScreen(media))
            await self.wait(pilot, lambda: isinstance(app.screen, PictureScreen))
            await pilot.press("s")
            await self.wait(pilot, lambda: (save / "cat.png").exists(), what="saved")
            await self.wait(pilot, lambda: any(str(save) in n for n in self.notes))
            app.core.media_bytes = lambda url: done(error=OSError("offline"))
            app.save_media(media[0])
            await self.wait(pilot, lambda: errors and "offline" in errors[-1])
            scr = app.screen
            self.assertIn(_("save_image"), str(scr.query_one("#pic-title").render()))
            self.assertEqual(scr.query_one("#pic-title").tooltip, _("viewer_save_tip"))
            with mock.patch("fedtail.frontends.tui.pictures.available", return_value=True):
                await pilot.press("r")  # once more: the original didn't come
                await self.wait(pilot, lambda: "offline" in str(
                    scr.query_one("#pic").render()), what="unreachable said")
            app.save_media(SimpleNamespace(url="", remote_url="", preview=""))


if __name__ == "__main__":
    unittest.main()
