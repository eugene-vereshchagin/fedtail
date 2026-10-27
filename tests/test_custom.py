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

LOCAL = fakes.acct("L", "lena")


def _own(loaded):
    """custom.load gives every lane of rules (the set's too): the config's own one and the
    warnings."""
    from fedtail.core import presets
    rules, warnings = loaded
    theirs = {x["name"] for x in presets.lanes_of("fedtail") + presets.extra()}
    return next(c for c in rules if c.name not in theirs), warnings  # my server's: no @host

FEED = {"name": "feed", "title": "Лента", "any": [
    {"author": "local", "kind": "post"}, {"me": "reply"}, {"author": "me"}]}


class LoadTest(unittest.TestCase):
    def test_load_and_sources(self):
        cfg, warnings = config.validate({"lanes": {"custom": [FEED]}})
        self.assertEqual(warnings, [])
        c = next(c for c in custom.load(cfg)[0] if c.name == "feed")
        self.assertEqual((c.name, c.title, c.stream, c.routed), ("feed", "Лента", "custom:feed",
                                                                 True))
        self.assertEqual(c.feeds, {"local", "mentions", "mine"})
        lane = c.lane()
        self.assertEqual((lane.source, lane.feeds, lane.lazy), ("custom:feed",
                         ("local", "mentions", "mine"), False))
        names = [x.name for x in lanes.enabled(cfg)]
        self.assertIn("feed", names)
        personal = dict(lanes.grouped(lanes.enabled(cfg)))["personal"]
        self.assertEqual(personal[-2:], ["feed", "unsorted"])  # at the end of Personal
        self.assertNotIn("custom", dict(lanes.grouped(lanes.enabled(cfg))))
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
        own = {"a", "far"} & {c.name for c in custom.load(cfg)[0]}
        self.assertEqual(own, {"a", "far"})
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

    def ids(self, core, name="feed"):
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
        self.assertEqual(core.lane_title("feed"), "Лента")
        self.assertIsNone(core.lane_title("gone"))
        self.assertIsNone(core.lane_title("home"))  # a set's lane: the interface's word
        self.assertTrue(any(n == "lanes_updated" and "feed" in pl
                            for n, pl in self.events))
        # the next round: only what's new goes through the rules
        w.local.append(w.add(status("006", LOCAL, minute=6)))
        w.add(status("007", NEWS, minute=7), home=True)
        core.poll_once()
        self.assertEqual(self.ids(core), ["002", "004", "005", "006"])
        self.assertTrue(any(n == "lanes_updated" and pl.get("feed") for n, pl
                            in self.events))
        self.assertGreaterEqual(core.unread_count("feed"), 3)

    def test_two_lanes_their_own_feeds(self):
        core, w = self.make([FEED, {"name": "botz", "source": "home",
                                     "any": [{"author": "bot"}]}])
        w.add(status("005", ME, minute=5), home=True)
        w.add(status("007", NEWS, minute=7), home=True)
        core.connect().result()
        core.poll_once()
        self.assertEqual(self.ids(core), ["005"])
        self.assertEqual(self.ids(core, "botz"), ["007"])
        w.add(status("008", NEWS, minute=8), home=True)
        w.add(status("009", ME, minute=9), home=True)
        core.poll_once()
        self.assertEqual(self.ids(core, "botz"), ["007", "008"])
        self.assertEqual(self.ids(core), ["005", "009"])

    def test_filled_anew_when_the_rule_changes(self):
        core, w = self.make([FEED])
        w.local.append(w.add(status("002", LOCAL, minute=2)))
        w.add(status("005", ME, minute=5), home=True)
        core.connect().result()
        core.poll_once()
        self.assertEqual(self.ids(core), ["002", "005"])
        c = next(c for c in core.customs if c.name == "feed")
        self.assertFalse(custom.stale(core.store, c))
        # another rule under the same name: what's stored is sorted again, nothing fetched
        core.cfg["lanes"]["custom"] = [{"name": "feed", "source": ["mine", "mentions"],
                                        "any": [{"author": "me"}]}]
        core._apply_lists(core.lists, core.list_members)
        self.assertTrue(custom.stale(core.store, next(c for c in core.customs
                                                      if c.name == "feed")))
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
        self.assertEqual(self.ids(core, "f"), ["001"])
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
        self.assertTrue(core.lane_by_name["b"].lazy)
        w.local.append(w.add(status("002", LOCAL, minute=2)))
        core.connect().result()
        core.poll_once()
        self.assertEqual(self.ids(core, "b"), [])  # closed: federated not fetched
        core.set_active_lane("b")
        core.poll_once()
        self.assertEqual(self.ids(core, "b"), ["002"])

    def test_read_through_lane_catches_local_up(self):
        core, w = self.make([{"name": "l", "source": "local", "any": [{"kind": "post"}]}])
        w.local.append(w.add(status("002", LOCAL, minute=2)))
        core.connect().result()
        core.poll_once()  # Local is a browse lane, closed; the free lane still needs it
        self.assertEqual(self.ids(core, "l"), ["002"])


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
        first = next(x for x in rows if x["name"] == "feed")
        self.assertEqual((first["title"], first["section"], first["tip"]),
                         ("Лента", "personal", ""))
        got = web.Web(core, "KEY").lane("feed")
        self.assertIn("005", json.dumps(got, default=str))


