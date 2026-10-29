"""The sound scheme: what the core asks for (core/sounds.py), which file a theme gives
(frontends/soundpack.py), how it is played (frontends/common/sound.py), the web page's
share of it, and that the shipped sets are what tools/make_sounds.py makes."""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fedtail.core import auth, config, paths
from fedtail.core.app import Core
from fedtail.core.sounds import EVENTS, Chime, event_for_lane, weightiest
from fedtail.frontends import soundpack, themefile
from fedtail.frontends.common.sound import Player, Sounds

from . import fakes, test_cli
from .fakes import BOB, ME, FakeApi, status
from .test_core import TmpDir

ROOT = Path(__file__).resolve().parent.parent


def cfg(**sound):
    sound.setdefault("enabled", "on")
    c, errors = config.validate({"sound": sound})
    assert not errors, errors
    return c


class Clock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


class ChimeTest(unittest.TestCase):
    def test_lanes_have_their_events(self):
        """By the rule, never the name: how personal (Core.lane_rank), the events taken."""
        self.assertEqual(event_for_lane(1), "reply")
        self.assertEqual(event_for_lane(0), "direct")
        self.assertEqual(event_for_lane(3), "thread")
        self.assertEqual(event_for_lane(4), "message")
        self.assertEqual(event_for_lane(4, {"follow_request"}), "request")
        self.assertEqual(event_for_lane(4, {"favourite", "follow"}), "activity")
        self.assertEqual(weightiest(["message", "thread", "reply"]), "reply")
        self.assertIsNone(weightiest([]))

    def test_a_batch_chimes_once_with_the_weightiest(self):
        clock = Clock()
        named = {"subs": "thread", "replies": "reply", "direct": "direct"}
        ch = Chime(cfg(), clock=clock, event_of=lambda n: named.get(n, "message"))
        self.assertEqual(ch.for_news(["subs", "replies", "direct"]), "direct")
        clock.t += 1  # within min_gap_seconds: quiet
        self.assertIsNone(ch.for_news(["replies"]))
        clock.t += 5
        self.assertEqual(ch.for_news(["replies"]), "reply")

    def test_lanes_not_asked_for_are_quiet(self):
        clock = Clock()
        ch = Chime(cfg(), clock=clock)
        self.assertIsNone(ch.for_news(["home", "bots", "activity"]))  # not in sound.lanes
        ch = Chime(cfg(lanes=["all"], **{"except": ["bots"]}), clock=clock)
        self.assertIsNone(ch.for_news(["bots"]))
        self.assertEqual(ch.for_news(["bots", "home"]), "message")

    def test_off_and_moments(self):
        clock = Clock()
        self.assertIsNone(Chime(cfg(enabled="off"), clock=clock).for_news(["replies"]))
        self.assertIsNone(Chime(cfg(scheme="none"), clock=clock).for_news(["replies"]))
        ch = Chime(cfg(sent=False), clock=clock)
        self.assertIsNone(ch.for_moment("sent"))
        self.assertEqual(ch.for_moment("online"), "online")
        self.assertIsNone(ch.for_moment("reply"))  # not a moment

    def test_auto_is_on_in_development_only(self):
        from fedtail.core import sounds
        c, _w = config.validate({})
        self.assertEqual(c["sound"]["enabled"], "auto")
        with mock.patch("fedtail.__version__", "0.19.0.dev3"):
            self.assertTrue(sounds.enabled(c))
        with mock.patch("fedtail.__version__", "0.19.0"):
            self.assertFalse(sounds.enabled(c))
            self.assertTrue(sounds.enabled(cfg(enabled="on")))
        self.assertFalse(sounds.enabled(cfg(enabled="off")))
        c, _w = config.validate({"sound": {"enabled": False}})  # the first dev builds' word
        self.assertEqual(c["sound"]["enabled"], "off")

    def test_config_checks(self):
        for bad in ({"volume": 120}, {"lanes": ["nope"]}, {"scheme": 3}, {"enabled": "yes"}):
            with self.assertRaises(config.ConfigError, msg=bad):
                config.validate({"sound": bad})
        c, _w = config.validate({"sound": {"lanes": ["comments"]}})  # an old name
        self.assertEqual(c["sound"]["lanes"], ["replies"])
        with self.assertRaises(config.ConfigError):
            config.validate({"tui": {"sound": "loud"}})


