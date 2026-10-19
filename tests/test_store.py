import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