class ConfigToolsWithTablesTest(unittest.TestCase):
    """--update-config, --rebuild-config and the settings page with [[lanes.custom]] (and
    [[lanes.tag_groups]]) in the file: a section's options stay in the section, before its
    sub-tables — never inside the last one, where TOML would read them as its keys."""

    USER = """[lanes]
enabled = ["home", "local"]

[[lanes.custom]]
name = "feed"
any = [{ author = "me" }]

[[lanes.tag_groups]]
name = "Georgia"
any = ["грузия"]

[ui]
theme = "point"
"""

    def test_mentioned_and_missing(self):
        from fedtail.core import config_update as u
        have = u.mentioned(self.USER)
        self.assertIn("custom", have["lanes"])
        self.assertIn("tag_groups", have["lanes"])
        self.assertEqual(have["lanes.custom"], {"name", "any"})
        missing = u.missing(self.USER, config.example_text("en"))
        self.assertNotIn("lanes.custom", missing)
        self.assertIn("lanes.preset", missing)

    def test_update_keeps_tables_whole(self):
        import tomllib

        from fedtail.core import config_update as u
        for lang in ("ru", "en"):
            out = u.update(self.USER, config.example_text(lang))
            out = out if isinstance(out, str) else out[0]
            d = tomllib.loads(out)
            self.assertEqual(d["lanes"]["custom"], [{"name": "feed", "any": [{"author": "me"}]}])
            self.assertEqual(d["lanes"]["tag_groups"], [{"name": "Georgia", "any": ["грузия"]}])
            self.assertEqual(d["lanes"]["preset"], "fedtail")
            self.assertEqual(d["ui"]["theme"], "point")
            config.validate(d)

    def test_rebuild_writes_tables_as_tables(self):
        import tomllib

        from fedtail.core import config_update as u
        out = u.rebuild(self.USER, config.example_text("en"))
        out = out if isinstance(out, str) else out[0]
        self.assertIn("\n[[lanes.custom]]\nname = \"feed\"\n", out)
        self.assertIn("#custom = []  # → [[lanes.custom]]", out)
        d = tomllib.loads(out)
        self.assertEqual(d["lanes"]["custom"][0]["name"], "feed")
        self.assertEqual(d["lanes"]["enabled"], ["home", "local"])
        empty = u.rebuild("[lanes]\ncustom = []\n", config.example_text("en"))
        empty = empty if isinstance(empty, str) else empty[0]
        self.assertEqual(tomllib.loads(empty)["lanes"]["custom"], [])

    def test_settings_page_writes_into_the_section(self):
        import tomllib

        from fedtail.core import config_edit as e
        for key, value in (("mentions_all", True), ("enabled", ["home"])):
            out = e.set_value(self.USER, "lanes", key, value)
            d = tomllib.loads(out)
            self.assertEqual(d["lanes"][key], value)
            self.assertNotIn(key, d["lanes"]["custom"][0])
            self.assertNotIn(key, d["lanes"]["tag_groups"][0])


