"""Core tests. No network, no display:  python3 -m unittest -v"""

import os
import sqlite3
import stat
import tempfile
import time
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
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)
        # a cleanup, not tearDown: it must run after the cores' shutdowns (registered
        # later, run earlier), or Windows refuses to delete their open databases
        self.addCleanup(self._tmp.cleanup)


class ConfigTest(TmpDir):
    def test_defaults_and_example_written(self):
        p = self.tmp / "c" / "config.toml"
        cfg, warns = config.load(p)
        self.assertTrue(p.exists())
        self.assertEqual(cfg["post"]["default_visibility"], "private")
        self.assertEqual(warns, [])

    def test_activity_all_and_the_reference_layout(self):
        cfg, _ = config.validate({"activity": {"types": ["all"]}})
        self.assertEqual(set(cfg["activity"]["types"]), config.ACTIVITY_TYPES)
        text = config.example_text()
        # every launch key of this version is listed at the top of the reference
        import re

        import fedtail.__main__ as main_mod
        src = Path(main_mod.__file__).read_text("utf-8")
        for key in re.findall(r'add_argument\((?:"-\w", )?"(--[a-z-]+)"', src):
            self.assertIn(key, text.split("[ui]")[0], key)
        # one option, one block: a blank line before the next explanation
        lines = text.splitlines()
        for i, line in enumerate(lines[:-1]):
            if re.match(r"^[a-z_]+ = ", line) and lines[i + 1].startswith("# "):
                self.fail(f"no blank line after {line!r}")
        # --update-config adds missing options the same way
        from fedtail.core import config_update
        out = config_update.update("[activity]\n", text)
        self.assertIn("\n\n# Что показывать в «Активности»", out)

    def test_example_is_all_defaults(self):
        # every option in the example is set to the real default
        import tomllib
        parsed = tomllib.loads(config.example_text())
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
        # the old ui.esc_hides: true gets the curtain (the new default), false stays off
        cfg, warns = config.validate({"ui": {"esc_hides": True}})
        self.assertEqual((cfg["ui"]["esc"], len(warns)), ("curtain", 1))
        cfg, _ = config.validate({"ui": {"esc_hides": False}})
        self.assertEqual(cfg["ui"]["esc"], "off")
        cfg, _ = config.validate({"lists": {"exclusive_hides": False}})
        self.assertEqual(cfg["lists"]["hide_members"], "off")
        with self.assertRaises(config.ConfigError):
            config.validate({"lanes": {"enabled": ["people", "tiktok"]}})
        with self.assertRaises(config.ConfigError):
            config.validate({"ui": {"close_to_tray": 1}})  # int is not bool


class ConfigUpdateTest(unittest.TestCase):
    def test_missing_and_update(self):
        import tomllib

        from fedtail.core import config_update as cu
        example = config.example_text()
        old = ("# my config\n[ui]\ntheme = \"terminal\"\n#language = \"auto\"\n\n"
               "[feed]\norder = \"newest_first\"\n")
        miss = cu.missing(old, example)
        self.assertIn("ui.actions", miss)
        self.assertIn("post.default_visibility", miss)
        self.assertNotIn("ui.theme", miss)
        self.assertNotIn("ui.language", miss)  # commented out still counts
        new = cu.update(old, example)
        self.assertEqual(cu.missing(new, example), [])
        parsed = tomllib.loads(new)  # still valid TOML, user values untouched
        self.assertEqual(parsed["ui"]["theme"], "terminal")
        self.assertEqual(parsed["feed"]["order"], "newest_first")
        self.assertEqual(config.validate(parsed)[1], [])
        self.assertLess(new.index("\nactions ="), new.index("\n[feed]"))  # inside [ui]
        self.assertEqual(cu.update(new, example), new)  # idempotent

    def test_rebuild_keeps_values_in_chapters(self):
        import tomllib

        from fedtail.core import config_update as cu
        example = config.example_text()
        old = ("# my notes\n[ui]\ntheme = \"bnw\"\n#font_size = 14\nwhatever = 3\n\n"
               "[notify]\nlanes = [\"comments\", \"list:Друзья\"]\n\n[mystery]\nx = \"y\"\n")
        report = {}
        new = cu.rebuild(old, example, report)
        parsed = tomllib.loads(new)
        self.assertEqual(parsed["ui"]["theme"], "bnw")
        self.assertEqual(parsed["ui"]["font_size"], 0)  # commented out: the default
        self.assertEqual(parsed["notify"]["lanes"], ["comments", "list:Друзья"])
        self.assertEqual(parsed["ui"]["whatever"], 3)
        self.assertEqual(parsed["mystery"], {"x": "y"})
        self.assertEqual(sorted(report["kept"]), ["notify.lanes", "ui.theme"])
        self.assertEqual(sorted(report["extra"]), ["mystery.x", "ui.whatever"])
        self.assertIn("Главы:", new)
        self.assertLess(new.index("whatever ="), new.index("\n[feed]"))
        self.assertEqual(cu.missing(new, example), [])
        self.assertEqual(cu.rebuild(new, example), new)  # stable

    def test_update_refreshes_explanations_keeps_user_lines(self):
        import tomllib

        from fedtail.core import config_update as cu
        example = config.example_text()
        old = ("# fedtail — конфиг профиля.\n# старая шапка\n\n[ui]\n"
               "# Тема — файл в ~/.config/fedtail/themes/<имя>.toml или встроенная:\n"
               "#   \"system\"   — светлая/тёмная, как в KDE;\n"
               "theme = \"point\"\n"
               "# Esc закрывает то, что сверху, а последний Esc сразу убирает окно\n"
               "#esc_hides = true\n"
               "# моя заметка: шрифт побольше\nfont_size = 12\n")
        report = {}
        new = cu.update(old, example, report)
        self.assertEqual(report["refreshed"], ["ui.theme"])
        self.assertEqual(report["dropped"], ["ui.esc_hides"])
        self.assertIn('"pink"', new)  # the themes of this version are listed now
        self.assertNotIn("esc_hides", new)
        self.assertNotIn("старая шапка", new)  # our header, refreshed
        self.assertIn("# моя заметка: шрифт побольше\nfont_size = 12", new)  # theirs stays
        parsed = tomllib.loads(new)
        self.assertEqual((parsed["ui"]["theme"], parsed["ui"]["font_size"]), ("point", 12))
        self.assertEqual(cu.update(new, example), new)


