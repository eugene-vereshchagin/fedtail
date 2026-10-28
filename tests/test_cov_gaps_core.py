"""The core's and the common parts' last untested turns: a collection without a name,
leaving someone's, a server that won't say what it translates, the poller paused and
slow, a round without an API, a Direct-less window, a push subscription that fails,
a quote's draft, the merged window's reactions, reports and rounds, and the small
pieces of frontends/common, issue.py and version.py."""

import threading
import time
import types
import unittest
from unittest import mock

from fedtail import i18n, issue, version
from fedtail.core.merged import MergedCore
from fedtail.core.view import View
from fedtail.frontends.common import actions, images, lane, links, profile
from fedtail.model import Relationship
from fedtail.protocols.mastodon import adapter
from fedtail.protocols.mastodon.api import ApiError

from .fakes import BOB, ME, status
from .test_slow import Base


class CoreTurnsTest(Base):
    def test_collections_and_the_server(self):
        core, w = self.make()
        with self.assertRaises(ValueError):
            core.save_collection(None, "  ")
        w.collections["C1"] = {"id": "C1", "account_id": "B", "name": "x", "description": "",
                               "discoverable": True, "sensitive": False,
                               "members": {"I1": (ME["id"], "accepted")}}
        core.collection_revoke("C1", "I1").result()
        self.assertEqual(w.collections["C1"]["members"], {})
        with mock.patch.object(core.api, "translation_languages",
                               side_effect=ApiError(404, "no")):
            self.assertEqual(core.server_info().result()["translates"], {})
            core.caps.translation = True
            self.assertIsNone(core.load_translation_languages())
        core.caps.translation = True
        self.assertEqual(core.load_translation_languages(), {"en": ["ru", "de"], "ru": ["en"]})
        # the instance document doesn't say it translates, the list says it does: it does
        # (28.10's report: "Translate" gone though the server translates)
        core.caps.translation = False
        with self.assertLogs("fedtail.core.social", "INFO") as logs:
            self.assertEqual(core.load_translation_languages(),
                             {"en": ["ru", "de"], "ru": ["en"]})
        self.assertTrue(core.caps.translation)
        self.assertIn("doesn't say", logs.output[-1])
        core.caps.translation = False  # it neither says nor lists: none
        with mock.patch.object(core.api, "translation_languages", return_value={}):
            self.assertIsNone(core.load_translation_languages())
        self.assertFalse(core.caps.translation)

    def test_a_late_v2_document_keeps_the_v1_facts(self):
        """/api/v2/instance timing out cost every fact of /api/v1/instance (the limits,
        Markdown): the two are asked apart now."""
        import requests
        core, w = self.make()
        with mock.patch.object(type(core.api_class("https://example.test", "t")),
                               "instance_v2", side_effect=requests.Timeout("slow")):
            core.connect().result()
        self.assertGreater(core.caps.max_characters, 0)
        self.assertEqual(core.caps.max_characters,
                         core.proto.capabilities(core.api.instance(), None).max_characters)

    def test_the_poller_paused_then_slow(self):
        core, _w = self.make()
        core._paused = True
        t = threading.Thread(target=core._poll_loop, daemon=True)
        t.start()
        time.sleep(0.05)
        core._stop.set()
        core._wake.set()
        t.join(2)
        self.assertFalse(t.is_alive())
        core._stop.clear()
        core._paused = False
        core.set_slow(5)
        with mock.patch.object(core, "poll_once") as rounds, \
                mock.patch.object(core, "_pace", return_value=0):
            t = threading.Thread(target=core._poll_loop, daemon=True)
            t.start()
            time.sleep(0.05)
            core._stop.set()
            core._wake.set()
            t.join(2)
        self.assertFalse(t.is_alive())
        self.assertEqual(rounds.call_count, 1)  # one round, then the slow wait

    def test_small_turns(self):
        core, _w = self.make()
        api, core.api = core.api, None
        self.assertIsNone(core.poll_once())  # no API: no round
        core.api = api
        core._note_fresh({}, (), ["a", "b"])  # activity that isn't a dict: none of a lane's
        self.assertNotIn("activity", core._fresh)
        lanes = {k: v for k, v in core.lane_by_name.items() if k != "direct"}
        with mock.patch.object(core, "lane_by_name", lanes):
            self.assertEqual(core._carry_my_direct([]), 0)
        with mock.patch.object(core.api, "push_subscription",
                               side_effect=ApiError(500, "boom")):
            with self.assertRaises(ApiError):
                core.push_subscription().result()
        self.assertEqual(core.draft_key(quote_id="5"), "quote:5")
        me, core.store.me_id = core.store.me_id, None
        self.assertEqual(core.store.my_direct_outside("mentions"), [])
        core.store.me_id = me
        got = View(core).event_payload("requests_updated", [BOB])
        self.assertEqual(got[0].id, "B")