CHIPPED = {"name": "feed", "title": "Лента", "any": [
    {"source": "home", "kind": "post"},
    {"source": "home", "kind": "reply", "switch": "Комменты", "shown": False},
    {"author": "me", "switch": "Моё"}]}


class ChipsTest(FreeBase):
    """Quick filters of a free lane: `switch` makes a condition one, `shown = false` keeps
    it out of the main view (and of the counts and the news) until its chip is on."""

    def setup_lane(self):
        core, w = self.make([CHIPPED])
        w.add(status("001", BOB, minute=1), home=True)
        w.add(status("002", BOB, reply_to="001", reply_acc="B", minute=2), home=True)
        w.add(status("003", ME, minute=3), home=True)
        core.connect().result()
        core.poll_once()
        return core, w

    def test_chips_of_the_rule(self):
        c, _w = _own(custom.load(config.validate({"lanes": {"custom": [CHIPPED]}})[0]))
        self.assertEqual(c.chips(), (("main", ""), ("chip:1", "Комменты"), ("chip:2", "Моё")))
        self.assertEqual(c.default_filter(), "main")
        plain, _w = _own(custom.load(config.validate({"lanes": {"custom": [FEED]}})[0]))
        self.assertEqual((plain.chips(), plain.default_filter()), ((), "all"))
        self.assertEqual(plain.lane().chips, ())

    def test_main_all_and_one_chip(self):
        core, w = self.setup_lane()
        name = "feed"
        self.assertEqual(core.lane_filter(name), "main")
        self.assertEqual(self.ids(core), ["001", "003"])       # the comment hidden
        core.set_lane_filter(name, "all")
        self.assertEqual(self.ids(core), ["001", "002", "003"])
        core.set_lane_filter(name, "chip:1")
        self.assertEqual(self.ids(core), ["002"])
        core.set_lane_filter(name, "chip:2")
        self.assertEqual(self.ids(core), ["003"])
        core.set_lane_filter(name, "chip:9")                   # gone from the rule
        self.assertEqual(core.lane_filter(name), "main")
        self.assertEqual(core.lane_filter("home"), "all")

    def test_hidden_not_counted_nor_news(self):
        core, w = self.setup_lane()
        name = "feed"
        self.assertEqual(core.unread_count(name), 1)  # 001 (003 is mine: read)
        self.events.clear()
        core.cfg["notify"]["lanes"] = ["all"]
        w.add(status("004", BOB, reply_to="001", reply_acc="B", minute=4), home=True)
        core.poll_once()
        news = [st for n, pl in self.events if n == "notify" for lane, st in pl
                if lane == name]
        self.assertEqual(news, [])
        self.assertEqual(core.unread_count(name), 1)
        core.set_lane_filter(name, "chip:1")
        self.assertEqual(self.ids(core), ["002", "004"])

    def test_shows_odd_keys(self):
        c, _w = _own(custom.load(config.validate({"lanes": {"custom": [CHIPPED]}})[0]))
        w = World(me_id="ME")
        st = status("1", BOB)
        self.assertTrue(c.shows(st, w, "all"))
        self.assertTrue(c.shows(st, w, ""))
        self.assertTrue(c.shows(st, w, "chip:x"))
        self.assertTrue(c.shows(st, w, "whatever"))

    def test_lane_model_offers_them(self):
        from fedtail import i18n
        from fedtail.core.view import View
        from fedtail.frontends.common.lane import LaneModel
        i18n.setup("ru")
        core, w = self.setup_lane()
        m = LaneModel(View(core), "feed")
        self.assertEqual(m.filters, ["main", "all", "chip:1", "chip:2", "unread"])
        self.assertEqual(m.filter_words("main")[0], "Основное")
        self.assertEqual(m.filter_words("chip:1")[0], "Комменты")
        self.assertIn("Комменты", m.filter_words("chip:1")[1])
        self.assertEqual(m.filter_words("all")[0], i18n._("show_all"))
        self.assertEqual(m.current_filter(), "main")
        m.set_filter("chip:2")
        self.assertEqual(m.current_filter(), "chip:2")
        m.set_filter("unread")
        self.assertEqual((m.current_filter(), core.lane_filter("feed")),
                         ("unread", "all"))
        m.set_filter("all")
        self.assertEqual(m.current_filter(), "all")
        plain = LaneModel(View(core), "home")
        self.assertEqual(plain.filters, ["all", "posts", "chip:1", "chip:2", "chip:3", "unread"])

    def test_web_gives_the_words(self):
        from fedtail import i18n
        from fedtail.frontends.web import server as web
        i18n.setup("en")
        self.addCleanup(i18n.setup, "ru")
        core, w = self.setup_lane()
        got = web.Web(core, "KEY").lane("feed")
        self.assertEqual([f[:2] for f in got["filters"]],
                         [["main", "Main"], ["all", i18n._("show_all")],
                          ["chip:1", "Комменты"], ["chip:2", "Моё"],
                          ["unread", i18n._("unread_only")]])
        self.assertEqual(got["filter"], "main")


