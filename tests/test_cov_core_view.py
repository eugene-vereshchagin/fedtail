"""core/view.py — the model-only face of a Core — at its edges: futures cancelled or
failing, every kind of server object made the model and back, the remembered raw
objects kept to their cap, pictures from the shared cache or the network, the roster's
people, probes and redrafts."""

import hashlib
import time
import unittest
from concurrent.futures import Future
from unittest import mock

from fedtail.core import auth, config, paths
from fedtail.core import view as view_mod
from fedtail.core.app import Core
from fedtail.core.threads import Node
from fedtail.core.view import View, _probe, _rel_raw, _shape, _then, is_entry
from fedtail.model import Account, Activity, Post, Relationship, ThreadItem, UserList
from fedtail.protocols.mastodon import adapter

from . import fakes
from .fakes import BOB, ME, NEWS, FakeApi, status
from .test_core import TmpDir

T = 10


def done(v):
    f = Future()
    f.set_result(v)
    return f


class ThenTest(unittest.TestCase):
    def test_cancelled_failed_and_a_failing_fn(self):
        f = Future()
        out = _then(f, lambda x: x)
        f.cancel()
        self.assertTrue(out.cancelled())
        f = Future()
        out = _then(f, lambda x: x)
        f.set_exception(KeyError("k"))
        with self.assertRaises(KeyError):
            out.result()
        with self.assertRaises(ZeroDivisionError):
            _then(done(1), lambda x: x / 0).result()


class ShapesTest(unittest.TestCase):
    def test_shapes_and_helpers(self):
        self.assertEqual(_shape({"id": "L", "title": "x", "exclusive": False}), "list")
        self.assertEqual(_shape({"id": "n", "type": "follow", "account": BOB,
                                 "created_at": "x"}), "activity")
        self.assertIsNone(_shape({"name": "x"}))
        self.assertIsNone(_shape({"id": "1"}))
        self.assertFalse(is_entry({"id": "1"}))
        p = _probe({"checked": 1700000000, "software": "gts", "version": "0.20",
                    "items": [("trends", "no", None)]})
        self.assertEqual(p.software, "gts")
        self.assertEqual(p.features[0].detail, "")
        self.assertIsNone(_probe({}).checked)
        rel = adapter.relationship({"id": "B", "following": True, "followed_by": False,
                                    "showing_reblogs": False, "languages": ["ru"]})
        raw = _rel_raw(rel)
        self.assertEqual((raw["showing_reblogs"], raw["languages"]), (False, ["ru"]))


