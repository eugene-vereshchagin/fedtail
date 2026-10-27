"""The small toolkit-free pieces of frontends/common the windows share, case by case:
a picture's focus point, the Activity rows' words, About's facts on every platform, how
a failed call is reported, the sync line, Ctrl+F's words, "＋ to lanes", the settings
model's corners, and the sound player's ways of playing."""

import logging
import os
import types
import unittest
from concurrent.futures import Future
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest import mock

from fedtail import i18n
from fedtail.frontends import soundpack
from fedtail.frontends.common import (
    about,
    activity,
    find,
    focus,
    results,
    settings,
    sound,
    syncline,
    taglanes,
)
from fedtail.model import Account, Activity, Notice, Ref


def acc(i):
    return Account(Ref("m", "", i), f"u{i}@x.test", f"u{i}")


class FocusTest(unittest.TestCase):
    def test_round_trip(self):
        self.assertEqual(focus.to_focus(50, 50, 100, 100), (0.0, 0.0))
        self.assertEqual(focus.to_focus(0, 0, 100, 100), (-1.0, 1.0))  # top left, y up
        self.assertEqual(focus.to_focus(500, -20, 100, 100), (1.0, 1.0))  # clamped
        self.assertEqual(focus.from_focus((0.0, 0.0), 200, 100), (100.0, 50.0))
        self.assertEqual(focus.from_focus((-1.0, 1.0), 200, 100), (0.0, 0.0))
        x, y = focus.from_focus(focus.to_focus(30, 70, 100, 100), 100, 100)
        self.assertAlmostEqual(x, 30)
        self.assertAlmostEqual(y, 70)


class ActivityWordsTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def a(self, kind, **kw):
        return Activity(Ref("m", "", kw.pop("i", "1")), kind, kw.pop("who", acc("A")),
                        None, kw.pop("sort", "1"), **kw)

    def test_keys(self):
        self.assertEqual(activity.act_key(self.a("request", asks="reply")), "pending.reply")
        self.assertEqual(activity.act_key(self.a("request", asks="odd")), "request")
        self.assertEqual(activity.act_key(self.a("notice", details=Notice("severed"))),
                         "severed_relationships")
        self.assertEqual(activity.act_key(self.a("notice")), "notice")
        self.assertEqual(activity.act_key(self.a("mention")), "mention")

    def test_notice_text(self):
        sev = activity.notice_text(Notice("severed", target="bad.test", lost=3))
        self.assertIn("bad.test", sev)
        self.assertIn("3", sev)
        self.assertIn("?", activity.notice_text(Notice("severed")))
        warn = activity.notice_text(Notice("warning", action="silence", text="x" * 500))
        self.assertIn("x" * 300, warn)
        self.assertNotIn("x" * 301, warn)
        self.assertTrue(activity.notice_text(Notice("warning")))
        self.assertEqual(activity.notice_text(Notice("other")), "")

    def test_a_notice_row_carries_its_words(self):
        n = self.a("notice", details=Notice("warning", action="none", text="be nice"))
        row = activity.rows([n], "0", lambda d: "")[0]
        self.assertIn("be nice", row.notice)
        t = datetime(2026, 1, 1, tzinfo=UTC)
        two = [Activity(Ref("m", "", "2"), "like", acc("B"), t + timedelta(days=1), "2"),
               Activity(Ref("m", "", "1"), "like", acc("A"), t, "1")]
        row = activity.rows(two, "1", lambda d: d.strftime("%d"), oldest_first=False)[0]
        self.assertEqual(row.when, "01 … 02")
        self.assertTrue(row.unread)