class OlderTest(FreeBase):
    def test_older_through_the_rule(self):
        # several sources: a stream of its own, filled through the rule
        core, w = self.make([{"name": "botz", "source": ["home", "subs"],
                              "any": [{"author": "bot"}]}])
        for i in range(1, 31):
            w.add(status(f"{i:03d}", NEWS if i % 2 else BOB, minute=i), home=True)
        core.connect().result()
        core.poll_once()  # the first page: the newest ten
        first = self.ids(core, "botz")
        self.assertEqual(len(first), 5)
        got = core.load_older("botz").result()
        self.assertEqual(got, 5)
        ids = self.ids(core, "botz")
        self.assertEqual(len(ids), 10)
        self.assertTrue(set(first) < set(ids))
        self.assertTrue(all(core.store.read_set([i]) for i in set(ids) - set(first)))

    def test_older_feed_failing_and_unknown(self):
        core, w = self.make([{"name": "x", "source": ["home", "subs"],
                              "any": [{"author": "bot"}]}])
        core.connect().result()
        core.poll_once()

        def broken(*a, **kw):
            raise RuntimeError("down")
        core.sources["home"].fetch = broken
        self.assertEqual(core.load_older("x").result(), 0)
        self.assertTrue(any(n == "error" and "home" in pl for n, pl in self.events))
        self.assertEqual(core._older_custom("nope"), 0)


class UnsortedTest(FreeBase):
    """"Unsorted": with free lanes, what came from a read-through source and no lane took."""

    def test_what_no_lane_took(self):
        core, w = self.make([{"name": "botz", "source": ["home", "mentions"],
                              "any": [{"author": "bot"}]}])
        core.cfg["lanes"]["enabled"] = ["my_posts"]  # no Home: its posts need a lane
        core._apply_lists([], {})
        self.assertIn("unsorted", core.lane_by_name)
        self.assertEqual(dict(lanes.grouped(core.lanes))["personal"][-2:],
                         ["botz", "unsorted"])
        w.add(status("001", NEWS, minute=1), home=True)   # the bots lane takes it
        w.add(status("002", BOB, minute=2), home=True)    # nobody does
        w.add(status("003", ME, minute=3), home=True)     # My posts takes it (source mine)
        core.connect().result()
        core.poll_once()
        unsorted = self.ids(core, "unsorted")
        self.assertIn("002", unsorted)
        self.assertNotIn("001", unsorted)
        # a post the free lane took before, come again through another source: not unsorted
        w.add(status("001", NEWS, minute=1), mention=True)
        core.poll_once()
        self.assertNotIn("001", self.ids(core, "unsorted"))

    def test_browse_sources_never(self):
        core, w = self.make([{"name": "bots", "source": "home", "any": [{"author": "bot"}]}])
        w.local.append(w.add(status("009", LOCAL, minute=9)))
        core.connect().result()
        core.set_active_lane("local")
        core.poll_once()
        self.assertNotIn("009", self.ids(core, "unsorted"))

    def test_off_and_without_free_lanes(self):
        cfg, _ = config.validate({"lanes": {"custom": [FEED], "unsorted": False}})
        self.assertNotIn("unsorted", [x.name for x in lanes.enabled(cfg)])
        cfg, _ = config.validate({"lanes": {"enabled": ["home", "unsorted"]}})
        self.assertEqual([x.name for x in lanes.enabled(cfg)], ["home"])
        self.assertNotIn("unsorted", lanes.sources_needed(lanes.enabled(config.validate(
            {"lanes": {"custom": [FEED]}})[0])))

    def test_held_by(self):
        core, w = self.make([FEED])
        w.add(status("005", ME, minute=5), home=True)
        core.connect().result()
        core.poll_once()
        self.assertEqual(core.store.held_by("custom:", ["005", "zzz"]), {"005"})
        self.assertEqual(core.store.held_by("custom:", []), set())


