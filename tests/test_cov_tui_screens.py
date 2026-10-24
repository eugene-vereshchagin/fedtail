"""The terminal's screens (frontends/tui/screens.py) beyond tests/test_tui_places.py: a
place's every answer (sure?, a line to type, an error, the editor, back, the same place
anew, another one), its rows of every kind, its form of every kind, its keys; the
editor's pictures, poll, "later", sending and leaving; the menus. Driven headless by
Textual's pilot; skipped without Textual."""

import unittest
from pathlib import Path
from unittest import mock

try:
    import textual  # noqa: F401
    HAVE_TEXTUAL = True
except ImportError:
    HAVE_TEXTUAL = False

from fedtail import i18n
from fedtail.frontends.common.places import Btn, Field, Out, Page, Row

from .fakes import BOB, ME, status
from .test_cov_tui_host import Base, done


class StubPlaces:
    """What a PlaceScreen asks of common/places.py: a page per (name, arg, tab), and
    the next of `outs` per act (noted)."""

    def __init__(self, pages, outs=()):
        self.pages, self.outs, self.acts = pages, list(outs), []

    def page(self, name, arg="", tab="", cursor=""):
        got = self.pages.get((name, tab)) or self.pages.get(name)
        if isinstance(got, Exception):
            raise got
        return got

    def act(self, place, key, data="", values=None, confirmed=False, answer=None):
        self.acts.append((place, key, data, values, confirmed, answer))
        return self.outs.pop(0) if self.outs else Out()

    def help_target(self, href, here):
        return Out(open={"url": href})


