"""The terminal interface's text side (no Textual needed): posts as lines, commands."""

import unittest

from fedtail import i18n
from fedtail.core.view import View
from fedtail.frontends.common import sidebar
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
        self.assertEqual(sidebar.lane_label(core, "home"), ("Home", 1))
        title, _n = sidebar.lane_label(core, "home", width=4)
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

    def test_event_lines(self):
        """An event's row: the windows' parts (common/activity.event_parts) as lines,
        each action a fedtail: link — names, ×, a request's yes / no, the post."""
        from fedtail.frontends.common import activity as act
        from fedtail.protocols.mastodon.adapter import activity
        mine = status("001", ME, minute=1, text="my post")
        a = activity({"id": "a1", "type": "favourite", "account": BOB, "status": mine,
                      "created_at": "2099-10-14T11:00:00.000Z"})
        row = act.rows([a], "", model.when)[0]
        lines = model.event_lines(act.event_parts(row, model.when))
        top = lines[0]
        self.assertEqual(top[0][0], "who")
        self.assertTrue(top[0][2].startswith("fedtail:account/"))
        self.assertIn(i18n._("act_favourite"), "".join(t for _k, t, _l in top))
        self.assertIn(("unread", " ●", None), top)
        self.assertEqual([x[2] for x in top if x[0] == "hide"], ["fedtail:eventhide/a1"])
        self.assertEqual(lines[-1][0][0], "event_post")
        self.assertIn("my post", lines[-1][0][1])
        self.assertTrue(lines[-1][0][2].startswith("fedtail:thread"))
        # a follow request waiting: its yes / no, and the keys for them
        req = activity({"id": "follow_request:Q", "type": "follow_request",
                        "account": BOB})
        row = act.rows([req], "", model.when)[0]
        lines = model.event_lines(act.event_parts(row, model.when))
        answers = [x for line in lines for x in line if x[0] in ("yes", "no")]
        self.assertEqual([x[2] for x in answers], ["fedtail:eventyes/follow_request%3AQ",
                                                   "fedtail:eventno/follow_request%3AQ"])
        self.assertIn(i18n._("ok_interaction"), answers[0][1])
        self.assertEqual(lines[-1][0][1], i18n._("tui_request_keys"))

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
        self.assertEqual(sidebar.lane_label(view, "activity")[1], 1)
        self.assertEqual(sidebar.lane_label(view, "requests")[1], 1)  # the core's number
        self.assertEqual(sidebar.lane_label(view, "requests")[1], view.unread_count("requests"))
        self.assertEqual([a.kind for a in view.activity()], ["like", "follow"])
        self.assertEqual([x.handle for x in view.follow_requests()], ["quinn@example.org"])