class NewDefaultsTest(FreeBase):
    """The lanes of 27 Oct: To me (replies and mentions, chips part them), Home's chips
    (tags, boosts, threads with news), Important people, tag lanes "not in Home"."""

    def make_new(self, **lanes_kw):
        FakeApi.world = fakes.World()
        user = {"feed": {"first_run_mark_read": False, "page_size": 10}}
        if lanes_kw:
            user["lanes"] = lanes_kw
        cfg, _ = config.validate(user)
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        self.events = []
        core.events.on("*", lambda n, pl: self.events.append((n, pl)))
        self.addCleanup(core.shutdown)
        return core, FakeApi.world

    def test_defaults(self):
        self.assertEqual(config.DEFAULTS["lanes"]["enabled"], [])  # the set's own order
        d = [x.name for x in lanes.enabled(config.validate({})[0])]
        self.assertIn("to_me", d)
        self.assertNotIn("replies", d)
        self.assertIn("important", d)

    def test_to_me_and_its_chips(self):
        core, w = self.make_new()
        w.add(status("001", ME, minute=1), home=True)
        w.add(status("002", BOB, reply_to="001", reply_acc="ME", minute=2), mention=True)
        m = status("003", BOB, minute=3)
        m["mentions"] = [{"id": "ME", "acct": "mira"}]
        w.add(m, mention=True)
        core.connect().result()
        core.poll_once()
        self.assertEqual(self.ids(core, "to_me"), ["002", "003"])
        core.set_lane_filter("to_me", "chip:1")
        self.assertEqual(self.ids(core, "to_me"), ["002"])
        core.set_lane_filter("to_me", "chip:2")
        self.assertEqual(self.ids(core, "to_me"), ["003"])
        self.assertEqual(core.lane_filter("home"), "all")
        self.assertIsNone(core._chipper("bots"))

    def test_home_chips(self):
        core, w = self.make_new()
        w.following = {"B"}
        w.followed_tags = {"грузия"}
        w.add(status("001", BOB, minute=1), home=True)
        stranger = fakes.acct("S", "sam@far.example")
        tagged = status("002", stranger, minute=2)
        tagged["tags"] = [{"name": "Грузия"}]
        w.add(tagged, home=True)
        w.add(dict(status("003", BOB, minute=3), reblog=status("004", stranger, minute=0)),
              home=True)
        core.connect().result()
        core._following, core._following_at = {"B"}, 1e18
        core._followed_tag_names = {"грузия"}
        core.poll_once()
        self.assertEqual(self.ids(core, "home"), ["001", "002", "003"])
        core.set_lane_filter("home", "chip:1")
        self.assertEqual(self.ids(core, "home"), ["002"])
        core.set_lane_filter("home", "chip:2")
        self.assertEqual(self.ids(core, "home"), ["003"])

    def test_threads_with_news(self):
        core, w = self.make_new()
        root = w.add(status("010", BOB, minute=1), home=True)
        w.add(status("011", ME, reply_to="010", reply_acc="B", minute=2))
        core.connect().result()
        core.poll_once()
        core.subscribe(root).result()
        w.add(status("012", fakes.acct("S", "sam@far.example"), reply_to="011",
                     reply_acc="ME", minute=3))
        core.set_lane_filter("home", "chip:3")
        core.store.kv_set("unused", 1)
        import fedtail.core.subs as subs
        subs.check(core.store, core.api, "ME", 0, 30, 50)
        core._lane_cache.clear()
        self.assertEqual(core.store.threads_with_news(), {"010"})
        self.assertEqual(self.ids(core, "home"), ["010"])
        core.store.mark_read(["012"])
        core._lane_cache.clear()
        self.assertEqual(self.ids(core, "home"), [])

    def test_important_people_shows_once_there_is(self):
        core, w = self.make_new()
        core.connect().result()
        core.poll_once()
        self.assertNotIn("important", core.lane_by_name)  # nothing yet: not shown
        st = w.add(status("020", BOB, minute=5))
        w.activity.append({"id": "n20", "type": "status", "created_at": st["created_at"],
                           "account": BOB, "status": st})
        core.poll_once()
        self.assertIn("important", core.lane_by_name)
        self.assertTrue(any(n == "lists_changed" for n, _p in self.events))
        self.assertEqual(self.ids(core, "important"), ["020"])

    def test_tag_lane_not_in_home(self):
        core, w = self.make_new()
        tagged = status("030", BOB, minute=1)
        tagged["tags"] = [{"name": "politics"}]
        w.add(tagged, home=True)
        w.add(status("031", BOB, minute=2), home=True)
        core.connect().result()
        core.poll_once()
        self.assertEqual(self.ids(core, "home"), ["030", "031"])
        name = core.save_tag_group({"any": ["politics"]}, "P", in_home=False).result()
        self.assertTrue(core.tag_groups[0]["not_in_home"])
        self.assertEqual(self.ids(core, "home"), ["031"])
        core.set_tag_group_in_home(name, True).result()
        self.assertEqual(self.ids(core, "home"), ["030", "031"])
        cfg, _ = config.validate({"lanes": {"tag_groups": [
            {"name": "x", "any": ["a"], "not_in_home": True}]}})
        self.assertTrue(cfg["lanes"]["tag_groups"][0]["not_in_home"])