def btn(label, key="go", data=""):
    return Btn(label, ("stub", key, data))


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class PlaceScreenTest(Base):
    def screen_of(self, stub, name="stub", arg="", tab=""):
        from fedtail.frontends.tui.screens import PlaceScreen

        class Stubbed(PlaceScreen):
            @property
            def places(self):
                return stub
        return Stubbed(name, arg, tab)

    async def test_rows_form_and_answers(self):
        from textual.widgets import Checkbox, Input, Select, TextArea

        from fedtail.frontends.tui.app import PostItem, ProfileScreen, ThreadScreen
        from fedtail.frontends.tui.screens import AskScreen, ComposeScreen, ConfirmScreen
        from fedtail.protocols.mastodon.adapter import account
        core, w = self.make()
        w.add(status("001", BOB, minute=1, text="a post", vis="public"), home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 48)) as pilot:
            await self.started(pilot, app)
            post = app.core.by_id("001")
            bob = account(BOB)
            rows = [Row("post", data=post),
                    Row("html", title="<p>plain <b>html</b></p>", key="h"),
                    Row("heading", "A heading"),
                    Row("account", "Bob", "@bob", data=bob),
                    Row("account", "Bob", "@bob", data=bob, buttons=(btn("Follow", "f"),)),
                    Row("item", "Item", buttons=(btn("One", "one"), btn("Two", "two")))]
            form = (Field("q", "Line", "x"), Field("t", "Text", "several\nlines", "text"),
                    Field("c", "Check", True, "check"),
                    Field("s", "Choice", "b", "choice", (("a", "A"), ("b", "B"))),
                    Field("m", "Many", ["a"], "checks", (("a", "A"), ("b", "B")), tip="why"))
            page = Page("stub", "The stub", hint="a hint", tabs=(("t1", "One"), ("t2", "Two")),
                        tab="t1", rows=rows, form=form, submit=btn("Send", "send"),
                        more=btn("More", "more"))
            outs = [Out(message="done", refresh=True)]
            stub = StubPlaces({"stub": page}, outs)
            screen = self.screen_of(stub)
            app.push_screen(screen)
            await self.wait(pilot, lambda: screen.page is not None, what="the page")
            kids = list(screen.query_one("#posts").children)
            self.assertIsInstance(kids[0], PostItem)
            self.assertEqual(len(kids), len(rows) + 1)  # and "more"
            self.assertEqual(screen.values(), {"q": "x", "t": "several\nlines", "c": True,
                                               "s": "b", "m": ["a"]})
            screen.query_one(TextArea).text = "changed"
            screen.query_one(Input).value = "y"
            screen.query_one(Checkbox).value = False
            self.assertEqual(screen.values()["t"], "changed")
            self.assertIsInstance(screen.query_one(Select), Select)

            # Ctrl+S: the form's button with what the form holds; a message, then anew
            await screen.action_submit()
            self.assertEqual(stub.acts[-1][1], "send")
            self.assertEqual(stub.acts[-1][3]["q"], "y")
            self.assertIn("done", self.notes)

            # the submit button does the same; another button doesn't
            from textual.widgets import Button
            await screen.on_button_pressed(Button.Pressed(screen.query_one("#submit",
                                                                           Button)))
            self.assertEqual(stub.acts[-1][1], "send")
            n = len(stub.acts)
            await screen.on_button_pressed(Button.Pressed(Button("other", id="other")))
            self.assertEqual(len(stub.acts), n)

            # 1…9 press the row's buttons
            lv = screen.query_one("#posts")
            lv.index = 5
            await screen.action_press(2)
            self.assertEqual(stub.acts[-1][1], "two")
            n = len(stub.acts)
            await screen.action_press(7)  # no such button
            self.assertEqual(len(stub.acts), n)

            # Enter: a post — its thread; a person without buttons — the profile; a row
            # with buttons — the first; a heading — nothing
            async def selected(i):
                lv.index = i
                await screen.on_list_view_selected(mock.Mock(item=lv.children[i]))
            await selected(0)
            await self.wait(pilot, lambda: isinstance(app.screen, ThreadScreen))
            app.pop_screen()
            await selected(3)
            await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen))
            app.pop_screen()
            await selected(4)
            self.assertEqual(stub.acts[-1][1], "f")
            n = len(stub.acts)
            await selected(2)  # a heading: a button-less row, not a person
            await screen.on_list_view_selected(mock.Mock(item=object()))
            self.assertEqual(len(stub.acts), n)

            # sure? — yes acts again confirmed; no doesn't
            stub.outs[:] = [Out(confirm="Really?"), Out(message="confirmed")]
            await screen.act(btn("Delete", "del"))
            await self.wait(pilot, lambda: isinstance(app.screen, ConfirmScreen))
            await pilot.press("y")
            await self.wait(pilot, lambda: "confirmed" in self.notes)
            self.assertTrue(stub.acts[-1][4])
            stub.outs[:] = [Out(confirm="Really?")]
            n = len(stub.acts)
            await screen.act(btn("Delete", "del"))
            await self.wait(pilot, lambda: isinstance(app.screen, ConfirmScreen))
            await pilot.press("n")
            await pilot.pause(0.1)
            self.assertEqual(len(stub.acts), n + 1)

            # a line to type, then acted with it; Esc — nothing
            stub.outs[:] = [Out(ask=("Name", "which?", "")), Out(message="named")]
            await screen.act(btn("Rename", "ren"))
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            await pilot.press(*"new")
            await pilot.press("enter")
            await self.wait(pilot, lambda: "named" in self.notes)
            self.assertEqual(stub.acts[-1][5], "new")
            stub.outs[:] = [Out(ask=("Name", "which?", ""))]
            await screen.act(btn("Rename", "ren"))
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            await pilot.press("enter")  # nothing typed: stays
            self.assertIsInstance(app.screen, AskScreen)
            await pilot.press("escape")
            await self.wait(pilot, lambda: not isinstance(app.screen, AskScreen))

            # an error said; the editor; the same place anew; back; another place
            errors = []
            app.show_error = errors.append
            stub.outs[:] = [Out(error="nope")]
            await screen.act(btn("X"))
            self.assertEqual(errors, ["nope"])
            stub.outs[:] = [Out(compose={"text": "hi"})]
            await screen.act(btn("Write"))
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))
            app.pop_screen()
            await pilot.pause(0.05)
            stub.outs[:] = [Out(open={"page": "stub", "arg": "a2", "tab": "t2",
                                      "cursor": "c"})]
            await screen.act(btn("Go"))
            self.assertEqual((screen.arg, screen.cursor), ("a2", "c"))
            stub.outs[:] = [Out(open={"thread": "001"})]
            await screen.act(btn("Thread"))
            await self.wait(pilot, lambda: isinstance(app.screen, ThreadScreen))
            app.pop_screen()
            await pilot.pause(0.05)
            stub.outs[:] = [Out()]
            await screen.act(btn("Nothing"))  # nothing to do: nothing happens
            stub.outs[:] = [Out(open={"back": True})]
            await screen.act(btn("Back"))
            await self.wait(pilot, lambda: app.screen is not screen)

    async def test_keys_tabs_load_failure_and_help_links(self):
        from fedtail.frontends.tui.app import ProfileScreen
        from fedtail.frontends.tui.screens import ComposeScreen, MenuScreen, PlaceScreen
        core, w = self.make()
        w.add(status("001", BOB, minute=1, text="a post", vis="public"), home=True)
        app = self.app_of(core)
        async with app.run_test(size=(120, 48)) as pilot:
            await self.started(pilot, app)
            post = app.core.by_id("001")
            one = Page("stub", "Tabs", tabs=(("t1", "One"), ("t2", "Two")), tab="t1",
                       rows=[Row("post", data=post)], form=(Field("q", "Search"),),
                       submit=btn("Find", "find"))
            two = Page("stub", "Tabs", tabs=(("t1", "One"), ("t2", "Two")), tab="t2",
                       empty="nothing here")
            stub = StubPlaces({("stub", "t1"): one, ("stub", "t2"): two, ("stub", ""): one})
            screen = self.screen_of(stub)
            app.push_screen(screen)
            await self.wait(pilot, lambda: screen.page is not None)
            # one field: Enter in it sends
            from textual.widgets import Input
            screen.query_one(Input).value = "bob"
            await screen.on_input_submitted(Input.Submitted(screen.query_one(Input), "bob"))
            self.assertEqual(stub.acts[-1][1], "find")
            # a post's keys work here as in the lane
            screen.query_one("#posts").focus()
            screen.query_one("#posts").index = 0
            seen = []
            for name in ("reply", "fav", "boost", "bookmark"):
                setattr(app, "post_" + name, lambda st, where, n=name: seen.append(n))
            screen.action_reply()
            screen.action_fav()
            screen.action_boost()
            screen.action_bookmark()
            self.assertEqual(seen, ["reply", "fav", "boost", "bookmark"])
            screen.action_cursor_down()
            screen.action_cursor_up()
            screen.action_profile()
            await self.wait(pilot, lambda: isinstance(app.screen, ProfileScreen))
            app.pop_screen()
            await pilot.pause(0.05)
            screen.action_post_menu()
            await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
            app.pop_screen()
            await pilot.pause(0.05)
            screen.status_changed(post)
            # ] — the next tab; an empty one says so, and with no post the keys rest
            await screen.action_tab(1)
            self.assertEqual(screen.tab, "t2")
            self.assertIn("nothing here", str(screen.query_one("#posts").children[0]
                                              .query_one("Static").render()))
            screen.action_reply()
            screen.action_profile()
            screen.action_post_menu()
            self.assertEqual(seen, ["reply", "fav", "boost", "bookmark"])
            # help links: another page of the help, or out
            await screen.on_markdown_link_clicked(mock.Mock(href="fedtail:help/keys#nav"))
            await self.wait(pilot, lambda: isinstance(app.screen, PlaceScreen) and
                            app.screen.name_ == "help" and app.screen.anchor == "nav")
            app.pop_screen()
            await pilot.pause(0.05)
            await screen.on_markdown_link_clicked(mock.Mock(href="https://example.test/"))
            self.browser.assert_called_with("https://example.test/")
            # a place without tabs: [ ] do nothing; Esc goes back
            stub.pages[("stub", "t2")] = Page("stub", "No tabs")
            await screen.load()
            await screen.action_tab(1)
            screen.action_back()
            await self.wait(pilot, lambda: app.screen is not screen)

            # a place that fails to load says so on its title
            bad = self.screen_of(StubPlaces({"stub": KeyError("gone")}))
            app.push_screen(bad)
            await self.wait(pilot, lambda: i18n._("load_failed", err="").split("{")[0]
                            .strip()[:6] in str(bad.query_one("#title").render()))
            app.pop_screen()
            # the real help: Markdown rows, a search's field focused at once
            app.push_screen(PlaceScreen("search"))
            await self.wait(pilot, lambda: app.screen.page is not None)
            self.assertTrue(app.screen.query_one(Input).has_focus)
            app.pop_screen()
            app.push_screen(ComposeScreen())
            await self.wait(pilot, lambda: isinstance(app.screen, ComposeScreen))

    async def test_a_place_closed_before_it_loads(self):
        core, _w = self.make()
        app = self.app_of(core)
        async with app.run_test(size=(100, 30)) as pilot:
            await self.started(pilot, app)
            page = Page("stub", "Slow")
            stub = StubPlaces({"stub": page})
            screen = self.screen_of(stub)
            app.push_screen(screen)
            await self.wait(pilot, lambda: screen.page is not None)
            app.pop_screen()
            await pilot.pause(0.05)
            screen.page = None
            await screen.load()  # not attached any more: nothing drawn
            self.assertIsNone(screen.page)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class MenuScreensTest(Base):
    async def test_menu_confirm_ask(self):
        from fedtail.frontends.tui.screens import AskScreen, ConfirmScreen, MenuScreen
        core, _w = self.make()
        app = self.app_of(core)
        async with app.run_test(size=(100, 30)) as pilot:
            await self.started(pilot, app)
            got = []
            menu = MenuScreen("Menu", ["-", ("One", 1), "-", ("Two", 2)])
            app.push_screen(menu, got.append)
            await self.wait(pilot, lambda: app.screen is menu)
            self.assertEqual(menu.labels(), ["One", "Two"])
            self.assertEqual(menu.query_one("#menu").index, 1)  # the first that can be chosen
            await pilot.press("j")
            await pilot.press("j")
            await pilot.press("k")
            await pilot.press("k")
            await pilot.press("enter")
            await self.wait(pilot, lambda: got == [1])
            menu = MenuScreen("Menu", [("One", 1)])
            app.push_screen(menu, got.append)
            await self.wait(pilot, lambda: app.screen is menu)
            menu.on_list_view_selected(mock.Mock(item=menu.query_one("#menu").children[0]))
            await self.wait(pilot, lambda: got == [1, 1])
            menu = MenuScreen("Menu", ["-", ("One", 1)])
            app.push_screen(menu, got.append)
            await self.wait(pilot, lambda: app.screen is menu)
            menu.on_list_view_selected(mock.Mock(item=menu.query_one("#menu").children[0]))
            self.assertIs(app.screen, menu)  # a line between isn't a choice
            await pilot.press("q")
            await self.wait(pilot, lambda: got == [1, 1, None])
            app.push_screen(ConfirmScreen("Sure?", "really"), got.append)
            await pilot.pause(0.1)
            await pilot.press("escape")
            await self.wait(pilot, lambda: got[-1] is False)
            app.push_screen(AskScreen("Q", "which?", "prefilled"), got.append)
            await pilot.pause(0.1)
            await pilot.press("escape")
            await self.wait(pilot, lambda: got[-1] is None and len(got) == 5)


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class ComposeScreenTest(Base):
    async def test_the_editor(self):
        from textual.widgets import Input, Select, TextArea

        from fedtail.frontends.tui.screens import AskScreen, ComposeScreen, MenuScreen
        core, w = self.make()
        w.add(status("001", BOB, minute=1, text="bob's post", vis="public"), home=True)
        mine = w.add(status("002", ME, minute=2, text="my post", vis="public"), home=True)
        app = self.app_of(core)
        errors = []
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            app.show_error = errors.append
            bobs, my = app.core.by_id("001"), app.core.by_id("002")

            async def open_(screen):
                results = []
                app.push_screen(screen, results.append)
                await self.wait(pilot, lambda: app.screen is screen, what="the editor")
                return results

            def title(s):
                return str(s.query_one("#c-title").render())

            # a reply with a quote: the mentions first, then the quoted text
            s = ComposeScreen(reply_to=bobs, text="> bob's post")
            await open_(s)
            self.assertIn(i18n._("compose_reply"), title(s))
            text = s.query_one("#c-text", TextArea).text
            self.assertTrue(text.startswith("@bob"))
            self.assertTrue(text.endswith("> bob's post"))
            s.query_one("#c-text", TextArea).text = ""
            await pilot.press("escape")  # nothing written: no draft
            await self.wait(pilot, lambda: app.screen is not s)

            # a quote, an invitation
            s = ComposeScreen(quote=bobs)
            await open_(s)
            self.assertIn(i18n._("compose_quote"), title(s))
            app.pop_screen()
            s = ComposeScreen(reply_to=bobs, invite=True)
            await open_(s)
            self.assertIn(i18n._("compose_invite"), title(s))
            app.pop_screen()

            # an edit: the text as given, who sees it, the warning
            s = ComposeScreen(edit=my, text="my post", warning="cw", visibility="private")
            results = await open_(s)
            self.assertIn(i18n._("compose_edit"), title(s))
            self.assertEqual(s.query_one("#c-cw", Input).value, "cw")
            self.assertEqual(s.query_one("#c-vis", Select).value, "followers")
            s.query_one("#c-text", TextArea).text = "my post, fixed"
            await pilot.press("ctrl+s")
            await self.wait(pilot, lambda: results == [True])
            self.assertIn("fixed", w.statuses[mine["id"]]["content"])
            self.assertIn(i18n._("edited_msg"), self.notes)

            # a new post with a language and a warning; a failed send says why
            s = ComposeScreen(warning="careful", visibility="direct", language="ka")
            results = await open_(s)
            self.assertEqual(s.query_one("#c-lang", Input).value, "ka")
            s.query_one("#c-text", TextArea).text = "first"
            with mock.patch.object(type(app.core), "post",
                                   return_value=done(error=OSError("down"))):
                s.action_send()
                await self.wait(pilot, lambda: errors)
            self.assertFalse(s.sending)
            s.sending = True
            s.action_send()  # one at a time
            s.sending = False
            s.query_one("#c-text", TextArea).text = "  "
            s.action_send()  # nothing to send
            self.assertEqual(results, [])

            # Ctrl+O: pictures, sensitive, a poll, later
            pic = Path(self.tmp) / "cat.png"
            pic.write_bytes(b"\x89PNG\r\n")

            async def extras(pick):
                s.action_extras()
                await self.wait(pilot, lambda: isinstance(app.screen, MenuScreen))
                menu = app.screen
                value = next(v for label, v in (x for x in menu.items if x != "-")
                             if pick(label, v))
                menu.dismiss(value)
                await pilot.pause(0.1)

            await extras(lambda _l, v: v == "attach")
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            app.screen.dismiss(str(pic))
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen) and
                            app.screen.allow_empty)
            app.screen.dismiss("a cat")
            await self.wait(pilot, lambda: s.media == [(str(pic), "a cat")])
            await extras(lambda _l, v: v == "sensitive")
            self.assertTrue(s.sensitive)
            extras_text = str(s.query_one("#c-extras").render())
            self.assertIn("cat.png", extras_text)
            await extras(lambda _l, v: v == "attach")  # a file that isn't there
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            app.screen.dismiss("/no/such/file.png")
            await self.wait(pilot, lambda: errors[-1] == i18n._("save_failed",
                                                                err="/no/such/file.png"))
            await extras(lambda _l, v: v == "attach")
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            app.screen.dismiss(None)  # never mind
            await pilot.pause(0.1)
            s.media.append(("/tmp/nothing.png", ""))
            s.show_extras()
            self.assertIn(i18n._("no_alt"), str(s.query_one("#c-extras").render()))
            await extras(lambda _l, v: isinstance(v, tuple) and v[1] == 1)
            await extras(lambda _l, v: isinstance(v, tuple))
            self.assertEqual(s.media, [])
            await extras(lambda _l, v: v == "poll")
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            app.screen.dismiss("yes | no; maybe")
            await self.wait(pilot, lambda: s.poll is not None)
            self.assertEqual(s.poll["options"], ["yes", "no", "maybe"])
            self.assertIn("📊", str(s.query_one("#c-extras").render()))
            await extras(lambda _l, v: v == "poll")  # again: away with it
            self.assertIsNone(s.poll)
            await extras(lambda _l, v: v == "poll")
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            app.screen.dismiss("only one")
            await self.wait(pilot, lambda: errors[-1] == i18n._("tui_poll_options"))
            s._polled("")
            await extras(lambda _l, v: v == "when")
            await self.wait(pilot, lambda: isinstance(app.screen, AskScreen))
            app.screen.dismiss("not a time")
            await self.wait(pilot, lambda: errors[-1] == i18n._("tui_when"))
            s._scheduled("")
            s._scheduled("2099-10-23 09:30")
            self.assertEqual(s.when, "2099-10-23 09:30")
            self.assertIn("2099-10-23 09:30", str(s.query_one("#c-extras").render()))
            await extras(lambda _l, v: v == "when")  # again: now
            self.assertEqual(s.when, "")
            s.poll = {"options": ["a", "b"], "expires_in": 3600, "multiple": True}
            s.show_extras()
            self.assertIn(i18n._("poll_several"), str(s.query_one("#c-extras").render()))
            s.poll = None
            # away with a text: the draft kept, and it's there next time
            s.query_one("#c-text", TextArea).text = "unfinished"
            await pilot.press("escape")
            await self.wait(pilot, lambda: results == [False])
            self.assertIn(i18n._("draft_saved"), self.notes)
            s = ComposeScreen(warning="careful", visibility="direct", language="ka")
            results = await open_(s)
            self.assertEqual(s.query_one("#c-text", TextArea).text, "unfinished")
            s.query_one("#c-text", TextArea).text = ""
            s.query_one("#c-cw", Input).value = ""  # a warning alone is still kept
            await pilot.press("escape")  # emptied: the draft goes
            await self.wait(pilot, lambda: results == [False])
            self.assertIsNone(app.core.get_draft(s.key))

    async def test_from_another_account(self):
        from textual.widgets import Select, TextArea

        from fedtail.frontends.tui.screens import ComposeScreen
        core, w = self.make()
        app = self.app_of(core)
        async with app.run_test(size=(120, 40)) as pilot:
            await self.started(pilot, app)
            sent = []
            view = app.core
            with mock.patch.object(type(view), "post_accounts", create=True,
                                   return_value=([("", "@mira@example.test"),
                                                  ("work", "@w@work.example")], "work")), \
                    mock.patch.object(type(view), "post", lambda self, *a, **kw: (
                        sent.append(kw.get("account")), done(None))[1]):
                s = ComposeScreen()
                app.push_screen(s)
                await self.wait(pilot, lambda: app.screen is s)
                self.assertEqual(s.query_one("#c-from", Select).value, "work")
                self.assertEqual(s.query_one("#c-from", Select).tooltip,
                                 i18n._("post_from_tip"))
                s.query_one("#c-text", TextArea).text = "from work"
                s.action_send()
                await self.wait(pilot, lambda: sent == ["work"])


if __name__ == "__main__":
    unittest.main()