class MergedTest(TmpDir):
    """Two accounts in one window: the other one's ids prefixed, actions routed."""

    def setUp(self):
        super().setUp()
        from fedtail.core.merged import MergedCore
        FakeApi.world = home = fakes.World()
        work = fakes.World()
        work.me = dict(ME, id="W", acct="w", username="w")
        FakeApi.worlds = {"https://work.example": work}
        self.addCleanup(setattr, FakeApi, "worlds", {})
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False}})
        cores = []
        for name, server in (("home", "https://example.test"), ("work", "https://work.example")):
            p = paths.resolve(name, config=str(self.tmp / f"{name}.toml"),
                              data=str(self.tmp / name))
            auth.save(p.auth_file, {"server": server, "token": "tok"})
            core = Core(cfg, p, api_class=FakeApi)
            core._origin_json = lambda url: None
            self.addCleanup(core.shutdown)
            cores.append(core)
        self.home, self.work = home, work
        self.m = MergedCore(cores[0], {"work": cores[1]})
        self.events = []
        self.m.events.on("*", lambda n, pl: self.events.append((n, pl)))

    def test_lanes_merge_and_actions_route(self):
        m = self.m
        self.home.add(status("010", BOB, minute=10), home=True)
        shared = status("010", BOB, minute=10)  # the same post reached both accounts
        self.work.add(dict(shared, id="499"), home=True)
        self.work.add(status("500", NEWS, minute=11, text="через work"), home=True)
        self.work.add(status("501", BOB, minute=12, text="тоже через work"), home=True)
        for core in (m.primary, m.others["work"]):
            core.connect().result()
            core.poll_once()
        got = m.lane_entries("people")
        self.assertEqual([st["id"] for _i, st in got], ["010", "work~501"])  # bob, no dup
        self.assertEqual(got[1][1]["_via"], "@w")
        self.assertEqual(got[1][1]["account"]["id"], "work~B")
        self.assertEqual(m.unread_ids(got), {"010", "work~501"})
        self.assertEqual(m.unread_count("people"), 2)
        m.mark_read(["work~501"])
        self.assertEqual(m.unread_ids(got), {"010"})
        self.assertIn(("read_changed", ["work~501"]), self.events)  # translated back
        self.assertEqual(m.store.get_status("work~501")["id"], "work~501")
        # a like and a reply go from the account that got the post
        m.favourite(m.store.get_status("work~501")).result()
        self.assertTrue(self.work.statuses["501"]["favourited"])
        self.assertFalse(self.home.statuses["010"].get("favourited"))
        st = m.post("ответ", "private", reply_to="work~501").result()
        self.assertTrue(st["id"].startswith("work~"))
        self.assertEqual(self.work.posted[-1][2], "501")
        self.assertEqual(self.home.posted, [])
        m.post("новый пост", "private").result()  # new posts: the main account
        self.assertEqual(self.home.posted[-1][0], "новый пост")
        nodes = m.thread("work~501").result()
        self.assertTrue(all(n.status["id"].startswith("work~") for n in nodes))
        self.assertEqual(m.relationship("work~B").result()["id"], "B")


class PathsAuthTest(TmpDir):
    def test_profiles_listing(self):
        from fedtail.core import profiles
        os.environ["XDG_CONFIG_HOME"] = str(self.tmp / "cfg")
        os.environ["XDG_DATA_HOME"] = str(self.tmp / "data")
        self.addCleanup(os.environ.pop, "XDG_CONFIG_HOME")
        self.addCleanup(os.environ.pop, "XDG_DATA_HOME")
        home = paths.resolve()
        home.ensure()
        auth.save(home.auth_file, {"server": "https://social.example", "token": "SECRET"})
        profiles.remember(home, {"acct": "veresk", "display_name": "V"},
                          "https://social.example")
        work = paths.resolve("work")
        work.ensure()  # made, not logged in yet
        work.config_file.write_text("", encoding="utf-8")
        (self.tmp / "cfg/fedtail/themes").mkdir()   # the shared themes: not a profile
        (self.tmp / "cfg/fedtail/stray").mkdir()    # an empty folder: not one either
        got = profiles.listing()
        self.assertEqual([p["name"] for p in got], ["default", "work"])
        self.assertEqual(profiles.label(got[0]), "@veresk@social.example")
        self.assertEqual(profiles.label(got[1]), "work")
        self.assertEqual([p["logged_in"] for p in got], [True, False])
        card = (home.data_dir / profiles.CARD).read_text("utf-8")
        self.assertNotIn("SECRET", card)  # the card never holds the token
        argv, _cwd = profiles.command("work")
        self.assertEqual(argv[-2:], ["--profile", "work"])

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
        if os.name != "nt":  # Windows: the user's AppData is theirs, no mode bits
            self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)
        self.assertEqual(auth.load(f)["token"], "t")
        auth.forget(f)
        self.assertIsNone(auth.load(f))


class ModelTest(unittest.TestCase):
    def test_visibility_and_mentions(self):
        self.assertEqual(model.narrower("public", "private"), "private")
        self.assertEqual(model.narrower("direct", "private"), "direct")
        p = status("1", BOB)
        p["mentions"] = [{"acct": "veresk"}, {"acct": "alice@x.y"}, {"acct": "BOB@social.example"}]
        self.assertEqual(model.reply_mentions(p, "veresk"), "@bob@social.example @alice@x.y ")
        self.assertTrue(model.is_bot(NEWS))
        self.assertTrue(model.is_bot(BOB, ["@Bob@Social.example"]))

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