class RebuildNoteLanguageTest(unittest.TestCase):
    def test_the_note_speaks_the_files_language(self):
        from fedtail.core import config_update as u
        old = "[sync]\nwhat = [\"read\"]\n"
        en = u.rebuild(old, config.example_text("en"))
        ru = u.rebuild(old, config.example_text("ru"))
        en, ru = (x if isinstance(x, str) else x[0] for x in (en, ru))
        self.assertIn("# not of this version — kept as it was:", en)
        self.assertIn("# не из этой версии — оставлено как было:", ru)


class RequestsInActivityTest(FreeBase):
    """activity.requests: without a Requests lane, follow requests stand in Activity, on
    top, answered by its buttons; counted there; × doesn't touch them."""

    def make_new(self, enabled=None, **activity):
        FakeApi.world = fakes.World()
        user = {"feed": {"first_run_mark_read": False}}
        if enabled is not None:
            user["lanes"] = {"enabled": enabled}
        if activity:
            user["activity"] = activity
        cfg, _ = config.validate(user)
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        self.events = []
        core.events.on("*", lambda n, pl: self.events.append((n, pl)))
        self.addCleanup(core.shutdown)
        return core, FakeApi.world

    def test_in_activity_and_answered(self):
        from fedtail.core.view import View
        from fedtail.frontends.common import activity as act
        core, w = self.make_new()
        self.assertNotIn("requests", core.lane_by_name)
        w.requests.append(BOB)
        core.connect().result()
        core.poll_once()
        self.assertEqual(core.activity_unread(), 1)
        self.assertTrue(any(n == "activity_updated" for n, _p in self.events))
        view = View(core)
        rows = view.activity()
        self.assertEqual((rows[0].kind, rows[0].asks, rows[0].who.id), ("request", "follow", "B"))
        self.assertEqual(act.act_key(rows[0]), "follow_request")
        (row,) = [r for r in act.rows(rows, view.activity_seen(), str) if r.request]
        self.assertEqual(row.kind, "follow_request")
        core.dismiss_activity(rows[0].id).result()  # × leaves it waiting
        self.assertEqual(len(core.follow_requests), 1)
        self.assertTrue(view.answer_interaction(rows[0], True).result())
        self.assertEqual(core.follow_requests, [])
        self.assertEqual(core.activity_unread(), 0)

    def test_with_its_own_lane_not_twice(self):
        core, w = self.make_new(enabled=["home", "activity", "requests"])
        w.requests.append(BOB)
        core.connect().result()
        core.poll_once()
        self.assertEqual(core.activity_unread(), 0)
        self.assertFalse(any(e["type"] == "follow_request" for e in core.activity_entries()))

    def test_off(self):
        core, w = self.make_new(requests=False)
        w.requests.append(BOB)
        core.connect().result()
        core.poll_once()
        self.assertEqual(core.activity_entries(), [])
        self.assertEqual(core.follow_requests, [])  # nobody shows them: not even asked

    def test_answer_by_id_alone(self):
        core, w = self.make_new()
        w.requests.append(BOB)
        core.connect().result()
        core.poll_once()
        self.assertTrue(core.answer_interaction({"id": "follow_request:B",
                                                 "type": "follow_request"}, False).result())
        self.assertEqual(core.follow_requests, [])