class AboutTest(unittest.TestCase):
    def test_platform_names(self):
        with mock.patch.object(about.sys, "platform", "win32"), \
                mock.patch.object(about.platform, "release", return_value="11"):
            self.assertEqual(about.platform_name(), "Windows 11")
        with mock.patch.object(about.sys, "platform", "win32"), \
                mock.patch.object(about.platform, "release", return_value=""):
            self.assertEqual(about.platform_name(), "Windows")
        with mock.patch.object(about.sys, "platform", "darwin"), \
                mock.patch.object(about.platform, "mac_ver", return_value=("15.1", "", "")):
            self.assertEqual(about.platform_name(), "macOS 15.1")
        with mock.patch.object(about.sys, "platform", "linux"), \
                mock.patch.object(about.platform, "freedesktop_os_release",
                                  side_effect=OSError), \
                mock.patch.object(about.platform, "system", return_value="Linux"):
            self.assertEqual(about.platform_name(), "Linux")
        with mock.patch.object(about.sys, "platform", "linux"), \
                mock.patch.object(about.platform, "freedesktop_os_release",
                                  return_value={}), \
                mock.patch.object(about.platform, "system", return_value=""):
            self.assertEqual(about.platform_name(), "linux")

    def test_facts_of_a_merged_window(self):
        i18n.setup("en")
        core = types.SimpleNamespace(
            post_accounts=lambda _r: ([("", "@a@x.test"), ("w", "@b@y.test")], ""),
            sync_status=lambda: None)
        view = types.SimpleNamespace(_core=core, cfg={"ui": {"theme": "paper"}},
                                     paths=types.SimpleNamespace(profile="p",
                                                                 data_dir=Path("/d")),
                                     caps=types.SimpleNamespace(software="gotosocial",
                                                                version="0.20"))
        a = about.facts(view, "Qt", "6.8")
        rows = dict(a.rows)
        self.assertEqual(rows["Qt"], "6.8")
        self.assertEqual(rows[i18n._("about_accounts")], "@a@x.test, @b@y.test")
        self.assertEqual(rows[i18n._("about_server")], "gotosocial 0.20")
        self.assertEqual(rows[i18n._("about_theme")], "paper")
        self.assertIn("gotosocial 0.20", a.text())


class ResultsTest(unittest.TestCase):
    def test_an_unexpected_failure_is_logged_with_its_traceback(self):
        f = Future()
        f.set_exception(KeyError("bug"))
        said = []
        with self.assertLogs("fedtail.frontends.common.results", "WARNING") as logs:
            results.handle(f, None, None, on_error=said.append)
        self.assertEqual(said, ["'bug'"])
        self.assertTrue(logs.records[0].exc_info)

    def test_rate_text(self):
        i18n.setup("en")
        until = datetime(2030, 1, 1, 15, 4).timestamp()
        self.assertIn("15:04", results.rate_text({"until": until}))
        self.assertTrue(results.rate_text(None))
        self.assertTrue(results.rate_text("odd"))


class SynclineTest(unittest.TestCase):
    def test_status_through_a_view_and_a_failing_core(self):
        core = types.SimpleNamespace(sync_status=lambda: {"where": "w"})
        self.assertEqual(syncline.status(types.SimpleNamespace(_core=core)), {"where": "w"})

        def boom():
            raise RuntimeError
        self.assertIsNone(syncline.status(types.SimpleNamespace(sync_status=boom)))
        self.assertEqual(syncline.local_time("not a time"), "")

    def test_bar_and_about(self):
        i18n.setup("en")

        def view(st):
            return types.SimpleNamespace(sync_status=lambda: st)
        self.assertEqual(syncline.bar(view(None))[0], i18n._("sync_bar_off"))
        self.assertEqual(syncline.about(view(None)), i18n._("about_sync_off"))
        bad = syncline.bar(view({"where": "w", "last": {"error": "403"}}))
        self.assertIn("403", bad[1])
        self.assertEqual(syncline.bar(view({"where": "w"}))[0], i18n._("sync_bar_wait"))
        now = datetime.now(UTC).isoformat()
        ok = syncline.bar(view({"where": "https://s", "last": {"at": now, "sent": 2}}))
        self.assertIn(syncline.local_time(now), ok[0])
        self.assertIn("https://s", syncline.about(view({"where": "https://s",
                                                         "last": {"at": now}})))
        old = (datetime.now(UTC) - timedelta(days=3)).isoformat()
        self.assertIn(".", syncline.local_time(old))  # not today: with its date