class MergedTurnsTest(unittest.TestCase):
    def test_reactions_reports_rounds(self):
        a, b = mock.Mock(), mock.Mock()
        m = MergedCore.__new__(MergedCore)
        m.primary, m.others = a, {"w": b}
        m.own = lambda st: (b, "w", st)
        m._wrapped = lambda tag, fut: fut
        m.react({"id": "1"}, "👍")
        b.react.assert_called_with({"id": "1"}, "👍", True)
        m.report({"id": "1"}, "spam")
        b.report.assert_called_with({"id": "1"}, "spam")
        b.logged_in, b.me = True, {"id": "x"}
        b.poll_once.side_effect = RuntimeError("down")
        m.poll_once()  # one that fails doesn't stop the rest
        a.poll_once.assert_called_once()


class CommonTurnsTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_profile_buttons(self):
        acc = adapter.account(BOB)
        view, host = mock.Mock(), mock.Mock()
        view.me = adapter.account(ME)
        profile.do("mute", acc, Relationship(muting=True), view, host, lambda r: None)
        view.mute.assert_called_with("B", False)
        profile.do("collections", acc, None, view, host, lambda r: None)
        host._place.assert_called_with("collections", "B")
        profile.do("collections", view.me, None, view, host, lambda r: None)
        host._place.assert_called_with("collections", "")  # mine
        profile.do("collect", acc, None, view, host, lambda r: None)
        host._place.assert_called_with("collect", "B")

    def test_a_link_shared_by_others(self):
        st = status("1", BOB, text="x")
        st["card"] = {"url": "https://news.example/a", "title": "A"}
        p = adapter.post(st)
        from fedtail.core import config
        cfg, _w = config.validate({})
        ctx = actions.Ctx(cfg, "ME", supports=lambda f: f == "link_timeline")
        urls = [i.url for i in actions.menu(p, ctx) if i.kind == "link"]
        self.assertIn("fedtail:linkposts/1", urls)

    def test_reaction_link_and_start(self):
        host = mock.Mock()
        p = adapter.post(status("1", BOB, text="x"))
        lk = links.Links(mock.Mock(), host)
        lk.post_action("react", "1", p)
        host._place.assert_called_with("react", "1")
        fake = types.SimpleNamespace(start=lambda specs: ("k", "top"), newest_first=False)
        self.assertEqual(lane.LaneModel.start_key(fake, ["s"]), "k")

    def test_weakly_kept_callbacks(self):
        fn = lambda *_a: None  # noqa: E731
        self.assertIs(images._weakly(object(), fn), fn)  # no __dict__: as it was
        owner = types.SimpleNamespace(_ft_picture_callbacks=list(range(65)))
        images._weakly(owner, fn)
        self.assertEqual(len(owner._ft_picture_callbacks), 34)  # the oldest gone

    def test_issue_scrub_and_logs(self):
        self.assertIn("https://<server>/", issue.scrub("see https://my.server/x"))
        with mock.patch("pathlib.Path.glob", side_effect=OSError("gone")):
            self.assertEqual(issue.recent_errors("/nowhere"), [])
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "2026-01-01.log").write_text("x")
            with mock.patch("pathlib.Path.read_text", side_effect=OSError("locked")):
                self.assertEqual(issue.recent_errors(d), [])

    def test_version_without_tags(self):
        answers = {("rev-parse", "--short", "HEAD"): "abc1234", ("log", "-1", "--format=%cs"):
                   "2026-10-26", ("status", "--porcelain", "--untracked-files=no"): "",
                   ("describe", "--tags", "--long", "--match", "v[0-9]*"): "",
                   ("rev-list", "--count", "HEAD"): "42"}
        version.info.cache_clear()
        self.addCleanup(version.info.cache_clear)
        import tempfile
        from pathlib import Path
        root = tempfile.TemporaryDirectory()  # a checkout with .git, wherever this runs
        self.addCleanup(root.cleanup)
        (Path(root.name) / ".git").mkdir()
        with mock.patch.dict("sys.modules", {"fedtail._build": None}), \
                mock.patch.object(version, "ROOT", Path(root.name)), \
                mock.patch.object(version, "_git", lambda *a: answers.get(a, "")), \
                mock.patch.object(version.shutil, "which", return_value="/usr/bin/git"):
            got = version.info()
        self.assertEqual(got["commit"], "abc1234")


if __name__ == "__main__":
    unittest.main()
