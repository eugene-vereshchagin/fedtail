"""Drive the GTK window against the fake API. Skipped without PyGObject + GTK 4 or
without a display (CI runs it under xvfb-run)."""

import os
import tempfile
import time
import unittest
from pathlib import Path

try:
    from fedtail.frontends.gtk.gi_setup import GLib, Gtk
    HAVE_GTK = Gtk.init_check() if hasattr(Gtk, "init_check") else True
    from gi.repository import Gdk
    HAVE_GTK = HAVE_GTK and Gdk.Display.get_default() is not None
except ImportError:
    HAVE_GTK = False

from fedtail import i18n  # noqa: E402
from fedtail.core import auth, config, paths  # noqa: E402
from fedtail.core.app import Core  # noqa: E402

from . import fakes  # noqa: E402
from .fakes import BOB, ME, NEWS, FakeApi, status  # noqa: E402


def _done(value):
    """A future already done (a fake core call)."""
    from concurrent.futures import Future
    f = Future()
    f.set_result(value)
    return f


def pump(until=None, timeout=3.0):
    """Run the main loop until until() is true (or a while, when None)."""
    ctx = GLib.MainContext.default()
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        while ctx.pending():
            ctx.iteration(False)
        if until is not None and until():
            return True
        time.sleep(0.01)
    return until is None


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class _GtkBase(unittest.TestCase):
    UI = {}  # more of [ui] for a test class of its own (the split layout)

    def setUp(self):
        from fedtail.core.view import View
        from fedtail.frontends.gtk import theme as themes
        from fedtail.frontends.gtk.bridge import Bridge
        from fedtail.frontends.gtk.window import MainWindow
        i18n.setup("ru")
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        tmp = Path(self._tmp.name)
        os.environ["XDG_CONFIG_HOME"] = str(tmp / "xdg")
        FakeApi.world = w = fakes.World()
        mine = w.add(status("010", ME, minute=10, text="мой пост"), home=True)
        w.add(status("011", BOB, minute=11, text="<p>привет <b>жирно</b> &amp; "
                                                  "<a href=\"https://e.test/\">ссылка</a></p>"),
              home=True)
        w.add(status("012", NEWS, minute=12, text="новости"), home=True)
        reply = status("013", BOB, mine["id"], "ME", minute=13, text="коммент")
        reply["spoiler_text"] = "осторожно"
        w.add(reply, home=True, mention=True)
        self.world = w
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False},
                                  "ui": {"start_lane": "home", "arts_mode": False,
                                         "frontend": "gtk", "adwaita": "off", **self.UI}})
        p = paths.resolve("t", config=str(tmp / "c.toml"), data=str(tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        self.core = Core(cfg, p, api_class=FakeApi)
        self.core._origin_json = lambda url: None
        self.view = View(self.core)
        self.bridge = Bridge(self.view)
        self.errors = []
        self.theme = themes.apply(cfg)
        self.win = MainWindow(None, self.core, self.view, self.bridge, self.theme)
        self.bridge.on_error = self.errors.append  # the window's own goes: catch them
        self.win.present()
        self.win.start()
        self.assertTrue(pump(lambda: self.win.lane_rows, 5), "never connected")
        self.core.poll_once()
        pump(lambda: self._lane("home") and self._lane("home").rows, 5)

    def tearDown(self):
        self.assertEqual(self.errors, [], "a handler failed")
        self.win.quitting = True
        self.win.close()  # as a user would: the lanes stop their queued work
        self.win.destroy()
        pump(timeout=0.1)
        self.core.shutdown()
        self._tmp.cleanup()

    def _lane(self, name):
        return self.win.lane_views.get(name)


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkSmokeTest(_GtkBase):

    def test_lanes_and_cards(self):
        self.assertIn("home", self.win.lane_rows)
        lane = self._lane("home")
        self.assertGreaterEqual(len(lane.rows), 3)
        texts = [c.post.text for c in lane.rows.values()]
        self.assertTrue(any("привет" in t for t in texts))
        # the reply's warning hides its text in an expander
        reply = next(c for c in lane.rows.values() if c.post.warning)
        exp = next(w for w in _walk(reply) if isinstance(w, Gtk.Expander))
        from fedtail.core import config as config_mod
        # open or not as ui.expand_cw / ui.arts_mode say, the pictures with it
        self.assertEqual(exp.get_expanded(), config_mod.expand_cw(self.core.cfg))

    def test_seen_posts_get_read(self):
        """The window is active and every post fits: all are seen, so all are read."""
        lane = self._lane("home")
        self.assertTrue(pump(lambda: not any(c.unread for c in lane.rows.values()), 5))
        self.assertFalse(self.view.unread([c.entry for c in lane.rows.values()]))

    def test_all_read_clears_badge(self):
        lane = self._lane("home")
        lane.mark_all_read()
        pump(timeout=0.3)
        self.assertFalse(any(c.unread for c in lane.rows.values()))
        self.win.update_badges()
        self.assertFalse(self.win.lane_rows["home"].badge.get_visible())

    def test_main_menu_and_a_narrow_window(self):
        for name in ("write", "refresh", "profile", "config", "logs", "about", "quit"):
            self.assertIsNotNone(self.win.lookup_action(name), name)
        lane = self._lane("home")
        self.win.set_default_size(560, 500)  # ui.max_width is wider: the column narrows
        self.assertTrue(pump(lambda: 0 < self.win.get_width() <= 600, 3),
                        f"the window stays {self.win.get_width()} px wide")
        pump(timeout=0.3)
        self.assertLessEqual(lane.list.get_width(), lane.get_width())
        self.assertLessEqual(lane.get_width(), self.win.get_width())

    def test_the_menu_and_what_it_opens(self):
        """≡ as Qt's: its items made, and each window or tab they open comes up
        without an error (on the fake server)."""
        menu = self.win.menu
        model = menu.model()
        labels = []

        def walk(m):
            for i in range(m.get_n_items()):
                label = m.get_item_attribute_value(i, "label", None)
                if label is not None:
                    labels.append(label.get_string())
                for link in ("section", "submenu"):
                    sub = m.get_item_link(i, link)
                    if sub is not None:
                        walk(sub)
        walk(model)
        for key in ("tender_menu", "accounts", "try_theme", "debug_menu", "help_title",
                    "about", "open_config", "silence_muted"):
            self.assertTrue(any(i18n._(key) in x for x in labels), key)
        errors = []
        self.win.error = lambda e: errors.append(str(e))
        self.win.bridge.on_error = errors.append
        for name in ("filters", "muted", "scheduled", "server", "federation", "help",
                     "test_notify", "stacks", "census", "trim", "whats_this"):
            self.win.activate_action("win." + name, None)
            pump(timeout=0.3)
        self.assertTrue(self.win.hints_on)
        self.win.activate_action("win.whats_this", None)
        self.assertFalse(self.win.hints_on)
        self.win.open_search("bob")
        pump(lambda: "search" in self.win.extra_tabs, 3)
        self.win.open_tag("linux")
        pump(timeout=0.3)
        self.assertIn("tag:linux", self.win.extra_tabs)
        self.assertEqual(errors, [])
        for w in list(Gtk.Window.list_toplevels()):
            if w is not self.win:
                w.close()

    def test_columns_and_full_width(self):
        lane = self._lane("home")
        self.win.columns_btn.set_active(True)
        pump(timeout=0.3)
        self.assertIsNotNone(self.win.columns)
        self.assertIn("home", self.win.columns.frames)
        self.assertIs(lane.get_parent(), self.win.columns.frames["home"])
        self.assertTrue(self.win.lane_on_screen("home"))
        self.win.columns_btn.set_active(False)
        pump(timeout=0.3)
        self.assertIsNone(self.win.columns)
        self.assertIs(lane.get_parent(), self.win.stack)
        self.win.wide_btn.set_active(not self.win.wide_btn.get_active())
        pump(timeout=0.2)
        self.assertEqual(bool(self.core.cfg["ui"]["max_width"]),
                         not self.win.wide_btn.get_active())

    def test_a_section_folds(self):
        from fedtail.frontends.gtk.window import SectionRow
        heads = [r for r in _walk(self.win.sidebar) if isinstance(r, SectionRow)]
        if not heads:
            self.skipTest("no sections in this sidebar")
        head = heads[0]
        self.win._row_activated(self.win.sidebar, head)
        self.assertTrue(all(not self.win.lane_rows[n].get_visible() for n in head.names))
        self.win._row_activated(self.win.sidebar, head)
        self.assertTrue(all(self.win.lane_rows[n].get_visible() for n in head.names))

    def test_filters_and_the_funnel(self):
        """The header's choices (common/lane.py): posts only, the media funnel."""
        lane = self._lane("home")
        pump(lambda: lane.positioned and not lane._pending(), 5)
        everything = len(lane.rows)
        lane._filter_buttons["posts"].set_active(True)  # no replies
        pump(lambda: lane.positioned and not lane._pending(), 5)
        self.assertLess(len(lane.rows), everything)
        self.assertFalse(any(c.post.reply_to for c in lane.rows.values()))
        lane._filter_buttons["all"].set_active(True)
        pump(lambda: len(lane.rows) == everything, 5)
        lane.media_checks["text"].set_active(False)  # posts with pictures only: none here
        pump(lambda: not lane.rows, 5)
        self.assertFalse(lane.rows)
        self.assertTrue(lane.info.get_text())
        lane.media_checks["text"].set_active(True)
        pump(lambda: len(lane.rows) == everything, 5)
        self.assertEqual(len(lane.rows), everything)

    def test_new_post_joins_at_the_bottom(self):
        lane = self._lane("home")
        # the lane done building first (in a busy run it may still be): what's on screen
        pump(lambda: lane.positioned and not lane._pending() and len(lane.order) ==
             len(lane.keys), 5)
        before = list(lane.order)
        self.world.add(status("020", BOB, minute=20, text="новое"), home=True)
        self.core.poll_once()
        pump(lambda: len(lane.order) == len(before) + 1, 5)
        self.assertEqual(lane.order[:len(before)], before)
        self.assertEqual(lane.rows[lane.order[-1]].post.id, "020")

    def test_thread_opens_in_a_tab(self):
        lane = self._lane("home")
        reply = next(c for c in lane.rows.values() if c.post.id == "013")
        self.win.open_thread(reply.post)
        self.assertTrue(pump(lambda: self.win.tabs.get_n_pages() == 2 and
                             any(True for _ in _cards(self.win)), 5))
        self.win.close_thread("013")
        self.assertEqual(self.win.tabs.get_n_pages(), 1)

    def test_links(self):
        opened = []
        self.win.open_url = opened.append
        self.win.on_link("https://e.test/x")
        self.assertEqual(opened, ["https://e.test/x"])
        self.win.on_link("fedtail:account/B")  # a profile: a tab with the posts
        self.assertTrue(pump(lambda: "B" in self.win.accounts and
                             any(isinstance(w, Gtk.Button) and
                                 w.get_label() in (i18n._("follow"), i18n._("unfollow"))
                                 for w in _walk(self.win.accounts["B"])), 5))
        self.win._close_current_tab()
        self.assertNotIn("B", self.win.accounts)
        self.win.on_link("fedtail:thread/011")
        self.assertTrue(pump(lambda: "011" in self.win.threads, 5))
        self.win.on_link("fedtail:copyhandle/bob%40social.example")
        self.assertIn("@bob@social.example", self.win.status_line.get_text())

    def test_post_text_is_one_layout_with_links(self):
        from fedtail.frontends.gtk.textblock import TextBlock, links_of
        shown, links = links_of('при&amp;вет <a href="https://e.test/?a=1&amp;b=2">ссылка</a>!',
                                "#123456")
        self.assertNotIn("<a", shown)
        self.assertEqual(len(links), 1)
        start, end, url = links[0]
        self.assertEqual(url, "https://e.test/?a=1&b=2")
        text = "при&вет ссылка!".encode()
        self.assertEqual(text[start:end].decode(), "ссылка")
        lane = self._lane("home")
        card = next(c for c in lane.rows.values() if c.post.id == "011")
        body = next(w for w in _walk(card) if isinstance(w, TextBlock))
        self.assertIn("привет", body.text())
        pump(lambda: body.get_width() > 0, 3)
        followed = []
        body.on_link = followed.append
        start, end, url = body.links[0]
        idx = (start + end) // 2
        rect = body.layout.index_to_pos(idx)
        from fedtail.frontends.gtk.gi_setup import Pango
        x, y = rect.x / Pango.SCALE + 1, rect.y / Pango.SCALE + 1
        self.assertEqual(body.link_at(x, y), "https://e.test/")
        self.assertIsNone(body.link_at(0, 0))  # "привет": no link

    def test_like_updates_the_card(self):
        lane = self._lane("home")
        card = next(c for c in lane.rows.values() if c.post.id == "011")
        # ☆ by the word, or the desktop icon theme's star (the system theme: "desktop")
        self.assertTrue("☆" in "".join(b.get_label() or "" for b in _walk(card.actions)
                                       if isinstance(b, Gtk.Button))
                        or any(isinstance(w, Gtk.Image) for w in _walk(card.actions)))
        self.win.on_link("fedtail:fav/011")
        self.assertTrue(pump(lambda: card.post.mine.liked, 5))
        self.assertTrue(any("ft-active" in b.get_css_classes() for b in _walk(card.actions)
                            if isinstance(b, Gtk.Button)))

    def test_post_menu_from_the_shared_list(self):
        lane = self._lane("home")
        card = next(c for c in lane.rows.values() if c.post.id == "011")
        card._fill_menu(card.more)
        labels = [b.get_label() for b in _walk(card.more.get_popover())
                  if isinstance(b, Gtk.Button)]
        self.assertIn(i18n._("open_browser"), labels)
        self.assertIn(i18n._("block_acct", acct="bob@social.example"), labels)
        self.assertNotIn(i18n._("delete"), labels)  # not mine

    def test_delete_asks_first(self):
        asked = []
        self.win.confirm = lambda title, text, then: asked.append(then)
        self.win.on_link("fedtail:delete/010")
        self.assertEqual(len(asked), 1)
        self.assertNotIn("010", self.world.deleted if hasattr(self.world, "deleted") else [])
        asked[0]()  # yes
        self.assertTrue(pump(lambda: self.view.by_id("010") is None or
                             getattr(self.world, "deleted", None), 5))

    def test_what_the_post_menu_opens(self):
        """The ⋯ items that open a window or a tab — a post's versions, a complaint,
        who liked it, the quotes of my post — and "read up to here": as in Qt, no
        "not here yet"."""
        said = []
        self.win.status = lambda text, *a: said.append(text)
        before = set(Gtk.Window.list_toplevels())
        self.win.on_link("fedtail:history/011")
        self.win.on_link("fedtail:report/011")
        pump(timeout=0.5)
        new = [w for w in Gtk.Window.list_toplevels() if w not in before]
        self.assertGreaterEqual(len(new), 2)
        self.win.on_link("fedtail:favourited_by/011")
        self.win.on_link("fedtail:quotes/010")
        pump(timeout=0.5)
        self.assertIn("favourited_by:011", self.win.extra_tabs)
        self.assertIn("quotes:010", self.win.extra_tabs)
        self.win.on_link("fedtail:readupto/012")
        pump(timeout=0.3)
        self.assertNotIn(i18n._("gtk_not_yet"), said)
        for w in new:
            w.close()

    def test_vote_in_a_poll(self):
        """A poll not voted in: options and Vote, as in Qt; voted — the results."""
        st = status("020", BOB, minute=20, text="опрос", vis="public")
        st["poll"] = {"id": "P2", "expired": False, "multiple": False, "voted": False,
                      "own_votes": [], "votes_count": 3, "voters_count": 3,
                      "expires_at": "2099-01-01T12:00:00Z",
                      "options": [{"title": "да", "votes_count": 2},
                                  {"title": "нет", "votes_count": 1}]}
        self.world.add(st, home=True)
        self.core.poll_once()
        lane = self._lane("home")
        self.assertTrue(pump(lambda: any(c.post.id == "020" for c in lane.rows.values()), 5))
        card = next(c for c in lane.rows.values() if c.post.id == "020")
        checks = [w for w in _walk(card) if isinstance(w, Gtk.CheckButton)]
        vote = next(w for w in _walk(card) if isinstance(w, Gtk.Button) and
                    w.get_label() == i18n._("poll_vote"))
        self.assertEqual([c.get_label() for c in checks], ["да", "нет"])
        self.assertFalse(vote.get_sensitive())
        checks[1].set_active(True)
        self.assertTrue(vote.get_sensitive())
        vote.emit("clicked")
        self.assertTrue(pump(lambda: not any(isinstance(w, Gtk.CheckButton)
                                             for w in _walk(card)), 5))

    def test_profile_buttons_as_in_qt(self):
        """A profile's buttons come from common/profile.py (as Qt offers them) and do
        their thing: mute, a note, whom they follow."""
        from fedtail.frontends.common import profile as prof
        self.win.open_account("B")
        page = self.win.accounts.get("B")
        self.assertIsNotNone(page)

        def labels():
            return [b.get_label() for b in _walk(page) if isinstance(b, Gtk.Button)]
        self.assertTrue(pump(lambda: i18n._("mute") in labels(), 5))
        for key in ("block", "note_edit", "copy_handle"):
            self.assertIn(i18n._(key), labels())
        mute = next(b for b in _walk(page) if isinstance(b, Gtk.Button)
                    and b.get_label() == i18n._("mute"))
        mute.emit("clicked")
        self.assertTrue(pump(lambda: i18n._("unmute") in labels(), 5))
        asked = []
        self.win.ask_text = lambda title, q, then, text="", allow_empty=False: \
            asked.append(then)
        note = next(b for b in _walk(page) if isinstance(b, Gtk.Button)
                    and b.get_label() == i18n._("note_edit"))
        note.emit("clicked")
        self.assertEqual(len(asked), 1)
        self.assertEqual(prof.parse_langs("ru; en  de"), ["ru", "en", "de"])

    def test_translate_and_read_whole(self):
        """⋯ → Translate puts the server's translation in the text's place (the original
        a click away); 📄 the whole text opens a page — as in Qt."""
        from fedtail.model import Translation
        lane = self._lane("home")
        card = next(c for c in lane.rows.values() if c.post.id == "011")
        self.view.translate = lambda p: _done(Translation("<p>hello</p>", "ru", "test"))
        card.translate()
        self.assertTrue(pump(lambda: getattr(card, "showing_translation", False), 3))
        card.translate()
        self.assertFalse(card.showing_translation)
        self.view.long_form = lambda st: _done({"name": "Статья", "start": "", "end": "",
                                                "location": "", "summary": "",
                                                "content": "<p>всё</p>",
                                                "url": "https://e.test/a"})
        before = set(Gtk.Window.list_toplevels())
        self.win.read_whole(card.post)
        pump(timeout=0.4)
        new = [w for w in Gtk.Window.list_toplevels() if w not in before]
        self.assertEqual([w.get_title() for w in new], ["Статья"])
        for w in new:
            w.close()

    def test_add_to_list(self):
        """"Add to list" from a post's ⋯ and a profile, as in Qt: someone not followed —
        the ticks dead under "follow first", Follow right there."""
        lane = self._lane("home")
        card = next(c for c in lane.rows.values() if c.post.id == "011")
        card._fill_menu(card.more)
        labels = [b.get_label() for b in _walk(card.more.get_popover())
                  if isinstance(b, Gtk.Button)]
        self.assertIn(i18n._("add_to_list"), labels)
        pop = self.win.lists_popover(card.post.author, card.more)
        self.assertTrue(pump(lambda: any(
            isinstance(w, Gtk.Label) and w.get_text() == i18n._("list_follow_first")
            for w in _walk(pop)), 3))
        pop.popdown()

    def test_a_lists_menu_in_the_sidebar(self):
        """A right click on a list: who's in it, up/down, rename, exclusive, delete —
        as in Qt; on another lane: a new list."""
        from fedtail.frontends.gtk import lists
        row = next((r for n, r in self.win.lane_rows.items() if not n.startswith("list:")))
        pop = lists.lane_menu(self.win, row)
        if self.win.cfg["lists"]["enabled"]:
            labels = [b.get_label() for b in _walk(pop) if isinstance(b, Gtk.Button)]
            self.assertIn(i18n._("list_new"), labels)
            pop.popdown()
        made = []
        self.win.call(self.view.create_list("Друзья"), made.append)
        self.assertTrue(pump(lambda: made and f"list:{made[0].id}" in self.win.lane_rows, 5))
        row = self.win.lane_rows[f"list:{made[0].id}"]
        pop = lists.lane_menu(self.win, row)
        labels = [b.get_label() for b in _walk(pop) if isinstance(b, Gtk.Button)]
        for key in ("list_people", "list_rename", "list_delete"):
            self.assertIn(i18n._(key), labels)
        pop.popdown()
        page = lists.open_list_people(self.win, made[0])
        self.assertIsNotNone(page)

    def test_announcements(self):
        """The server's announcements as Qt's strip: shown, "Got it" sends it away."""
        from fedtail.model import Announcement
        bar = self.win.announce_bar
        bar.got([Announcement(id="A1", html="<p>Обновление сервера в полночь</p>")])
        self.assertTrue(bar.get_visible())
        self.assertIn("Обновление", bar.body.get_text())
        bar.dismiss()
        self.assertFalse(bar.get_visible())

    def test_about_says_what_qt_says(self):
        before = set(Gtk.Window.list_toplevels())
        self.win.about()
        pump(timeout=0.3)
        new = [w for w in Gtk.Window.list_toplevels() if w not in before]
        self.assertEqual(len(new), 1)
        self.assertIn(i18n._("made_by_long"), new[0].get_comments())
        new[0].close()

    def test_edit_my_profile(self):
        """My profile's Edit as in Qt: loaded, only what changed goes to the server."""
        ed = self.win.edit_profile()
        self.assertTrue(pump(lambda: ed.loaded is not None, 5))
        self.assertEqual(ed.changes(), {})
        ed.name.set_text("Новое имя")
        self.assertEqual(ed.changes(), {"name": "Новое имя"})
        ed.dlg.close()

    def test_find_in_the_lane(self):
        """Ctrl+F as in Qt: the words, "1 of 1", the card brought and marked."""
        bar = self.win.find_bar
        bar.open()
        self.assertTrue(bar.get_visible())
        bar.entry.set_text("коммент")
        bar.search(jump=True)
        lv = self.win.current_lane_view()
        self.assertIsNotNone(lv, "no lane in front")
        self.assertEqual(len(bar.hits), 1)
        self.assertTrue(pump(lambda: bar._marked is not None, 3))
        self.assertTrue(bar._marked.has_css_class("ft-found"))
        self.assertEqual(bar.count.get_text(), i18n._("find_count", i=1, n=1))
        bar.entry.set_text("нет такого слова")
        bar.search(jump=True)
        self.assertEqual(bar.count.get_text(), i18n._("find_none"))
        bar.close_bar()
        self.assertFalse(bar.get_visible())

    def test_reply_in_the_editor(self):
        from fedtail.frontends.gtk.compose import ComposeWindow
        post = self.view.by_id("011")
        dlg = self.win.compose(reply_to=post)
        self.assertIsInstance(dlg, ComposeWindow)
        self.assertTrue(dlg._text().startswith("@bob@social.example"))
        dlg.buffer.insert_at_cursor("ответ из GTK")
        before = len(self.world.posted)
        dlg.send()
        self.assertTrue(pump(lambda: len(self.world.posted) > before, 5))
        text, _vis, reply_to, _md = self.world.posted[-1]
        self.assertEqual(reply_to, "011")
        self.assertTrue(text.endswith("ответ из GTK"))
        self.assertFalse(self.view.get_draft(dlg.key))
        # "you replied" under the post answered, at once (not at the next poll)
        card = next(c for c in self._lane("home").rows.values() if c.post.id == "011")
        self.assertTrue(pump(lambda: bool(card.mine_ids), 5))

    def test_the_editor_is_a_panel_in_the_window(self):
        """As Qt's: over the window's middle, following its size; language, Later,
        Preview, Discard; one editor at a time."""
        dlg = self.win.compose()
        self.assertIs(dlg.get_parent(), self.win.overlay)
        pump(lambda: dlg.get_width() > 0, 3)
        self.assertLessEqual(dlg.get_width(), self.win.overlay.get_width())
        self.assertEqual(dlg.language(), self.core.cfg["post"].get("language") or "")
        dlg._set_language("ka")
        self.assertEqual(dlg.language(), "ka")
        dlg.buffer.set_text("**жирно** и _нет_")
        prev = dlg.preview()
        self.assertTrue(prev.get_visible())
        prev.close()
        later = dlg.ask_schedule()
        later.close()
        other = self.win.compose()  # the first one goes, its text kept — and back
        self.assertTrue(dlg.closed)
        self.assertIsNone(dlg.get_parent())
        self.assertEqual(other._text(), "**жирно** и _нет_")
        asked = []
        self.win.confirm = lambda _t, _x, then: asked.append(then)
        other.discard()
        asked[0]()
        self.assertTrue(other.closed)
        self.assertFalse(self.view.get_draft(other.key))

    def test_editor_keeps_a_draft(self):
        dlg = self.win.compose()
        dlg.buffer.set_text("недописанное")
        dlg.close()
        pump(timeout=0.2)
        self.assertEqual(self.view.get_draft(dlg.key)["text"], "недописанное")
        again = self.win.compose()
        self.assertEqual(again._text(), "недописанное")
        again.buffer.set_text("")
        again.close()
        pump(timeout=0.2)
        self.assertFalse(self.view.get_draft(again.key))

    def test_editor_pictures_and_poll(self):
        import struct
        import zlib
        png = Path(self._tmp.name) / "p.png"
        raw = b"\x00" + b"\x10\x20\x30" * 4

        def chunk(k, d):
            return struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))
        png.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(
            ">IIBBBBB", 4, 1, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) +
            chunk(b"IEND", b""))
        dlg = self.win.compose()
        dlg._add_media(str(png))
        self.assertFalse(dlg.poll_btn.get_sensitive())  # pictures or a poll, not both
        self.assertTrue(dlg.sensitive_btn.get_visible())
        asked = []
        dlg._ask_alt = lambda n, *_a: asked.append(n)
        dlg.buffer.set_text("с картинкой")
        dlg.send()
        self.assertEqual(asked, [1])  # no description: asked first
        dlg._remove_media(dlg.media[0], dlg.media_box.get_first_child())
        self.assertTrue(dlg.poll_btn.get_sensitive())
        dlg.poll_btn.set_active(True)
        self.assertFalse(dlg.attach_btn.get_sensitive())
        dlg.poll_options[0].set_text("да")
        self.assertIsNone(dlg.poll_data())  # one option is no poll
        dlg.poll_options[1].set_text("нет")
        self.assertEqual(dlg.poll_data()["options"], ["да", "нет"])
        dlg.close()
        pump(timeout=0.2)
        back = self.win.compose()
        self.assertTrue(back.poll_btn.get_active())  # the draft kept the poll
        self.assertEqual(back.poll_options[1].get_text(), "нет")
        back.close()

    def test_notifications(self):
        shown = []
        n = self.win.notifier
        n.show = shown.append
        n.cfg = dict(n.cfg, enabled=True, when_focused=True)
        n.notify([("mentions", self.core.store.get_status("013"))])
        self.assertEqual(len(shown), 1)
        self.assertEqual(shown[0].lane, "mentions")
        n.opened("thread:013")  # a click: the thread
        self.assertTrue(pump(lambda: "013" in self.win.threads, 5))

    def test_activity_lane(self):
        mine = self.core.store.get_status("010")
        self.world.act("x1", "favourite", BOB, mine, minute=1)
        self.world.act("x2", "favourite", NEWS, mine, minute=2)
        self.world.act("x3", "follow", NEWS, minute=3)
        self.core.poll_once()  # the first fetch: history
        self.world.act("x4", "reblog", BOB, mine, minute=4)
        self.core.poll_once()
        pump(timeout=0.3)
        self.assertIn("activity", self.win.lane_rows)
        self.win.sidebar.select_row(self.win.lane_rows["activity"])
        lane = self.win.lane_views["activity"]
        self.assertTrue(pump(lambda: lane.positioned, 5))
        rows = [w for w in _walk(lane.list) if hasattr(w, "newest_sort")]
        self.assertEqual(len(rows), 3)  # the two likes of one post are one row
        # on screen in an active window: seen
        self.assertTrue(pump(lambda: self.core.activity_unread() == 0, 5))
        # Clear: asked first, then gone here and on the server
        self.assertTrue(lane.clear_btn.get_visible())
        asked = []
        self.win.confirm = lambda _t, _x, then: asked.append(then)
        lane.clear_btn.emit("clicked")
        self.assertEqual(len(asked), 1)
        asked[0]()
        self.assertTrue(pump(lambda: not self.world.activity and not
                             [w for w in _walk(lane.list) if hasattr(w, "newest_sort")], 5))

    def test_command_line(self):
        bar = self.win.cmdline
        self.assertIsNotNone(bar)
        alias = self.view.short_ids([self.view.by_id("011")])["011"]
        bar.entry.set_text(f"#{alias} согласен")
        self.assertIn(alias, bar.hint.get_text())  # says what Enter will do
        before = len(self.world.posted)
        bar.run()
        self.assertTrue(pump(lambda: len(self.world.posted) > before, 5))
        self.assertEqual(self.world.posted[-1][2], "011")
        self.assertTrue(pump(lambda: bar.entry.get_text() == "", 2))
        self.win.on_link(f"fedtail:alias/{alias}")
        self.assertEqual(bar.entry.get_text(), f"#{alias} ")

    def test_a_pictures_menu_saves_it(self):
        from fedtail.model import Media
        card = next(iter(self._lane("home").rows.values()))
        m = Media(card.post.ref, "image", url="https://e.test/a.png")
        asked = []
        self.win.images.save = lambda url, where: (asked.append(url), _done("/x/a.png"))[1]
        pop = card._media_menu(card, m)
        buttons = [w for w in _walk(pop) if isinstance(w, Gtk.Button)]
        self.assertEqual([b.get_label() for b in buttons],
                         [i18n._("save_image"), i18n._("open_browser"), i18n._("copy_link")])
        buttons[0].emit("clicked")
        self.assertTrue(pump(lambda: asked, 2))
        self.assertEqual(asked, ["https://e.test/a.png"])

    def test_tag_tab_follows_and_features(self):
        from fedtail.frontends.gtk.people import TagRow
        page = self.win.open_tag("linux")

        def row():
            return next((w for w in _walk(page) if isinstance(w, TagRow)), None)
        self.assertTrue(pump(lambda: row() is not None, 3))
        r = row()
        self.assertEqual(r.follow.get_label(), i18n._("tag_follow"))
        r.follow.emit("clicked")
        self.assertTrue(pump(lambda: "linux" in self.world.followed_tags, 3))
        self.assertTrue(pump(lambda: r.follow.get_label() == i18n._("tag_unfollow"), 3))
        self.assertIsNotNone(r.feature)
        self.assertTrue(pump(lambda: r.feature.get_sensitive(), 3))
        r.feature.emit("clicked")
        self.assertTrue(pump(lambda: "linux" in self.world.my_tags, 3))
        self.assertTrue(pump(lambda: r.feature.get_label() == i18n._("tag_unfeature"), 3))


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkPanelsTest(_GtkBase):
    """What comes over the window: the pictures' viewer, the help; and the pictures in a
    card, the desktop notification, ≡ → Quit."""

    def _post_with_pictures(self, n):
        from fedtail.protocols.mastodon import adapter

        def offline(*_a, **_k):
            raise OSError("no network in the tests")
        self.win.images.http.get = offline
        raw = status("090", BOB, minute=30, text="картинки")
        raw["media_attachments"] = [
            {"id": f"m{i}", "type": "image", "url": f"https://e.test/{i}.png",
             "preview_url": f"https://e.test/{i}s.png", "description": f"картинка {i}",
             "meta": {"original": {"width": 800, "height": 400}}} for i in range(n)]
        return adapter.post(raw, "t")

    def test_pictures_keep_their_shape(self):
        from fedtail.frontends.gtk.card import Card
        one = Card(self.win.ctx, "090", self._post_with_pictures(1))
        grid = one.media_box
        cell = grid.get_child_at(0, 0)
        w, h = cell.get_size_request()
        # one alone: as tall as ui.image_height allows within the lane, its shape kept
        self.assertGreater(h, 300)
        self.assertEqual(w, 2 * h)
        four = Card(self.win.ctx, "091", self._post_with_pictures(4))
        self.assertIsNotNone(four.media_box.get_child_at(2, 0))  # three in a row
        self.assertIsNotNone(four.media_box.get_child_at(0, 1))
        self.assertEqual(four.media_box.get_child_at(0, 0).get_size_request()[1], 115)

    def test_viewer_over_the_window(self):
        from fedtail.frontends.gtk import viewer
        media = list(self._post_with_pictures(3).media)
        v = viewer.show(self.win, media, 1)
        self.assertIs(v.get_parent(), self.win.overlay)
        self.assertIn("2 / 3", v.caption.get_text())
        v.go(1)
        self.assertEqual(v.i, 2)
        v.go(1)
        self.assertEqual(v.i, 0)
        v._set_actual(True)
        self.assertTrue(v.actual)
        v.close()
        self.assertIsNone(v.get_parent())
        self.assertIsNone(self.win.viewer)
        self.win.cfg["ui"]["image_viewer"] = "browser"
        opened = []
        self.win.open_url = opened.append
        self.assertIsNone(viewer.show(self.win, media, 0))
        self.assertEqual(opened, ["https://e.test/0.png"])

    def test_help_is_a_panel_in_the_window(self):
        before = set(Gtk.Window.list_toplevels())
        panel = self.win.open_help()
        pump(timeout=0.3)
        self.assertIs(panel.get_parent(), self.win.overlay)
        self.assertEqual(set(Gtk.Window.list_toplevels()), before)  # no window of its own
        self.assertEqual(panel.current, "index")
        self.assertTrue(panel.blocks)
        from fedtail.frontends import helpdocs
        other = next(p.name for p in helpdocs.pages() if p.name != "index")
        panel.show_page(other)
        self.assertEqual(panel.current, other)
        panel.back()
        self.assertEqual(panel.current, "index")
        panel.search.set_text("тема")
        panel._filter("тема")
        self.assertTrue(panel.found.get_visible())
        panel.close()
        self.assertFalse(panel.get_visible())
        self.assertIs(self.win.open_help(), panel)  # the same one, back where it was
        self.assertTrue(panel.get_visible())

    def test_notification_goes_out(self):
        from fedtail.frontends import notifytext
        sent = []

        class App:
            def send_notification(self, _id, n):
                sent.append(n)
        n = self.win.notifier
        n.app, n.backend = App(), "gio"
        n.show(notifytext.Note("t", "b", "home"))
        self.assertEqual(len(sent), 1)

    def test_quit_quits(self):
        self.win.quit_app()
        pump(timeout=0.2)
        self.assertTrue(self.win.quitting)
        self.assertFalse(self.win.get_visible())


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkSplitTest(_GtkBase):
    """ui.layout = "split": the roster window, the lanes in tabs, the input line."""
    UI = {"layout": "split"}

    def test_roster_tabs_and_the_input_line(self):
        win = self.win
        self.assertIsNotNone(win.roster)
        self.assertTrue(win.roster.get_visible())
        self.assertFalse(win.stack.get_visible())
        pump(lambda: win.roster.rows, 5)
        self.assertIn("home", win.roster.rows)
        self.assertIn("home", win.lane_tabs)  # the start lane: a tab of its own
        lane = win.lane_tabs["home"]
        self.assertTrue(win.lane_on_screen("home"))
        win.roster.open("replies")
        pump(timeout=0.3)
        self.assertIn("replies", win.lane_tabs)
        self.assertTrue(win.lane_on_screen("replies"))
        win.close_lane_tab("replies")
        self.assertNotIn("replies", win.lane_tabs)
        # the input line: a new post over a lane; a reply when the card's button says so
        win.tabs.set_current_page(win.tabs.page_num(lane))
        pump(timeout=0.2)
        dock = win.dock
        self.assertIsNone(dock.target)
        post = self.view.by_id("011")
        win.compose(reply_to=post)  # the card's Reply: into the input line, not a window
        self.assertEqual(dock.target.id, "011")
        self.assertTrue(dock._text().startswith("@bob"))
        dock.buffer.insert_at_cursor("ответ снизу")
        before = len(self.world.posted)
        dock.send()
        self.assertTrue(pump(lambda: len(self.world.posted) > before, 5))
        self.assertEqual(self.world.posted[-1][2], "011")
        # a command goes to the command line, a post doesn't
        dock._set_text("#zz9 привет")
        self.assertIsNotNone(dock.command())
        dock._set_text("@bob привет")
        self.assertIsNone(dock.command())
        # a private talk: its tab, written to privately
        bob = post.author
        win.write_to(bob)
        pump(timeout=0.3)
        self.assertIn("talk:" + bob.id, win.extra_tabs)
        self.assertEqual(dock.visibility, "direct")
        # the author bar follows what's read
        win.tabs.set_current_page(win.tabs.page_num(lane))
        pump(timeout=0.3)
        win._follow_author(lane)
        if win.author_bar is not None:
            self.assertTrue(win.author_bar.who is None or win.author_bar.who.id)
        # another theme: the lanes' tabs drawn anew, in their places
        win.try_theme("psi")
        pump(timeout=0.3)
        self.assertIn("home", win.lane_tabs)
        self.assertIsNot(win.lane_tabs["home"], lane)
        self.assertTrue(win.lane_on_screen("home"))
        lane = win.lane_tabs["home"]
        # the tabs: in rows of chips, one a page (the lanes' stack none)
        rows = win.tab_rows
        self.assertIsNotNone(rows)
        rows.sync()
        self.assertEqual(set(rows.chips), set(rows.pages()))
        self.assertNotIn(win.stack, rows.chips)
        self.assertFalse(win.tabs.get_show_tabs())
        n = len(rows.chips)
        rows.close(win.extra_tabs["talk:" + bob.id])
        pump(timeout=0.3)
        self.assertEqual(len(rows.chips), n - 1)
        # the roster's look and folds
        win.roster.set_look("compact", True)
        win.roster.toggle("standard")
        win.roster.toggle("standard")
        # closing the messages window keeps the roster
        win.close()
        pump(timeout=0.2)
        self.assertFalse(win.get_visible())
        self.assertTrue(win.roster.get_visible())


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkPicturesTest(_GtkBase):
    """The theme's own set in the split layout: its pictures on the buttons, the
    messengers' too (psi: PNGs — drawn even where gdk-pixbuf reads no SVG)."""
    UI = {"layout": "split", "theme": "psi"}

    def test_theme_pictures_on_the_buttons(self):
        from fedtail.frontends.gtk import icons
        win = self.win
        self.assertEqual(icons.how(win.theme), "own")
        self.assertTrue(icons.wanted(win.theme))
        self.assertIsInstance(win.dock.send_btn.get_child(), Gtk.Box)  # picture + "Send"
        self.assertIsInstance(win.dock.cw_btn.get_child(), Gtk.Image)
        lane = win.lane_tabs["home"]
        card = next(iter(lane.rows.values()))
        pictures = [w for w in _walk(card.actions) if isinstance(w, Gtk.Image)]
        self.assertTrue(pictures)  # Reply, Favourite… with their pictures
        self.assertIsNotNone(icons.nobody(win.theme, 36))
        win.try_theme("terminal")  # no pictures: the words come back
        self.assertEqual(icons.how(win.theme), "words")
        self.assertEqual(win.dock.send_btn.get_label(), i18n._("dock_send"))
        self.assertIsNone(icons.image("menu", win.theme))
        win.try_theme("system")  # the desktop's, by freedesktop names
        self.assertEqual(icons.how(win.theme), "desktop")


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkAgentTest(_GtkBase):
    """The split layout in a Mail.ru Agent theme: a face column beside the posts."""
    UI = {"layout": "split", "theme": "mra"}

    def test_agent_face(self):
        win = self.win
        self.assertIsNone(win.author_bar)
        face = win.agent_face
        self.assertIsNotNone(face)
        self.assertTrue(face.get_visible())
        pump(lambda: "home" in win.lane_tabs, 5)
        lane = win.lane_tabs["home"]
        win.tabs.set_current_page(win.tabs.page_num(lane))
        pump(lambda: getattr(lane, "positioned", True), 5)
        win._follow_author(lane)
        self.assertIsNotNone(face.who)  # someone's face, never an empty frame
        bob = self.view.by_id("011").author
        win.write_to(bob)  # a talk: whom I talk to
        pump(timeout=0.3)
        win._follow_author()
        self.assertEqual(face.who.id, bob.id)
        self.assertTrue(face.name.get_text())


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkBigLaneTest(unittest.TestCase):
    """Thousands of posts in a lane: only a window of them is built, in batches, so the
    main loop never stops for long (the first try froze the desktop for good: 5.6 s for
    1500 posts). The bound is loose: under Xvfb GTK paints in software, a frame of new
    cards there takes a few tenths of a second that a real desktop doesn't."""

    N = 2000
    STEP_MAX = 1.0  # s: the longest a single turn of the main loop may take

    def setUp(self):
        from fedtail.core.view import View
        from fedtail.frontends.gtk import theme as themes
        from fedtail.frontends.gtk.bridge import Bridge
        from fedtail.frontends.gtk.window import MainWindow
        from fedtail.protocols.mastodon import adapter
        i18n.setup("ru")
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        tmp = Path(self._tmp.name)
        FakeApi.world = fakes.World()
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False},
                                  "ui": {"start_lane": "home", "adwaita": "off"}})
        p = paths.resolve("t", config=str(tmp / "c.toml"), data=str(tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        self.core = Core(cfg, p, api_class=FakeApi)
        self.view = View(self.core)
        self.big = [(f"{i:05d}", adapter.post(
            status(f"{i:05d}", BOB, minute=i % 59, text="<p>пост " + "текст " * 30 + "</p>"),
            "t")) for i in range(self.N)]
        self.view.entries = lambda lane: self.big if lane == "home" else []
        self.view.unread = lambda entries: set()  # all read: the lane opens at its end
        self.win = MainWindow(None, self.core, self.view, Bridge(self.view), themes.apply(cfg))
        self.win.set_default_size(900, 600)
        self.win.present()
        self.worst = 0.0
        self.win.start()
        self.loop(lambda: self.lane() is not None and self.lane().positioned, 10)

    def tearDown(self):
        self.win.close()  # as a user would: the lanes stop their queued work
        self.win.destroy()
        pump(timeout=0.1)
        self.core.shutdown()
        self._tmp.cleanup()

    def lane(self):
        return self.win.lane_views.get("home")

    def loop(self, until, timeout=5.0):
        """pump(), keeping the longest single step of the main loop."""
        ctx = GLib.MainContext.default()
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            while ctx.pending():
                t = time.monotonic()
                ctx.iteration(False)
                self.worst = max(self.worst, time.monotonic() - t)
            if until():
                return True
            time.sleep(0.005)
        return False

    def test_only_a_window_is_built_and_the_loop_keeps_going(self):
        from fedtail.frontends.gtk import lane as lane_mod
        lv = self.lane()
        self.assertLessEqual(len(lv.rows), lane_mod.WINDOW)
        self.assertEqual(lv.order[-1], self.big[-1][0])  # opened at the newest end
        self.assertLess(self.worst, self.STEP_MAX, "the main loop stopped for too long")

    def test_scrolling_up_grows_without_a_jump(self):
        lv = self.lane()
        before = len(lv.rows)
        grow, lv._grow = lv._grow, lambda: None
        lv.adj.set_value(0)  # at the top of what's built…
        pump(timeout=0.3)
        top = lv._first_visible()
        offset = lv._y(lv.rows[top]) - lv.adj.get_value()
        lv._grow = grow
        lv._grow()  # …older ones join above
        self.assertTrue(self.loop(lambda: len(lv.rows) > before, 5))
        self.loop(lambda: not lv._pending() and lv._held_upper is None, 5)
        pump(timeout=0.2)
        # the post at the top is still where it was on screen: the view moved with it
        self.assertAlmostEqual(lv._y(lv.rows[top]) - lv.adj.get_value(), offset, delta=2)
        self.assertGreater(lv.adj.get_value(), 0)
        self.assertLess(self.worst, self.STEP_MAX)


def _walk(widget):
    """widget and everything inside it."""
    if widget is None:
        return
    yield widget
    child = widget.get_first_child()
    while child is not None:
        yield from _walk(child)
        child = child.get_next_sibling()


def _cards(win):
    from fedtail.frontends.gtk.window import _cards as cards
    for page in win.threads.values():
        yield from cards(page)


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class TitlebarTest(unittest.TestCase):
    def test_desktop_frame_outside_gnome(self):
        from unittest import mock

        from fedtail.frontends.gtk import gi_setup
        from fedtail.frontends.gtk.window import own_titlebar
        cfg = {"ui": {"gtk_headerbar": "auto"}}
        with mock.patch.object(gi_setup, "Adw", None):
            for desk, own in (("KDE", False), ("XFCE", False), ("X-Cinnamon", False),
                              ("GNOME", True), ("ubuntu:GNOME", True), ("", False)):
                with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": desk}):
                    self.assertEqual(own_titlebar(cfg), own, desk)
            with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "KDE"}):
                self.assertTrue(own_titlebar({"ui": {"gtk_headerbar": "on"}}))
        with mock.patch.dict(os.environ, {"XDG_CURRENT_DESKTOP": "GNOME"}):
            self.assertFalse(own_titlebar({"ui": {"gtk_headerbar": "off"}}))


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkImagesTest(unittest.TestCase):
    """common/images.py with GTK's pictures: read small, to disk, from disk."""

    def test_a_picture_comes_small_and_is_kept_on_disk(self):
        import gi
        gi.require_version("GdkPixbuf", "2.0")
        from gi.repository import GdkPixbuf

        from fedtail.frontends.gtk import images

        pix = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, False, 8, 300, 200)
        pix.fill(0x336699FF)
        ok, data = pix.save_to_bufferv("png", [], [])
        self.assertTrue(ok)
        tex = images.decode(bytes(data), 100)
        self.assertEqual((tex.get_width(), tex.get_height()), (100, 67))
        self.assertIsNone(images.decode(b"not a picture", 100))

        class Resp:
            headers = {"Content-Type": "image/png"}
            is_redirect = False

            def __enter__(self):
                return self

            def __exit__(self, *_a):
                return False

            def raise_for_status(self):
                pass

            def iter_content(self, _size):
                yield bytes(data)

            def close(self):
                pass

        class Bridge:
            def call(self, future, ok=None, fail=None):
                future.add_done_callback(lambda f: GLib.idle_add(
                    lambda: (ok(f.result()) if ok else None) and False))
                return future

        with tempfile.TemporaryDirectory() as tmp:
            core = type("C", (), {"cfg": {"ui": {}}, "_own_hosts": lambda self: set(),
                                  "paths": type("P", (), {"cache_dir": Path(tmp)})()})()
            imgs = images.Images(core, Bridge())
            imgs.http.get = lambda url, timeout, **_kw: Resp()
            got = []
            try:
                imgs.get("https://media.example/a.png", got.append, max_side=50)
                self.assertTrue(pump(lambda: got, 5))
                self.assertEqual(got[0].get_width(), 50)
                self.assertTrue(imgs.local("https://media.example/a.png"))  # on disk now
            finally:
                imgs.shutdown()


@unittest.skipUnless(HAVE_GTK, "no GTK 4 or no display")
class GtkThemeTest(unittest.TestCase):
    def test_every_theme_makes_css_gtk_takes(self):
        from fedtail.frontends import themefile
        from fedtail.frontends.gtk import theme as themes
        for p in sorted(themefile.BUILTIN_DIR.glob("*.toml")):
            data, _w = themefile.load(p.stem)
            css = themes.Theme(data, themes.desktop()).css("Sans", 1.1)
            prov = Gtk.CssProvider()
            errors = []
            prov.connect("parsing-error",
                         lambda _p, _s, e, errors=errors: errors.append(e.message))
            themes._load_css(prov, css)
            self.assertEqual(errors, [], p.stem)


if __name__ == "__main__":
    unittest.main()
