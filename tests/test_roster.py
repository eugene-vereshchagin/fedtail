"""View.roster: the lanes as a messenger's roster — groups, unread, the newest post."""

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
        self.assertEqual(home.title, core.lane_title("home"))
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
