"""The store (core/store.py) beyond the everyday: counts for completion kept up to date
as posts come, odd aliases, the remembered hidden notifications trimmed to their cap,
dismissals from another device that name a whole server group, and the small
accessors the windows call."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fedtail.core import store as store_mod
from fedtail.core.store import Store


def st(i, acct="bob", tags=(), mentions=(), minute=0):
    return {"id": i, "created_at": f"2026-01-01T00:{minute:02d}:00.000Z", "content": i,
            "account": {"id": acct, "acct": acct, "display_name": acct.title()},
            "tags": [{"name": t} for t in tags],
            "mentions": [{"acct": m} for m in mentions]}


def note(i, kind="favourite", key="", minute=0, acc="bob"):
    n = {"id": i, "type": kind, "account": {"id": acc, "acct": acc},
         "created_at": f"2026-01-01T00:{minute:02d}:00.000Z"}
    if key:
        n["_group"] = {"key": key, "count": 2, "accounts": []}
    return n


class StoreEdgesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "s.db"
        self.s = Store(self.path)
        self.addCleanup(self.s.close)

    def test_private_on_windows_and_unchangeable_files(self):
        with mock.patch.object(os, "name", "nt"), mock.patch.object(os, "chmod") as ch:
            Store._private(self.path)
        ch.assert_not_called()
        with mock.patch.object(os, "chmod", side_effect=OSError("read-only fs")):
            Store._private(self.path)  # quietly left as it is

    def test_counts_follow_new_posts(self):
        self.assertIsNone(self.s.tag_counts(compute=False))
        self.s.put_statuses([st("1", tags=["georgianews"])])
        self.assertEqual(self.s.tag_counts()["georgianews"], ["georgianews", 1])
        self.assertEqual(self.s.people_counts()["bob"][2], 1)
        self.s.put_statuses([st("2", "ann", tags=["GeorgiaNews", ""], mentions=["bob", ""]),
                             {"id": "3", "created_at": "", "reblog": st("4", "cid")}])
        self.assertEqual(self.s.tag_counts()["georgianews"], ["GeorgiaNews", 2])
        people = self.s.people_counts()
        self.assertEqual(people["bob"][2], 2)  # posted once, mentioned once
        self.assertEqual(people["ann"][1], "Ann")
        self.assertEqual(people["cid"][2], 1)  # the author of the boosted post

    def test_odd_aliases(self):
        self.assertIsNone(self.s.by_alias("!!"))
        self.assertIsNone(self.s.by_alias("a"))
        self.assertIsNone(self.s.by_alias("abcdefghijk"))  # longer than any code
        self.assertIsNone(self.s.by_alias("abc-def"))

    def test_small_accessors(self):
        self.assertEqual(self.s.mark_mine_read(), 0)  # who "mine" is isn't known yet
        self.assertIsNone(self.s.left_root_of([None, ""]))
        self.s.quiet_set("q")
        self.s.sub_add("r", "", "", False, ["r"])
        self.s.sub_remove("r", members=["r", "x"])
        self.assertEqual(self.s.quiet_roots(), {"q"})
        self.assertEqual(self.s.quiet_roots(left_too=True), {"q", "r"})
        self.assertEqual(self.s.subs_count(), 0)
        self.s.save_draft("a", {"text": "one"})
        self.s.save_draft("b", {"text": "two"})
        self.assertEqual(sorted(k for k, _d, _u in self.s.list_drafts()), ["a", "b"])

    def test_groups_and_hidden_keep_their_cap(self):
        with mock.patch.object(store_mod, "GROUPS_KEEP", 2), \
                mock.patch.object(store_mod, "HIDDEN_KEEP", 2):
            self.s.activity_put([note(str(i), key=f"g{i}", minute=i) for i in range(4)])
            self.assertEqual(sorted(self.s.kv_get("activity_groups")), ["g2", "g3"])
            self.s.activity_hide(["0", "1", "2"])
            self.assertEqual(sorted(self.s.kv_get("activity_hidden")), ["1", "2"])
            self.assertEqual(sorted(self.s.kv_get("activity_hidden_groups")), ["g1", "g2"])
            # a hidden group stays hidden when it comes back under a new id
            self.assertEqual(self.s.activity_put([note("9", key="g2", minute=9)]), [])
            self.s.activity_hide_known([("x", "s1", "k1"), ("y", "s2", "k2"),
                                        ("z", "s3", "")])
            self.assertEqual(len(self.s.kv_get("activity_hidden")), 2)
            self.assertEqual(len(self.s.kv_get("activity_hidden_groups")), 2)

    def test_dismissed_elsewhere_by_group(self):
        self.assertFalse(self.s.activity_hide_known([]))
        self.s.activity_put([note("1", key="likes-of-5"), note("2", key="other"),
                             note("3")])
        # a row with an account that isn't JSON (an old database): left alone
        with self.s.lock:
            self.s.db.execute("UPDATE activity SET account='not json' WHERE id='3'")
        self.assertEqual(self.s.activity_group_of("3"), "")
        self.assertEqual(self.s.activity_group_of("nope"), "")
        self.assertTrue(self.s.activity_hide_known([("77", "s", "likes-of-5")]))
        with self.s.lock:
            left = {r[0] for r in self.s.db.execute("SELECT id FROM activity")}
        self.assertEqual(left, {"2", "3"})
        self.assertFalse(self.s.activity_hide_known([("78", "s", "unknown-group")]))

    def test_activity_keeps_the_servers_notices(self):
        n = dict(note("5", kind="severed_relationships"),
                 relationship_severance_event={"type": "domain_block"})
        self.s.activity_put([n])
        with self.s.lock:
            acc = self.s.db.execute("SELECT account FROM activity WHERE id='5'").fetchone()[0]
        self.assertEqual(json.loads(acc)["_notice"], {"type": "domain_block"})


if __name__ == "__main__":
    unittest.main()
