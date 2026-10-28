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
    """view = "threads" (the extra set's "Commented posts", as on Point): a card a
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
        m = LaneModel(view, "commented")
        specs = [s for s in m.build(False).specs if s.entry is not None]
        self.assertEqual([s.entry.id for s in specs], ["100"])  # one card: the post
        self.assertEqual(specs[0].extra["conversation"]["unread"], 2)
        self.assertFalse(m.conversations_offered())  # always threads: no switch
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
