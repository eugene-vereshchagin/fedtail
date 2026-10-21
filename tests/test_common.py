"""frontends/common: links, post actions, the writing rules and the command line — the
decisions both windows share, tested without a toolkit."""

import unittest

from fedtail import i18n
from fedtail.core.view import View
from fedtail.frontends.common import actions, commands, links
from fedtail.frontends.common import compose as rules
from fedtail.frontends.common import lane as lanes
from fedtail.protocols.mastodon.adapter import post as to_post

from . import test_cli
from .fakes import BOB, ME, status
from .test_core import TmpDir


class Host:
    """A window as common/links.py sees it, writing down what it was asked."""

    def __init__(self, yes=True):
        self.did, self.yes = [], yes

    def call(self, future, ok=None, fail=None):
        try:
            got = future.result()
        except Exception as e:  # noqa: BLE001
            self.did.append(("failed", str(e)))
            if fail:
                fail(str(e))
            return future
        if ok:
            ok(got)
        return future

    def status(self, text):
        self.did.append(("status", text))

    def error(self, text):
        self.did.append(("error", text))

    def confirm(self, title, text, then):
        self.did.append(("asked", title))
        if self.yes:
            then()

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: self.did.append((name, a, k))


class CommonTest(TmpDir):
    make = test_cli.CliTest.make

    def setUp(self):
        super().setUp()
        i18n.setup("en")
        self.core, self.w = self.make()
        self.w.add(status("001", BOB, minute=1, vis="public", text="hello"), home=True)
        self.w.add(status("002", ME, minute=2, vis="public", text="mine"), home=True)
        self.core.connect().result()
        self.core.poll_once()
        self.view = View(self.core)

    # ---- links ---------------------------------------------------------------------
    def test_link_kinds(self):
        self.assertIsNone(links.parse("https://x.test/"))
        self.assertEqual(links.parse("fedtail:thread/001"), links.Link("thread", "001"))
        self.assertEqual(links.make("fav", "001"), "fedtail:fav/001")

    def test_links_go_to_the_host_and_the_core(self):
        h = Host()
        ls = links.Links(self.view, h)
        ls.open("https://x.test/a")
        ls.open("fedtail:thread/001")
        ls.open("fedtail:account/B")
        ls.open("fedtail:tag/linux%2B")
        ls.open("fedtail:reply/001")
        names = [d[0] for d in h.did]
        self.assertEqual(names, ["open_url", "open_thread", "open_account", "open_tag",
                                 "compose"])
        self.assertEqual(h.did[3][1], ("linux+",))  # unquoted
        ls.open("fedtail:fav/001")
        self.assertTrue(self.view.by_id("001").mine.liked)
        ls.open("fedtail:nosuch/999")
        self.assertEqual(h.did[-1][0], "error")

    def test_dangerous_ones_ask_first(self):
        h = Host(yes=False)
        ls = links.Links(self.view, h)
        ls.open("fedtail:delete/002")
        self.assertEqual(h.did[-1][0], "asked")
        self.assertIsNotNone(self.view.by_id("002"))  # not deleted: the answer was no
        ls.open("fedtail:mute/001")  # muting doesn't ask
        self.assertEqual(h.did[-1][0], "status")

    def test_a_host_without_a_thing_says_so(self):
        class Small(Host):
            report = None
        h = Small()
        h.report = None
        ls = links.Links(self.view, type("H", (), {
            "status": h.status, "error": h.error, "call": h.call, "confirm": h.confirm})())
        ls.open("fedtail:report/001")
        self.assertEqual(h.did[-1], ("status", i18n._("gtk_not_yet")))

    # ---- what a post offers -----------------------------------------------------------
    def ctx(self, **kw):
        return actions.Ctx(cfg=self.core.cfg, me_id="ME", supports=lambda _w: True, **kw)

    def test_buttons(self):
        p = self.view.by_id("001")
        got = actions.buttons(p, self.ctx(), unread=False)
        self.assertEqual([b.action for b in got][:4], ["reply", "fav", "boost", "thread"])
        self.assertEqual(got[1].url, "fedtail:fav/001")
        in_thread = actions.buttons(p, self.ctx(in_thread=True))
        self.assertNotIn("thread", [b.action for b in in_thread])

    def test_menu_mine_and_theirs(self):
        theirs = actions.menu(self.view.by_id("001"), self.ctx(), short_id="a00")
        mine = actions.menu(self.view.by_id("002"), self.ctx())
        urls = lambda items: [i.url for i in items if i.kind == "link"]  # noqa: E731
        self.assertIn("fedtail:block/001", urls(theirs))
        self.assertNotIn("fedtail:delete/001", urls(theirs))
        self.assertIn("fedtail:delete/002", urls(mine))
        self.assertNotIn("fedtail:block/002", urls(mine))
        self.assertIn(("copy", "#a00"), [(i.kind, i.text) for i in theirs])
        arts = dict(self.core.cfg, ui=dict(self.core.cfg["ui"], arts_mode=True))
        no_report = actions.menu(self.view.by_id("001"),
                                 actions.Ctx(cfg=arts, me_id="ME"))
        self.assertNotIn("fedtail:report/001", urls(no_report))

    # ---- writing ------------------------------------------------------------------------
    def test_a_reply_starts_with_the_mentions_and_the_warning(self):
        st = status("003", BOB, minute=3, vis="public", text="careful")
        st["spoiler_text"] = "spoilers"
        p = to_post(st)
        key = rules.draft_key(self.view, reply_to=p)
        s = rules.start(self.view, key, reply_to=p)
        self.assertTrue(s.text.startswith("@bob@social.example"))
        self.assertEqual(s.cw, "spoilers")
        call = rules.start(self.view, rules.draft_key(self.view, p, invite=True), p,
                           invite=True)
        self.assertEqual((call.text, call.hint), ("@", "invite_hint"))

    def test_drafts_come_back(self):
        key = rules.draft_key(self.view)
        snap = rules.snapshot("half", "", "public", [], None, False, None)
        self.assertEqual(rules.keep(snap, {}, False), "save")
        self.view.save_draft(key, snap)
        back = rules.start(self.view, key)
        self.assertEqual((back.text, back.visibility, back.restored), ("half", "public", True))
        empty = rules.snapshot("  ", "", "public", [], None, False, None)
        self.assertEqual(rules.keep(empty, snap, True), "delete")
        self.assertEqual(rules.keep(snap, snap, False), "skip")

    def test_counter_tokens_poll(self):
        c = rules.count("hello #lowercasetag", "cw", 10, self.core.cfg)
        self.assertEqual((c.n, c.over), (21, True))
        self.assertEqual(rules.token_at_end("a #lin"), ("#", "lin"))
        self.assertEqual(rules.token_at_end("say @bob@soc"), ("@", "bob@soc"))
        self.assertEqual(rules.token_at_end("a:b"), (None, None))
        self.assertIsNone(rules.poll_data(True, ["one", " "], 300, False))
        self.assertEqual(rules.poll_data(True, ["a", "b"], 300, True)["options"], ["a", "b"])
        self.assertEqual(rules.put_alias("#abc/2 hi", "k9"), "#k9 hi")
        self.assertEqual(rules.more_people([("a@x", "")], [("A@x", ""), ("b@y", "B")]),
                         [("@a@x", "@a@x"), ("@b@y", "@b@y — B")])

    # ---- the command line ---------------------------------------------------------------
    def test_preview_and_history(self):
        alias = self.view.short_ids([self.view.by_id("001")])["001"]
        self.assertIn(alias, commands.preview(self.view, f"#{alias} hi"))
        self.assertIn("zz9", commands.preview(self.view, "#zz9 hi"))
        self.assertEqual(commands.preview(self.view, " "), "")
        h = commands.History()
        h.add("one")
        h.add("two")
        h.add("two")
        self.assertEqual((h.up(), h.up(), h.up(), h.down(), h.down()),
                         ("two", "one", "one", "two", ""))

    def test_unknown_alias_as_a_post_only_when_asked(self):
        cmds = commands.Commands(self.view)
        fut, msg = cmds.run("#zz9 hi")
        self.assertIsNone(fut)
        fut, _msg = cmds.run("#zz9 hi", unknown_as_post=True)
        fut.result()
        self.assertEqual(self.w.posted[-1][0], "#zz9 hi")
        fut, _msg = cmds.run("@nobody@nowhere.test")
        self.assertIsInstance(fut.result(), commands.Failed)

    # ---- a lane ---------------------------------------------------------------------------
    def test_a_lane_builds_with_the_divider_and_starts_at_it(self):
        self.w.add(status("003", BOB, minute=3, vis="public", text="new"), home=True)
        self.core.poll_once()
        self.view.mark_read(["001", "002"])
        lm = lanes.LaneModel(self.view, "home", lambda n: f"{n} new")
        built = lm.build(positioned=False)
        keys = [s.key for s in built.specs]
        self.assertEqual(built.unread, 1)
        self.assertEqual(keys[-2], lanes.SEPARATOR)
        self.assertEqual(built.specs[-2].extra["separator"], "1 new")
        self.assertEqual(lm.start(built.specs), (lanes.SEPARATOR, "top"))
        self.assertIn("short_id", built.specs[-1].extra)
        self.assertEqual(lm.filters, ["all", "posts", "unread"])
        lm.set_filter("unread")
        only = lm.build(positioned=False)
        self.assertEqual([s.post.id for s in only.specs], ["003"])
        self.assertTrue(lm.read(["003"]))

    def test_the_media_funnel_and_true_kinds(self):
        from fedtail.protocols.mastodon import adapter
        clip = {"id": "m", "type": "image", "url": "https://x/a.MP4?x=1",
                "preview_url": "", "description": ""}
        self.assertEqual(lanes.true_kind(adapter.media(clip)).kind, "video")
        f = lanes.MediaFilter()
        self.assertFalse(f.active())
        f.toggle("text", False)
        self.assertTrue(f.active())
        self.assertFalse(f.keeps(self.view.by_id("001")))  # text only
        f.reset()
        self.assertTrue(f.keeps(self.view.by_id("001")))

    def test_what_counts_as_seen(self):
        self.assertEqual(lanes.seen(10, 90, 0, 100), "read")
        self.assertEqual(lanes.seen(50, 150, 0, 100), "glimpsed")
        self.assertEqual(lanes.seen(50, 150, 0, 100, at_end=True), "read")
        self.assertEqual(lanes.seen(-200, 60, 0, 100), "read")      # taller, its end seen
        self.assertEqual(lanes.seen(-80, -10, 0, 100, glimpsed=True), "read")  # went past
        self.assertIsNone(lanes.seen(200, 300, 0, 100))

    # ---- what the Silence dialog and the announcements bar get -------------------------------
    def test_filters_people_announcements_as_the_model(self):
        self.core.add_filter("крипта", ["крипта", "nft"], "hide").result()
        (f,) = self.view.filters().result()
        self.assertEqual((f.title, f.words, f.action), ("крипта", ("крипта", "nft"), "hide"))
        self.core.mute("B").result()
        got = self.view.silenced_people().result()
        self.assertEqual([a.id for a in got.muted], ["B"])
        self.w.announcements = [{"id": "a1", "content": "<p>hi</p>", "read": False,
                                 "published_at": "2099-10-14T09:00:00.000Z",
                                 "reactions": [{"name": "👍", "count": 2, "me": False}]}]
        (a,) = self.view.announcements().result()
        self.assertEqual((a.id, a.published.year, a.reactions[0].count), ("a1", 2099, 2))
        from fedtail.frontends.common.announce import react
        after = react(a.reactions, "👍", True)
        self.assertEqual((after[0].count, after[0].me), (3, True))
        self.assertEqual(react(after, "👍", False)[0].count, 2)
        self.assertEqual([r.name for r in react((), "🎉", True)], ["🎉"])

    # ---- the split layout ------------------------------------------------------------------
    def test_the_input_line_of_the_split_layout(self):
        from fedtail.frontends.common import split
        bob = self.view.by_id("001")
        start = split.reply_start(self.view, bob)
        self.assertTrue(start.prefill.startswith("@bob"))
        self.assertEqual(start.whom.id, bob.author.id)
        self.assertEqual(split.private_start(bob.author).visibility, "direct")
        cfg = self.core.cfg
        self.assertEqual(split.command("#a3f hi", "", cfg), "#a3f hi")
        self.assertIsNone(split.command("@bob hi", "", cfg))
        self.assertIsNone(split.command("#a3f\nhi", "", cfg))
        self.assertIsNone(split.command(start.prefill, start.prefill, cfg))
        me = self.view.by_id("002").author
        self.assertIsNone(split.face("qip", me, me))
        self.assertEqual(split.face("agent", bob.author, me), me)
        self.assertEqual(split.other_side(self.view.by_id("002"), me, bob).id, bob.author.id)
        self.assertIsNone(split.other_side(None, me))
        self.assertIn("·", split.about_line(start.about, "public"))

    def test_the_roster_rows(self):
        from fedtail.frontends.common import roster
        from fedtail.model import RosterItem
        bob = self.view.by_id("001")
        lane = RosterItem("lane", "home", "Home", unread=2, total=5, last=bob)
        talk = RosterItem("talk", "001", "Bob", ids=("001",))
        person = RosterItem("person", "B", "Bob", who=bob.author)
        self.assertEqual([roster.row_key(x) for x in (lane, talk)], ["home", "talk/001"])
        self.assertEqual(roster.what("talk/001"), ("talk", "001"))
        self.assertEqual(roster.what("home"), ("lane", "home"))
        line, tip, status = roster.lines(lane, faces=True)
        self.assertIn("hello", line)
        self.assertTrue(status)
        self.assertEqual(roster.lines(person, faces=False)[0], "@" + bob.author.handle)
        self.assertEqual(roster.tip(person), "")
        look = dict(roster.LOOK, only_new=True)
        self.assertTrue(roster.hidden(talk, "", "", False, look))      # read: away
        self.assertFalse(roster.hidden(lane, line, "", False, look))
        self.assertTrue(roster.hidden(lane, line, "nothing like it", False, look))
        self.assertEqual(roster.read_ids(self.view, "talk/001", talk), ["001"])
        self.assertEqual(roster.look(self.view)["groups"], True)

    def test_results_reach_the_window(self):
        from concurrent.futures import Future

        from fedtail.frontends.common import results
        said = []
        bad = Future()
        bad.set_exception(TimeoutError("slow"))
        results.handle(bad, None, said.append)
        good = Future()
        good.set_result(1)
        with self.assertLogs("fedtail.frontends.common.results", "ERROR"):
            results.handle(good, lambda _r: 1 / 0, None, on_error=said.append)
        gone = Future()
        gone.set_result(1)
        results.handle(gone, lambda _r: (_ for _ in ()).throw(RuntimeError("deleted")), None,
                       on_error=said.append, gone=lambda e: isinstance(e, RuntimeError))
        self.assertEqual(said, ["slow", "ZeroDivisionError: division by zero"])

    def test_server_page_probe_table_profile_changes(self):
        from fedtail.frontends.common import server
        from fedtail.model import MyProfile, ServerInfo
        info = ServerInfo(title="Ex", domain="x.test", description="plain <words>",
                          rules=(("be nice", "really"),), about="<p>long</p>")
        page = server.server_html(info, lambda h: "[" + h + "]")
        self.assertIn("<h2>Ex</h2>", page)
        self.assertIn("[plain <words>]", page)  # "<" in it: HTML, the toolkit cleans it
        self.assertIn("<li>be nice<br><small>really</small></li>", page)
        md = server.probe_markdown("x.test", "today", [("polls", "yes")])
        self.assertTrue(md.startswith("x.test — today\n"))
        self.assertIn("| polls | yes |", md)
        me = self.view.by_id("002").author
        prof = MyProfile(me, bio="hi", fields=(("site", "x"),))
        flags = {"locked": me.locked, "bot": me.bot, "discoverable": bool(me.discoverable)}
        self.assertEqual(server.profile_changes(prof, me.name, "hi", [(" site", "x ")],
                                                flags), {})
        got = server.profile_changes(prof, "New", "hi", [("", "")], dict(flags, bot=True),
                                     avatar="/a.png")
        self.assertEqual(got, {"name": "New", "fields": [], "bot": True, "avatar": "/a.png"})

    def test_find(self):
        from fedtail.frontends.common import find
        lm = lanes.LaneModel(self.view, "home")
        specs = lm.build(positioned=True).specs
        self.assertEqual(len(find.hits(specs, "hello")), 1)
        self.assertEqual(find.hits(specs, "  "), [])
        self.assertEqual((find.step(-1, 3, 1), find.step(-1, 3, -1), find.step(2, 3, 1)),
                         (0, 2, 0))
        self.assertEqual(find.count_text("x", 0, 0), (i18n._("find_none"), True))
        self.assertEqual(find.count_text("x", 0, 0, everywhere=True, searched=False),
                         ("", False))


if __name__ == "__main__":
    unittest.main()
