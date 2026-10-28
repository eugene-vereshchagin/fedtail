"""One object per post for the whole program (docs/en/dev/memory.md, step 1): the store
parses a stored status once and hands the same, read-only object to every lane."""

import copy
import json
import pickle
import tempfile
import unittest
from pathlib import Path

from fedtail.core.store import Frozen, Store
from tests.fakes import BOB, status


class IdentityTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        self.store = Store(Path(tmp.name) / "s.db")
        self.addCleanup(self.store.close)

    def test_one_object_for_every_reader(self):
        st = status("10", BOB, text="hello")
        self.store.put_items("home", [("10", st, "")])
        self.store.put_items("local", [("10", st, "")])
        a = self.store.get_status("10")
        b = dict(self.store.items("home", 10))["10"]
        c = next(s for _i, s in self.store.iter_items("local"))
        d = self.store.get_statuses(["10"])["10"]
        self.assertIs(a, b)
        self.assertIs(a, c)
        self.assertIs(a, d)
        self.assertIsInstance(a, dict)  # what every reader checks
        self.assertIsInstance(a["account"], Frozen)  # nested ones too

    def test_a_changed_post_is_a_new_object(self):
        self.store.put_items("home", [("10", status("10", BOB, text="one"), "")])
        a = self.store.get_status("10")
        self.store.put_items("home", [("10", status("10", BOB, text="two"), "")])
        b = self.store.get_status("10")
        self.assertIsNot(a, b)
        self.assertIn("two", b["content"])
        self.store.delete_status("10")
        self.assertIsNone(self.store.get_status("10"))

    def test_shared_so_read_only(self):
        self.store.put_items("home", [("10", status("10", BOB), "")])
        st = self.store.get_status("10")
        for change in (lambda: st.__setitem__("x", 1), lambda: st.update(x=1),
                       lambda: st.pop("id"), lambda: st.setdefault("x", 1),
                       lambda: st.__delitem__("id"), lambda: st["account"].clear()):
            with self.assertRaises(TypeError):
                change()
        mine = dict(st)
        mine["x"] = 1  # a copy is anyone's
        deep = copy.deepcopy(st)
        deep["account"]["id"] = "other"
        self.assertEqual(type(deep["account"]), dict)
        self.assertEqual(type(copy.copy(st)), dict)
        self.assertEqual(type(pickle.loads(pickle.dumps(st))), dict)
        self.assertEqual(json.dumps(st), json.dumps(dict(st)))  # it is written as any dict

    def test_kept_only_while_held(self):
        import gc
        self.store.put_items("home", [(f"{i:03d}", status(f"{i:03d}", BOB), "")
                                      for i in range(25)])
        held = [self.store.get_status(f"{i:03d}") for i in range(25)]
        self.assertEqual(len(self.store._parsed), 25)
        del held[5:]
        gc.collect()
        self.assertEqual(len(self.store._parsed), 5)


if __name__ == "__main__":
    unittest.main()
