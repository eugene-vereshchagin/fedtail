"""Who stopped following me (core/derived.py): snapshots compared, without lying."""

from fedtail.core import derived

from . import fakes
from .fakes import BOB, NEWS
from .test_custom import FreeBase


def acc(i, host="far.example"):
    return fakes.acct(i, f"user{i}@{host}")


class DerivedTest(FreeBase):
    def setUp(self):
        super().setUp()
        self.core, self.w = self.make([])
        self.core.connect().result()
        self.w.followers_list = [BOB, NEWS, acc("C")]

    def rows(self):
        return [n for n in self.core.store.activity_recent(50)
                if n["type"].startswith("fedtail.") and n["type"] != self.core.MY_FOLLOW]

    def test_first_is_the_start(self):
        self.core.derived.run()
        self.w.followers_list = [NEWS, acc("C")]
        self.core.derived.run()  # gone once: not yet
        self.assertEqual(self.rows(), [])
        self.core.derived.run()  # gone twice, and not following when asked: said
        rows = self.rows()
        self.assertEqual([(r["type"], r["account"]["id"]) for r in rows],
                         [(derived.TYPE_UNFOLLOW, BOB["id"])])
        self.assertGreater(self.core.activity_unread(), 0)  # news, unlike my own doings
        self.core.derived.run()
        self.assertEqual(len(self.rows()), 1)  # once

    def test_a_list_not_whole_says_nothing(self):
        self.w.followers_list = [BOB, NEWS] + [acc(f"K{i}") for i in range(8)]
        self.core.derived.run()
        self.w.followers_list = [NEWS, acc("K1")]
        self.w.followers_count = 10  # the server counts ten: the list has holes
        self.core.derived.run()
        self.core.derived.run()
        self.assertEqual(self.rows(), [])

    def test_back_in_between_or_still_following(self):
        self.core.derived.run()
        self.w.followers_list = [NEWS, acc("C")]
        self.core.derived.run()
        self.w.followers_list = [BOB, NEWS, acc("C")]  # back again
        self.core.derived.run()
        self.w.followers_list = [NEWS, acc("C")]
        self.core.derived.run()
        self.assertEqual(self.rows(), [])  # gone once again: not twice in a row yet

    def test_my_own_removal_isnt_news(self):
        self.core.derived.run()
        self.core.remove_follower(BOB["id"]).result()
        self.w.followers_list = [NEWS, acc("C")]
        self.core.derived.run()
        self.core.derived.run()
        self.assertEqual(self.rows(), [])

    def test_a_server_lost_is_one_row(self):
        many = [acc(f"M{i}", "down.example") for i in range(12)]
        self.w.followers_list = [BOB] + many
        self.core.derived.run()
        self.w.followers_list = [BOB]
        self.core.derived.run()
        self.core.derived.run()
        rows = self.rows()
        self.assertEqual([r["type"] for r in rows], [derived.TYPE_LOST])
        self.assertEqual(rows[0]["account"]["acct"], "down.example")

    def test_shown_and_taken_by_rules(self):
        from fedtail.core.view import View
        from fedtail.frontends.common.activity import rows as act_rows
        from fedtail.i18n import _
        self.core.derived.run()
        self.w.followers_list = [NEWS, acc("C")]
        self.core.derived.run()
        self.core.derived.run()
        got = act_rows(View(self.core).activity(), "", lambda d: "t")
        self.assertIn(_("act_unfollow"), [r.what for r in got])
        from fedtail.core.atoms import event_facts
        n = self.rows()[0]
        self.assertEqual(event_facts(n).event, {"unfollow"})
        self.w.following.add(BOB["id"])
        self.core._following = {BOB["id"]}
        self.assertEqual(event_facts(dict(n, account=dict(n["account"], _back=True))).event,
                         {"unfollow", "unfollowed_back"})

    def test_moved_isnt_an_unfollow(self):
        old = acc("O")
        new = acc("N2", "new.example")
        self.w.followers_list = [BOB, NEWS, old]
        self.core.derived.run()
        self.w.add(fakes.status("990", dict(old, moved=new), minute=1))  # its account now
        self.w.followers_list = [BOB, NEWS]
        self.core.derived.run()
        self.core.derived.run()
        rows = self.rows()
        self.assertEqual([r["type"] for r in rows], [derived.TYPE_MOVED])
        self.assertEqual(rows[0]["account"]["_moved_to"], new["acct"])

    def test_likes_taken_back(self):
        core = self.core
        core.cfg["activity"]["unlikes"] = True
        mine = fakes.status("995", fakes.ME, minute=1)
        mine["created_at"] = __import__("time").strftime("%Y-%m-%dT%H:%M:%S.000Z",
                                                         __import__("time").gmtime())
        self.w.add(mine, home=True)
        self.w.statuses["995"] = mine
        core.store.put_items("mine", [("995", mine, mine["created_at"])])
        self.w.reactions["995"] = {"favourited_by": [BOB, NEWS]}
        self.assertTrue(core.derived.likes_due())
        self.assertEqual(core.derived.run_likes(), [])  # the start
        self.w.reactions["995"] = {"favourited_by": [NEWS]}
        got = core.derived.run_likes()
        self.assertEqual([(n["type"], n["account"]["id"]) for n in got],
                         [(derived.TYPE_UNLIKED, BOB["id"])])
        self.assertFalse(core.derived.likes_due())  # not before unfollows_minutes
        core.cfg["activity"]["unlikes"] = False
        core.store.kv_set("derived.likes_at", 0)
        self.assertFalse(core.derived.likes_due())

    def test_due_and_off(self):
        self.assertTrue(self.core.derived.due())
        self.core.derived.run()
        self.assertFalse(self.core.derived.due())
        self.core.store.kv_set("derived.at", 0)
        self.core.cfg["activity"]["unfollows"] = False
        self.assertFalse(self.core.derived.due())