class FindTest(unittest.TestCase):
    def test_words(self):
        i18n.setup("en")
        self.assertEqual(find.step(0, 0, 1), -1)
        text, none = find.count_text("x", 1, 5, "Replies", everywhere=True)
        self.assertIn("Replies", text)
        self.assertFalse(none)
        text, _n = find.count_text("x", -1, 5)
        self.assertIn("0", text)


class TagLanesTest(unittest.TestCase):
    def test_choices_skip_config_lanes_and_its_own(self):
        i18n.setup("en")
        from fedtail.core import taggroups
        own = taggroups.lane_name(taggroups.normal({"any": ["tbilisi"]}))
        view = types.SimpleNamespace(lane_by_name={}, tag_groups=[
            {"any": ["a"]},  # from the config: not offered
            dict(taggroups.normal({"any": ["tbilisi"]}), saved=True),  # its own lane
            {"any": ["a", "tbilisi"], "saved": True, "name": "Georgia"}])
        got = taglanes.choices(view, "#Tbilisi")
        self.assertEqual([k for k, _w, _o in got][0], taglanes.OWN)
        self.assertEqual(len(got), 2)
        self.assertFalse(got[1][2])  # already in Georgia
        self.assertNotIn(own, [k for k, _w, _o in got[1:]])
        saved = []
        view.save_tag_group = saved.append
        taglanes.apply(view, taglanes.OWN, "#Tbilisi")
        self.assertEqual(saved, [{"any": ["tbilisi"]}])
        view.add_tag_to_group = lambda lane, tag: (lane, tag)
        self.assertEqual(taglanes.apply(view, "tags:georgia", "#Tbilisi"),
                         ("tags:georgia", "tbilisi"))


