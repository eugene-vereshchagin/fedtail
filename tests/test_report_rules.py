"""Rule keys from the competitors' report (feeds.md §4): a condition that holds till a
date, words matched in the author's name, at most N posts of one author, a lane bundled
by author, and people taken out of Home while still followed."""

import unittest
from datetime import UTC, datetime, timedelta

from fedtail.core import atoms
from fedtail.core.app import _bundled, _per_author

from .test_atoms import BOT, FRIEND, STRANGER, facts, st


class UntilTest(unittest.TestCase):
    def test_a_condition_ends(self):
        now = datetime.now(UTC)
        f = facts(st("a", FRIEND))
        later = (now + timedelta(days=2)).strftime("%Y-%m-%d")
        gone = (now - timedelta(days=2)).strftime("%Y-%m-%d")
        self.assertTrue(atoms.Condition.parse({"author": "followed", "until": later}).matches(f))
        self.assertFalse(atoms.Condition.parse({"author": "followed", "until": gone}).matches(f))
        from datetime import date
        self.assertTrue(atoms.Condition.parse({"until": date(2999, 1, 1)}).matches(f))
        w = []
        self.assertTrue(atoms.Condition.parse({"until": "next week"}, w).broken)
        self.assertTrue(w)


class NameTest(unittest.TestCase):
    def test_words_in_the_name(self):
        f = facts(st("a", BOT))
        c = atoms.Condition.parse({"text": "news@", "text_in": "name"})
        self.assertTrue(c.matches(f))
        self.assertFalse(atoms.Condition.parse({"text": "news@"}).matches(f))  # not in text
        rx = atoms.Condition.parse({"text": r"@news@bots\.example$", "text_in": ["name"],
                                    "text_regex": True})
        self.assertTrue(rx.matches(f))


class PerAuthorBundleTest(unittest.TestCase):
    def entries(self):
        def e(i, who, minute):
            return (str(i), {"id": str(i), "account": {"id": who},
                             "created_at": f"2026-10-27T10:{minute:02d}:00.000Z"})
        return [e(1, "a", 1), e(2, "b", 2), e(3, "a", 3), e(4, "a", 4), e(5, "c", 5),
                e(6, "b", 6)]

    def test_at_most_n_of_one(self):
        got = [x[0] for x in _per_author(self.entries(), 2)]
        self.assertEqual(got, ["2", "3", "4", "5", "6"])  # a's oldest went

    def test_bundled_by_author(self):
        got = [x[0] for x in _bundled(self.entries(), True)]
        self.assertEqual(got, ["1", "3", "4", "2", "6", "5"])  # a (3), b (2), c (1)
        got = [x[0] for x in _bundled(self.entries(), False)]
        self.assertEqual(got, ["5", "2", "6", "1", "3", "4"])

    def test_rule_keys(self):
        r = atoms.Rule.parse({"name": "x", "any": [{}], "per_author": 3, "bundle": "author"})
        self.assertEqual((r.per_author, r.bundle, r.warnings), (3, "author", []))
        bad = atoms.Rule.parse({"name": "x", "any": [{}], "per_author": "many",
                                "bundle": "topic"})
        self.assertEqual(len(bad.warnings), 2)


class HiddenHomeTest(unittest.TestCase):
    def test_the_atom_and_the_home_lanes(self):
        from fedtail.core import presets
        f = facts(st("a", FRIEND), hidden_home={FRIEND["id"]})
        self.assertIn("hidden_home", f.author)
        self.assertNotIn("hidden_home", facts(st("b", STRANGER)).author)
        for name in presets.names():
            home = next(t for t in presets.lanes_of(name) if t["name"] == "home")
            self.assertIn({"author": "hidden_home"}, home["none"], name)

    def test_the_profile_button(self):
        from fedtail import i18n
        from fedtail.core import config
        from fedtail.frontends.common import profile
        from fedtail.model import Relationship
        i18n.setup("en")
        cfg, _w = config.validate({})
        acc = type("A", (), {"id": "2", "following": 0, "followers": 0, "url": "",
                             "handle": "friend@far.example"})()
        rel = Relationship(following=True)
        keys = [a.key for a in profile.actions(acc, rel, False, cfg, lambda _x: True)]
        self.assertNotIn("home_hide", keys)  # off by default (people.home_hide)
        cfg["feed"]["home_hide"] = True
        acts = profile.actions(acc, rel, False, cfg, lambda _x: True)
        self.assertIn("home_hide", [a.key for a in acts])
        hidden = profile.actions(acc, Relationship(following=True, hidden_home=True), False,
                                 cfg, lambda _x: True)
        label = next(a.label for a in hidden if a.key == "home_hide")
        self.assertIn(i18n._("home_hide_off"), label)