class AliasTest(TmpDir):
    def test_aliases(self):
        from fedtail.core.store import alias_number, alias_text
        self.assertEqual(alias_text(1), "a00")
        for n in (1, 2, 35, 36, 1000, 33696, 33697, 2_000_000):
            self.assertEqual(alias_number(alias_text(n)), n)
            self.assertTrue(alias_text(n)[0].isalpha())
        self.assertIsNone(alias_number("#!!"))
        s = Store(self.tmp / "a.db")
        a = s.aliases(["X", "Y"])
        self.assertEqual(s.aliases(["Y", "Z"])["Y"], a["Y"])  # stable
        self.assertEqual(len({*a.values(), s.aliases(["Z"])["Z"]}), 3)  # unique
        self.assertEqual(s.by_alias("#" + a["X"]), "X")
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
        core._origin_json = lambda url: None  # tests never reach other servers
        self.events = []
        core.events.on("*", lambda n, pl: self.events.append((n, pl)))
        self.addCleanup(core.shutdown)
        return core, FakeApi.world

    def test_emoji_suggestions(self):
        core, w = self.make()
        w.emoji = [{"shortcode": "blobcat"}, {"shortcode": "catjam"}, {"shortcode": "hidden_cat",
                                                                    "visible_in_picker": False},
                   {"shortcode": "dog"}]
        core.connect().result()
        self.assertEqual(core.emoji_suggestions("cat"), [])  # not fetched yet
        core.prepare_emoji()
        deadline = time.time() + 5
        while not core._emoji and time.time() < deadline:
            time.sleep(0.01)
        self.assertEqual([c for c, _e in core.emoji_suggestions("cat")], ["catjam", "blobcat"])
        self.assertEqual(core.emoji_suggestions(""), [])

    def test_featured_tags_and_people(self):
        core, w = self.make()
        core.connect().result()
        self.assertEqual(core.featured("B").result(), {"tags": [], "people": []})
        w.featured["B"] = {"tags": [{"name": "x"}], "people": [NEWS]}
        got = core.featured("B").result()
        self.assertEqual((got["tags"][0]["name"], got["people"][0]["id"]), ("x", "N"))

    def test_filtered_notifications(self):
        core, w = self.make()
        core.connect().result()
        self.assertIsNone(core.filtered().result())  # no such API: nothing to show
        w.policy = {"for_not_following": "accept", "for_new_accounts": "filter"}
        w.held = [{"id": "r1", "account": BOB, "notifications_count": "2"}]
        got = core.filtered().result()
        self.assertEqual(got["pending"], 1)
        self.assertEqual(got["policy"]["for_new_accounts"], "filter")
        core.answer_filtered("r1", True).result()
        self.assertEqual(w.answered, [("r1", True)])
        core.set_filter_policy(for_not_following="drop").result()
        self.assertEqual(w.policy["for_not_following"], "drop")
        with self.assertRaises(ValueError):
            core.set_filter_policy(for_everyone="drop")

    def test_announcements_not_read_oldest_first(self):
        core, w = self.make()
        w.announcements = [{"id": "2", "read": False, "published_at": "2099-01-02"},
                           {"id": "1", "read": False, "published_at": "2099-01-01"},
                           {"id": "0", "read": True}]
        core.connect().result()
        self.assertEqual([a["id"] for a in core.announcements().result()], ["1", "2"])
        core.dismiss_announcement("1").result()
        self.assertEqual([a["id"] for a in core.announcements().result()], ["2"])
        core.api.announcements = lambda: (_ for _ in ()).throw(ApiError(404, "no"))
        self.assertEqual(core.announcements().result(), [])
        core.cfg["ui"]["announcements"] = "off"
        self.assertEqual(core.announcements().result(), [])

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

    def test_honest_counters_on_thread_open(self):
        core, w = self.make(feed={"honest_counters": True})
        st = w.add(status("050", BOB, vis="public"), home=True)
        st["uri"] = "https://mastodon.social/users/bob/statuses/9"
        asked = []

        def origin(url):
            asked.append(url)
            return {"uri": st["uri"], "favourites_count": 12, "reblogs_count": 2,
                    "replies_count": 0}
        core._origin_get = origin
        core.connect().result()
        core.thread("050").result()
        deadline = time.time() + 5
        while core.store.get_status("050")["favourites_count"] != 12 and time.time() < deadline:
            time.sleep(0.01)  # the check runs in the background
        self.assertEqual(asked, ["https://mastodon.social/api/v1/statuses/9"])
        self.assertEqual(core.store.get_status("050")["favourites_count"], 12)
        core.thread("050").result()
        time.sleep(0.2)
        self.assertEqual(len(asked), 1)  # not again within ten minutes

    def test_people_tags_and_resolving(self):
        core, w = self.make()
        st = w.add(status("070", BOB, text="про #Linux и прочее"), home=True)
        core.connect().result()
        self.assertFalse(core.relationship("B").result()["following"])
        self.assertTrue(core.follow("B").result()["following"])
        self.assertEqual([s["id"] for s in core.tag_timeline("linux").result()], ["070"])
        self.assertEqual(core.resolve(st["url"]).result()[0], "status")
        self.assertEqual(core.resolve(BOB["url"]).result()[0], "account")
        self.assertIsNone(core.resolve("https://nowhere.example/@x").result())

    def test_search_people_and_tags(self):
        core, w = self.make()
        w.add(status("080", BOB), home=True)
        core.connect().result()
        res = core.search("bob").result()
        self.assertEqual([a["id"] for a in res["accounts"]], ["B"])
        self.assertFalse(res["relations"]["B"]["following"])
        core.follow("B").result()
        got, nxt = core.people("ME", "following").result()
        self.assertEqual([a["id"] for a in got["accounts"]], ["B"])
        self.assertIsNone(nxt)
        self.assertEqual([t["name"] for t in core.search("#lin").result()["hashtags"]], ["linux"])
        core.follow_tag("linux").result()
        self.assertTrue(core.tag_info("linux").result()["following"])
        self.assertEqual([t["name"] for t in core.followed_tags().result()], ["linux"])

    def test_browse_lanes_fetch_only_while_open(self):
        core, w = self.make()
        w.add(status("090", BOB), home=True)
        core.connect().result()
        core.poll_once()
        self.assertEqual(core.lane_entries("global"), [])  # not open: not fetched
        core.set_active_lane("global")
        core.poll_once()
        self.assertEqual([st["id"] for _, st in core.lane_entries("global")], ["090"])
        from fedtail.core import lanes
        groups = dict(lanes.grouped(core.lanes))
        self.assertEqual(groups["standard"], ["global", "people", "local", "bots"])
        self.assertEqual(groups["personal"][:4], ["mine", "direct", "mentions", "comments"])
        self.assertEqual([g for g, _n in lanes.grouped(core.lanes)][-1], "lists")

    def test_bookmarks(self):
        core, w = self.make()
        st = w.add(status("095", BOB), home=True)
        w.add(status("096", BOB, minute=5, text="old one"), home=True)
        w.statuses["096"]["bookmarked"] = True  # bookmarked from another client
        core.connect().result()
        core.poll_once()
        core.bookmark(st).result()  # here: shows at once
        self.assertEqual([s["id"] for _, s in core.lane_entries("bookmarks")], ["095"])
        core.set_active_lane("bookmarks")
        core.poll_once()  # the server's list joins in
        self.assertEqual(sorted(s["id"] for _, s in core.lane_entries("bookmarks")),
                         ["095", "096"])
        core.bookmark(core.store.get_status("095")).result()  # toggled off
        self.assertEqual([s["id"] for _, s in core.lane_entries("bookmarks")], ["096"])

    def test_followed_among_explains_home_replies(self):
        core, w = self.make()
        carol = fakes.acct("C", "carol@x.example")
        w.following.add("B")
        core.connect().result()
        got = core.followed_among([ME, BOB, carol, BOB]).result()
        self.assertEqual([a["id"] for a in got], ["B"])  # me left out, once each
        self.assertEqual(core.followed_among([ME]).result(), [])

    def test_new_replies_announced_for_open_threads(self):
        core, w = self.make()
        w.add(status("110", BOB, minute=1), home=True)
        core.connect().result()
        core.poll_once()
        seen = []
        core.events.on("arrived", lambda name, payload: seen.append((name, payload)))
        w.add(status("111", BOB, "110", "B", minute=2), home=True)
        core.poll_once()
        arrived = [p for n, p in seen if n == "arrived"]
        self.assertEqual(arrived, [[("111", "110")]])

    def test_follow_requests_event_only_on_change(self):
        core, w = self.make()
        core.connect().result()
        seen = []
        core.events.on("requests_updated", lambda name, payload: seen.append(len(payload)))
        core.poll_once()
        core.poll_once()
        self.assertEqual(seen, [0])  # the first look, then nothing new: quiet
        w.requests.append(fakes.acct("R", "reader@x.example"))
        core.poll_once()
        core.poll_once()
        self.assertEqual(seen, [0, 1])

    def test_thread_is_the_same_from_any_post(self):
        core, w = self.make()
        root = w.add(status("130", BOB, minute=1, vis="public"))
        w.add(status("131", NEWS, "130", "B", minute=2, vis="public"))   # branch one
        w.add(status("132", ME, "131", "N", minute=3, vis="public"))
        w.add(status("133", fakes.acct("H", "hub@x.example"), "130", "B", minute=4,
                      vis="public"))                                    # branch two
        core.connect().result()
        core.cfg["feed"]["complete_threads"] = False
        ids = lambda sid: [n.status["id"] for n in core.thread(sid).result()]
        # a server's context of 133 knows nothing of 131/132 (siblings): read from the top
        self.assertEqual(ids("133"), ids("132"))
        self.assertEqual(ids("133"), ["130", "131", "132", "133"])
        del root

    def test_thread_completed_from_the_origin(self):
        core, w = self.make()
        root = w.add(status("140", BOB, minute=1, vis="public"))
        root["uri"] = "https://far.example/objects/140"
        w.add(status("141", ME, "140", "B", minute=2, vis="public"))
        lost = status("142", fakes.acct("K", "kos@far.example"), "140", "B", minute=3,
                      vis="public")
        lost["uri"] = "https://far.example/objects/142"
        w.remote[lost["uri"]] = lost  # my server never got this one
        far = {"https://far.example/objects/140": {
            "id": "https://far.example/objects/140",
            "replies": {"type": "Collection", "first": {
                "type": "CollectionPage",
                "items": ["https://example.test/s/141", "https://far.example/objects/142"]}}}}
        asked = []
        core._origin_json = lambda url: asked.append(url) or far.get(url)
        grew = []
        core.events.on("thread_grew", lambda _n, p: grew.append(p))
        core.connect().result()
        first = [n.status["id"] for n in core.thread("141").result()]
        self.assertEqual(first, ["140", "141"])
        import time
        end = time.time() + 5
        while not grew and time.time() < end:  # the look runs in the background
            time.sleep(0.01)
        self.assertEqual(grew, ["140"])
        self.assertEqual([n.status["id"] for n in core.thread("141").result()],
                         ["140", "141", "142"])
        self.assertIn("https://far.example/objects/140", asked)
        # not again right away; never without the flag
        asked.clear()
        core.thread("141").result()
        time.sleep(0.2)
        self.assertEqual(asked, [])

    def test_polls_vote_and_refresh(self):
        core, w = self.make()
        st = w.add(status("120", BOB, minute=1, text="чай или кофе?"), home=True)
        st["poll"] = {"id": "P1", "expired": False, "multiple": False, "voted": False,
                      "own_votes": [], "votes_count": 3, "voters_count": 3,
                      "expires_at": "2099-01-01T00:00:00Z",
                      "options": [{"title": "чай", "votes_count": 2},
                                  {"title": "кофе", "votes_count": 1}]}
        core.connect().result()
        core.poll_once()
        got = []
        core.events.on("status_updated", lambda _n, p: got.append(p["id"]))
        voted = core.vote(core.store.get_status("120"), [1]).result()
        self.assertTrue(voted["poll"]["voted"])
        self.assertEqual(voted["poll"]["own_votes"], [1])
        self.assertEqual([o["votes_count"] for o in voted["poll"]["options"]], [2, 2])
        self.assertEqual(core.store.get_status("120")["poll"]["voters_count"], 4)  # stored
        self.assertEqual(got, ["120"])  # cards update everywhere
        with self.assertRaises(ApiError):
            core.vote(core.store.get_status("120"), [0]).result()  # once is enough
        w.statuses["120"]["poll"]["options"][0]["votes_count"] = 9  # others voted meanwhile
        fresh = core.refresh_poll(core.store.get_status("120")).result()
        self.assertEqual(fresh["poll"]["options"][0]["votes_count"], 9)

    def test_silence_mute_block_filters(self):
        core, w = self.make(ui={"arts_mode": False})
        w.add(status("100", BOB, minute=1), home=True)
        w.add(status("101", NEWS, minute=2), home=True)
        spam = w.add(status("102", fakes.acct("S", "spam@x.example"), minute=3), home=True)
        spam["filtered"] = [{"filter": {"id": "F1", "title": "крипта", "filter_action": "hide"},
                             "keyword_matches": ["крипта"]}]
        core.connect().result()
        core.poll_once()
        self.assertEqual([st["id"] for _, st in core.lane_entries("people")], ["100"])
        core.mute("B").result()  # gone from every lane at once
        self.assertEqual(core.lane_entries("people"), [])
        core.mute("B", False).result()
        core.block("N").result()
        self.assertEqual(core.lane_entries("bots"), [])
        self.assertEqual(w.blocked, {"N"})
        f = core.add_filter("шум", ["крипта", "nft"], "hide").result()
        self.assertEqual([x["title"] for x in core.filters().result()], ["шум"])
        core.delete_filter(f["id"]).result()
        self.assertEqual(core.filters().result(), [])
        w.muted.add("B")  # muted from another client: picked up on refresh
        core._silence_checked = None
        core.poll_once()
        self.assertEqual(core.lane_entries("people"), [])
        # arts mode: a server filter hides nothing; your own mutes and blocks still do
        self.assertTrue(core.silenced(spam))
        core.cfg["ui"]["arts_mode"] = True
        self.assertFalse(core.silenced(spam))
        self.assertTrue(core.silenced(w.statuses["100"]))  # B is still muted

    def test_edit_my_post(self):
        core, w = self.make()
        mine = w.add(status("110", ME, text="очепятка"), home=True)
        mine["media_attachments"] = [{"id": "m9", "type": "image", "url": "u"}]
        core.connect().result()
        self.assertEqual(core.source(mine).result()["text"], "очепятка")
        st = core.edit(mine, "опечатка", "", draft_key="edit:110").result()
        self.assertIn("опечатка", core.store.get_status("110")["content"])
        self.assertEqual([m["id"] for m in st["media_attachments"]], ["m9"])  # kept
        self.assertTrue(st.get("edited_at"))
        self.assertEqual(len(core.history(mine).result()), 2)

    def test_deep_find_extends_the_lane(self):
        core, w = self.make(feed={"render_limit": 20, "page_size": 40})
        for i in range(1, 41):
            w.add(status(f"{i:03d}", BOB, minute=i % 60, text="иголка" if i == 3 else "сено"),
                  home=True)
        core.connect().result()
        core.poll_once()  # all 40 stored, the lane shows the newest 20
        self.assertNotIn("003", [st["id"] for _, st in core.lane_entries("people")])
        res = core.deep_find("people", "ИГОЛКА").result()
        self.assertEqual(res, {"total": 1, "more": True})
        self.assertIn("003", [st["id"] for _, st in core.lane_entries("people")])
        self.assertEqual(core.deep_find("people", "нету").result(), {"total": 0, "more": False})

    def test_activity_favourites_boosts_follows(self):
        core, w = self.make()
        mine = w.add(status("100", ME, minute=1), home=True)
        w.act("a1", "favourite", BOB, mine, minute=1)  # history: seen already
        core.connect().result()
        core.poll_once()
        self.assertEqual(core.activity_unread(), 0)
        self.assertEqual(len(core.activity_entries()), 1)
        w.act("a2", "favourite", NEWS, mine, minute=2)
        w.act("a3", "reblog", BOB, mine, minute=3)
        w.act("a4", "follow", NEWS, minute=4)
        w.act("a5", "mention", BOB, mine, minute=5)  # not an activity kind
        core.poll_once()
        self.assertEqual(core.activity_unread(), 3)
        got = core.activity_entries()
        self.assertEqual([(x["type"], x["account"]["id"]) for x in got],
                         [("follow", "N"), ("reblog", "B"), ("favourite", "N"),
                          ("favourite", "B")])
        self.assertEqual(got[1]["status"]["id"], "100")
        notes = [e for e in self.events if e[0] == "notify"][-1][1]
        self.assertEqual(sorted(n["id"] for lane, n in notes if lane == "activity"),
                         ["a2", "a3", "a4"])
        core.mark_activity_seen()
        self.assertEqual(core.activity_unread(), 0)

    def test_lists_are_lanes_and_members_leave_general_lanes(self):
        core, w = self.make()
        w.lists["L1"] = {"title": "Новости", "exclusive": True, "members": {"N"}}
        core.connect().result()
        self.assertIn("list:L1", core.lane_by_name)
        self.assertEqual(core.lane_title("list:L1"), "Новости")
        w.add(status("010", BOB, minute=10), home=True)
        w.add(status("011", NEWS, minute=11), home=True)
        core.poll_once()
        self.assertEqual([st["id"] for _, st in core.lane_entries("list:L1")], ["011"])
        # in an exclusive list: gone from "bots", only its list shows it
        self.assertEqual(core.lane_entries("bots"), [])
        self.assertEqual([st["id"] for _, st in core.lane_entries("people")], ["010"])
        # somebody boosts a post of the list's member: that stays out of Home too
        boost = status("012", fakes.acct("Z", "zed@example.org"), minute=12)
        boost["reblog"] = w.statuses["011"]
        w.add(boost, home=True)
        core.poll_once()
        self.assertEqual([st["id"] for _, st in core.lane_entries("people")], ["010"])

        # a new list with bob in it, from a post's menu
        x = core.create_list("Друзья", add="B").result()
        self.assertIn(f"list:{x['id']}", core.lane_by_name)
        self.assertEqual(core.lists_of("B"), {x["id"]})
        # in any list (lists.hide_members = "all"): gone from Home too, read in the list
        self.assertEqual(core.lane_entries("people"), [])
        core.poll_once()  # the new list's timeline comes with the next poll
        self.assertEqual([st["id"] for _, st in core.lane_entries(f"list:{x['id']}")], ["010"])
        core.cfg["lists"]["hide_members"] = "exclusive"  # only exclusive lists hide
        core._lists_version += 1
        self.assertIn("010", [st["id"] for _, st in core.lane_entries("people")])
        core.cfg["lists"]["hide_members"] = "all"
        core.cfg["lists"]["hide_in"] = ["bots"]  # hidden only where asked
        core._lists_version += 1
        self.assertIn("010", [st["id"] for _, st in core.lane_entries("people")])
        core.cfg["lists"]["hide_in"] = ["people", "bots", "global", "local"]
        core._lists_version += 1
        core.set_in_list("L1", "N", False).result()
        self.assertEqual([st["id"] for _, st in core.lane_entries("bots")], ["011"])
        core.delete_list(x["id"]).result()
        self.assertNotIn(f"list:{x['id']}", core.lane_by_name)
        self.assertEqual(core.lane_entries(f"list:{x['id']}"), [])

    def test_tag_suggestions(self):
        core, w = self.make()
        core.connect().result()
        a = status("010", BOB, minute=10)
        a["tags"] = [{"name": "georgia"}, {"name": "GeorgiaNews"}]
        b = status("011", NEWS, minute=11)
        b["tags"] = [{"name": "georgia"}, {"name": "go"}]
        w.add(a, home=True)
        w.add(b, home=True)
        core.poll_once()
        self.assertIsNone(core.store.tag_counts(compute=False))  # not built before asked
        core.prepare_tags()
        core.store.tag_counts()  # waits for the background pass, if still running
        self.assertEqual(core.tag_suggestions("ge"), ["georgia", "GeorgiaNews"])
        self.assertEqual(core.tag_suggestions("G"), ["georgia", "GeorgiaNews", "go"])
        c = status("012", NEWS, minute=12)
        c["tags"] = [{"name": "gogo"}]
        core.store.put_statuses([c])  # kept up to date as posts come
        self.assertIn("gogo", core.tag_suggestions("go"))
        self.assertEqual(core.tag_suggestions(""), [])

    def test_posts_from_origin_outbox(self):
        """A profile my server knows little about: newest public posts from the
        author's outbox, fetched into my server by address."""
        core, w = self.make()
        core.connect().result()
        far = fakes.acct("F", "fay@far.example")
        far["uri"] = "https://far.example/users/fay"
        pub = "https://www.w3.org/ns/activitystreams#Public"
        docs = {
            "https://far.example/users/fay": {"outbox": "https://far.example/users/fay/outbox"},
            "https://far.example/users/fay/outbox": {
                "first": "https://far.example/users/fay/outbox?page=1"},
            "https://far.example/users/fay/outbox?page=1": {"orderedItems": [
                {"type": "Create", "to": [pub], "object": {"id": "https://far.example/n/3"}},
                {"type": "Create", "to": ["https://far.example/users/fay/followers"],
                 "object": {"id": "https://far.example/n/2", "to": []}},  # not public
                {"type": "Announce", "to": [pub], "object": "https://else.example/n/9"},
                {"type": "Create", "cc": [pub], "object": "https://far.example/n/1"}]},
        }
        core._origin_json = docs.get
        for n in (1, 3):
            st = status(f"7{n}", far, minute=n, vis="public")
            st["uri"] = f"https://far.example/n/{n}"
            w.remote[st["uri"]] = st
        got = core.posts_from_origin(far).result()
        self.assertEqual(sorted(st["id"] for st in got), ["71", "73"])
        self.assertIsNotNone(core.store.get_status("73"))
        core.cfg["feed"]["remote_profiles"] = False
        self.assertEqual(core.posts_from_origin(far).result(), [])

    def test_interaction_policy_for_gotosocial(self):
        from fedtail.core.model import interaction_policy
        self.assertIsNone(interaction_policy({}))
        self.assertEqual(interaction_policy({"who_can_reply": "followers", "who_can_like": ""}),
                         {"can_reply": {"always": ["author", "followers", "mentioned"],
                                        "with_approval": []}})
        core, w = self.make(post={"who_can_reply": "mentioned"})
        core.connect().result()  # the fake server says it's GoToSocial
        core.post("тест", "public").result()
        self.assertEqual(w.extras[-1]["interaction_policy"]["can_reply"]["always"],
                         ["author", "mentioned"])

    def test_block_domain_and_note(self):
        core, w = self.make()
        core.connect().result()
        w.add(status("040", BOB, minute=1), home=True)
        w.add(status("041", NEWS, minute=2), home=True)
        core.poll_once()
        ids = lambda: [st["id"] for _, st in core.lane_entries("people")] + \
            [st["id"] for _, st in core.lane_entries("bots")]
        self.assertIn("040", ids())
        core.block_domain("Social.Example", True).result()
        self.assertNotIn("040", ids())
        self.assertIn("041", ids())  # from my own server
        self.assertEqual(core.silenced_people().result()["domains"], ["social.example"])
        core.block_domain("social.example", False).result()
        self.assertIn("040", ids())
        core.set_note("B", "знакомый по Point").result()
        self.assertEqual(w.notes["B"], "знакомый по Point")

    def test_my_likes_lane_and_bell(self):
        core, w = self.make(lanes={"enabled": ["people", "favourites"]})
        core.connect().result()
        liked = w.add(status("050", BOB, minute=1), home=True)
        liked["favourited"] = True
        core.set_active_lane("favourites")
        core.poll_once()
        self.assertEqual([st["id"] for _, st in core.lane_entries("favourites")], ["050"])
        core.notify_posts("B", True).result()
        self.assertTrue(w.bells["B"])

    def test_pin_my_post(self):
        core, w = self.make()
        core.connect().result()
        mine = w.add(status("030", fakes.ME, minute=1, vis="public"))
        core.pin(mine, True).result()
        self.assertEqual([s["id"] for s in core.pinned("ME").result()], ["030"])
        core.pin(mine, False).result()
        self.assertEqual(core.pinned("ME").result(), [])

    def test_direct_lane(self):
        core, w = self.make()
        core.connect().result()
        dm = status("020", BOB, "010", "ME", minute=20, vis="direct", text="лично")
        w.add(status("010", fakes.ME, minute=10), home=True)
        w.add(dm, mention=True)
        w.add(status("021", BOB, "010", "ME", minute=21), mention=True)
        core.poll_once()
        ids = lambda lane: [st["id"] for _, st in core.lane_entries(lane)]
        self.assertEqual(ids("direct"), ["020"])
        self.assertEqual(ids("comments"), ["021"])  # the private one lives apart
        core.cfg["lanes"]["direct_apart"] = False
        core._lists_version += 1
        self.assertEqual(ids("comments"), ["020", "021"])

    def test_people_from_origin(self):
        core, w = self.make()
        core.connect().result()
        far = fakes.acct("F", "fay@far.example")
        far["uri"] = "https://far.example/users/fay"
        w.add(status("080", BOB, minute=1))  # Bob is known to my server
        bob_uri = "https://social.example/users/bob"
        w.statuses["080"]["account"]["url"] = bob_uri
        core._origin_json = {
            "https://far.example/users/fay": {"followers": "https://far.example/f"},
            "https://far.example/f": {"totalItems": 120, "first": {"orderedItems": [bob_uri]}},
        }.get
        res, nxt = core.people_from_origin(far, "followers").result()
        self.assertIsNone(nxt)
        self.assertEqual(res["total"], 120)
        self.assertEqual([a["id"] for a in res["accounts"]], ["B"])
        res, _ = core.people_from_origin(far, "followers", have_ids={"B"}).result()
        self.assertEqual(res["accounts"], [])  # shown already

    def test_async_refresh_grows_thread(self):
        """Mastodon 4.5+ says it's fetching the rest of a thread: when it's done, the
        open thread is told to grow."""
        core, w = self.make()
        core.connect().result()
        root = w.add(status("010", BOB, minute=10, vis="public"), home=True)
        hints = [("r1", 1)]
        core.api.last_async_refresh = lambda: hints.pop() if hints else None
        core.api.async_refresh = lambda rid: "finished"
        core.thread(root["id"]).result()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and not any(
                e == ("thread_grew", "010") for e in self.events):
            time.sleep(0.05)
        self.assertIn(("thread_grew", "010"), self.events)
        core.cfg["feed"]["complete_threads"] = False  # that switch covers this too
        self.events.clear()
        hints.append(("r2", 1))
        core.thread(root["id"]).result()
        time.sleep(1.5)
        self.assertNotIn(("thread_grew", "010"), self.events)

    def test_markers_shared_read_position(self):
        core, w = self.make(feed={"page_size": 40})
        core.connect().result()
        for i in range(10, 15):
            w.add(status(f"0{i}", BOB, minute=i), home=True)
        core.poll_once()
        core.poll_once()
        self.assertEqual(core.unread_count("people"), 5)
        # read on the phone up to 012: those are read here too
        w.markers["home"] = "012"
        core.poll_once()
        self.assertEqual(sorted(core.store.read_set(["010", "011", "012", "013", "014"])),
                         ["010", "011", "012"])
        # read here up to 013 (014 still not): the server hears 013
        core.mark_read(["013"])
        core.poll_once()
        self.assertEqual(w.markers["home"], "013")
        core.cfg["read"]["sync_markers"] = False
        w.markers["home"] = "014"
        core.poll_once()
        self.assertNotIn("014", core.store.read_set(["014"]))

    def test_mention_suggestions(self):
        core, w = self.make()
        core.connect().result()
        a = status("010", BOB, minute=10)
        a["mentions"] = [{"acct": "bonnie@far.example"}, {"acct": "veresk"}]
        w.add(a, home=True)
        w.add(status("011", BOB, minute=11), home=True)
        core.poll_once()
        core.prepare_people()
        core.store.people_counts()  # waits for the background pass, if still running
        got = core.mention_suggestions("bo")
        self.assertEqual(got[0][0], "bob@social.example")  # seen most
        self.assertIn("bonnie@far.example", [x[0] for x in got])
        self.assertEqual(core.mention_suggestions("veresk"), [])  # never yourself
        self.assertEqual(core.search_people("bob").result()[0][0], "bob@social.example")

    def test_notify_about_one_list_by_title(self):
        core, w = self.make()
        w.lists["L1"] = {"title": "Новости", "exclusive": True, "members": {"N"}}
        w.lists["L2"] = {"title": "Друзья", "exclusive": True, "members": {"B"}}
        core.cfg["notify"]["lanes"] = ["comments", "list:друзья"]
        core.connect().result()
        core.poll_once()
        w.add(status("010", BOB, minute=10), home=True)
        w.add(status("011", NEWS, minute=11), home=True)
        core.poll_once()
        notes = [e for e in self.events if e[0] == "notify"][-1][1]
        self.assertEqual([(lane, st["id"]) for lane, st in notes], [("list:L2", "010")])
        cfg, errors = config.validate({"notify": {"lanes": ["mentions", "list:Друзья"]}})
        self.assertEqual(errors, [])

    def test_thread_subscriptions(self):
        alice = fakes.acct("A", "alice@example.org")
        core, w = self.make()
        core.connect().result()
        core.poll_once()  # first run
        core.cfg["subs"]["interval_minutes"] = 0  # check every poll here

        # my post: followed by itself; a talk under it reaches me even without @me
        w.add(status("100", ME, minute=20), home=True)
        core.poll_once()
        self.assertTrue(core.subscribed(w.statuses["100"]))
        w.add(status("101", BOB, "100", "ME", minute=21), mention=True)
        w.add(status("102", alice, "101", "B", minute=22))  # alice answers bob, no @me
        core.poll_once()
        self.assertEqual([st["id"] for _, st in core.lane_entries("comments")], ["101"])
        self.assertEqual([st["id"] for _, st in core.lane_entries("subs")], ["102"])
        notes = [e for e in self.events if e[0] == "notify"]
        self.assertIn("102", [s["id"] for lane, s in notes[-1][1] if lane == "subs"])
        core.poll_once()  # nothing new: nothing twice
        self.assertEqual(len(core.lane_entries("subs")), 1)

        # leaving the thread empties the lane, and my next comment doesn't bring it back
        core.unsubscribe(w.statuses["102"]).result()
        self.assertFalse(core.subscribed(w.statuses["100"]))
        self.assertEqual(core.lane_entries("subs"), [])
        w.add(status("103", ME, "102", "A", minute=23), home=True)
        core.poll_once()
        self.assertFalse(core.subscribed(w.statuses["100"]))

        # by hand: someone else's thread; only what comes after counts
        w.add(status("200", BOB, minute=30), home=True)
        w.add(status("201", alice, "200", "B", minute=31))
        core.poll_once()
        core.subscribe(w.statuses["201"]).result()
        self.assertTrue(core.subscribed(w.statuses["200"]))
        core.poll_once()
        self.assertEqual(core.lane_entries("subs"), [])
        w.add(status("202", alice, "201", "A", minute=32))
        core.poll_once()
        self.assertEqual([st["id"] for _, st in core.lane_entries("subs")], ["202"])

        # my comment in a thread follows it (subs.auto = comments)
        w.add(status("300", BOB, minute=40), home=True)
        w.add(status("301", ME, "300", "B", minute=41), home=True)
        core.poll_once()
        self.assertTrue(core.subscribed(w.statuses["300"]))

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
        core.cfg["lanes"]["mentions_all"] = True  # replies to me show in mentions too
        core._lane_cache.clear()
        self.assertEqual(sorted(st["id"] for _, st in core.lane_entries("mentions")),
                         ["013", "014"])
        core.cfg["lanes"]["mentions_all"] = False
        self.assertIn("012", core.store.read_set(["012"]))  # my own post is read
        notes = [e for e in self.events if e[0] == "notify"]
        self.assertEqual(sorted(s["id"] for _, s in notes[0][1]), ["013", "014"])
        # a new follow request is news too; an old one is not
        w.requests = [BOB]
        core.poll_once()
        notes = [e for e in self.events if e[0] == "notify"]
        self.assertEqual(notes[-1][1], [("requests", BOB)])
        core.poll_once()
        self.assertEqual(len([e for e in self.events if e[0] == "notify"]), len(notes))
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

    def test_my_replies_are_found(self):
        core, w = self.make()
        core.connect().result()
        mine = w.add(status("040", ME, minute=1), home=True)
        c1 = w.add(status("041", BOB, mine["id"], "ME", minute=2), mention=True)
        c2 = w.add(status("042", BOB, mine["id"], "ME", minute=3), mention=True)
        core.poll_once()
        # I answered c1 long ago, in another client: only the server knows
        old = status("043", ME, c1["id"], "B", minute=4, text="ответ")
        w.statuses[old["id"]] = old
        c1["replies_count"] = 1
        self.assertEqual(core.my_replies([c1, c2]), {})
        core.check_my_replies([c1, c2])
        import time
        end = time.time() + 5
        while core._replies_inflight and time.time() < end:  # background check
            time.sleep(0.01)
        self.assertEqual([r["id"] for r in core.my_replies([c1])["041"]], ["043"])
        self.assertIn("041", core.store.read_set(["041"]))  # answered → read
        self.assertNotIn("042", core.store.read_set(["042"]))
        # replying from fedtail marks the comment read and is found at once
        core.post("ага", "private", reply_to="042").result()
        self.assertIn("042", core.store.read_set(["042"]))
        self.assertIn("042", core.my_replies([c2]))

    def test_migration_from_v1(self):
        import json as _json
        import sqlite3 as _sq
        db = self.tmp / "old.db"
        con = _sq.connect(db)
        con.executescript("CREATE TABLE statuses (id TEXT PRIMARY KEY, data TEXT NOT NULL, "
                          "created_at TEXT NOT NULL);")
        st = status("1", ME, "p", "B")
        con.execute("INSERT INTO statuses VALUES (?, ?, ?)", ("1", _json.dumps(st), "x"))
        con.commit()
        con.close()
        s = Store(db)
        self.assertEqual(list(s.replies_by(["p"], "ME")), ["p"])
        s.close()

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

    def test_post_language(self):
        core, w = self.make(post={"language": "ka"})
        core.connect().result()
        core.post("გამარჯობა", "private").result()  # post.language by default
        core.post("hello", "private", language="en").result()  # chosen for this one
        core.post("whatever", "private", language="").result()  # none: the server decides
        self.assertEqual(w.languages, ["ka", "en", ""])
        with self.assertRaises(config.ConfigError):
            config.validate({"post": {"language": "Russian"}})
        with self.assertRaises(config.ConfigError):
            config.validate({"post": {"languages": ["ru", "EN"]}})

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


class ConversationsTest(unittest.TestCase):
    def test_grouped_by_thread_at_the_newest(self):
        from fedtail.core.threads import conversations
        root = status("1", BOB, minute=1)
        a = status("2", ME, "1", "B", minute=2)
        other = status("3", NEWS, minute=3)
        b = status("4", BOB, "2", "ME", minute=4)
        known = {s["id"]: s for s in (root, a, other, b)}
        got = conversations([("2", a), ("3", other), ("4", b)], known.get, {"4"})
        self.assertEqual([g["key"] for g in got], ["3", "1"])  # the thread moved down
        thread = got[1]
        self.assertEqual(thread["top"]["id"], "1")  # its root, though not in the lane
        self.assertEqual([m["id"] for m in thread["members"]], ["2", "4"])
        self.assertEqual((thread["unread"], thread["last"]["id"]), (1, "4"))