class ActivityFilterTest(FreeBase):
    """Activity's quick filters: all · likes & boosts · followers · requests · mine · other."""

    def test_filters(self):
        from fedtail.core.view import View
        from fedtail.frontends.common.places import Places
        core, w = self.make([])
        mine = w.add(fakes.status("900", fakes.ME, minute=1), home=True)
        w.act("n1", "favourite", BOB, mine, minute=2)
        w.act("n2", "follow", NEWS, minute=3)
        core.connect().result()
        core.poll_once()
        w.act("n3", "favourite", NEWS, mine, minute=4)
        w.act("n4", "follow", BOB, minute=5)
        core.poll_once()
        core.follow(BOB["id"]).result()
        v = View(core)
        kinds = lambda which: sorted(a.kind for a in v.activity(which=which))  # noqa: E731
        self.assertEqual(kinds("reactions"), ["like", "like"])
        self.assertEqual(kinds("follows"), ["follow", "follow"])
        self.assertEqual(kinds("mine"), ["my_follow"])
        self.assertEqual(len(v.activity()), 5)
        page = Places(v).page("activity", tab="follows")
        self.assertEqual(page.tab, "follows")
        self.assertEqual([k for k, _w in page.tabs][:3], ["all", "reactions", "follows"])
        self.assertEqual(len(v.activity()), 2)  # the choice stays
        v.set_activity_filter("all")
        self.assertEqual(len(v.activity()), 5)

    def test_this_run_only_and_only_what_can_show(self):
        from fedtail.core.view import View
        from fedtail.frontends.common import activity as act
        core, w = self.make([])
        core.connect().result()
        v = View(core)
        self.assertIn("requests", act.offered(v))  # follow requests stand in Activity
        v.set_activity_filter("follows")
        self.assertEqual(act.chosen(v), "follows")
        self.assertIsNone(core.store.kv_get("ui.activity_filter"))  # nothing kept
        core.cfg["feed"]["remember_choices"] = True  # the tick: kept between runs
        v.set_activity_filter("reactions")
        self.assertEqual(core.store.kv_get("ui.activity_filter"), "reactions")
        core.cfg["feed"]["remember_choices"] = False
        v.set_activity_filter("all")
        # follow requests in a lane of their own, no approvals: no "Requests" filter
        core.cfg["lanes"]["enabled"] = ["home", "activity", "requests"]
        core.cfg["activity"]["approvals"] = False
        core._apply_lists([], {})
        self.assertNotIn("requests", act.offered(v))
        v.set_activity_filter("requests")
        self.assertEqual(act.chosen(v), "all")  # not offered: everything
        core.cfg["activity"]["my_follows"] = False
        self.assertNotIn("mine", act.offered(v))


    def test_deleted_post_marked_and_kept(self):
        from fedtail.core.view import View
        from fedtail.frontends.common.lane import LaneModel
        core, w = self.make([])
        core.connect().result()
        w.add(fakes.status("996", BOB, minute=1), home=True)
        core.poll_once()
        del w.statuses["996"]  # its server lost it
        from fedtail.protocols.mastodon.api import ApiError
        with self.assertRaises((ApiError, KeyError)):
            core.thread("996").result()
        self.assertIn("996", core.deleted_ids())
        specs = LaneModel(View(core), "home").build(False).specs
        spec = next(s for s in specs if s.entry is not None and s.entry.id == "996")
        self.assertTrue(spec.extra.get("deleted"))
        from fedtail.core.atoms import post_facts
        self.assertIn("deleted", post_facts(core.store.get_status("996"),
                                            core._world()).state)
