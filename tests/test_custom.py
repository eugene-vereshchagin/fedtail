"""Free lanes, first version (core/custom.py): [[lanes.custom]] read from the config, fed from
the real sources after each poll, filled anew from the store when a rule is new or changed,
shown like any other lane (title, sidebar section, counts)."""

import json
import tempfile
import unittest
from pathlib import Path

from fedtail.core import auth, config, custom, lanes, paths
from fedtail.core.app import Core
from fedtail.core.atoms import Rule, World

from . import fakes
from .fakes import BOB, ME, NEWS, FakeApi, status

LOCAL = fakes.acct("L", "lena")  # my server's: no @host

FEED = {"name": "feed", "title": "Лента", "any": [
    {"author": "local", "kind": "post"}, {"me": "reply"}, {"author": "me"}]}


class LoadTest(unittest.TestCase):
    def test_load_and_sources(self):
        cfg, warnings = config.validate({"lanes": {"custom": [FEED]}})
        self.assertEqual(warnings, [])
        (c,), _ = custom.load(cfg)
        self.assertEqual((c.name, c.title), ("custom:feed", "Лента"))
        self.assertEqual(c.feeds, {"local", "mentions", "mine"})
        lane = c.lane()
        self.assertEqual((lane.source, lane.feeds, lane.lazy), ("custom:feed",
                         ("local", "mentions", "mine"), False))
        names = [x.name for x in lanes.enabled(cfg)]
        self.assertIn("custom:feed", names)
        self.assertEqual(lanes.grouped(lanes.enabled(cfg))[0], ("custom", ["custom:feed"]))
        self.assertIn("local", lanes.sources_needed(lanes.enabled(cfg)))
        self.assertNotIn("custom:feed", lanes.sources_needed(lanes.enabled(cfg)))

    def test_no_custom_no_section(self):
        cfg, _ = config.validate({})
        self.assertNotIn("custom", [g for g, _n in lanes.grouped(lanes.enabled(cfg))])

    def test_warnings(self):
        cfg, warnings = config.validate({"lanes": {"custom": [
            {"name": "a", "any": [{"me": "replys"}]},
            {"name": "a", "any": [{"author": "me"}]},
            {"any": [{"author": "me"}]},
            {"name": "far", "any": [{"source": "remote:x.example"}]},
        ]}})
        text = "\n".join(warnings)
        self.assertIn("lanes.custom[0] a: me: unknown value 'replys'", text)
        self.assertIn("lanes.custom[1] a: the name is taken", text)
        self.assertIn("lanes.custom[2] ?: a lane needs a name", text)
        self.assertIn("sources not in this version: remote:x.example", text)
        self.assertEqual([c.name for c in custom.load(cfg)[0]], ["custom:a", "custom:far"])
        with self.assertRaises(config.ConfigError):
            config.validate({"lanes": {"custom": {"name": "x"}}})

    def test_infer_sources(self):
        def feeds(**cond):
            return custom.infer_sources(Rule.parse({"name": "x", "any": [cond]}).any[0])
        self.assertEqual(feeds(source=["home", "list:3"]), {"home", "list:3"})
        self.assertEqual(feeds(me="mention"), {"mentions"})
        self.assertEqual(feeds(me="in_my_thread"), {"subs"})
        self.assertEqual(feeds(author="me"), {"mine"})
        self.assertEqual(feeds(author="local"), {"local"})
        self.assertEqual(feeds(state="bookmarked"), {"bookmarks"})
        self.assertEqual(feeds(state="liked"), {"favourites"})
        self.assertEqual(feeds(kind="post"), {"home"})
        rule = Rule.parse({"name": "x", "source": "federated", "any": [{"author": "me"}]})
        self.assertEqual(custom.Custom(rule).feeds, {"federated"})

    def test_is_custom(self):
        self.assertTrue(custom.is_custom("custom:x"))
        self.assertFalse(custom.is_custom("home"))
        self.assertFalse(custom.is_custom(None))

    def test_takes(self):
        c = custom.Custom(Rule.parse(FEED))
        w = World(me_id="ME", my_host="example.test")
        self.assertTrue(c.takes(status("1", ME), w, "mine"))
        self.assertTrue(c.takes(status("2", LOCAL), w, "local"))
        self.assertFalse(c.takes(status("3", BOB), w, "home"))


class FreeBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def make(self, rules):
        FakeApi.world = fakes.World()
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False, "page_size": 10},
                                  "lanes": {"custom": rules}})
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        self.events = []
        core.events.on("*", lambda n, pl: self.events.append((n, pl)))
        self.addCleanup(core.shutdown)
        return core, FakeApi.world

    def ids(self, core, name="custom:feed"):
        return [st["id"] for _i, st in core.lane_entries(name)]


class CoreFreeLaneTest(FreeBase):

    def test_fed_from_several_sources(self):
        core, w = self.make([FEED])
        w.add(status("001", BOB, minute=1), home=True)                 # far away: no
        w.local.append(w.add(status("002", LOCAL, minute=2)))          # my server's post
        w.local.append(w.add(status("003", LOCAL, reply_to="x", reply_acc="Z", minute=3)))
        w.add(status("004", BOB, reply_to="999", reply_acc="ME", minute=4), mention=True)
        w.add(status("005", ME, minute=5), home=True)                   # mine
        core.connect().result()
        core.poll_once()
        self.assertEqual(self.ids(core), ["002", "004", "005"])
        self.assertEqual(core.lane_title("custom:feed"), "Лента")
        self.assertEqual(core.lane_title("custom:gone"), "gone")
        self.assertTrue(any(n == "lanes_updated" and "custom:feed" in pl
                            for n, pl in self.events))
        # the next round: only what's new goes through the rules
        w.local.append(w.add(status("006", LOCAL, minute=6)))
        w.add(status("007", NEWS, minute=7), home=True)
        core.poll_once()
        self.assertEqual(self.ids(core), ["002", "004", "005", "006"])
        self.assertTrue(any(n == "lanes_updated" and pl.get("custom:feed") for n, pl
                            in self.events))
        self.assertGreaterEqual(core.unread_count("custom:feed"), 3)

    def test_two_lanes_their_own_feeds(self):
        core, w = self.make([FEED, {"name": "bots", "source": "home",
                                     "any": [{"author": "bot"}]}])
        w.add(status("005", ME, minute=5), home=True)
        w.add(status("007", NEWS, minute=7), home=True)
        core.connect().result()
        core.poll_once()
        self.assertEqual(self.ids(core), ["005"])
        self.assertEqual(self.ids(core, "custom:bots"), ["007"])
        w.add(status("008", NEWS, minute=8), home=True)
        w.add(status("009", ME, minute=9), home=True)
        core.poll_once()
        self.assertEqual(self.ids(core, "custom:bots"), ["007", "008"])
        self.assertEqual(self.ids(core), ["005", "009"])

    def test_filled_anew_when_the_rule_changes(self):
        core, w = self.make([FEED])
        w.local.append(w.add(status("002", LOCAL, minute=2)))
        w.add(status("005", ME, minute=5), home=True)
        core.connect().result()
        core.poll_once()
        self.assertEqual(self.ids(core), ["002", "005"])
        c = core.customs[0]
        self.assertFalse(custom.stale(core.store, c))
        # another rule under the same name: what's stored is sorted again, nothing fetched
        core.customs = custom.load(config.validate({"lanes": {"custom": [
            {"name": "feed", "any": [{"author": "me"}]}]}})[0])[0]
        self.assertTrue(custom.stale(core.store, core.customs[0]))
        core.poll_once()
        self.assertEqual(self.ids(core), ["005"])

    def test_following_known_for_atoms(self):
        core, w = self.make([{"name": "f", "source": "home", "any": [{"author": "followed"}]}])
        w.following = {"B"}
        w.followed_tags = {"грузия"}
        w.add(status("001", BOB, minute=1), home=True)
        w.add(status("002", NEWS, minute=2), home=True)
        core.connect().result()
        core.poll_once()
        self.assertEqual(self.ids(core, "custom:f"), ["001"])
        self.assertEqual(core._followed_tag_names, {"грузия"})
        kept = core.store.kv_get("custom_following")
        self.assertEqual((kept["ids"], kept["tags"]), (["B"], ["грузия"]))
        # a new run reads it back and doesn't ask again within the hours
        core._following = None
        calls = len(w.calls)
        core._refresh_following()
        self.assertEqual(core._following, {"B"})
        self.assertEqual(len(w.calls), calls)

    def test_following_failure_keeps_the_old(self):
        core, w = self.make([{"name": "f", "any": [{"author": "followed"}]}])
        core.connect().result()
        core._following, core._following_at = {"B"}, 0.0

        def broken(*a, **kw):
            raise RuntimeError("down")
        core.api.following = broken
        core._refresh_following()
        self.assertEqual(core._following, {"B"})

    def test_following_pages(self):
        core, w = self.make([{"name": "f", "any": [{"author": "followed"}]}])
        core.connect().result()
        pages = iter([([{"id": "1"}], "m1"), ([{"id": "2"}], None)])
        core.api.following = lambda me, max_id=None: next(pages)
        core._following_at = 0.0
        core._refresh_following()
        self.assertEqual(core._following, {"1", "2"})

    def test_world(self):
        core, w = self.make([FEED])
        w.add(status("001", ME, minute=1), home=True)
        core.connect().result()
        core.poll_once()
        world = core._world()
        self.assertEqual((world.me_id, world.my_host), ("ME", "example.test"))
        self.assertNotIn("zzz", world.read)
        core.store.mark_read(["001"])
        self.assertIn("001", world.read)
        self.assertEqual(world.parents.get("001")["id"], "001")
        self.assertIsNone(world.parents.get("nope"))
        core.store.mark_missing("gone")
        self.assertEqual(world.parents.get("gone"), "missing")

    def test_no_customs_no_work(self):
        core, w = self.make([])
        core.connect().result()
        self.assertEqual(core._route_custom({"home": ["1"]}), {})

    def test_browse_lane_fetches_its_feeds_only_while_open(self):
        core, w = self.make([{"name": "b", "read": "browse", "source": "federated",
                              "any": [{"kind": "post"}]}])
        self.assertTrue(core.lane_by_name["custom:b"].lazy)
        w.local.append(w.add(status("002", LOCAL, minute=2)))
        core.connect().result()
        core.poll_once()
        self.assertEqual(self.ids(core, "custom:b"), [])  # closed: federated not fetched
        core.set_active_lane("custom:b")
        core.poll_once()
        self.assertEqual(self.ids(core, "custom:b"), ["002"])

    def test_read_through_lane_catches_local_up(self):
        core, w = self.make([{"name": "l", "source": "local", "any": [{"kind": "post"}]}])
        w.local.append(w.add(status("002", LOCAL, minute=2)))
        core.connect().result()
        core.poll_once()  # Local is a browse lane, closed; the free lane still needs it
        self.assertEqual(self.ids(core, "custom:l"), ["002"])


if __name__ == "__main__":
    unittest.main()


class WebShowsFreeLanesTest(FreeBase):
    """The interfaces need nothing new: a free lane is a lane (the web page as the witness —
    it runs without a toolkit)."""

    def test_sidebar_and_lane(self):
        from fedtail import i18n
        from fedtail.frontends.web import server as web
        i18n.setup("en")
        self.addCleanup(i18n.setup, "ru")
        core, w = self.make([FEED])
        w.add(status("005", ME, minute=5), home=True)
        core.connect().result()
        core.poll_once()
        rows = web.Web(core, "KEY").lanes()
        first = rows[0]
        self.assertEqual((first["name"], first["title"], first["group"], first["tip"]),
                         ("custom:feed", "Лента", "My own", ""))
        got = web.Web(core, "KEY").lane("custom:feed")
        self.assertIn("005", json.dumps(got, default=str))
