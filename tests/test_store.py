import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from fedtail.core.app import KEEP_FLOOR, next_keep
from fedtail.core.store import Store


class IterItemsTest(unittest.TestCase):
    def test_chunks_follow_on_without_gaps_or_repeats(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(Path(d) / "s.db")
            store.put_statuses([{"id": f"{i:03d}"} for i in range(9)])
            with store.lock:  # equal sort keys across a chunk border: both kept, in order
                for i in range(9):
                    store.db.execute("INSERT INTO items(source, item_id, status_id, sort) "
                                     "VALUES ('home', ?, ?, ?)",
                                     (f"{i:03d}", f"{i:03d}", "x" if i in (3, 4, 5) else
                                      f"{i:03d}"))
            got = [item for item, _st in store.iter_items("home", chunk=2)]
            self.assertEqual(sorted(got), [f"{i:03d}" for i in range(9)])
            self.assertEqual(len(got), len(set(got)))
            self.assertEqual(got[:3], ["005", "004", "003"])  # "x" sorts above the digits
            self.assertEqual(len(list(store.iter_items("home", chunk=2, max_rows=4))), 4)
            store.close()


def _st(sid, reply_to=None, author="a", **extra):
    return {"id": sid, "created_at": "2026-01-01T00:00:00.000Z", "in_reply_to_id": reply_to,
            "account": {"id": author, "acct": author}, **extra}


class GcTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.store = Store(Path(self._tmp.name) / "s.db")
        self.addCleanup(self.store.close)
        self.store.me_id = "me"

    def age(self):
        """Every stored post as if stored long ago: only references keep them."""
        with self.store.lock:
            self.store.db.execute("UPDATE statuses SET touched='2000-01-01T00:00:00.000000Z'")

    def ids(self):
        with self.store.lock:
            return {r[0] for r in self.store.db.execute("SELECT id FROM statuses")}

    def test_keeps_what_is_pointed_at_and_drops_the_rest(self):
        s = self.store
        root, mid = _st("01"), _st("02", reply_to="01")
        boost = _st("10", reblog=_st("03", reply_to="02"))
        quote = _st("11", quote={"state": "accepted", "quoted_status_id": "04"})
        s.put_statuses([root, mid, _st("04"), _st("05"), _st("06"), _st("07"),
                        _st("08", author="me"), _st("09")])
        s.put_items("home", [("10", boost, boost["created_at"]),
                             ("11", quote, quote["created_at"])])
        s.save_draft("reply:06", {"text": "…"})
        s.activity_put([{"id": "n1", "type": "favourite", "account": {"id": "x"},
                         "status": _st("07"), "created_at": "2026-01-01T00:00:00.000Z"}])
        with s.lock:
            s.db.execute("INSERT INTO kv VALUES ('replies_checked:09', '1')")
            s.db.execute("INSERT INTO kv VALUES ('replies_checked:01', '1')")
            s.db.execute("INSERT INTO missing VALUES ('zz')")
        self.age()
        got = s.gc(keep_activity=10, grace_hours=1)
        # boost and its post, up the thread; the quoted post; the draft's parent;
        # the activity's post; my own post
        self.assertEqual(self.ids(), {"10", "03", "02", "01", "11", "04", "06", "07", "08"})
        self.assertEqual(got["statuses"], 2)  # 05 and 09
        self.assertIsNone(s.kv_get("replies_checked:09"))
        self.assertEqual(s.kv_get("replies_checked:01"), 1)
        self.assertFalse(s.is_missing("zz"))  # nobody answers to it any more

    def test_recently_stored_posts_stay_for_the_grace_time(self):
        self.store.put_statuses([_st("01")])
        self.store.gc(grace_hours=48)
        self.assertEqual(self.ids(), {"01"})
        self.age()
        self.store.gc(grace_hours=48)
        self.assertEqual(self.ids(), set())

    def test_activity_keeps_the_newest(self):
        s = self.store
        s.activity_put([{"id": f"n{i}", "type": "follow", "account": {"id": "x"},
                         "created_at": f"2026-01-0{i}T00:00:00.000Z"} for i in range(1, 6)])
        s.gc(keep_activity=2)
        with s.lock:
            left = {r[0] for r in s.db.execute("SELECT id FROM activity")}
        self.assertEqual(left, {"n4", "n5"})

    def test_read_marks_go_only_when_asked(self):
        s = self.store
        s.put_statuses([_st("01")])
        s.mark_read(["01"])
        self.age()
        s.gc()
        self.assertEqual(s.read_set(["01"]), {"01"})
        s.gc(drop_read=True)
        self.assertEqual(s.read_set(["01"]), set())

    def test_short_ids_outlive_their_posts(self):
        s = self.store
        s.put_statuses([_st("01")])
        alias = s.aliases(["01"])["01"]
        self.age()
        s.gc()
        self.assertEqual(s.by_alias(alias), "01")

    def test_file_gives_space_back(self):
        s = self.store
        s.put_statuses([_st(f"{i:05d}", content="x" * 4000) for i in range(2000)])
        with s.lock:
            pages = s.db.execute("PRAGMA page_count").fetchone()[0]
        self.age()
        s.gc()
        with s.lock:
            self.assertLess(s.db.execute("PRAGMA page_count").fetchone()[0], pages / 4)


class MigrationV5Test(unittest.TestCase):
    def test_old_file_gets_touched_and_incremental_vacuum(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            path = Path(d) / "s.db"
            db = sqlite3.connect(path)
            db.executescript(
                "CREATE TABLE statuses (id TEXT PRIMARY KEY, data TEXT NOT NULL, "
                "created_at TEXT NOT NULL, reply_to TEXT, author TEXT);"
                "CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);")
            db.execute("INSERT INTO statuses VALUES ('01', ?, '', NULL, 'a')",
                       (json.dumps(_st("01")),))
            db.execute("INSERT INTO kv VALUES ('schema', '4')")
            db.commit()
            db.close()
            store = Store(path)
            try:
                with store.lock:
                    self.assertEqual(store.db.execute("PRAGMA auto_vacuum").fetchone()[0], 2)
                    touched = store.db.execute("SELECT touched FROM statuses").fetchone()[0]
                self.assertTrue(touched.startswith("20"))
                store.gc(grace_hours=1)
                self.assertIsNotNone(store.get_status("01"))  # migrated as stored just now
            finally:
                store.close()


class NextKeepTest(unittest.TestCase):
    def test_over_budget_cuts_down_to_the_floor(self):
        self.assertEqual(next_keep(1100, 1024, 3000, 3000), 2100)
        self.assertEqual(next_keep(1100, 1024, KEEP_FLOOR, 3000), KEEP_FLOOR)

    def test_grows_back_when_roomy_and_never_past_the_config(self):
        self.assertEqual(next_keep(100, 1024, 1000, 3000), 1300)
        self.assertEqual(next_keep(100, 1024, 2900, 3000), 3000)
        self.assertEqual(next_keep(800, 1024, 1000, 3000), 1000)
        self.assertEqual(next_keep(100, 1024, 3000, 2000), 2000)


if __name__ == "__main__":
    unittest.main()