if __name__ == "__main__":
    unittest.main()


class ThreadsViewTest(unittest.TestCase):
    """view = "threads" (the extra set's "Comments", as on Point): a card a
    thread with new comments, and a click opens it at the first of them."""

    def test_a_card_a_thread_and_the_jump(self):
        import tempfile
        from pathlib import Path

        from fedtail import i18n
        from fedtail.core import auth, config, paths
        from fedtail.core.app import Core
        from fedtail.core.view import View
        from fedtail.frontends.common.lane import LaneModel
        from tests import fakes
        from tests.fakes import BOB, ME, FakeApi, status
        i18n.setup("en")
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        FakeApi.world = w = fakes.World()
        w.add(status("090", BOB, minute=0, vis="public"), home=True)
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False},
                                  "lanes": {"enabled": ["home", "commented"]}})
        p = paths.resolve("t", config=str(Path(tmp.name) / "c.toml"),
                          data=str(Path(tmp.name) / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        self.addCleanup(core.shutdown)
        core.connect().result()
        core.cfg["subs"]["interval_minutes"] = 0  # checked every poll here
        core.poll_once()  # the first run
        root = w.add(status("100", ME, minute=1, vis="public"), home=True)
        core.poll_once()  # my post: followed by itself (subs.auto = posts)
        self.assertTrue(core.subscribed(root))
        w.add(status("101", BOB, "100", "ME", minute=2), mention=True)  # to me
        w.add(status("102", fakes.acct("A", "alice@example.org"), "101", "B", minute=3))
        core.poll_once()
        view = View(core)
        lane = core.lane_by_name["commented"]
        self.assertEqual(lane.view, "threads")
        lane.threads_shown = ""  # the extra set's way: the threads with news only
        m = LaneModel(view, "commented")
        specs = [s for s in m.build(False).specs if s.entry is not None]
        self.assertEqual([s.entry.id for s in specs], ["100"])  # one card: the post
        self.assertEqual(specs[0].extra["conversation"]["unread"], 2)
        self.assertFalse(m.conversations_offered())  # always threads: no switch
        # the number on the lane is the threads with news (the cards), not the comments:
        # one card here, two comments in it (28.10's report: "64 +64" for a few cards)
        self.assertEqual(core.unread_count("commented"), 1)
        self.assertEqual(core.fresh_count("commented"), 1)
        from fedtail.frontends.common import sidebar
        self.assertEqual(sidebar.count(view, "commented"), 1)
        # where its thread opens: the lane says "first_unread" — the card's links say it
        self.assertEqual(specs[0].open_at, "first_unread")
        self.assertEqual(view.open_at("commented"), "first_unread")
        self.assertEqual(view.open_at("home"), "post")  # threads.open_at
        from fedtail.frontends.common import actions
        from fedtail.frontends.common.cardtext import card_words
        w = card_words(specs[0], core.cfg, str)
        self.assertEqual(w.meta[0].link, "fedtail:threadnew/100")
        items = view.thread("100").result()
        self.assertEqual(view.thread_focus("100", items, "first_unread"), "101")
        self.assertEqual(view.thread_focus("100", items, "post"), "100")
        home = [s for s in LaneModel(view, "home").build(False).specs if s.entry is not None]
        self.assertTrue(all(s.open_at == "post" for s in home))
        core.cfg["feed"]["open_at"] = "first_unread"  # the setting: every lane without its own
        self.assertEqual(view.open_at("home"), "first_unread")
        core.cfg["feed"]["open_at"] = "post"
        del actions
        core.mark_read(["101", "102"])
        view._cache.clear()
        self.assertEqual(len([s for s in m.build(True).specs if s.entry]), 1)  # kept now
        m.left()
        self.assertEqual([s for s in m.build(False).specs if s.entry], [])  # nothing new


class AllThreadsTest(unittest.TestCase):
    """30.10, the author: fedtail's "Comments" shows every thread I took part in (my
    post, my comment, one I follow), those with new comments together where reading
    starts, the "new below" line over them — "read below" under them, newest first."""

    def test_every_thread_the_new_together(self):
        import tempfile
        from pathlib import Path

        from fedtail import i18n
        from fedtail.core import auth, config, paths
        from fedtail.core.app import Core
        from fedtail.core.view import View
        from fedtail.frontends.common.lane import SEPARATOR, LaneModel
        from tests import fakes
        from tests.fakes import BOB, ME, FakeApi, status
        i18n.setup("en")
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        FakeApi.world = w = fakes.World()
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False},
                                  "lanes": {"preset": "fedtail",
                                            "enabled": ["home", "commented"]}})
        p = paths.resolve("t", config=str(Path(tmp.name) / "c.toml"),
                          data=str(Path(tmp.name) / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        self.addCleanup(core.shutdown)
        core.connect().result()
        core.cfg["subs"]["interval_minutes"] = 0
        core.poll_once()
        w.add(status("100", ME, minute=1, vis="public"), home=True)
        w.add(status("200", ME, minute=2, vis="public"), home=True)
        core.poll_once()  # my posts: followed by themselves
        w.add(status("201", BOB, "200", "ME", minute=3), mention=True)  # older news…
        w.add(status("101", BOB, "100", "ME", minute=4), mention=True)  # …then read
        core.poll_once()
        core.mark_read(["101"])
        view = View(core)
        self.assertEqual(core.lane_by_name["commented"].threads_shown, "all")
        self.assertEqual(i18n._("lane_commented"), "Comments")
        built = LaneModel(view, "commented").build(False).specs
        # the read thread too, before the line; the new one after it, though older
        self.assertEqual([s.entry.id if s.entry else s.key for s in built],
                         ["100", SEPARATOR, "200"])
        self.assertEqual(built[1].extra["separator"], "new below")
        core.cfg["feed"]["order"] = "newest_first"
        built = LaneModel(view, "commented").build(False).specs
        self.assertEqual([s.entry.id if s.entry else s.key for s in built],
                         ["200", SEPARATOR, "100"])
        self.assertEqual(built[1].extra["separator"], "read below")
        core.cfg["feed"]["order"] = "oldest_first"
        # the extra set's lane of the same name: only the threads with news, as before
        core.lane_by_name["commented"].threads_shown = ""
        built = LaneModel(view, "commented").build(False).specs
        self.assertEqual([s.entry.id for s in built if s.entry], ["200"])


class CommentAsMentionTest(unittest.TestCase):
    """28.10: a comment in a followed thread that came only as a mention (an unlisted
    reply to me in a public thread) went to "To me" alone — the thread's membership was
    learned at its next check — and "Commented posts" didn't come up. Up its parents it
    is a member at once now."""

    def test_the_thread_comes_up_at_once(self):
        import tempfile
        from pathlib import Path

        from fedtail import i18n
        from fedtail.core import auth, config, paths
        from fedtail.core.app import Core
        from fedtail.core.view import View
        from fedtail.frontends.common.lane import LaneModel
        from tests import fakes
        from tests.fakes import BOB, ME, FakeApi, status
        i18n.setup("en")
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        FakeApi.world = w = fakes.World()
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False},
                                  "lanes": {"enabled": ["home", "to_me", "commented"]}})
        p = paths.resolve("t", config=str(Path(tmp.name) / "c.toml"),
                          data=str(Path(tmp.name) / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        self.addCleanup(core.shutdown)
        core.connect().result()
        core.cfg["subs"]["interval_minutes"] = 0
        core.poll_once()
        root = w.add(status("100", ME, minute=1, vis="public"), home=True)
        core.poll_once()  # my post: followed (subs.auto = posts), its thread checked
        self.assertTrue(core.subscribed(root))
        mine = w.add(status("101", ME, "100", "ME", minute=2, vis="public"), home=True)
        core.poll_once()
        core.mark_read(["100", "101"])
        # the thread isn't checked again before the reply comes (a long interval)
        core.cfg["subs"]["interval_minutes"] = 600
        w.add(status("102", BOB, mine["id"], "ME", minute=3, vis="unlisted"), mention=True)
        core.poll_once()
        self.assertEqual(core.followed_root("102"), "100")
        self.assertEqual(core.store.sub_root_of("102"), "100")  # a member from now on
        view = View(core)
        specs = [s for s in LaneModel(view, "commented").build(False).specs
                 if s.entry is not None]
        self.assertEqual([s.entry.id for s in specs], ["100"])  # the thread came up
        self.assertEqual(core.unread_count("commented"), 1)
        self.assertIsNone(core.followed_root("nope"))
