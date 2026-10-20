"""The terminal interface's text side (no Textual needed): posts as lines, commands."""

import unittest

from fedtail import i18n
from fedtail.core.view import View
from fedtail.frontends.tui import model
from fedtail.protocols.mastodon.adapter import post as to_post

from . import test_cli
from .fakes import BOB, ME, status
from .test_core import TmpDir


class TuiModelTest(TmpDir):
    make = test_cli.CliTest.make

    def setUp(self):
        super().setUp()
        i18n.setup("en")

    def test_post_lines(self):
        core, w = self.make()
        parent = status("001", ME, minute=1, text="what do you think?")
        st = status("002", BOB, "001", "ME", minute=2, text="I think yes<br>and more")
        st["media_attachments"] = [{"type": "image"}]
        st["favourites_count"] = 3
        parent, st = to_post(parent), to_post(st)
        core = View(core)
        shown = model.show_post(core, st, "a3f", unread=True, parent=parent, width=40)
        kinds = dict(shown.head)
        self.assertEqual(kinds["alias"], "#a3f")
        self.assertEqual(kinds["who"], "@bob@social.example")
        self.assertIn("unread", kinds)
        self.assertEqual(shown.context, "↳ @mira: what do you think?")
        self.assertEqual(shown.body, ["I think yes", "and more"])
        self.assertIn("[1 attachment]", shown.foot)
        self.assertIn("☆ 3", shown.foot)
        gone = model.show_post(core, st, parent="missing")
        self.assertIn("deleted", gone.context)
        core.cfg["tui"]["show_context"] = False
        self.assertEqual(model.show_post(core, st, parent=parent).context, "")
        # in a thread: the /N number instead of the context line
        self.assertEqual(model.show_post(core, st, number=2, parent=parent).head[0],
                         ("num", "/2"))

    def test_cw_folds_unless_expand(self):
        core, _w = self.make(ui={"expand_cw": False, "arts_mode": False})
        st = status("003", BOB, minute=3, text="spoiler")
        st["spoiler_text"] = "careful"
        shown = model.show_post(View(core), to_post(st))
        self.assertEqual((shown.cw, shown.body), ("⚠ careful", []))

    def test_commands(self):
        core, w = self.make()
        w.add(status("001", BOB, minute=1, vis="public"), home=True)
        core.connect().result()
        core.poll_once()
        alias = core.short_ids([core.store.get_status("001")])["001"]
        c = model.Commands(View(core))
        fut, _msg = c.run(f"#{alias} hello")
        self.assertEqual(fut.result(), i18n._("sent"))
        self.assertEqual(w.posted[-1][2], "001")
        self.assertTrue(w.posted[-1][0].startswith("@bob@social.example hello"))
        fut, _msg = c.run(f"#{alias}")
        self.assertEqual(fut.result(), ("thread", "001"))
        fut, _msg = c.run(f"! #{alias}")
        self.assertEqual(fut.result(), i18n._("cmd_boosted"))
        fut, msg = c.run("#zzz9 hi")
        self.assertIsNone(fut)
        self.assertIn("zzz9", msg)
        fut, msg = c.run("?")
        self.assertEqual(msg, i18n._("cmd_help"))
        fut, _msg = c.run("just a post")
        fut.result()
        self.assertEqual(w.posted[-1][0], "just a post")

    def test_lane_label(self):
        core, w = self.make()
        w.add(status("001", BOB, minute=1), home=True)
        core.connect().result()
        core.poll_once()
        self.assertEqual(model.lane_label(core, "home"), ("Home", 1))
        title, _n = model.lane_label(core, "home", width=4)
        self.assertLessEqual(len(title), 4)


class DeleteGuardTest(unittest.TestCase):
    def test_deleted_only_when_said_twice(self):
        now = [100.0]
        g = model.DeleteGuard(clock=lambda: now[0])
        self.assertFalse(g.confirmed("1"))  # asks
        self.assertTrue(g.confirmed("1"))   # Enter again: yes
        self.assertFalse(g.confirmed("1"))  # and a third time asks anew
        self.assertFalse(g.confirmed("2"))  # another post: asks about that one
        now[0] += g.WINDOW + 1
        self.assertFalse(g.confirmed("2"))  # too late: asks again
        self.assertTrue(g.confirmed("2"))

class ActivityRowsTest(TmpDir):
    make = test_cli.CliTest.make

    def setUp(self):
        super().setUp()
        i18n.setup("en")

    def test_activity_and_request_rows(self):
        from fedtail.protocols.mastodon.adapter import account, activity
        mine = status("001", ME, minute=1, text="my post")
        a = activity({"id": "a1", "type": "favourite", "account": BOB, "status": mine,
                      "created_at": "2099-10-14T11:00:00.000Z"})
        shown = model.show_activity(a, width=40, unread=True)
        kinds = dict(shown.head)
        self.assertEqual(kinds["who"], "@bob@social.example")
        self.assertEqual(kinds["boost"], i18n._("act_favourite"))
        self.assertIn("unread", kinds)
        self.assertEqual(shown.body, ["my post"])
        f = activity({"id": "a2", "type": "follow", "account": BOB,
                      "created_at": "2099-10-14T11:01:00.000Z"})
        self.assertEqual(dict(model.show_activity(f).head)["boost"], i18n._("act_follow"))
        self.assertEqual(model.show_activity(f).body, [])
        req = model.show_request(account(BOB))
        self.assertEqual(dict(req.head)["who"], "@bob@social.example")
        self.assertIn("a —", req.foot)

    def test_activity_and_requests_counted(self):
        from . import fakes
        core, w = self.make(lanes={"enabled": ["home", "activity", "requests"]})
        w.act("a0", "follow", BOB, minute=1)
        core.connect().result()
        core.poll_once()  # the first fetch is history
        w.act("a1", "favourite", BOB, minute=5)
        w.requests.append(fakes.acct("Q", "quinn@example.org"))
        core.poll_once()
        view = View(core)
        self.assertEqual(model.lane_label(view, "activity")[1], 1)
        self.assertEqual(model.lane_label(view, "requests")[1], 1)
        self.assertEqual([a.kind for a in view.activity()], ["like", "follow"])
        self.assertEqual([x.handle for x in view.follow_requests()], ["quinn@example.org"])