class ViewTest(TmpDir):
    def setUp(self):
        super().setUp()
        FakeApi.world = self.w = fakes.World()
        reply = status("011", BOB, "010", "ME", minute=11, text="ответ @mira")
        reply["mentions"] = [{"id": "ME", "acct": "mira", "username": "mira",
                              "url": "https://example.test/@mira"}]
        reply["content"] = ('<p><a href="https://example.test/@mira" class="u-url mention">'
                            '@mira</a> ответ</p>')
        self.w.add(status("010", ME, minute=10, text="мой пост"), home=True)
        self.w.add(reply, home=True)
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False,
                                           "complete_threads": False}})
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok",
                                "acct": "mira"})
        self.core = Core(cfg, p, api_class=FakeApi)
        self.core._origin_json = lambda url: None
        self.core._origin_get = lambda url: None  # never another server
        self.addCleanup(self.core.shutdown)
        self.core.connect().result(timeout=T)
        self.core.poll_once()
        self.v = View(self.core)

    def post(self, sid):
        return self.v.by_id(sid)

    def test_converting_both_ways(self):
        v = self.v
        act = v._out({"id": "n1", "type": "follow", "account": BOB,
                      "created_at": "2026-01-01T00:00:00Z"})
        self.assertIsInstance(act, Activity)
        self.assertEqual(v._in(act)["id"], "n1")
        self.assertIsInstance(v._out({"id": "L", "title": "x", "exclusive": True}), UserList)
        node = v._out(Node(self.core.store.get_status("010"), 0, 0))
        self.assertIsInstance(node, ThreadItem)
        self.assertEqual(v._out(("a", [1])), ("a", [1]))
        rel = Relationship(following=True)
        self.assertTrue(v._in(rel)["following"])
        self.assertTrue(v._in(("x", rel))[1]["following"])
        stranger = adapter.account(dict(NEWS, id="Z"), "elsewhere")
        raw = v._in(stranger)  # never seen: made up from the model
        self.assertEqual((raw["id"], raw["acct"]), ("Z", NEWS["acct"]))
        self.assertEqual(v._raw("nope"), {"id": "nope"})
        self.assertEqual(v.raw("010")["id"], "010")
        self.assertEqual(v.raw_account(stranger)["id"], "Z")

    def test_raw_objects_kept_to_their_cap(self):
        v = self.v
        with mock.patch.object(view_mod, "RAW_KEEP", 2):
            for i in range(4):
                v.acc(dict(BOB, id=f"A{i}"))
                v._activity_of({"id": f"n{i}", "type": "follow", "account": BOB,
                                "created_at": "2026-01-01T00:00:00Z"})
        self.assertEqual(len(v._raw_accounts), 2)
        self.assertEqual(len(v._raw_activity), 2)
        self.assertIsNone(v.acc("not an account"))

    def test_lookups(self):
        v = self.v
        reply = self.post("011")
        self.assertEqual(v.parent(reply).id, "010")
        self.assertEqual(v.read_ids([]), set())
        self.assertEqual(v.read_ids(["010", "011"]), {"010"})  # mine: read
        self.assertIsNone(v.by_id("nope"))
        self.assertEqual(v.stored("010").id, "010")
        self.assertIsNone(v.stored("nope"))
        self.assertIn("fedtail:account/ME", v.in_app(reply))
        self.assertIn("fedtail:tag/x",
                      v.in_app_html('<a class="hashtag" href="https://e.test/tags/x">#x</a>'))
        self.assertIsNone(v.relation_known("B"))
        v.relationship("B").result(timeout=T)
        self.assertIsInstance(v.relation_known("B"), Relationship)
        self.assertEqual(v.auth_handle, "mira")
        v.unsubscribe(reply).result(timeout=T)
        self.assertFalse(v.subscribed(reply))

    def test_scheduled_filtered_resolve(self):
        v = self.v
        self.w.scheduled = [{"id": "S", "scheduled_at": "2030-01-01T00:00:00Z",
                             "params": {"text": "потом"}}, "junk"]
        got = v.scheduled().result(timeout=T)
        self.assertEqual([(s.id, s.text) for s in got], [("S", "потом")])
        self.w.policy = {"for_not_following": "filter"}
        self.w.held = [{"id": "R", "account": BOB, "notifications_count": 2,
                        "last_status": status("099", BOB, minute=1)}]
        self.core.caps.learn("notification_policy", True)
        f = v.filtered().result(timeout=T)
        self.assertEqual(f["requests"][0].count, 2)
        self.w.policy = None
        self.assertIsNone(v.filtered().result(timeout=T))
        self.assertIsNone(v.resolve("https://nowhere.test/x").result(timeout=T))
        url = self.w.statuses["011"].get("url") or "https://example.test/@bob/011"
        self.w.statuses["011"]["url"] = url
        self.assertEqual(v.resolve(url).result(timeout=T).id, "011")
        self.assertIsInstance(v.resolve(BOB["acct"]).result(timeout=T), Account)

    def test_pictures(self):
        v = self.v
        url = "https://cdn.test/a.png"
        cached = self.core.paths.cache_dir / hashlib.sha1(url.encode()).hexdigest()
        cached.write_bytes(b"png")
        with mock.patch("os.utime", side_effect=OSError("ro")):
            self.assertEqual(v.media_bytes(url).result(timeout=T), b"png")

        class R:
            def __init__(self, kind):
                self.headers = {"Content-Type": kind}

            def raise_for_status(self):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False
        png = b"\x89PNG\r\n\x1a\n" + b"\0\0\0\rIHDR" + bytes(17) + b"\0\0\0\0IEND\xaeB`\x82"
        # by the bytes, not the header: an emoji off S3 comes as octet-stream (TUI, 30.10)
        for i, (kind, data, keep) in enumerate((
                ("image/png; q=1", png, True), ("application/octet-stream", png, True),
                ("text/html", png, False), ("image/png", b"<html>", False),
                ("image/png", png[:20], False))):  # cut short
            url = f"https://cdn.test/{i}"
            path = self.core.paths.cache_dir / hashlib.sha1(url.encode()).hexdigest()
            with mock.patch("fedtail.core.remote.open_url", return_value=R(kind)), \
                    mock.patch("fedtail.core.remote.read", return_value=data):
                self.assertEqual(v.media_bytes(url).result(timeout=T), data)
            self.assertEqual(path.exists(), keep, kind)
        url = "https://cdn.test/ro"
        with mock.patch("fedtail.core.remote.open_url", return_value=R("image/png")), \
                mock.patch("fedtail.core.remote.read", return_value=b"d"), \
                mock.patch("pathlib.Path.write_bytes", side_effect=OSError("full")):
            self.assertEqual(v.media_bytes(url).result(timeout=T), b"d")
        v._media.shutdown()

    def test_roster_people_with_a_talk(self):
        v = self.v
        dm = status("020", BOB, minute=20, text="@mira привет", vis="direct")
        dm["mentions"] = [{"id": "ME", "acct": "mira", "username": "mira"}]
        group = status("021", NEWS, minute=21, text="всем", vis="direct")
        group["mentions"] = [{"id": "ME", "acct": "mira", "username": "mira"},
                             {"id": "B", "acct": BOB["acct"], "username": "bob"}]
        self.w.add(dm, mention=True)  # the direct lane is made of mentions
        self.w.add(group, mention=True)
        self.w.conversations = [{"id": "c1", "unread": True, "accounts": [BOB],
                                 "last_status": dm}]
        self.core.poll_once()
        self.core.store.kv_set("mutuals", {"me": "ME", "at": time.time(),
                                           "accounts": [BOB, dict(NEWS)]})
        out = {g.name: g for g in v.roster()}
        people = {i.who.id: i for i in out["people"].items}
        self.assertIn("direct", self.core.lane_by_name)
        self.assertEqual(people["B"].talk, "020")  # just the two of us
        self.assertEqual(people["N"].talk, "")     # only in a talk of three

    def test_probe_post_accounts_redraft_events(self):
        v = self.v
        with mock.patch.object(self.core, "probe_server",
                               return_value=done({"software": "x", "items": []})), \
                mock.patch.object(self.core, "last_probe", return_value=None):
            self.assertEqual(v.probe_server().result(timeout=T).software, "x")
            self.assertIsNone(v.last_probe())
        with mock.patch.object(self.core, "last_probe", return_value={"version": "1"}):
            self.assertEqual(v.last_probe().version, "1")
        with mock.patch.object(type(self.core), "post_accounts", None, create=True):
            self.assertEqual(v.post_accounts(), ([], ""))
        pick = mock.Mock(return_value=([("", "@me")], ""))
        with mock.patch.object(self.core, "post_accounts", pick, create=True):
            v.post_accounts("011")
            v.post_accounts(self.post("011"))
        self.assertEqual([c.args for c in pick.call_args_list], [("011",), ("011",)])
        mine = self.post("010")
        r = v.redraft(mine).result(timeout=T)
        self.assertEqual(r.text, "мой пост")
        me = v.event_payload("me_updated", ME)
        self.assertIsInstance(me, Account)
        self.assertIsInstance(v.event_payload("status_updated", self.w.statuses["011"]),
                              Post)


if __name__ == "__main__":
    unittest.main()