class SettingsCornersTest(unittest.TestCase):
    def view(self, path, **kw):
        return types.SimpleNamespace(paths=types.SimpleNamespace(config_file=path), **kw)

    def test_option_words_and_parsing(self):
        o = settings.Option("ui", "esc", "choice", "tray", "curtain",
                            choices=[("tray", "to the tray")])
        self.assertEqual(o.words_of("tray"), "to the tray")
        self.assertEqual(o.words_of("off"), "off")
        b = settings.Option("ui", "x", "bool", False, False)
        self.assertTrue(b.parse("yes"))
        self.assertTrue(b.parse(True))
        self.assertFalse(b.parse("nope"))
        self.assertEqual(settings._title("", "font_size"), "font size")
        self.assertEqual(b.shown(True), "true")
        self.assertEqual(b.shown(""), '""')
        self.assertEqual(b.shown([]), "—")

    def test_reference_options_the_program_doesnt_have_are_left_out(self):
        extra = settings.reference("en") + [(1, "Look", "ui", "", "gone_option", [])]
        with mock.patch.object(settings, "reference", return_value=extra):
            chapters = settings.model(self.view(Path("/nowhere")), lang="en", text="")
        self.assertIsNone(settings.option(chapters, "ui.gone_option"))

    def test_arrays_of_tables_stay_in_the_file(self):
        """[[lanes.custom]] as a line to type would be written back broken."""
        text = '[[lanes.custom]]\nname = "x"\nany = [{}]\n'
        chapters = settings.model(self.view(Path("/nowhere")), lang="en", text=text)
        self.assertIsNone(settings.option(chapters, "lanes.custom"))
        self.assertIsNone(settings.option(chapters, "lanes.tag_groups"))
        self.assertIsNotNone(settings.option(chapters, "lanes.unsorted"))

    def test_lane_words_and_themes_that_fail(self):
        i18n.setup("en")

        def title(_n):
            raise KeyError
        words = settings._lane_words(types.SimpleNamespace(lane_title=title))
        self.assertEqual(words("home"), i18n._("lane_home"))
        self.assertEqual(words("list:7"), "list:7")
        with mock.patch("fedtail.frontends.themefile.available", side_effect=OSError):
            self.assertEqual(settings._theme_names(), [])

    def test_a_broken_file_shows_the_defaults(self):
        chapters = settings.model(self.view(Path("/nowhere")), lang="en", text="[ui\n")
        self.assertEqual(settings.option(chapters, "ui.theme").value, "system")

    def test_save_nothing_and_warnings(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "config.toml"
            f.write_text("[ui]\n[nonsense]\nx = 1\n", "utf-8")
            v = self.view(f)
            self.assertEqual(settings.save(v, {}), "")
            words = settings.save(v, {("ui", "theme"): "paper"})
            self.assertIn("unknown section", words)
            chapters = settings.model(v, lang="en")
            self.assertEqual(settings.changes_of(chapters, {"no.such": "1"}), {})


class SoundPlayerTest(unittest.TestCase):
    def player(self, platform="linux", have=(), **cfg):
        return sound.Player({"sound": cfg}, which=lambda n: f"/bin/{n}" if n in have
                            else None, platform=platform, run=lambda argv: None)

    def test_commands(self):
        f = soundpack.Sound("file", "/s/a.wav", "reply")
        d = soundpack.Sound("desktop", "message", "reply", file="/s/b.wav")
        self.assertIsNone(self.player(player="  ").command(f))  # an empty own command
        self.assertIsNone(self.player().command(None))
        self.assertIsNone(self.player().command(soundpack.Sound("bell", "", "reply")))
        self.assertFalse(self.player().play(None))  # nothing to play it with
        self.assertIsNone(self.player().command(soundpack.Sound("file", "", "reply")))
        self.assertEqual(self.player(have=("paplay",)).command(d)[-1], "/s/b.wav")
        self.assertIsNone(self.player(platform="win32").command(
            soundpack.Sound("file", "/s/a.ogg", "reply")))

    def test_busy_and_failing_players(self):
        import threading
        p = self.player(have=("aplay",))
        gate = threading.Event()
        p._run = lambda argv: gate.wait(5)
        f = soundpack.Sound("file", "/s/a.wav", "reply")
        self.assertTrue(p.play(f))
        self.assertFalse(p.play(f))  # one at a time
        gate.set()

    def test_subprocess_runs_or_stays_silent(self):
        with mock.patch.dict(os.environ, {"FEDTAIL_SOUND": "on"}), \
                mock.patch.object(sound.subprocess, "run") as run:
            sound.Player._subprocess(["/bin/aplay", "x.wav"])
        self.assertEqual(run.call_args[0][0], ["/bin/aplay", "x.wav"])
        fake = types.SimpleNamespace(SND_FILENAME=1, PlaySound=mock.Mock())
        with mock.patch.dict(os.environ, {"FEDTAIL_SOUND": "on"}), \
                mock.patch.dict("sys.modules", {"winsound": fake}):
            sound.Player._subprocess(["winsound:C:/a.wav"])
        fake.PlaySound.assert_called_once_with("C:/a.wav", 1)
        with mock.patch.dict(os.environ, {"FEDTAIL_SOUND": "off"}), \
                mock.patch.object(sound.subprocess, "run") as run:
            sound.Player._subprocess(["/bin/aplay", "x.wav"])
        run.assert_not_called()

    def test_sounds_bell_and_test_words(self):
        i18n.setup("en")
        cfg = {"sound": {"enabled": "on"}, "ui": {}}

        def broken_bell():
            raise RuntimeError("no tty")
        s = sound.Sounds(cfg, "terminal", bell=broken_bell, only_bell=True)
        s.scheme = soundpack.Scheme("terminal", "bell")
        with mock.patch.dict(os.environ, {"FEDTAIL_SOUND": "on"}), \
                self.assertLogs("fedtail.frontends.common.sound", logging.DEBUG):
            self.assertEqual(s.play("reply"), "")
        s.bell = None
        self.assertEqual(s.play("reply"), "")
        self.assertIn("reply", s.test("reply"))  # silent: says so
        s.bell = lambda: None
        self.assertIn("bell", s.test("reply"))
        s.scheme = soundpack.Scheme("x", "none")
        self.assertEqual(s.play("reply"), "")
        played = []
        s.scheme = types.SimpleNamespace(theme="t", find=lambda e: soundpack.Sound(
            "file", "/a.wav", e))
        s.player = types.SimpleNamespace(play=lambda snd: played.append(snd) or False)
        self.assertEqual(s.play("reply"), "")  # the player couldn't: nothing done
        self.assertEqual(len(played), 1)


if __name__ == "__main__":
    unittest.main()
