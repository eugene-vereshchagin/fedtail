"""The application from the competitors' report, every bit off by default: a proxy for
everything (and typed at login), a lane by Ctrl+number, pinned tabs, the phone's live
stream on Wi-Fi only, "Statistics", LibreTranslate and posts translated by themselves."""

import datetime as dt
import json
import os
import unittest
from unittest import mock

from fedtail import i18n
from fedtail.core import config
from fedtail.core.view import View
from fedtail.frontends.common.places import Places
from tests.fakes import BOB, status

from .test_android_bridge import _Base
from .test_custom import FreeBase


class OffByDefaultTest(unittest.TestCase):
    def test_as_before(self):
        cfg, _w = config.validate({})
        self.assertEqual(cfg["net"], {"proxy": "", "proxy_at_login": False})
        self.assertEqual(cfg["ui"]["number_keys"], "alt")
        self.assertFalse(cfg["ui"]["pin_tabs"])
        self.assertEqual(cfg["phone"]["stream"], "always")
        self.assertFalse(cfg["feed"]["stats"])
        self.assertFalse(cfg["feed"]["translate_auto"])
        self.assertEqual(cfg["feed"]["translate_backend"], "server")


class ProxyTest(unittest.TestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(setattr, config, "_proxy_set", None)
        for name in config._PROXY_VARS:
            os.environ.pop(name, None)

    def test_the_environment_carries_it(self):
        self.assertTrue(config.proxy_ok("socks5h://127.0.0.1:1080"))
        self.assertTrue(config.proxy_ok(""))
        self.assertFalse(config.proxy_ok("127.0.0.1:1080"))  # no scheme
        self.assertFalse(config.proxy_ok("ftp://h:1"))
        config.apply_proxy({"net": {"proxy": "http://u:p@proxy.example:3128"}})
        self.assertEqual(os.environ["HTTPS_PROXY"], "http://u:p@proxy.example:3128")
        self.assertEqual(os.environ["all_proxy"], "http://u:p@proxy.example:3128")
        config.apply_proxy({"net": {"proxy": ""}})  # taken back: the system's again
        self.assertNotIn("HTTPS_PROXY", os.environ)
        os.environ["HTTPS_PROXY"] = "http://system.example:8080"
        config.apply_proxy({"net": {"proxy": ""}})
        self.assertEqual(os.environ["HTTPS_PROXY"], "http://system.example:8080")  # not ours


class LoginProxyTest(FreeBase):
    def setUp(self):
        super().setUp()
        i18n.setup("en")
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        self.addCleanup(setattr, config, "_proxy_set", None)

    def test_typed_at_login_written_and_used(self):
        core, _w = self.make([])
        core.paths.config_file.write_text("", "utf-8")
        page = Places(View(core)).page("login", core.paths.profile)
        self.assertEqual([f.name for f in page.form], ["server"])  # off: no field
        core.cfg["net"]["proxy_at_login"] = True
        page = Places(View(core)).page("login", core.paths.profile)
        self.assertEqual([f.name for f in page.form], ["server", "proxy"])
        with self.assertRaises(ValueError):
            core.set_proxy("nonsense")
        core.begin_login("https://example.test", proxy="socks5h://127.0.0.1:1080").result()
        self.assertEqual(os.environ["HTTPS_PROXY"], "socks5h://127.0.0.1:1080")
        cfg, _w = config.load(core.paths.config_file)
        self.assertEqual(cfg["net"]["proxy"], "socks5h://127.0.0.1:1080")
        self.assertIn("[server]", core.paths.config_file.read_text("utf-8"))


class PhoneStreamTest(_Base):
    def test_wifi_only(self):
        self.demo()
        core = self.bridge._s["core"]
        seen = []
        core.stream_allowed = seen.append
        self.assertEqual(self.call("network", False)["stream"], True)  # "always"
        core.cfg["phone"]["stream"] = "wifi"
        self.assertEqual(self.call("network", False)["stream"], False)
        self.assertEqual(self.call("network", True)["stream"], True)
        core.cfg["phone"]["stream"] = "off"
        self.assertEqual(self.call("network", True)["stream"], False)
        self.assertEqual(seen, [True, False, True, False])

    def test_the_login_screen_hears_of_the_proxy_field(self):
        json.loads(self.bridge.start(str(self.files), str(self.cache), "en", False))
        got = self.call("state")
        self.assertEqual((got["proxy_at_login"], got["proxy"]), (False, ""))


class StreamStopTest(FreeBase):
    def test_stopped_and_started(self):
        core, _w = self.make([])
        core.connect().result()
        stopped = []
        core._stream = mock.Mock(stop=lambda: stopped.append(True))
        core.stream_allowed(False)
        self.assertEqual(stopped, [True])
        self.assertIsNone(core._stream)
        started = []
        core._start_stream = lambda: started.append(True)
        core.stream_allowed(True)
        self.assertEqual(started, [True])


class StatsTest(FreeBase):
    def test_the_week(self):
        i18n.setup("en")
        core, w = self.make([])
        now = dt.datetime.now(dt.UTC)
        for i, back in enumerate((0, 0, 1, 3)):
            st = status(f"00{i}", BOB, vis="public")
            st["created_at"] = (now - dt.timedelta(days=back)).strftime(
                "%Y-%m-%dT%H:%M:%S.000Z")
            if i < 2:
                st["card"] = {"url": "https://news.example/a", "title": "A story"}
            w.add(st, home=True)
        core.connect().result()
        core.poll_once()
        days, authors = core.stats(7)
        self.assertEqual(len(days), 7)
        self.assertEqual(days[-1][0], dt.date.today())
        self.assertEqual(sum(d[1] for d in days), 4)
        self.assertEqual(days[-1][1], 2)
        self.assertEqual(authors[0], (BOB["acct"], 4))
        places = Places(View(core))
        self.assertNotIn("stats", [n for n, _t in places.menu()])
        core.cfg["feed"]["stats"] = True
        self.assertIn("stats", [n for n, _t in places.menu()])
        page = places.page("stats")
        self.assertIn("@" + BOB["acct"], [r.title for r in page.rows])
        self.assertIn("A story", [r.title for r in page.rows])
        self.assertEqual(places.act("stats", "open", "https://news.example/a").open,
                         {"url": "https://news.example/a"})


class TranslateTest(FreeBase):
    def setUp(self):
        super().setUp()
        i18n.setup("en")

    def test_libretranslate(self):
        core, w = self.make([])
        w.add(status("001", BOB, minute=1, vis="public", text="hola"), home=True)
        core.connect().result()
        core.poll_once()
        core.cfg["feed"].update(translate_backend="libretranslate",
                                translate_url="https://lt.example", translate_key="k")
        asked = []

        def post(url, json=None, **_kw):
            asked.append((url, json))
            return mock.Mock(status_code=200, json=lambda: {
                "translatedText": "<p>hello</p>", "detectedLanguage": {"language": "es"}})
        with mock.patch("fedtail.core.app.requests.post", post):
            got = core.translate(core.store.get_status("001")).result()
        self.assertEqual(got["content"], "<p>hello</p>")
        self.assertEqual(got["provider"], "LibreTranslate")
        self.assertEqual(asked[0][0], "https://lt.example/translate")
        self.assertEqual((asked[0][1]["target"], asked[0][1]["api_key"]), ("en", "k"))
        core.load_translation_languages()
        self.assertTrue(core.caps.translation)  # "Translate" in the menus, any server
        core.cfg["feed"]["translate_url"] = "http://lt.example"  # the internet, in the clear
        with self.assertRaises(ValueError):
            core._libre(core.store.get_status("001"), "en")

    def test_translated_by_itself(self):
        core, w = self.make([])
        st = status("001", BOB, minute=1, vis="public", text="hola amigos")
        st["language"] = "es"
        w.add(st, home=True)
        core.connect().result()
        core.poll_once()
        core.caps.translation = True
        raw = core.store.get_status("001")
        view = View(core)
        self.assertNotIn("[en]", view.entry(raw).text)  # off
        core.cfg["feed"]["translate_auto"] = True
        self.assertNotIn("[en]", view.entry(raw).text)  # asked for, not there yet
        for _i in range(200):
            if ("status_updated", raw) in self.events or \
                    any(n == "status_updated" for n, _p in self.events):
                break
            import time
            time.sleep(0.01)
        text = view.entry(raw).text
        self.assertIn("[en] hola amigos", text)
        self.assertIn("translated from xx", text)
        core.cfg["post"]["languages"] = ["es"]  # a language I write: left as it is
        self.assertNotIn("[en]", view.entry(raw).text)


if __name__ == "__main__":
    unittest.main()


class HoldTest(FreeBase):
    def test_new_posts_wait_for_refresh(self):
        from fedtail.frontends.common.lane import LaneModel
        i18n.setup("en")
        core, w = self.make([])
        w.add(status("001", BOB, minute=1, vis="public"), home=True)
        w.add(status("002", BOB, minute=2, vis="public"), home=True)
        core.connect().result()
        core.poll_once()
        core.cfg["feed"]["on_new"] = "hold"
        view = View(core)
        m = LaneModel(view, "home")
        keys = lambda b: [s.key for s in b.specs if s.entry is not None]  # noqa: E731
        first = m.build(False)
        self.assertEqual(keys(first), ["001", "002"])
        w.add(status("003", BOB, minute=3, vis="public"), home=True)
        core.poll_once()
        view._cache.clear()
        later = m.build(True)
        self.assertEqual(keys(later), ["001", "002"])  # held
        self.assertEqual(later.held, 1)
        self.assertIn("1 new", later.info)
        view.refresh_by_hand()
        shown = m.build(True)
        self.assertEqual(keys(shown), ["001", "002", "003"])
        self.assertEqual(shown.held, 0)
        core.cfg["feed"]["on_new"] = "keep_position"  # as before: in at once
        w.add(status("004", BOB, minute=4, vis="public"), home=True)
        core.poll_once()
        view._cache.clear()
        self.assertIn("004", keys(m.build(True)))


class PollShareTest(unittest.TestCase):
    def test_never_over_a_hundred(self):
        from fedtail.model import Poll, PollOption, Ref
        lagging = Poll(Ref("m", "", "p"), (PollOption("yes", 4), PollOption("no", 1),
                                      PollOption("depends", 1)), multiple=True,
                       votes=6, voters=1)  # 28.10: "1 person", 4 votes for "yes"
        self.assertEqual(lagging.people, 4)
        self.assertEqual(lagging.total, 4)
        self.assertLessEqual(max(100 * o.votes // lagging.total for o in lagging.options),
                             100)
        one = Poll(Ref("m", "", "q"), (PollOption("a", 3), PollOption("b", 2)), votes=4)
        self.assertEqual(one.total, 5)  # the counts ran ahead of votes_count
        none = Poll(Ref("m", "", "r"), (PollOption("a", 0),), votes=0)
        self.assertEqual(none.total, 0)


class BrowseWaitingTest(FreeBase):
    def test_federated_says_loading_till_the_server_answers(self):
        core, w = self.make([])
        core.connect().result()
        lane = next((x for x in core.lanes if x.lazy), None)
        if lane is None:
            self.skipTest("no browse lane in this set")
        self.assertFalse(core.lane_waiting(lane.name))
        core.set_active_lane(lane.name)
        self.assertTrue(core.lane_waiting(lane.name))
        core.poll_once()
        self.assertFalse(core.lane_waiting(lane.name))
