"""View.roster: the lanes as a messenger's roster — groups, unread, the newest post."""

from fedtail import i18n
from fedtail.core import auth, config, paths
from fedtail.core.app import Core
from fedtail.core.view import View
from fedtail.model import Post, RosterGroup

from . import fakes
from .fakes import BOB, FakeApi, status
from .test_core import TmpDir


class RosterTest(TmpDir):
    def make(self):
        FakeApi.world = fakes.World()
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False}})
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        self.addCleanup(core.shutdown)
        core.connect().result()
        return core, FakeApi.world

    def test_groups_unread_and_the_newest(self):
        core, w = self.make()
        w.add(status("1", BOB, minute=1, text="старое"), home=True)
        w.add(status("2", BOB, minute=2, text="свежее"), home=True)
        core.poll_once()
        v = View(core)
        roster = v.roster()
        self.assertTrue(all(isinstance(g, RosterGroup) for g in roster))
        self.assertEqual(roster[0].name, "standard")
        home = next(i for g in roster for i in g.items if i.key == "home")
        self.assertEqual(home.title, core.lane_title("home") or i18n._("lane_home"))
        self.assertTrue(all(isinstance(i.title, str) and i.title
                            for g in roster for i in g.items))  # every one has a name
        self.assertGreaterEqual(home.unread, 2)
        self.assertIsInstance(home.last, Post)
        self.assertEqual(home.last.id, "2")  # the newest, as a status line
        group = next(g for g in roster if any(i.key == "home" for i in g.items))
        self.assertGreaterEqual(group.unread, home.unread)
        core.mark_read(["1", "2"])
        home = next(i for g in v.roster() for i in g.items if i.key == "home")
        self.assertEqual(home.unread, 0)
        names = [i.key for g in roster for i in g.items]
        self.assertEqual(len(names), len(set(names)))  # each lane once
        self.assertEqual(set(names), {lane.name for lane in core.lanes})

    def test_threads_and_talks_are_contacts(self):
        """A followed thread and a private talk stand in the roster as items of their
        own, the freshest first, with what's new in them."""
        from fedtail.model import RosterItem
        core, w = self.make()
        core.poll_once()  # first run
        core.cfg["subs"]["interval_minutes"] = 0  # check every poll here
        alice = fakes.acct("A", "alice@example.org")
        w.add(status("100", fakes.ME, minute=20, text="мой тред"), home=True)
        core.poll_once()  # my post: followed by itself
        w.add(status("101", BOB, "100", "ME", minute=21), mention=True)
        w.add(status("102", alice, "101", "B", minute=22))  # alice answers bob, no @me
        core.poll_once()
        v = View(core)
        threads = next((g for g in v.roster() if g.name == "threads"), None)
        if "subs" not in core.lane_by_name:
            self.assertIsNone(threads)
            return
        self.assertIsNotNone(threads)
        item = threads.items[0]
        self.assertIsInstance(item, RosterItem)
        self.assertEqual((item.kind, item.key), ("thread", "100"))
        self.assertEqual(item.unread, 1)
        self.assertEqual(item.ids, ("102",))
        self.assertIn("мой тред", item.title)
        core.cfg["ui"]["roster_threads"] = 0
        self.assertFalse(any(g.name == "threads" for g in v.roster()))



class TalkTitleTest(TmpDir):
    def test_who_is_in_it_but_me(self):
        from fedtail.core.view import _conv_title
        from fedtail.protocols.mastodon import adapter
        dm = dict(status("5", BOB, text="привет"), visibility="direct",
                  mentions=[{"id": "ME", "acct": "mira", "username": "mira"},
                            {"id": "A", "acct": "alice@x", "username": "alice"}])
        me = adapter.account(fakes.ME)
        self.assertEqual(_conv_title(adapter.post(dm), "talk", me),
                         f"{BOB.get('display_name') or BOB['username']}, alice")
        mine = dict(status("6", fakes.ME, text="ну"), visibility="direct",
                    mentions=[{"id": "B", "acct": BOB["acct"], "username": BOB["username"]}])
        self.assertEqual(_conv_title(adapter.post(mine), "talk", me), BOB["username"])
        self.assertTrue(_conv_title(adapter.post(dm), "thread", me).endswith(": привет"))


class PeopleTest(RosterTest):
    def test_mutuals_stand_as_people_and_are_asked_once_a_day(self):
        """Whom I follow and who follows me back: the roster's "People", each a
        contact to write to in private; asked of the server once a day."""
        core, w = self.make()
        w.add(status("1", BOB, minute=1, text="привет"), home=True)
        w.following.add(BOB["id"])
        asked = []

        def rel(ids):
            asked.append(list(ids))
            return [{"id": i, "followed_by": True} for i in ids]
        core.api.relationships = rel
        v = View(core)
        self.assertEqual(v.mutuals(), [])
        self.assertEqual(v.refresh_mutuals().result(), 1)
        self.assertEqual([a.id for a in v.mutuals()], [BOB["id"]])
        v.refresh_mutuals().result()
        self.assertEqual(len(asked), 1)  # fresh: not asked again the same day
        people = next(g for g in v.roster() if g.name == "people")
        item = people.items[0]
        self.assertEqual((item.kind, item.key), ("person", BOB["id"]))
        self.assertEqual(item.who.id, BOB["id"])
        self.assertTrue(item.title)
