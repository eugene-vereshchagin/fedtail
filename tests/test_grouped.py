"""The server's grouped notifications (Mastodon 4.3+, /api/v2/notifications): flattened
to one notification per group, one Activity row per group that the group's next answer
replaces, hidden by its key, counted in the rows; GoToSocial's 404 means one by one."""

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from fedtail.core.store import Store
from fedtail.frontends.common import activity as act
from fedtail.protocols.mastodon import adapter
from fedtail.protocols.mastodon.api import ApiError, flatten_groups

from . import fakes
from .fakes import BOB, ME, NEWS, status


def acc(i):
    return dict(BOB, id=f"A{i}", acct=f"p{i}@social.example", username=f"p{i}",
                display_name=f"P{i}")


def answer(groups, statuses=()):
    people = {}
    for g in groups:
        for a in g.pop("_people", ()):
            people[a["id"]] = a
        g["sample_account_ids"] = list(g.get("sample_account_ids") or ())
    return {"accounts": list(people.values()), "statuses": list(statuses),
            "notification_groups": groups}


def group(key, newest, count, people, kind="favourite", sid=None, minute=0):
    return {"group_key": key, "notifications_count": count, "type": kind,
            "most_recent_notification_id": newest, "page_min_id": newest,
            "page_max_id": newest,
            "latest_page_notification_at": f"2099-10-14T11:{minute:02d}:00.000Z",
            "sample_account_ids": [a["id"] for a in people], "status_id": sid,
            "_people": people}


class FlattenTest(unittest.TestCase):
    def test_one_notification_per_group(self):
        st = status("500", ME, minute=1)
        people = [acc(i) for i in range(3)]
        got = flatten_groups(answer([group("favourite-500", "n9", 300, people, sid="500",
                                           minute=9),
                                     group("ungrouped-n3", "n3", 1, [BOB], kind="mention",
                                           minute=3)], [st]))
        self.assertEqual([n["id"] for n in got], ["n9", "n3"])
        self.assertEqual(got[0]["account"]["id"], "A0")  # the newest of the sample
        self.assertEqual(got[0]["status"]["id"], "500")
        self.assertEqual(got[0]["_group"]["count"], 300)
        self.assertEqual([a["id"] for a in got[0]["_group"]["accounts"]], ["A0", "A1", "A2"])
        self.assertNotIn("status", got[1])
        self.assertEqual(flatten_groups(None), [])
        a = adapter.activity(got[0])
        self.assertEqual((a.count, len(a.people), a.group_key), (300, 3, "favourite-500"))


class StoreGroupsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.s = Store(Path(self.tmp.name) / "s.db")

    def tearDown(self):
        self.s.close()
        self.tmp.cleanup()

    def put(self, *groups):
        return self.s.activity_put(flatten_groups(answer(list(groups))))

    def test_a_group_is_one_row_the_newest(self):
        new = self.put(group("favourite-500", "n2", 2, [acc(1), acc(0)], minute=2))
        self.assertEqual(len(new), 1)
        self.assertEqual(self.s.activity_group_of("n2"), "favourite-500")
        # the next like: the same group under its newest notification's id
        new = self.put(group("favourite-500", "n5", 3, [acc(2), acc(1), acc(0)], minute=5))
        self.assertEqual(len(new), 1)
        rows = self.s.activity_recent(10)
        self.assertEqual([r["id"] for r in rows], ["n5"])
        self.assertEqual(rows[0]["account"]["_group"]["count"], 3)
        self.assertEqual(self.s.activity_newest()[0], "n5")  # paging goes on from it
        self.assertEqual(self.s.activity_group_of("nope"), "")

    def test_hidden_group_stays_hidden(self):
        self.put(group("reblog-7", "n4", 2, [acc(1), acc(0)], kind="reblog", minute=4))
        self.s.activity_hide(["n4"])
        self.assertEqual(self.s.activity_recent(10), [])
        self.assertEqual(self.put(group("reblog-7", "n8", 3, [acc(2)], kind="reblog",
                                        minute=8)), [])
        self.assertEqual(self.s.activity_recent(10), [])
        # one by one (v1) as before: no group, no key
        self.s.activity_put([{"id": "n9", "type": "follow", "account": NEWS,
                              "created_at": "2099-10-14T11:09:00.000Z"}])
        self.assertEqual(self.s.activity_group_of("n9"), "")


class RowsTest(unittest.TestCase):
    def test_a_group_counts_whom_it_does_not_name(self):
        raw = flatten_groups(answer([group("favourite-500", "n9", 300,
                                           [acc(i) for i in range(5)], sid="500")],
                                    [status("500", ME)]))
        a = adapter.activity(raw[0])
        rows = act.rows([a], "", lambda d: d.strftime("%H:%M"))
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(len(r.people), min(5, act.MAX_NAMES))
        self.assertEqual(len(r.people) + r.more, 300)
        # activity.names_shown: how many it names, the rest counted
        [r] = act.rows([a], "", lambda d: "", names=1)
        self.assertEqual((len(r.people), r.more), (1, 299))

    def test_one_by_one_as_before(self):
        es = [adapter.activity({"id": f"n{i}", "type": "favourite", "account": acc(i),
                                "status": status("500", ME),
                                "created_at": datetime(2099, 1, 1).isoformat() + "Z"})
              for i in range(3)]
        r = act.rows(es, "", lambda d: "")[0]
        self.assertEqual(len(r.people) + r.more, 3)


class CoreGroupsTest(unittest.TestCase):
    def setUp(self):
        from .test_core import CoreTest
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.helper = CoreTest()
        self.helper.tmp = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def make(self):
        return self.helper.make()

    def test_groups_where_the_server_has_them(self):
        core, w = self.make()
        asked = []

        def groups(types, limit=40, max_id=None, min_id=None, **_kw):
            asked.append(min_id)
            likes = [n for n in fakes._page(w.activity, limit, max_id, min_id)
                     if n["type"] in types]
            if not likes:
                return []
            newest = max(likes, key=lambda n: n["id"])
            return flatten_groups(answer([group(
                "favourite-500", newest["id"], len(likes),
                [n["account"] for n in sorted(likes, key=lambda n: n["id"], reverse=True)],
                sid="500", minute=int(newest["created_at"][14:16]))],
                [status("500", ME)]))
        core.connect().result()
        core.caps.software = "mastodon"  # (the fake says GoToSocial, which has no groups)
        core.api.notification_groups = groups
        core.poll_once()  # history
        for i in range(3):
            w.act(f"n{i + 1}", "favourite", acc(i), status("500", ME), minute=i + 1)
        core.poll_once()
        rows = core.store.activity_recent(10)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["account"]["_group"]["count"], 3)
        self.assertTrue(asked)

    def test_one_by_one_where_it_has_none(self):
        core, w = self.make()

        def no(*_a, **_kw):
            raise ApiError(404, "Not Found")
        core.connect().result()
        core.caps.software = "mastodon"
        core.api.notification_groups = no
        core.poll_once()
        for i in range(3):
            w.act(f"n{i + 1}", "favourite", acc(i), status("500", ME), minute=i + 1)
        core.poll_once()
        self.assertEqual(len(core.store.activity_recent(10)), 3)
        self.assertFalse(core.supports("grouped"))
        core.cfg["activity"]["server_groups"] = False  # (and off by the config)
        core.poll_once()