class TitleLanguagesTest(unittest.TestCase):
    def test_title_per_language(self):
        from fedtail import i18n
        self.addCleanup(i18n.setup, "ru")
        rule = {"name": "posts", "title": {"ru": "Посты", "en": "Posts"},
                "any": [{"author": "me"}]}
        c, w = _own(custom.load(config.validate({"lanes": {"custom": [rule]}})[0]))
        self.assertEqual(w, [])
        i18n.setup("en")
        self.assertEqual(c.title, "Posts")
        i18n.setup("ru")
        self.assertEqual(c.title, "Посты")
        only, _w = _own(custom.load(config.validate({"lanes": {"custom": [
            dict(rule, title={"ka": "პოსტები"})]}})[0]))
        self.assertEqual(only.title, "პოსტები")
        en, _w = _own(custom.load(config.validate({"lanes": {"custom": [
            dict(rule, title={"en": "Posts", "ka": "პოსტები"})]}})[0]))
        self.assertEqual(en.title, "Posts")
        empty, _w = _own(custom.load(config.validate({"lanes": {"custom": [
            dict(rule, title={"en": ""})]}})[0]))
        self.assertEqual(empty.title, "posts")


class NamedInListsTest(FreeBase):
    def test_free_lanes_in_notify_icon_sound_start(self):
        user = {"lanes": {"custom": [FEED]}, "notify": {"lanes": ["custom:feed"]},
                "ui": {"icon_count": ["custom:feed"], "start_lane": "custom:feed"},
                "sound": {"lanes": ["custom:feed"]}}
        cfg, warnings = config.validate(user)
        self.assertEqual(cfg["notify"]["lanes"], ["feed"])  # the old way of naming it
        with self.assertRaises(config.ConfigError):
            config.validate(dict(user, notify={"lanes": ["custom:nope"]}))
        # lanes.enabled may name it: it stands there
        cfg, _ = config.validate({"lanes": {"enabled": ["home", "custom:feed", "direct"],
                                            "custom": [FEED]}})
        self.assertEqual([x.name for x in lanes.enabled(cfg)][:3],
                         ["home", "feed", "direct"])
        self.assertEqual(dict(lanes.grouped(lanes.enabled(cfg)))["personal"],
                         ["feed", "direct", "unsorted"])
        with self.assertRaises(config.ConfigError):
            config.validate({"lanes": {"enabled": ["home", "custom:nope"], "custom": [FEED]}})
        cfg, _ = config.validate({"lanes": {"custom": [dict(FEED, group="standard")]}})
        self.assertIn("feed", dict(lanes.grouped(lanes.enabled(cfg)))["standard"])

    def test_notified(self):
        core, w = self.make([FEED])
        core.cfg["notify"]["lanes"] = ["feed"]
        core.connect().result()
        core.poll_once()
        w.local.append(w.add(status("009", LOCAL, minute=9)))
        core.poll_once()
        got = [(lane, st["id"]) for n, pl in self.events if n == "notify" for lane, st in pl]
        self.assertIn(("feed", "009"), got)


