"""Core tests. No network, no display:  python3 -m unittest -v"""

import os
import sqlite3
import stat
import tempfile
import unittest
from pathlib import Path

from fedtail.core import auth, config, model, paths, threads
from fedtail.core.api import ApiError, capabilities_from_instance
from fedtail.core.app import Core
from fedtail.core.store import Store

from . import fakes
from .fakes import BOB, ME, NEWS, FakeApi, status


class TmpDir(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()


class ConfigTest(TmpDir):
    def test_defaults_and_example_written(self):
        p = self.tmp / "c" / "config.toml"
        cfg, warns = config.load(p)
        self.assertTrue(p.exists())
        self.assertEqual(cfg["post"]["default_visibility"], "private")
        self.assertEqual(warns, [])

    def test_example_is_all_defaults(self):
        # every commented line in the example must match the real default
        import tomllib
        text = "\n".join(line[1:] if line.startswith("#") and "=" in line and
                         not line.startswith("# ") else line
                         for line in config.example_text().splitlines())
        parsed = tomllib.loads(text)
        cfg, warns = config.validate(parsed)
        self.assertEqual(warns, [])
        self.assertEqual(cfg, config.DEFAULTS)

    def test_errors_and_warnings(self):
        with self.assertRaises(config.ConfigError) as e:
            config.validate({"feed": {"order": "sideways", "page_size": "10"},
                             "poll": {"interval_seconds": 5}})
        msg = str(e.exception)
        self.assertIn("feed.order", msg)
        self.assertIn("feed.page_size", msg)
        self.assertIn("poll.interval_seconds", msg)
        _, warns = config.validate({"nope": {}, "ui": {"colour": 1}})
        self.assertEqual(len(warns), 2)
        with self.assertRaises(config.ConfigError):
            config.validate({"lanes": {"enabled": ["people", "tiktok"]}})
        with self.assertRaises(config.ConfigError):
            config.validate({"ui": {"close_to_tray": 1}})  # int is not bool


class PathsAuthTest(TmpDir):
    def test_profiles(self):
        os.environ["XDG_CONFIG_HOME"] = str(self.tmp / "cfg")
        os.environ["XDG_DATA_HOME"] = str(self.tmp / "data")
        p = paths.resolve()
        self.assertEqual(p.config_file, self.tmp / "cfg/fedtail/default/config.toml")
        p = paths.resolve("croco")
        self.assertEqual(p.data_dir, self.tmp / "data/fedtail/croco")
        p = paths.resolve("x", config=str(self.tmp / "my.toml"), data=str(self.tmp / "d"))
        self.assertEqual(p.data_dir, self.tmp / "d")
        with self.assertRaises(ValueError):
            paths.resolve("../etc")

    def test_auth_file_is_private(self):
        f = self.tmp / "auth.json"
        auth.save(f, {"server": "https://x", "token": "t"})
        self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
        self.assertEqual(auth.load(f)["token"], "t")
        auth.forget(f)
        self.assertIsNone(auth.load(f))


class ModelTest(unittest.TestCase):
    def test_visibility_and_mentions(self):
        self.assertEqual(model.narrower("public", "private"), "private")
        self.assertEqual(model.narrower("direct", "private"), "direct")
        p = status("1", BOB)
        p["mentions"] = [{"acct": "veresk"}, {"acct": "alice@x.y"}, {"acct": "BOB@mastodon.social"}]
        self.assertEqual(model.reply_mentions(p, "veresk"), "@bob@mastodon.social @alice@x.y ")
        self.assertTrue(model.is_bot(NEWS))
        self.assertTrue(model.is_bot(BOB, ["@Bob@Mastodon.social"]))

    def test_capabilities(self):
        c = capabilities_from_instance({"version": "4.3.0", "configuration": {}})
        self.assertFalse(c.markdown)
        c = capabilities_from_instance(FakeApi().instance())
        self.assertTrue(c.markdown)
        self.assertEqual(c.max_media, 10)


class ThreadTest(unittest.TestCase):
    def test_tree_numbering_and_orphans(self):
        root = status("r", ME, minute=1)
        a = status("a", BOB, "r", "ME", minute=2)
        b = status("b", ME, "a", "B", minute=3)
        c = status("c", BOB, "r", "ME", minute=4)
        lost = status("z", BOB, "gone", "X", minute=5)
        nodes = threads.build(b, {"ancestors": [root, a], "descendants": [c, lost]})
        self.assertEqual([(n.status["id"], n.depth, n.number) for n in nodes],
                         [("r", 0, 0), ("a", 1, 1), ("b", 2, 2), ("c", 1, 3), ("z", 1, 4)])

    def test_deep_thread(self):
        chain = [status("0", ME)] + [status(str(i), BOB, str(i - 1), "X") for i in range(1, 3000)]
        nodes = threads.build(chain[-1], {"ancestors": chain[:-1], "descendants": []})
        self.assertEqual(nodes[-1].depth, 2999)


class StoreTest(TmpDir):
    def test_items_read_drafts(self):
        s = Store(self.tmp / "s.db")
        sts = [status(str(i), BOB, minute=i) for i in range(1, 6)]
        new = s.put_items("home", [(x["id"], x, x["created_at"]) for x in sts])
        self.assertEqual(len(new), 5)
        self.assertEqual(s.put_items("home", [(sts[0]["id"], sts[0], sts[0]["created_at"])]), [])
        self.assertEqual(s.newest_item("home"), "5")
        self.assertEqual(s.oldest_item("home"), "1")
        self.assertEqual([i for i, _ in s.items("home", 3)], ["3", "4", "5"])
        s.mark_read(["1", "2"])
        self.assertEqual(s.read_set(["1", "2", "3"]), {"1", "2"})
        s.save_draft("new", {"text": "привет"})
        self.assertEqual(s.get_draft("new")["text"], "привет")
        s.prune("home", 2)
        self.assertEqual(s.count_items("home"), 2)
        s.close()


class StoreLockTest(TmpDir):
    def test_failed_begin_releases_lock(self):
        import threading
        s = Store(self.tmp / "s.db")
        s.db.execute("BEGIN")  # simulate a dangling transaction
        with self.assertRaises(sqlite3.OperationalError):
            s.mark_read(["1"])
        s.db.execute("ROLLBACK")
        done = []
        t = threading.Thread(target=lambda: (s.mark_read(["2"]), done.append(1)))
        t.start()
        t.join(2)
        self.assertEqual(done, [1])  # another thread can still get the lock
        s.close()


class CoreTest(TmpDir):
    def make(self, **over):
        FakeApi.world = fakes.World()
        user = {"feed": {"first_run_mark_read": False, "page_size": 3}}
        for k, v in over.items():
            user.setdefault(k, {}).update(v)
        cfg, _ = config.validate(user)
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        self.events = []
        core.events.on("*", lambda n, pl: self.events.append((n, pl)))
        self.addCleanup(core.shutdown)
        return core, FakeApi.world

    def test_catch_up_forward_without_holes(self):
        core, w = self.make()
        for i in range(1, 5):
            w.add(status(f"{i:03d}", BOB, minute=i), home=True)
        core.connect().result()
        core.poll_once()
        self.assertEqual(len(core.lane_entries("people")), 3)  # first fetch = one page
        for i in range(5, 13):
            w.add(status(f"{i:03d}", BOB, minute=i), home=True)
        core.poll_once()
        ids = [st["id"] for _, st in core.lane_entries("people")]
        self.assertEqual(ids, [f"{i:03d}" for i in range(2, 13)])  # 005..012 fetched in pages
        self.assertTrue(any(c[2] for c in w.calls if c[0] == "home"))  # used min_id
        core.load_older("people").result()
        ids = [st["id"] for _, st in core.lane_entries("people")]
        self.assertEqual(ids[0], "001")
        self.assertIn("001", core.store.read_set(["001"]))  # history counts as read

    def test_lanes_split_and_notify(self):
        core, w = self.make()
        core.connect().result()
        core.poll_once()  # first run: nothing to notify
        w.add(status("010", BOB, minute=10), home=True)
        w.add(status("011", NEWS, minute=11), home=True)
        mine = w.add(status("012", ME, minute=12), home=True)
        w.add(status("013", BOB, mine["id"], "ME", minute=13), home=True, mention=True)
        w.add(status("014", BOB, "xxx", "SOMEONE", minute=14), mention=True)
        core.poll_once()
        people = [st["id"] for _, st in core.lane_entries("people")]
        self.assertEqual(people, ["010", "012", "013"])
        self.assertEqual([st["id"] for _, st in core.lane_entries("bots")], ["011"])
        self.assertEqual([st["id"] for _, st in core.lane_entries("comments")], ["013"])
        self.assertEqual([st["id"] for _, st in core.lane_entries("mentions")], ["014"])
        self.assertIn("012", core.store.read_set(["012"]))  # my own post is read
        notes = [e for e in self.events if e[0] == "notify"]
        self.assertEqual(sorted(s["id"] for _, s in notes[0][1]), ["013", "014"])
        self.assertEqual(core.parent_of(core.store.get_status("014")), "missing")
        self.assertEqual(core.parent_of(core.store.get_status("013"))["id"], "012")

    def test_mentions_ordered_by_post_time(self):
        core, w = self.make()
        core.connect().result()
        mine = w.add(status("020", ME, minute=1), home=True)
        late = status("021", BOB, mine["id"], "ME", minute=5)
        early = status("022", BOB, mine["id"], "ME", minute=3)
        w.add(late, mention=True)   # notification for the later post arrives first
        w.add(early, mention=True)  # the earlier post federates late
        w.notifications[-2]["created_at"] = "2099-10-14T10:06:00.000Z"
        w.notifications[-1]["created_at"] = "2099-10-14T10:07:00.000Z"
        core.poll_once()
        self.assertEqual([st["id"] for _, st in core.lane_entries("comments")], ["022", "021"])

    def test_lane_cache_invalidates(self):
        core, w = self.make()
        core.connect().result()
        w.add(status("030", BOB, minute=1), home=True)
        core.poll_once()
        first = core.lane_entries("people")
        self.assertIs(core.lane_entries("people"), first)  # cached
        core.favourite(first[0][1]).result()
        self.assertTrue(core.lane_entries("people")[0][1]["favourited"])

    def test_first_run_mark_read(self):
        core, w = self.make(feed={"first_run_mark_read": True})
        w.add(status("001", BOB, minute=1), home=True)
        core.connect().result()
        core.poll_once()
        self.assertEqual(core.unread_count("people"), 0)
        w.add(status("002", BOB, minute=2), home=True)
        core.poll_once()
        self.assertEqual(core.unread_count("people"), 1)
        core.mark_read(["002"])
        self.assertEqual(core.unread_count("people"), 0)

    def test_post_reply_visibility_and_actions(self):
        core, w = self.make()
        parent = w.add(status("050", BOB, minute=1, vis="private"), home=True)
        core.connect().result()
        self.assertEqual(core.reply_visibility(None), "private")
        self.assertEqual(core.reply_visibility(dict(parent, visibility="direct")), "direct")
        core.save_draft("reply:050", {"text": "**hi**"})
        st = core.post("**hi**", "private", reply_to="050", draft_key="reply:050").result()
        self.assertIsNone(core.get_draft("reply:050"))  # dropped by the core itself
        self.assertEqual(w.posted[-1], ("**hi**", "private", "050", True))  # GtS → markdown
        core.favourite(parent).result()
        self.assertTrue(core.store.get_status("050")["favourited"])
        core.delete(st).result()
        self.assertIsNone(core.store.get_status(st["id"]))
        nodes = core.thread("050").result()
        self.assertEqual(nodes[0].status["id"], "050")

    def test_markdown_flag_override(self):
        core, w = self.make(account={"markdown": "off"})
        core.connect().result()
        core.post("x", "private").result()
        self.assertFalse(w.posted[-1][3])

    def test_login(self):
        core, w = self.make()
        auth.forget(core.paths.auth_file)
        core.auth = None
        url = core.begin_login("example.test").result()
        self.assertIn("oauth/authorize", url)
        with self.assertRaises(ApiError):
            core.finish_login("bad").result()
        core.finish_login("good").result()
        self.assertEqual(auth.load(core.paths.auth_file)["acct"], "veresk")

    def test_auth_failure_event(self):
        core, w = self.make()
        core.connect().result()
        w.fail_auth = True
        w.home = None  # home() will blow up; make it an auth error instead

        def boom(**kw):
            raise ApiError(401, "expired")
        core.sources["home"].fetch = boom
        core.poll_once()
        self.assertTrue(any(e[0] == "auth_failed" for e in self.events))


if __name__ == "__main__":
    unittest.main()