class CoreSoundTest(unittest.TestCase):
    def make(self, **over):
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        FakeApi.world = fakes.World()
        user = {"feed": {"first_run_mark_read": False, "page_size": 3}}
        for k, v in over.items():
            user.setdefault(k, {}).update(v)
        c, _ = config.validate(user)
        p = paths.resolve("t", config=f"{tmp.name}/c.toml", data=f"{tmp.name}/d")
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(c, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        self.events = []
        core.events.on("*", lambda n, pl: self.events.append((n, pl)))
        self.addCleanup(core.shutdown)
        return core, FakeApi.world

    def test_a_reply_sounds_and_a_home_post_doesnt(self):
        core, w = self.make(sound={"enabled": "on"})
        core.chime.clock = Clock()
        core.connect().result()
        self.assertIn(("sound", "online"), self.events)
        core.poll_once()  # first run
        sounds = lambda: [p for n, p in self.events if n == "sound"]  # noqa: E731
        mine = w.add(status("020", ME, minute=1), home=True)
        core.poll_once()
        before = len(sounds())
        core.chime.clock.t += 60
        w.add(status("021", BOB, mine["id"], "ME", minute=5), mention=True)
        w.add(status("022", BOB, minute=6), home=True)
        core.poll_once()
        self.assertEqual(sounds()[before:], ["reply"])
        core.chime.clock.t += 60
        w.add(status("023", BOB, minute=7), home=True)
        core.poll_once()
        self.assertEqual(sounds()[before:], ["reply"])  # home is not in sound.lanes

    def test_sound_without_notifications(self):
        core, w = self.make(notify={"lanes": []}, sound={"lanes": ["home"], "enabled": "on"})
        core.chime.clock = Clock()
        core.connect().result()
        core.poll_once()
        core.chime.clock.t += 60
        w.add(status("030", BOB, minute=3), home=True)
        core.poll_once()
        self.assertFalse([1 for n, _p in self.events if n == "notify"])
        self.assertIn(("sound", "message"), self.events)

    def test_sent(self):
        core, _w = self.make(sound={"min_gap_seconds": 0, "enabled": "on"})
        core.connect().result()
        core.post("hello", "public").result()
        self.assertIn(("sound", "sent"), self.events)


class ThemeSetsTest(unittest.TestCase):
    def setUp(self):
        soundpack.forget()
        self.addCleanup(soundpack.forget)

    def test_every_builtin_theme_resolves(self):
        for name in themefile.available():
            sch = soundpack.scheme(name, cfg())
            self.assertIn(sch.source, soundpack.SOURCES, name)
            self.assertEqual(sch.missing(), [], name)  # an own set lacks nothing

    def test_own_sets_and_borrowing(self):
        for name, folder in (("qip-retro", "qip-retro"), ("qip-modern", "qip-retro"),
                             ("mra-blue", "mra"), ("psi", "psi"), ("juick", "point")):
            snd = soundpack.scheme(name, cfg()).find("reply")
            self.assertEqual(snd.kind, "file", name)
            self.assertEqual(Path(snd.value).parent.parent.name, folder, name)
            self.assertTrue(snd.value.endswith("reply.wav"))

    def test_desktop_bell_none(self):
        snd = soundpack.scheme("system", cfg()).find("reply")
        self.assertEqual((snd.kind, snd.value), ("desktop", "message-new-instant"))
        self.assertTrue(Path(snd.file).is_file())  # without canberra: our quiet set
        self.assertIsNone(soundpack.scheme("system", cfg()).find("online"))
        self.assertEqual(soundpack.scheme("terminal", cfg()).find("reply").kind, "bell")
        self.assertIsNone(soundpack.scheme("qip-retro", cfg(scheme="none")).find("reply"))
        self.assertIsNone(soundpack.scheme("qip-retro", cfg(enabled="off")).find("reply"))
        self.assertIsNone(soundpack.scheme("qip-retro", cfg()).find("nonsense"))
        # sound.scheme borrows another theme's sounds whatever the look
        snd = soundpack.scheme("system", cfg(scheme="psi")).find("message")
        self.assertEqual(Path(snd.value).parent.parent.name, "psi")

    def test_a_user_set_and_stand_ins(self):
        with tempfile.TemporaryDirectory() as d, \
                mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": d}):
            themes = Path(d) / "fedtail" / "themes"
            (themes / "mine" / "sounds").mkdir(parents=True)
            (themes / "mine.toml").write_text('name = "Mine"\ninherit = "system"\n'
                                              '[sound]\nsource = "own"\n', "utf-8")
            (themes / "mine" / "sounds" / "message.ogg").write_bytes(b"x")
            soundpack.forget()
            sch = soundpack.scheme("mine", cfg())
            # a reply → a mention → a message: the one file stands in for all three
            self.assertTrue(sch.find("reply").value.endswith("message.ogg"))
            self.assertIsNone(sch.find("online"))  # stands in for nothing
            self.assertIn("online", sch.missing())

    def test_shipped_files_are_what_the_script_makes(self):
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import make_sounds
        finally:
            sys.path.pop(0)
        self.assertEqual(make_sounds.stale(), [])


class PlayerTest(unittest.TestCase):
    def which(self, have):
        return lambda name: f"/usr/bin/{name}" if name in have else None

    def test_linux_players_in_order(self):
        snd = soundpack.Sound("file", "/x/reply.wav", "reply")
        p = Player(cfg(volume=50), which=self.which({"paplay", "aplay"}), platform="linux")
        self.assertEqual(p.command(snd), ["/usr/bin/paplay", "--property=media.role=event",
                                          "--volume=32768", "/x/reply.wav"])
        p = Player(cfg(), which=self.which({"pw-play", "paplay"}), platform="linux")
        self.assertEqual(p.command(snd)[0], "/usr/bin/pw-play")
        self.assertIn("--media-role=Notification", p.command(snd))  # an event, not music
        p = Player(cfg(), which=self.which({"aplay"}), platform="linux")
        self.assertEqual(p.command(snd), ["/usr/bin/aplay", "/x/reply.wav"])
        self.assertIsNone(Player(cfg(), which=self.which(set()), platform="linux").command(snd))

    def test_desktop_sounds(self):
        snd = soundpack.Sound("desktop", "message-new-instant", "reply", file="/f/m.wav")
        p = Player(cfg(), which=self.which({"canberra-gtk-play", "aplay"}), platform="linux")
        self.assertEqual(p.command(snd)[:3],
                         ["/usr/bin/canberra-gtk-play", "-i", "message-new-instant"])
        p = Player(cfg(), which=self.which({"aplay"}), platform="linux")
        self.assertEqual(p.command(snd), ["/usr/bin/aplay", "/f/m.wav"])

    def test_other_systems_and_own_command(self):
        snd = soundpack.Sound("file", "/x/reply.wav", "reply")
        self.assertEqual(Player(cfg(), platform="win32").command(snd), ["winsound:/x/reply.wav"])
        ogg = soundpack.Sound("file", "/x/reply.ogg", "reply")
        self.assertIsNone(Player(cfg(), platform="win32").command(ogg))  # WAV only there
        p = Player(cfg(volume=100), which=self.which({"afplay"}), platform="darwin")
        self.assertEqual(p.command(snd), ["/usr/bin/afplay", "-v", "1.00", "/x/reply.wav"])
        p = Player(cfg(player="mpv --no-video {file}"), platform="linux")
        self.assertEqual(p.command(snd), ["mpv", "--no-video", "/x/reply.wav"])
        p = Player(cfg(player="play -q"), platform="linux")
        self.assertEqual(p.command(snd), ["play", "-q", "/x/reply.wav"])

    def test_one_at_a_time_and_never_raises(self):
        import threading
        gate, ran = threading.Event(), []

        def run(argv):
            ran.append(argv)
            gate.wait(5)
            raise OSError("boom")
        p = Player(cfg(), which=self.which({"aplay"}), platform="linux", run=run)
        snd = soundpack.Sound("file", "/x/a.wav", "reply")
        self.assertTrue(p.play(snd))
        self.assertFalse(p.play(snd))  # busy
        gate.set()
        for _ in range(200):
            if p._busy.acquire(blocking=False):
                p._busy.release()
                break
            threading.Event().wait(0.01)
        self.assertTrue(p.play(snd))
        self.assertEqual(len(ran), 2)


class FakePlayer:
    def __init__(self):
        self.got = []

    def play(self, snd):
        self.got.append(snd)
        return True


class SilentTest(unittest.TestCase):
    """FEDTAIL_SOUND=off (the tests, the self-check): nothing reaches the speakers."""

    def test_nothing_runs_and_no_beep(self):
        from fedtail.frontends.common import sound
        beeps = []
        with mock.patch.dict(os.environ, {"FEDTAIL_SOUND": "off"}), \
                mock.patch.object(sound.subprocess, "run") as run:
            sound.Player._subprocess(["pw-play", "/x.wav"])
            run.assert_not_called()
            s = Sounds(cfg(when_focused=True), "terminal", bell=lambda: beeps.append(1),
                       player=FakePlayer(), only_bell=True)
            s.play("message", focused=True)
        self.assertEqual(beeps, [])


class LaneSoundTest(TmpDir):
    """A real core's lanes sound by their rules: "Commented" (followed threads) is a
    thread — it was a "message", the thread sound never played; a lane of one's own
    that takes private posts is private, whatever it's called."""
    make = test_cli.CliTest.make

    def test_by_the_rule(self):
        core, _w = self.make()
        self.assertEqual(core.lane_sound("direct"), "direct")
        self.assertEqual(core.lane_sound("to_me"), "reply")
        self.assertEqual(core.lane_sound("commented"), "thread")
        self.assertEqual(core.lane_sound("home"), "message")
        self.assertEqual(core.lane_sound("activity"), "activity")
        self.assertEqual(core.lane_sound("no such lane"), "message")
        shown = {x.name for x in core.lanes}
        self.assertTrue(set(core.private_lanes()) <= shown)
        self.assertIn("direct", core.private_lanes())
        self.assertTrue(core.thread_lanes())  # this set's: "subs"
        self.assertTrue(all(core.lane_rank(n) == 3 for n in core.thread_lanes()))


class SoundsTest(unittest.TestCase):
    def setUp(self):
        soundpack.forget()

    @mock.patch.dict(os.environ, {"FEDTAIL_SOUND": ""})  # the bell itself is under test
    def test_focus_bell_and_terminal(self):
        beeps = []
        s = Sounds(cfg(when_focused=False), "qip-retro", bell=lambda: beeps.append(1),
                   player=FakePlayer())
        self.assertEqual(s.play("reply", focused=True), "")
        self.assertEqual(s.play("reply"), "file")
        s.set_theme("terminal")
        self.assertEqual(s.play("reply"), "bell")
        self.assertEqual(beeps, [1])
        self.assertEqual(s.played, ["reply", "reply"])
        # the terminal's tui.sound = "bell": whatever the theme
        t = Sounds(cfg(), "qip-retro", bell=lambda: beeps.append(2), player=FakePlayer(),
                   only_bell=True)
        self.assertEqual(t.play("message"), "bell")
        self.assertEqual(Sounds(cfg(), "terminal", bell=None).play("reply"), "")

    def test_every_event_of_every_theme(self):
        for name in themefile.available():
            s = Sounds(cfg(), name, bell=lambda: None, player=FakePlayer())
            for e in EVENTS:
                s.play(e)  # never raises


class WebSoundTest(unittest.TestCase):
    def test_the_page_hears_the_newest_once(self):
        from fedtail.core.events import Events
        from fedtail.frontends.web.server import Web

        class FakeCore:
            def __init__(self):
                self.events = Events()
                self.cfg = cfg()
                self.cfg["ui"]["theme"] = "qip-retro"

            def on(self, name, fn):
                self.events.on(name, fn)

        core = FakeCore()
        with mock.patch("fedtail.frontends.web.server.View", FakeCore):
            web = Web(core, "k" * 24)
        first = web.sounds_since(-1)
        self.assertEqual(first, ([], 0))  # a page that just opened hears nothing old
        core.events.emit("sound", "mention")
        core.events.emit("sound", "reply")
        got, last = web.sounds_since(0)
        self.assertEqual((got, last), ([{"event": "reply", "kind": "file"}], 2))
        self.assertEqual(web.sounds_since(2), ([], 2))
        self.assertTrue(web.sound_file("reply").startswith(b"RIFF"))
        self.assertIsNone(web.sound_file("../../etc/passwd"))
        core.cfg["ui"]["theme"] = "terminal"
        soundpack.forget()
        core.events.emit("sound", "reply")
        self.assertEqual(web.sounds_since(2)[0], [{"event": "reply", "kind": "bell"}])


class MakeSoundsScriptTest(unittest.TestCase):
    def test_check_runs(self):
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "make_sounds.py"), "--check"],
                           capture_output=True, text=True, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


if __name__ == "__main__":
    unittest.main()