class LanesToConfigTest(unittest.TestCase):
    """fedtail --lanes-to-config: the set's lanes into config.toml, the lanes the same."""

    def test_written_out_and_the_same_lanes(self):
        import tomllib

        from fedtail.core import config_update as u
        user = config.example_text("en")
        before = [(x.name, x.source) for x in lanes.enabled(config.validate(
            tomllib.loads(user))[0])]
        report = {}
        out = u.lanes_to_config(user, report)
        self.assertIn("home", report["written"])
        self.assertIn("#custom = []  # → [[lanes.custom]] below", out)
        cfg, warnings = config.validate(tomllib.loads(out))
        self.assertEqual(warnings, [])
        self.assertEqual([(x.name, x.source) for x in lanes.enabled(cfg)], before)
        home = next(x for x in cfg["lanes"]["custom"] if x["name"] == "home")
        self.assertEqual(home["none"], [{"author": "bot"}])
        self.assertEqual(u.lanes_to_config(out), out)  # all there: nothing more

    def test_own_lanes_stay_and_russian(self):
        import tomllib

        from fedtail.core import config_update as u
        user = config.example_text("ru").replace(
            "\ncustom = []\n", "\n#custom = []\n") + \
            '\n[[lanes.custom]]\nname = "home"\nsource = "home"\nany = [{}]\n'
        report = {}
        out = u.lanes_to_config(user, report)
        self.assertNotIn("home", report["written"])
        self.assertIn("Ленты набора «fedtail»", out)
        cfg, _ = config.validate(tomllib.loads(out))
        homes = [x for x in cfg["lanes"]["custom"] if x["name"] == "home"]
        self.assertEqual(homes, [{"name": "home", "source": "home", "any": [{}]}])
        cfg, _ = config.validate({"lanes": {"preset": "tusky"}})
        self.assertIn("mentions", [x.name for x in lanes.enabled(cfg)])

    def test_hidden_lanes_stay_out(self):
        import tomllib

        from fedtail.core import config_update as u
        user = "[lanes]\nenabled = [\"home\", \"direct\"]\n"
        report = {}
        out = u.lanes_to_config(user, report)
        self.assertEqual(report["written"], ["home", "direct", "lists", "tags"])
        cfg, _ = config.validate(tomllib.loads(out))
        self.assertEqual([x.name for x in lanes.enabled(cfg)], ["home", "direct"])


class UnsortedAndListsTest(FreeBase):
    def test_list_members_are_not_unsorted(self):
        """Someone in a list leaves Home (lists.hide_in) for the list's lane: not Unsorted
        (24.10: "tits" went there)."""
        core, w = self.make([FEED])
        w.lists = {"L1": {"title": "tits", "exclusive": False, "members": {"B"}}}
        w.add(status("001", BOB, minute=1), home=True)
        w.add(dict(status("002", NEWS, minute=2), reblog=status("003", BOB, minute=0)),
              home=True)
        core.connect().result()
        core.poll_once()
        core.poll_once()  # the lists come with the first round; their lanes catch up next
        self.assertIn("list:L1", core.lane_by_name)
        self.assertNotIn("001", self.ids(core, "home"))
        self.assertIn("001", self.ids(core, "list:L1"))
        self.assertEqual(self.ids(core, "unsorted"), [])

    def test_cleared_once_a_lane_has_it(self):
        core, w = self.make([FEED])
        core.connect().result()
        core.poll_once()
        core.store.put_items("unsorted", [("009", status("009", BOB), "")])
        core.store.put_items("home", [("009", status("009", BOB), "")])
        self.assertEqual(core.store.drop_held("unsorted", {"home", "unsorted"}), 1)
        self.assertEqual(core.store.drop_held("unsorted", {"unsorted"}), 0)
        self.assertEqual(core.store.held_in([], ["009"]), set())
