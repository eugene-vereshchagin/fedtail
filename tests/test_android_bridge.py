"""The Android app's Python door (android/app/src/main/python/fedtail_android/bridge.py)
works on any Python: the core comes up in the folders it is given, logs in with the
code coming back to the app, and gives a lane's cards — no phone needed."""

import importlib.util
import json
import os
from pathlib import Path
from unittest import mock

from .test_core import TmpDir

BRIDGE = (Path(__file__).resolve().parent.parent / "android" / "app" / "src" / "main"
          / "python" / "fedtail_android" / "bridge.py")


def load_bridge():
    spec = importlib.util.spec_from_file_location("fedtail_android_bridge", BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _Base(TmpDir):
    def setUp(self):
        super().setUp()
        self.files, self.cache = self.tmp / "files", self.tmp / "cache"
        self.files.mkdir()
        self.cache.mkdir()
        env = mock.patch.dict(os.environ, {}, clear=False)  # XDG_*, LANG come back after
        env.start()
        self.addCleanup(env.stop)
        from fedtail import i18n
        self.addCleanup(i18n.setup, i18n.current_language())
        self.bridge = load_bridge()
        self.addCleanup(lambda: self.bridge._s["core"] and self.bridge._s["core"].shutdown())
        from fedtail import diag
        self.addCleanup(diag.running, "")  # start() says "android": not for the next tests

    def call(self, name, *args):
        got = json.loads(getattr(self.bridge, name)(*args))
        if isinstance(got, dict):
            self.assertNotIn("error", got, got.get("trace") or got.get("error"))
        return got

    def demo(self):
        got = json.loads(self.bridge.start(str(self.files), str(self.cache), "en", True))
        self.assertNotIn("error", got, got.get("trace"))
        self.call("open")


class BridgeTest(_Base):
    def test_the_formatting_buttons(self):
        """The phone's editor: the buttons with editor(), a button's work through
        format_text with Kotlin's UTF-16 positions — the desktop's rules."""
        self.demo()
        self.bridge._core().cfg["account"]["markdown"] = "on"
        self.bridge._core().cfg["post"]["format_bar"] = "bottom"
        facts = self.call("editor")
        self.assertIn("link", [b["name"] for b in facts["format_bar"]])
        self.assertEqual(facts["format_place"], "bottom")
        got = self.call("format_text", json.dumps({"name": "italic", "text": "😀 hi",
                                                   "start": 3, "end": 5}))
        self.assertEqual(got, {"text": "😀 *hi*", "start": 4, "end": 6})

    def test_the_phone_says_itself(self):
        """The phone's facts given to start(): the issue's draft and the report say the
        phone, its Android and "interface android" — not the config's "qt"."""
        from types import SimpleNamespace

        from fedtail import diag, issue
        facts = {"device": "Google Pixel 8", "android": "15 (API 35)", "memory": "7 GB"}
        got = json.loads(self.bridge.start(str(self.files), str(self.cache), "en", True,
                                           False, json.dumps(facts)))
        self.assertNotIn("error", got, got.get("trace"))
        self.assertEqual(diag.interface({"ui": {"frontend": "qt"}}), "android")
        body = issue.draft(SimpleNamespace(profile="default", data_dir=self.files),
                           {"ui": {"frontend": "qt"}}).body
        self.assertIn("device Google Pixel 8", body)
        self.assertIn("interface android", body)
        self.assertNotIn("7 GB", body)

    def test_the_core_starts_in_the_apps_folders(self):
        got = json.loads(self.bridge.start(str(self.files), str(self.cache), "en", False))
        self.assertNotIn("error", got, got.get("trace"))
        self.assertTrue(got["version"])
        self.assertIn("statuses", got["store"])
        self.assertEqual(got["profiles"], ["default"])
        self.assertIn("started_ms", got)
        # everything the core wrote is inside the app's own folders
        self.assertTrue((self.files / "config" / "fedtail" / "default" / "config.toml").exists())
        self.assertTrue((self.files / "data" / "fedtail" / "default" / "state.db").exists())
        self.assertEqual(self.call("state")["logged_in"], False)

    def test_a_broken_core_is_told_not_thrown(self):
        self.bridge.start(str(self.files), str(self.cache), "en", False)
        with mock.patch("fedtail.core.paths.data_base", side_effect=OSError("disk gone")):
            got = json.loads(self.bridge.info())
        self.assertEqual(got["error"], "OSError: disk gone")
        self.assertIn("error", json.loads(self.bridge.lane("nowhere")))

    def test_login_comes_back_to_the_app(self):
        from fedtail.core import config, paths
        from fedtail.core.app import Core

        from . import fakes
        self.bridge.start(str(self.files), str(self.cache), "en", False)
        fakes.FakeApi.world = fakes.World()
        self.bridge._s["core"].shutdown()
        cfg, _ = config.validate({})
        self.bridge._s["core"] = Core(cfg, paths.resolve(None), api_class=fakes.FakeApi)
        got = self.call("login_begin", "https://example.test")
        self.assertTrue(got["redirect"])
        self.assertIn("redirect_uri=fedtail://oauth", got["url"])
        self.assertEqual(fakes.FakeApi.world.redirects, ["fedtail://oauth"])
        self.assertEqual(self.call("login_finish", "good\n")["acct"], "mira")
        self.assertTrue(self.call("state")["logged_in"])
        self.assertIn("error", json.loads(self.bridge.login_begin("  ")))

    def test_demo_world_lanes_and_marks(self):
        got = json.loads(self.bridge.start(str(self.files), str(self.cache), "ru", True))
        self.assertNotIn("error", got, got.get("trace"))
        self.assertTrue(got["demo"])
        opened = self.call("open")
        self.assertEqual(opened["me"]["handle"], "mira")
        names = [x["name"] for x in opened["lanes"]]
        self.assertIn("home", names)
        lane = self.call("lane", "home", False)
        self.assertTrue(lane["posts"])
        first = lane["posts"][0]
        for key in ("id", "alias", "account", "created", "text", "unread"):
            self.assertIn(key, first)
        self.assertNotIn("<p>", first["text"])  # words, not HTML
        unread = [p["id"] for p in lane["posts"] if p["unread"]]
        self.assertTrue(unread)
        v = self.bridge.wait(-1, 0.1)  # something changed since "never"
        self.assertEqual(self.call("read", json.dumps(unread[:1])), {"ok": True})
        self.assertNotEqual(self.bridge.wait(v, 2), v)
        again = self.call("lane", "home", True)
        self.assertFalse(next(p for p in again["posts"] if p["id"] == unread[0])["unread"])
        # "mark all read", as the windows' button: the whole lane, in the core
        got = self.call("lane_read", "home")
        self.assertTrue(got["ok"])
        self.assertFalse([p for p in self.call("lane", "home", True)["posts"] if p["unread"]])
        self.assertEqual(self.call("pause", True), {"ok": True})
        self.assertEqual(self.call("pause", False), {"ok": True})
        self.assertEqual(self.call("refresh"), {"ok": True})
        self.assertTrue((self.files / "data" / "fedtail" / "demo" / "state.db").exists())

    def demo(self):
        got = json.loads(self.bridge.start(str(self.files), str(self.cache), "en", True))
        self.assertNotIn("error", got, got.get("trace"))
        self.call("open")

    def test_thread_and_writing(self):
        self.demo()
        th = self.call("thread", "101")
        ids = [p["sid"] for p in th["posts"]]
        self.assertEqual(ids[0], "100")  # from the root, whatever was opened
        self.assertIn("103", ids)
        self.assertTrue(all("depth" in p and "number" in p and "text" in p for p in th["posts"]))
        self.assertGreater(max(p["depth"] for p in th["posts"]), 0)
        sent = self.call("post", json.dumps({"text": "a reply from the phone",
                                             "reply_to": "103"}))
        self.assertTrue(sent["id"])
        from tests import fakes
        self.assertEqual(fakes.FakeApi.world.posted[-1][2], "103")
        liked = self.call("act", "like", "106")
        self.assertIn("text", liked)
        self.assertIn("error", json.loads(self.bridge.post(json.dumps({"text": "  "}))))

    def test_config_is_edited_in_the_app(self):
        self.demo()
        text = self.call("config_text")["text"]
        self.assertIn("[sync]", text)
        import re
        bad = json.loads(self.bridge.config_save(re.sub(
            r"(\[reading\][^\[]*?)^#?order = .*$", r'\1order = "sideways"', text,
            count=1, flags=re.M | re.S)))
        self.assertIn("error", bad)
        self.assertEqual(self.call("config_text")["text"], text)  # nothing landed
        self.assertIn("error", json.loads(self.bridge.config_save("this = is = not toml")))
        old_core = self.bridge._s["core"]
        mine = text.replace('[sync]\n', '[sync]\n# mine\n')
        self.assertEqual(self.call("config_save", mine), {"ok": True})
        self.assertIsNot(self.bridge._s["core"], old_core)  # made anew with it
        self.assertIn("# mine", self.call("config_text")["text"])

    def test_sync_from_the_phone(self):
        from fedtail.core.sync import crypto
        if not crypto.available():
            self.skipTest("needs cryptography")
        self.demo()
        self.assertEqual(self.call("sync_status"), {"enabled": False, "key": False})
        meet = self.tmp / "meet"
        meet.mkdir()
        text = self.call("config_text")["text"]
        head, _, sync = text.rpartition("\n[sync]\n")  # the table, not a mention of it
        sync = sync.replace("enabled = false", "enabled = true", 1)
        sync = sync.replace('backend = "server"', 'backend = "folder"', 1)
        sync = sync.replace('folder = ""', f'folder = "{meet.as_posix()}"', 1)
        on = head + "\n[sync]\n" + sync
        self.assertEqual(self.call("config_save", on), {"ok": True})
        self.call("open")
        st = self.call("sync_status")
        self.assertTrue(st["enabled"])
        self.assertEqual(st["backend"], "folder")
        self.assertEqual(self.call("sync_now"), {"sent": 0, "got": 0})
        key = self.call("sync_key")["key"]
        self.assertTrue(key)
        other = crypto.key_text(crypto.new_key())
        self.assertTrue(self.call("sync_join", other)["kid"])
        self.assertEqual(self.call("sync_key")["key"], other)
        self.assertIn("error", json.loads(self.bridge.sync_join("nonsense")))

    def test_the_overview_of_lanes(self):
        self.demo()
        self.assertIn("n", self.call("older", "home"))  # "earlier": the server asked
        hub = self.call("hub")
        self.assertFalse(any(x["capped"] for s in hub["sections"] for x in s["lanes"]))
        kinds = {s["key"]: [x["name"] for x in s["lanes"]] for s in hub["sections"]}
        self.assertEqual(list(kinds)[0], "you")  # what is addressed to you comes first
        self.assertIn("to_me", kinds["you"])
        self.assertIn("home", kinds["reading"])
        self.assertIn("federated", kinds["browse"])  # no counts: only browsed
        lanes = {x["name"]: x for s in hub["sections"] for x in s["lanes"]}
        self.assertEqual(lanes["federated"]["unread"], 0)
        self.assertTrue(lanes["home"]["unread"])
        self.assertIn(":", lanes["home"]["peek"])  # who: what
        # reading in a row: only lanes with news, yours first
        self.assertEqual(hub["order"], [x for x in hub["order"] if lanes[x]["unread"]])
        self.assertLess(hub["order"].index("to_me"), hub["order"].index("home"))
        self.assertEqual(hub["unread"], sum(lanes[x]["unread"] for x in hub["order"]))
        # where the set puts each lane, under which of its sections (lanes.preset)
        every = sorted(lanes.values(), key=lambda x: x["pos"])
        self.assertEqual([x["pos"] for x in every], list(range(len(every))))
        self.assertLess(lanes["federated"]["pos"], lanes["home"]["pos"])  # fedtail's order
        self.assertTrue(lanes["home"]["group"])
        self.assertNotEqual(lanes["home"]["group"], lanes["to_me"]["group"])

    def test_announcements_strip(self):
        """The windows' announcement strip: the ones not dismissed, with reactions, and
        "Got it" — none at all with ui.announcements = "off"."""
        from concurrent.futures import Future

        from fedtail.model import Announcement, Reaction
        self.demo()
        done = Future()
        done.set_result([Announcement("a1", "<p>Maintenance tonight</p>", None,
                                      (Reaction("👍", 2, True),)),
                         Announcement("a2", "<p>Second</p>", None, ())])
        web = self.bridge._s["web"]
        with mock.patch.object(web.core, "announcements", return_value=done), \
                mock.patch.object(self.bridge._core(), "supports", return_value=True):
            got = self.call("announcements")
        self.assertEqual([x["id"] for x in got["items"]], ["a1", "a2"])
        first = got["items"][0]
        self.assertEqual(first["text"], "Maintenance tonight")
        self.assertIn("📢", first["head"])
        self.assertEqual(first["reactions"][0], {"name": "👍", "count": 2, "me": True})
        self.assertIn("❤️", [r["name"] for r in first["reactions"]])
        self.assertTrue(got["ok"])
        self.bridge._core().cfg["ui"]["announcements"] = "off"
        self.assertEqual(self.call("announcements")["items"], [])

    def test_quote_lines_and_reveal(self):
        self.demo()
        got = self.call("quote_lines", "@bob hello\nworld")
        self.assertTrue(got["text"].startswith(">"))
        self.assertNotIn("@bob", got["text"])
        self.assertIn("grew", self.call("reveal", "home", 0))
        self.assertIn("threads", self.call("status"))

    def test_activity_is_a_lane_of_events(self):
        """Activity is a lane like any (a rule of events only): the lane brings its rows as
        events in their parts, every button a fedtail: link the phone runs through link();
        a row seen on screen goes to read() with its "event:<id>" key — its count goes."""
        self.demo()
        core = self.bridge._core()
        core.store.kv_set("activity_seen", "")  # none of it seen yet
        hub = self.call("hub")
        lanes = {x["name"]: x for s in hub["sections"] for x in s["lanes"]}
        you = next(s for s in hub["sections"] if s["key"] == "you")
        self.assertIn("activity", [x["name"] for x in you["lanes"]])  # by its rule, not name
        self.assertTrue(lanes["activity"]["unread"])
        got = self.call("lane", "activity")
        self.assertNotIn("place", got)
        self.assertNotIn("page", got)
        self.assertEqual(got["posts"], [])
        rows = {e["key"]: e["event"] for e in got["events"]}
        self.assertTrue(rows)
        self.assertTrue(all(k.startswith("event:") for k in rows))
        self.assertTrue(any(x["unread"] for x in rows.values()))
        self.assertTrue(all(u.startswith("fedtail:account/") for x in rows.values()
                            for _n, u in x["people"]))
        self.assertTrue(got["clear"])  # a lane of events only: "Clear"
        # a like seen on screen: seen, the count goes down by it
        before = core.unread_count("activity")
        like = next(k for k, x in rows.items() if x["kind"] == "favourite")
        self.call("read", json.dumps([like]))
        self.assertLess(core.unread_count("activity"), before)
        # a request answered by its button (a fedtail: link, as a card's ⋯ item)
        req = next(x for x in rows.values() if x["answers"])
        self.assertTrue(self.call("link", req["answers"][0][0]).get("refresh"))
        self.assertEqual(core.follow_requests, [])
        # × hides a row
        other = next(x for k, x in rows.items() if k != like and not x["answers"])
        self.call("link", other["hide"])
        after = {e["key"] for e in self.call("lane", "activity")["events"]}
        self.assertEqual(len(after), len(rows) - 2)  # the answered request, the hidden row
        # "mark all read" over the lane: its events all seen
        self.call("read", "[]", "activity")
        self.assertEqual(core.unread_count("activity"), 0)
        # "Clear": asked first, then every notification goes
        self.assertIn("confirm", self.call("lane_clear", "activity"))
        self.assertEqual(self.call("lane_clear", "activity", True), {"refresh": True})
        self.assertNotIn("requests", lanes)  # requests are in Activity (no lane of their own)

    def test_the_command_line_is_off_on_the_phone_unless_asked(self):
        self.demo()
        self.assertFalse(self.call("open")["me"]["command_line"])
        text = self.call("config_text")["text"]
        self.assertEqual(self.call("config_save", text + "\n"), {"ok": True})
        self.assertFalse(self.call("open")["me"]["command_line"])  # the file didn't say
        self.assertIn("command_line = false", text)  # written into the file, once
        on = text.replace("command_line = false", "command_line = true", 1)
        self.assertEqual(self.call("config_save", on), {"ok": True})
        self.assertTrue(self.call("open")["me"]["command_line"])
        alias = self.call("lane", "home", False)["posts"][0]["alias"]
        self.assertIn(alias, self.call("command_preview", f"#{alias} hello")["text"])
        got = self.call("command", f"#{alias}", False)
        self.assertTrue(got["ok"])
        self.assertIn("thread", got["open"])

    def test_a_cards_menu_and_links(self):
        self.demo()
        got = self.call("open")
        self.assertEqual(got["me"]["overview"], "tiles")
        self.assertEqual(got["me"]["layout"], "auto")
        self.assertIn("expand_cw", got["me"])  # ui.expand_cw / ui.arts_mode: CWs open
        m = self.call("menu", "103")
        self.assertIn("subscribed", m)
        self.assertIn("url", m)
        self.assertTrue(self.call("thread_act", "sub", "103")["message"])
        self.assertTrue(self.call("menu", "103")["subscribed"])
        self.assertIn("found", self.call("resolve", "https://nowhere.example/@x/1"))
        self.assertIn("error", json.loads(self.bridge.thread_act("sideways", "103")))

    def test_pinned_lanes_come_as_tiles_in_their_order(self):
        self.demo()
        self.assertEqual(self.call("hub")["pinned"], [])  # none: every counted lane
        self.assertEqual(self.call("pin", '["home", "list:L1", "nowhere", "to_me"]'),
                         {"ok": True})
        self.assertEqual(self.call("hub")["pinned"], ["home", "list:L1", "to_me"])
        self.assertEqual(self.bridge._s["core"].pinned_tiles()[0], "home")  # the core's

    def test_the_settings_page(self):
        self.demo()
        got = self.call("settings")
        titles = [c["title"] for c in got["chapters"]]
        self.assertTrue(titles)
        opts = {(o["section"], o["key"]): o for c in got["chapters"] for o in c["options"]}
        self.assertNotIn(("web", "port"), opts)  # the desktop's browser: not here
        self.assertNotIn(("appearance", "gtk_headerbar"), opts)  # the windows' own
        self.assertNotIn(("appearance", "font"), opts)
        self.assertIn(("appearance", "language"), opts)
        self.assertIn(("sync", "url"), opts)  # a chapter of its own
        order = opts[("reading", "order")]
        self.assertEqual(order["kind"], "choice")
        self.assertIn("newest_first", [v for v, _w in order["choices"]])
        self.assertTrue(order["title"] and order["about"])
        self.assertEqual(opts[("window", "command_line")]["value"], False)  # the phone's
        self.assertEqual(opts[("phone", "overview")]["kind"], "choice")
        before = self.bridge._s["core"]
        self.assertEqual(self.call("setting_set", "reading", "order", '"newest_first"')["value"],
                         "newest_first")
        self.assertIn('order = "newest_first"', self.call("config_text")["text"])
        bad = json.loads(self.bridge.setting_set("reading", "order", '"sideways"'))
        self.assertIn("error", bad)
        self.assertIn('order = "newest_first"', self.call("config_text")["text"])  # kept
        self.assertEqual(self.call("setting_set", "phone", "overview", '"list"')["value"],
                         "list")
        self.assertEqual(self.call("setting_set", "phone", "overview", "null")["value"],
                         "tiles")  # the default again
        self.assertIs(self.bridge._s["core"], before)  # not remade at every tap…
        self.assertEqual(self.call("settings_apply"), {"restarted": True})  # …but on leaving
        self.assertIsNot(self.bridge._s["core"], before)
        self.assertEqual(self.call("settings_apply"), {"restarted": False})

    def test_the_self_check(self):
        self.demo()
        steps = json.loads(self.bridge.selfcheck_steps())
        self.assertIn("lanes", steps)
        results = []
        with mock.patch("requests.get") as get:  # the made-up world's pictures
            get.return_value.content = b"x" * 2048
            for name in steps:
                r = json.loads(self.bridge.selfcheck_step(name))
                self.assertEqual(r["name"], name)
                self.assertIn("ms", r)
                results.append(r)
        bad = [r for r in results if not r["ok"]]
        self.assertEqual(bad, [], bad)
        self.assertIn("home", next(r for r in results if r["name"] == "lanes")["detail"])
        got = self.call("selfcheck_report", json.dumps(results),
                        json.dumps({"device": "Pixel 8", "android": "16"}))
        import tarfile
        with tarfile.open(got["path"]) as tar:
            names = tar.getnames()
            text = tar.extractfile("logs/selfcheck.txt").read().decode()
        self.assertIn("Pixel 8", text)
        self.assertIn("system.txt", names)
        self.assertFalse(any(n.endswith(("auth.json", "state.db")) for n in names))
        self.assertFalse(json.loads(self.bridge.selfcheck_step("nowhere"))["ok"])


class BridgePlacesTest(_Base):
    """The doors the phone's generic screens use: every place, a card's whole ⋯ menu,
    a profile and its buttons, attachments, polls, the editor's facts."""

    def test_every_place_is_data(self):
        self.demo()
        menu = self.call("places")
        names = [x["name"] for x in menu]
        for n in ("search", "lists", "silence", "server", "help", "accounts", "remote"):
            self.assertIn(n, names)
        pg = self.call("page", "lists")
        for key in ("title", "rows", "form", "submit", "more", "empty", "tabs"):
            self.assertIn(key, pg)
        made = self.call("place_act", json.dumps(["lists", "new", ""]), False,
                         json.dumps({"title": "С телефона"}))
        self.assertTrue(made.get("refresh") or made.get("message"))
        titles = [r["title"] for r in self.call("page", "lists")["rows"]]
        self.assertIn("С телефона", titles)
        tag = self.call("page", "tag", "fedi")
        posts = [r["post"] for r in tag["rows"] if r.get("post")]
        self.assertTrue(all("text" in p for p in posts))
        self.assertIn("error", json.loads(self.bridge.page("nowhere")))

    def test_a_cards_whole_menu(self):
        self.demo()
        m = self.call("post_menu", "103")
        kinds = {i["kind"] for i in m["items"]}
        self.assertIn("link", kinds)
        bm = next(i for i in m["items"] if i["url"].startswith("fedtail:bookmark/"))
        got = self.call("link", bm["url"])
        self.assertTrue(got.get("message") or got.get("refresh"))
        mute = next(i for i in m["items"] if i["url"].startswith("fedtail:mute/"))
        ask = self.call("link", mute["url"])
        self.assertIn("choose", ask)  # how long first
        key = ask["choose"]["options"][1]["key"]
        done = self.call("link", mute["url"], False, json.dumps({"key": key, "ticked": True}))
        self.assertTrue(done.get("message"))

    def test_a_profile_and_its_buttons(self):
        self.demo()
        p = self.call("post_menu", "103")
        author = self.call("lane", "home", True)["posts"][0]["account"]["id"]
        prof = self.call("account", author)
        for key in ("account", "relation", "actions", "posts", "shows"):
            self.assertIn(key, prof)
        self.assertTrue(all("text" in x for x in prof["posts"]))
        keys = [a["key"] for a in prof["actions"]]
        self.assertTrue(keys)
        media = self.call("account", author, "media")
        self.assertTrue(any(s["on"] and s["key"] == "media" for s in media["shows"]))
        self.assertTrue(p)

    def test_attachments_polls_and_the_editor(self):
        self.demo()
        pic = self.cache / "picked.png"
        pic.write_bytes(b"\x89PNG fake")
        up = self.call("upload", str(pic), "cat.png")
        self.assertTrue(up["token"].endswith(".png"))
        self.assertFalse(pic.exists())  # the cache's copy goes
        sent = self.call("post", json.dumps({"text": "with a cat", "media": [
            {"token": up["token"], "alt": "a cat"}]}))
        self.assertTrue(sent["id"])
        from tests import fakes
        self.assertEqual(fakes.FakeApi.world.uploads[-1][1], "a cat")
        ed = self.call("editor")
        for key in ("limit", "languages", "visibility", "poll_lengths"):
            self.assertIn(key, ed)
        self.assertIn("n", self.call("compose_check", json.dumps({"text": "hello"})))


class BridgeNotesTest(_Base):
    """The phone's notification shade: what the windows notify about, by a round in the
    background as well as while the app is open."""

    def test_a_background_round_brings_the_notes(self):
        self.demo()
        from tests.fakes import BOB, FakeApi, status
        first = self.call("notes", -1)
        self.assertEqual(first["notes"], [])  # a page that just opened: nothing old
        self.assertIn("when_focused", first)
        FakeApi.world.add(status("950", BOB, "100", "ME", minute=59, text="ping from the test"),
                          mention=True)
        got = self.call("background_round", first["n"])
        self.assertTrue(any("ping from the test" in n["body"] for n in got["notes"]), got)
        again = self.call("notes", got["n"])
        self.assertEqual(again["notes"], [])  # said once

    def test_ready_makes_the_core_once(self):
        # the app's own log (diag) stays off here: its file would outlive the test's
        # folder in the process's logger (Windows then can't write it: a Traceback)
        self.bridge._s["logging"] = True
        got = self.call("ready", str(self.files), str(self.cache), "en")
        self.assertFalse(got["logged_in"])  # no account yet: nothing to ask the server
        core = self.bridge._s["core"]
        self.call("ready", str(self.files), str(self.cache), "en")
        self.assertIs(self.bridge._s["core"], core)
        self.assertEqual(self.call("background_round", 0)["notes"], [])

    def test_a_round_in_a_process_the_system_made(self):
        """The app closed: the system wakes a process for the round — the core comes up
        without the screens, connects, asks once; the screens then still get a poller."""
        got = json.loads(self.bridge.start(str(self.files), str(self.cache), "en", True))
        self.assertNotIn("error", got)
        core = self.bridge._s["core"]
        self.assertIsNone(core.me)
        self.call("background_round", 0)
        self.assertIsNotNone(core.me)
        self.assertIsNone(getattr(core, "_poller", None))
        self.call("open")
        self.assertIsNotNone(core._poller)


class BridgeAccountsTest(_Base):
    """Another account on the phone: the windows' place "accounts" — switching makes
    that profile's core the bridge's, the screens start again on it."""

    def test_switching_to_another_account(self):
        self.demo()
        from fedtail.core import auth, paths
        where = paths.resolve("second")
        where.ensure()
        auth.save(where.auth_file, {"server": self.bridge.DEMO_SERVER, "token": "demo2"})
        names = [r["key"] for r in self.call("page", "accounts")["rows"]]
        self.assertIn("second", names)
        before = self.bridge._s["core"]
        got = self.call("place_act", json.dumps(["accounts", "switch", "second"]), False)
        self.assertTrue(got.get("reload"), got)
        now = self.bridge._s["core"]
        self.assertIsNot(now, before)
        self.assertEqual(now.paths.profile, "second")
        self.assertTrue(self.call("open")["lanes"])  # the screens come up on it


class BridgeThemeTest(_Base):
    """The phone in the windows' themes: ui.theme's colours, read as the web page reads
    them; "system" — the phone's own light or dark."""

    def test_a_theme_paints_the_phone(self):
        self.demo()
        self.assertEqual(self.call("theme")["colors"], {})  # system: nothing of its own
        self.assertEqual(self.call("pictures"), {})  # the desktop's icons: the phone's then
        names = [o["key"] for c in self.call("settings")["chapters"] for o in c["options"]]
        self.assertIn("theme", names)  # chosen on the phone's settings page
        self.assertIn("when_focused", names)  # and when the shade says what
        self.call("setting_set", "ui", "theme", json.dumps("night"))
        self.call("settings_apply")
        got = self.call("theme")
        self.assertEqual(got["name"], "night")
        self.assertFalse(got["light"])
        for k in ("bg", "text", "accent"):
            self.assertRegex(got["colors"][k], r"^#[0-9a-fA-F]{6}")
        # a theme's own font, as files that come with fedtail (no Tahoma on a phone)
        self.call("setting_set", "ui", "theme", json.dumps("paper"))
        self.call("settings_apply")
        font = self.call("theme")["font"]
        self.assertTrue(font["text"]["regular"].endswith(".ttf"), font)
        self.assertTrue(os.path.isfile(font["text"]["regular"]))
        self.call("setting_set", "ui", "theme", json.dumps("juick"))
        self.call("settings_apply")
        # tried for this run: the config keeps its own
        names = [t["name"] for t in self.call("themes")["themes"]]
        self.assertIn("night", names)
        self.assertTrue(self.call("try_theme", "night")["message"])
        self.assertEqual(self.call("theme")["name"], "night")
        self.assertIn("error", json.loads(self.bridge.try_theme("nope")))
        self.call("try_theme", "juick")
        pics = self.call("pictures")  # juick draws its own: the phone's buttons get them
        for word in ("reply", "boost", "like", "liked", "more", "refresh", "send"):
            self.assertIn("<svg", pics[word].get("svg", "") or open(pics[word]["png"]).read(4))


class BridgePushTest(_Base):
    """UnifiedPush: the server is told the distributor's address and the phone's keys;
    "off" takes it back. Only https addresses."""

    def test_subscribe_and_back(self):
        self.demo()
        from tests.fakes import FakeApi
        self.assertEqual(self.call("open")["me"]["push"], "auto")
        self.call("push_on", "https://push.example/up/abc", "BKey", "auth")
        self.assertEqual(FakeApi.world.push["endpoint"], "https://push.example/up/abc")
        self.call("push_off")
        self.assertIsNone(FakeApi.world.push)
        self.assertIn("error", json.loads(self.bridge.push_on("http://plain/x", "k", "a")))


class BridgeMergeTest(_Base):
    """All accounts in one window on the phone: the desktop's MergedCore, made by the
    bridge at once; out of sight, every account's rounds stop."""

    def test_two_accounts_in_one(self):
        from fedtail.core import auth, paths
        from tests.fakes import FakeApi, World
        FakeApi.world = World()
        self.call("start", str(self.files), str(self.cache), "en", False)  # the app's folders
        for name in ("one", "two"):
            where = paths.resolve(name)
            where.ensure()
            auth.save(where.auth_file, {"server": "https://example.test", "token": name})
        paths.set_main("one")
        real = self.bridge._make

        def make(demo):  # the real accounts, over the fake server
            from fedtail.core import app
            orig = app.Core.__init__

            def init(core, cfg, where, *a, **kw):
                kw.setdefault("api_class", FakeApi)
                orig(core, cfg, where, *a, **kw)
            with mock.patch.object(app.Core, "__init__", init):
                real(demo)
        self.bridge._make = make
        self.call("start", str(self.files), str(self.cache), "en", False)
        self.assertFalse(self.call("open")["me"]["merged"])
        got = self.call("merge", True)
        self.assertTrue(got["merged"] and got["reload"])
        core = self.bridge._s["core"]
        self.assertEqual(list(core.others), ["two"])
        self.call("pause", True)
        self.assertTrue(core.primary._paused and core.others["two"]._paused)
        self.call("merge", False)
        self.assertFalse(hasattr(self.bridge._s["core"], "others"))


class BridgeDraftTest(_Base):
    """The phone's editor keeps drafts in the core, as the windows do (synced across
    devices): a reply's draft comes back, an emptied one goes, a sent one is dropped."""

    def test_drafts_and_preview(self):
        self.demo()
        start = self.call("draft_start", "103", "", "", False)
        self.assertEqual(start["key"], "reply:103")
        self.assertFalse(start["restored"])
        self.assertTrue(start["text"].startswith("@"))  # the reply's mentions
        self.call("draft_save", "reply:103", json.dumps({"text": "недописанный ответ",
                                                          "visibility": "public"}))
        again = self.call("draft_start", "103", "", "", False)
        self.assertTrue(again["restored"])
        self.assertEqual(again["text"], "недописанный ответ")
        self.assertEqual(again["visibility"], "public")
        self.call("draft_save", "reply:103", json.dumps({"text": "  "}))  # emptied: gone
        self.assertFalse(self.call("draft_start", "103", "", "", False)["restored"])
        self.call("draft_save", "new", json.dumps({"text": "новый"}))
        self.call("draft_drop", "new")
        self.assertFalse(self.call("draft_start", "", "", "", False)["restored"])
        self.assertIn("error", json.loads(self.bridge.draft_save("../x", "{}")))
        pv = self.call("preview", json.dumps({"text": "раз\n\nдва", "cw": "осторожно"}))
        self.assertTrue(pv["parts"] and pv["cw"] == "осторожно")


class BridgeLaneToolsTest(_Base):
    """A lane's switches, finding in it and everywhere, a poll's fresh counts — the
    page's own, for the phone."""

    def test_switches_and_finding(self):
        self.demo()
        got = self.call("lane", "home", False)
        for key in ("filters", "conversations", "media", "info"):
            self.assertIn(key, got)
        self.call("lane_set", json.dumps({"name": "home", "media": "text", "on": False}))
        self.assertTrue(self.call("lane", "home", True)["media"]["active"])
        self.call("lane_set", json.dumps({"name": "home", "media": "reset"}))
        word = got["posts"][0]["text"].split()[0]
        found = self.call("find", "home", word)
        self.assertIn(got["posts"][0]["id"], found["ids"])
        every = self.call("find_everywhere", word)
        self.assertTrue(every["hits"] and every["hits"][0]["title"])
        self.assertIn("more", self.call("find_deeper", "home", word))
        with_poll = [p for p in got["posts"] if p.get("poll")]
        if with_poll:
            self.assertIn("poll", self.call("poll_refresh", with_poll[0]["sid"]))


class BridgeGapsTest(_Base):
    """What the phone caught up with: the overview's "of them new" and slow mode, the arts
    mark in ≡, another language, the editor's hints, the log, the background round in
    slow mode."""

    def test_overview_fresh_and_slow(self):
        self.demo()
        hub = self.call("hub")
        self.assertIn("fresh", hub)
        self.assertIn("slow", hub)
        for sec in hub["sections"]:
            for lane in sec["lanes"]:
                self.assertLessEqual(lane["fresh"], lane["unread"])
        core = self.bridge._s["core"]
        core.set_slow(30)
        core._next_round = 2_000_000_000
        self.assertTrue(self.call("hub")["slow"])
        core.set_slow(0)

    def test_arts_mark_language_hints_log(self):
        self.demo()
        core = self.bridge._s["core"]
        core.cfg["ui"]["arts_mode"] = True
        menu = self.call("places")
        self.assertEqual(menu[0]["name"], "")  # a mark, not a place
        self.assertIn("log", [x["name"] for x in menu])
        core.cfg["ui"]["arts_mode"] = False
        self.assertNotEqual(self.call("places")[0]["name"], "")
        got = self.call("add_language", "eo")
        self.assertEqual(got["code"], "eo")
        self.assertIn("error", json.loads(self.bridge.add_language("not a code")))
        hints = self.call("compose_check", json.dumps({"text": "#georgianews hello"}))
        self.assertTrue(hints["camel"])
        log = self.call("page", "log")
        self.assertEqual(log["name"], "log")

    def test_background_round_keeps_slow_mode(self):
        self.demo()
        core = self.bridge._s["core"]
        core.pause_polling(True)  # as on the phone: out of sight, the poller waits (it
        # polled at once when woken by set_slow, and poll_once counted twice: flaky)
        self.addCleanup(lambda: setattr(core, "_paused", False))
        core.set_slow(60)
        core._last_poll_ok = __import__("time").time()
        with mock.patch.object(core, "poll_once") as poll:
            self.call("background_round", 0)
        poll.assert_not_called()  # its turn hasn't come
        core.set_slow(0)
        with mock.patch.object(core, "poll_once") as poll:
            self.call("background_round", 0)
        poll.assert_called_once()
