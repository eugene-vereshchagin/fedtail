"""Every lane is a rule, events too (feeds.md, 28.10): Activity and Requests are lanes of
events only, built by the same lane model as any other; a follow request is an event any
lane may take; an event's row is the same everywhere (common/activity.EventParts), its
buttons fedtail: links; seen on screen = seen everywhere."""

import tempfile
import unittest
from pathlib import Path

from fedtail import i18n
from fedtail.core import auth, config, paths
from fedtail.core.app import Core
from fedtail.core.view import View
from fedtail.frontends.common import activity, links
from fedtail.frontends.common.lane import LaneModel
from tests import fakes
from tests.fakes import BOB, FakeApi, status


class Host:
    """What common/links.py asks of a window, writing down what it was asked."""

    def __init__(self):
        self.said, self.errors = [], []

    def call(self, fut, ok=None, fail=None):
        try:
            got = fut.result(5)
        except Exception as e:  # noqa: BLE001
            if fail:
                fail(str(e))
            return
        if ok:
            ok(got)

    def status(self, text):
        self.said.append(text)

    def error(self, text):
        self.errors.append(text)


class EventLanesTest(unittest.TestCase):
    def make(self, lanes=None, custom=()):
        i18n.setup("en")
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        FakeApi.world = w = fakes.World()
        user = {"feed": {"first_run_mark_read": False},
                "lanes": {"custom": list(custom)}}
        if lanes:
            user["lanes"]["enabled"] = lanes
        cfg, _ = config.validate(user)
        p = paths.resolve("t", config=str(Path(tmp.name) / "c.toml"),
                          data=str(Path(tmp.name) / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        self.addCleanup(core.shutdown)
        core.connect().result()
        core.poll_once()
        return core, w

    def like(self, core, nid, post_id="500"):
        core.store.activity_put([{"id": nid, "type": "favourite", "account": BOB,
                                  "created_at": "2026-10-28T10:00:00.000Z",
                                  "status": status(post_id, fakes.ME, minute=1)}])

    def test_activity_is_a_lane_of_rules(self):
        core, w = self.make()
        lane = core.lane_by_name["activity"]
        self.assertTrue(lane.events)
        self.assertIsNone(lane.source)  # no posts at all
        c = next(c for c in core.customs if c.name == "activity")
        self.assertTrue(c.events_only)
        # its quick filters are its rule's switches: reactions, follows, requests…
        self.assertIn("@actf_reactions", dict(lane.chips).values())

    def test_rows_seen_and_answered_in_any_lane(self):
        core, w = self.make()
        view = View(core)
        self.like(core, "n1")
        w.requests.append(BOB)
        core.poll_once()
        self.assertEqual(core.unread_count("activity"), 2)  # the like, the request
        m = LaneModel(view, "activity")
        specs = [s for s in m.build(False).specs if s.extra.get("event")]
        self.assertEqual(len(specs), 2)
        kinds = {s.extra["row"].kind for s in specs}
        self.assertEqual(kinds, {"favourite", "follow_request"})
        req = next(s for s in specs if s.extra["row"].request)
        parts = activity.event_parts(req.extra["row"], str)
        self.assertEqual(len(parts.answers), 1)
        self.assertTrue(parts.answers[0][0].startswith("fedtail:eventyes/"))
        self.assertTrue(parts.hide.startswith("fedtail:eventhide/"))
        self.assertEqual(parts.people[0][1], "fedtail:account/B")
        like = next(s for s in specs if not s.extra["row"].request)
        lp = activity.event_parts(like.extra["row"], str)
        self.assertEqual(lp.post_link, "fedtail:thread/500")
        self.assertIn("«", lp.post)
        # the like seen on screen: seen everywhere; the request still waits
        m.read([like.key])
        self.assertEqual(core.unread_count("activity"), 1)
        # answered by its link, as any interface's button does
        host = Host()
        links.Links(view, host).open(parts.answers[0][0])
        self.assertEqual(host.errors, [])
        self.assertEqual(core.follow_requests, [])
        self.assertEqual(core.unread_count("activity"), 0)

    def test_requests_where_one_wants_them(self):
        """A lane of one's own taking follow requests (here: among the federated posts
        of Home) — the requests come there; Activity keeps them too (no Requests lane)."""
        mine = {"name": "home", "source": "home",
                "any": [{}, {"event": "follow_request", "switch": "requests"}]}
        core, w = self.make(custom=[mine])
        view = View(core)
        w.add(status("010", BOB, minute=2), home=True)
        w.requests.append(BOB)
        core.poll_once()
        self.assertTrue(core.lane_by_name["home"].events)
        m = LaneModel(view, "home")
        keys = [s.key for s in m.build(False).specs if s.entry is not None or
                s.extra.get("event")]
        self.assertIn("event:follow_request:B", keys)
        self.assertTrue(any(k.endswith("010") for k in keys))
        notes = [pl for n, pl in core._events_by_lane([BOB]).items()]
        self.assertTrue(notes)

    def test_requests_apart_when_their_lane_is_shown(self):
        core, w = self.make(lanes=["home", "activity", "requests"])
        w.requests.append(BOB)
        core.poll_once()
        self.assertEqual(core.unread_count("requests"), 1)
        self.assertEqual(core.unread_count("activity"), 0)  # apart = "requests"
        self.assertEqual([n["type"] for n in core.lane_events("requests")],
                         ["follow_request"])

    def test_hide_by_link(self):
        core, w = self.make()
        view = View(core)
        self.like(core, "n7")
        core._events_cache = {}
        m = LaneModel(view, "activity")
        (spec,) = [s for s in m.build(False).specs if s.extra.get("event")]
        host = Host()
        links.Links(view, host).open(activity.event_parts(spec.extra["row"], str).hide)
        self.assertEqual(host.errors, [])
        self.assertEqual(core.lane_events("activity"), [])

    def test_legacy_kind_in_the_file(self):
        """`kind = "activity"` written into config.toml before 0.22: the set's rule."""
        core, w = self.make(custom=[{"name": "activity", "group": "personal",
                                     "kind": "activity"}])
        self.assertTrue(core.lane_by_name["activity"].events)


if __name__ == "__main__":
    unittest.main()
