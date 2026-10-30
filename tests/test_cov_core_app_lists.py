"""Lists, lanes of tags, thread states and lane choices in the core (core/app.py) at
their edges: moving a list past the ends, people waiting to go into a list when the
server is down, tag lanes saved twice, threads left from another device, muted-thread
checks that fail, and choices kept or not between runs."""

import unittest
from unittest import mock

from fedtail.core import taggroups
from fedtail.protocols.mastodon.api import ApiError

from .fakes import BOB, ME, status
from .test_cov_core_app_poll import CoreCase, boom

T = 10


class ListsTest(CoreCase):
    def setUp(self):
        super().setUp()
        self.w.lists = {"L1": {"title": "Один", "exclusive": False, "members": {"B"}},
                        "L2": {"title": "Два", "exclusive": True, "members": set()}}
        self.connect()
        self.core.sync = mock.Mock()

    def test_move_list(self):
        c = self.core
        c.move_list("nope", 1)
        c.move_list("L1", -1)  # already first
        c.sync.record_setting.assert_not_called()
        c.move_list("L1", 1)
        self.assertEqual([x["id"] for x in c.lists], ["L2", "L1"])
        c.sync.record_setting.assert_called_with("list_order")

    def test_hidden_authors_off(self):
        c = self.core
        c.cfg["lists"]["hide_members"] = "off"
        self.assertEqual(c._hidden_authors(), frozenset())
        c.cfg["lists"]["hide_members"] = "exclusive"
        self.assertEqual(c._hidden_authors(), frozenset())
        c.cfg["lists"]["hide_members"] = "all"
        self.assertEqual(c._hidden_authors(), frozenset({"B"}))

    def test_people_waiting_to_go_in(self):
        c = self.core
        c.store.kv_set("list_pending", [["L2", "N", 9e12], ["L2", "X", 9e12]])
        with mock.patch.object(c, "_list_pending",
                               return_value=[["L2", "N", 0], ["L2", "X", 0]]):
            calls = []

            def account(acc_id):
                calls.append(acc_id)
                if acc_id == "X":
                    raise ApiError(404, "gone")
                return dict(BOB, id=acc_id)
            c.api.account = account
            got, _n = c.list_people("L2").result(timeout=T)
        self.assertEqual([a["id"] for a in got["accounts"]], ["N"])

    def test_into_a_list_and_out(self):
        c = self.core
        c.api.list_remove = boom(ApiError(404, "not in it"))
        self.assertEqual(c.set_in_list("L1", "B", False).result(timeout=T), "done")
        c.api.list_remove = boom(ApiError(500, "oops"))
        with self.assertRaises(ApiError):
            c.set_in_list("L1", "B", False).result(timeout=T)
        c.api.list_add = boom(ApiError(500, "oops"))
        with self.assertRaises(ApiError):
            c.set_in_list("L1", "N", True).result(timeout=T)

    def test_retry_pending_when_the_server_fails(self):
        c = self.core
        import time
        c.store.kv_set("list_pending", [["L1", "N", time.time()]])
        c.api.relationships = boom()
        c.api.list_add = boom(OSError("down"))
        c._retry_list_pending()
        self.assertEqual([p[1] for p in c.store.kv_get("list_pending")], ["N"])


class TagLanesTest(CoreCase):
    def test_saved_twice_added_dropped_and_read(self):
        c = self.connect()
        c.sync = mock.Mock()
        spec = taggroups.parse("#a #b")
        name = c.save_tag_group(spec).result(timeout=T)
        c.save_tag_group(spec, "мои").result(timeout=T)  # the same tags: replaced
        self.assertEqual(len(c.store.kv_get("tag_groups")), 1)
        new = c.add_tag_to_group(name, "#C").result(timeout=T)
        self.assertEqual(new, taggroups.lane_name(taggroups.parse("#a #b #c")))
        c.drop_tag_group(new).result(timeout=T)
        self.assertEqual(c.store.kv_get("tag_groups"), [])
        self.assertEqual(c.sync.record_setting.call_count, 4)
        st = dict(status("030", BOB, minute=30), tags=[{"name": "a"}])
        self.w.add(st)
        with mock.patch.object(type(c.api), "tag_timeline",
                               lambda self, tag, **k: [st] if tag == "a" else []):
            page = c.tag_group_timeline(spec).result(timeout=T)
        self.assertEqual([p["id"] for p in page], ["030"])


