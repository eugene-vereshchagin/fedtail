"""frontends/common: links, post actions, the writing rules and the command line — the
decisions both windows share, tested without a toolkit."""

import unittest

from fedtail import i18n
from fedtail.core.view import View
from fedtail.frontends.common import actions, commands, links
from fedtail.frontends.common import compose as rules
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


if __name__ == "__main__":
    unittest.main()