class ThreadsTest(CoreCase):
    user = {"lanes": {"enabled": ["home", "mentions", "subs"]}}

    def test_left_from_another_device(self):
        c = self.connect()
        c.store.quiet_set("010")
        c.apply_thread_state("010", "left")
        self.assertNotIn("010", c.store.quiet_roots())
        self.assertIn(("subs_changed", "010"), self.events)

    def test_mention_checks(self):
        c = self.connect()
        self.assertIsNone(c._mention_entry({"id": "n", "type": "follow"}))
        n = {"id": "n1", "type": "mention", "status": status("040", BOB, minute=40),
             "created_at": "2026-01-01T00:00:00Z"}
        with mock.patch("fedtail.core.subs.silenced", boom()), \
                self.assertLogs("fedtail.core.app", "WARNING"):
            self.assertIsNotNone(c._mention_entry(n))  # never lost to a failing check
        c._silence_seen = {str(i): None for i in range(2001)}
        n2 = dict(n, status=status("041", BOB, minute=41))
        self.assertIsNotNone(c._mention_entry(n2))
        self.assertEqual(len(c._silence_seen), 1)  # the cache started over

    def test_auto_subscribe_that_fails(self):
        c = self.connect()
        with mock.patch("fedtail.core.subs.subscribe", boom()), \
                self.assertLogs("fedtail.core.app", "WARNING"):
            c._auto_subscribe([status("050", ME, minute=50)])


class FollowForActsTest(CoreCase):
    """30.10, the author: threads.auto takes my acts on someone's post too — "boosts",
    "likes", "bookmarks", "quotes", "votes": its thread followed, news from then on."""

    def test_each_act_follows_when_asked(self):
        c = self.connect()
        for i, sid in enumerate(("060", "061", "062", "063", "064")):
            self.w.add(status(sid, BOB, minute=60 + i, vis="public"), home=True)
        self.w.statuses["064"]["poll"] = {"id": "P64", "options": [{"title": "a"}],
                                          "expired": False, "voted": False}
        c.poll_once()
        get = c.store.get_status
        c.favourite(get("060")).result(timeout=T)  # not asked: nothing followed
        self.assertFalse(c.subscribed(get("060")))
        c.cfg["subs"]["auto"] = ["posts", "comments", "boosts", "likes", "bookmarks",
                                 "quotes", "votes"]
        c.favourite(get("060")).result(timeout=T)  # unliked now: nothing
        self.assertFalse(c.subscribed(get("060")))
        c.favourite(get("060")).result(timeout=T)  # liked
        c.boost(get("061")).result(timeout=T)
        c.bookmark(get("062"), True).result(timeout=T)
        c.post("look", "public", quote="063").result(timeout=T)
        c.vote(dict(self.w.statuses["064"]), [0]).result(timeout=T)
        for sid in ("060", "061", "062", "063", "064"):
            self.assertTrue(c.subscribed(get(sid) or {"id": sid}), sid)


class WatchRepliesTest(CoreCase):
    """30.10, the author: "follow replies to all posts of someone" — who answers a bot
    of his. Rare: off by default, not even the button; on — the latest posts' threads
    followed, and each new post's as the round brings it."""

    def test_the_button_the_latest_and_the_new(self):
        from fedtail.core.view import View
        from fedtail.frontends.common import profile as prof
        from fedtail.model import Account, Relationship
        c = self.connect()
        self.w.add(status("070", BOB, minute=70, vis="public"), home=True)
        self.w.add(status("071", BOB, "070", "B", minute=71, vis="public"), home=True)
        c.poll_once()
        acc = Account(ref=None, handle="bob", username="bob")
        keys = [a.key for a in prof.actions(acc, Relationship(), False, c.cfg,
                                            lambda _f: True)]
        self.assertNotIn("watch_replies", keys)  # off: no button at all
        c.cfg["feed"]["watch_replies"] = True
        keys = [a.key for a in prof.actions(acc, Relationship(), False, c.cfg,
                                            lambda _f: True)]
        self.assertIn("watch_replies", keys)
        view = View(c)
        self.assertTrue(view.watch_replies("B", True).result(timeout=T))
        self.assertTrue(c.subscribed(c.store.get_status("070")))  # the latest: at once
        self.assertTrue(view.relationship("B").result(timeout=T).watched_replies)
        later = status("079", BOB, minute=90, vis="public")
        later["created_at"] = "2099-12-31T00:00:00.000Z"  # after the watch began
        self.w.add(later, home=True)
        c.poll_once()
        self.assertTrue(c.subscribed(c.store.get_status("079")))  # new: as it comes
        view.watch_replies("B", False).result(timeout=T)
        self.assertFalse(view.relationship("B").result(timeout=T).watched_replies)


class ChoicesTest(CoreCase):
    user = {"feed": {"remember_choices": True}}

    def test_choices_kept_between_runs(self):
        c = self.connect()
        c.set_choice("posts_only:home", True)
        self.assertTrue(c.choice("posts_only:home"))
        self.assertTrue(c.get_state("posts_only:home"))

    def test_scheduled_cancel(self):
        c = self.connect()
        self.w.scheduled = [{"id": "S"}]
        c.cancel_scheduled("S").result(timeout=T)
        self.assertEqual(self.w.scheduled, [])


if __name__ == "__main__":
    unittest.main()
