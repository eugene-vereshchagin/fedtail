"""What the network may throw at fedtail (docs/*/dev/robustness.md): a page that isn't
JSON (a captive portal), an answer too big to read, rounds failing again and again."""

import io
import tempfile
import time
import unittest
from unittest import mock

import requests

from fedtail.protocols.mastodon import api as api_mod


def answer(body, status=200, ctype="application/json", length=True):
    r = requests.Response()
    r.status_code = status
    r.headers["Content-Type"] = ctype
    if length:
        r.headers["Content-Length"] = str(len(body))
    r.raw = io.BytesIO(body)
    return r


class AnswersTest(unittest.TestCase):
    def api(self, *answers):
        s = mock.Mock()
        s.headers = {}
        s.request.side_effect = list(answers)
        return api_mod.Api("https://example.test", "tok", session=s)

    def test_json_read_from_the_stream(self):
        a = self.api(answer(b'{"id": "1"}'))
        self.assertEqual(a.get("/x"), {"id": "1"})
        self.assertTrue(a.s.request.call_args.kwargs["stream"])

    def test_a_portal_page_is_an_error_that_says_so(self):
        a = self.api(answer(b"<html>Log in to the Wi-Fi</html>", ctype="text/html"))
        with self.assertRaises(api_mod.ApiError) as e:
            a.get("/api/v1/timelines/home")
        self.assertIn("text/html", str(e.exception))

    def test_too_big_by_its_length_and_by_what_comes(self):
        with mock.patch.object(api_mod, "MAX_ANSWER", 1000):
            a = self.api(answer(b"x" * 2000))
            with self.assertRaises(api_mod.TooBig):
                a.get("/big")
            a = self.api(answer(b"[" + b"1," * 1500 + b"1]", length=False))
            with self.assertRaises(api_mod.TooBig):
                a.get("/chunked")
            a = self.api(answer(b"[1]", length=False))
            self.assertEqual(a.get("/small"), [1])
        r = answer(b"{}")
        r.headers["Content-Length"] = "lots"  # a header that says nothing: read on
        self.assertEqual(self.api(r).get("/x"), {})
        self.assertIsNone(self.api(answer(b"")).get("/empty"))

    def test_paged_lists_go_the_same_way(self):
        r = answer(b'[{"id": "a"}]')
        r.headers["Link"] = '<https://example.test/api/v1/x?max_id=77>; rel="next"'
        items, nxt = self.api(r).get_page("/api/v1/accounts/1/following")
        self.assertEqual((items, nxt), ([{"id": "a"}], "77"))
        with self.assertRaises(api_mod.ApiError):
            self.api(answer(b'{"error": "no"}', status=404)).get_page("/p")



class BackoffTest(unittest.TestCase):
    def test_doubles_and_stops_at_the_cap(self):
        from fedtail.core.app import Core
        core = mock.Mock(cfg={"poll": {"interval_seconds": 90}}, BACKOFF_MAX=900)
        waits = []
        for n in range(6):
            core._fails_in_row = n
            waits.append(Core.backoff(core))
        self.assertEqual(waits, [0, 0, 180, 360, 720, 900])



class BrokenConfigTest(unittest.TestCase):
    """A broken config.toml: in a terminal it is said and fedtail stops; from a menu (no
    terminal) a window says it and may go on with the defaults."""

    def test_a_terminal_stops(self):
        import tempfile
        from pathlib import Path

        from fedtail import __main__ as main_mod
        with tempfile.TemporaryDirectory() as d:
            cfg = Path(d) / "c.toml"
            cfg.write_text("[ui\n", "utf-8")
            with mock.patch.object(main_mod, "_config_trouble", return_value=False) as asked, \
                    mock.patch("sys.stderr", io.StringIO()) as err:
                code = main_mod.main(["--config", str(cfg), "--data", d + "/data"])
            self.assertEqual(code, 2)
            self.assertIn("config error", err.getvalue())
            asked.assert_called_once()

    def test_no_window_to_ask_in(self):
        from fedtail import __main__ as main_mod
        tty = mock.Mock()
        tty.isatty.return_value = True
        with mock.patch("sys.stdin", tty):
            self.assertFalse(main_mod._config_trouble("c.toml", "bad"))
        tty.isatty.return_value = False
        with mock.patch("sys.stdin", tty):  # the tests say no windows (FEDTAIL_NO_DIALOGS)
            self.assertFalse(main_mod._config_trouble("c.toml", "bad"))
        with mock.patch("sys.stdin", tty), \
                mock.patch.dict("os.environ", {"FEDTAIL_NO_DIALOGS": "",
                                               "QT_QPA_PLATFORM": ""}), \
                mock.patch.dict("sys.modules", {"PySide6.QtWidgets": None}):
            self.assertFalse(main_mod._config_trouble("c.toml", "bad"))



class LogFolderTest(unittest.TestCase):
    def test_elsewhere_or_nowhere(self):
        import tempfile
        import types
        from pathlib import Path

        from fedtail import diag
        with tempfile.TemporaryDirectory() as d:
            blocker = Path(d) / "file"
            blocker.write_text("x", "utf-8")
            bad = blocker / "logs"  # under a file: can't be made
            prof = types.SimpleNamespace(profile="t")
            with mock.patch("sys.stderr", io.StringIO()) as err, \
                    mock.patch("tempfile.gettempdir", return_value=d):
                got = diag._writable(bad, prof)
            self.assertEqual(got, Path(d) / "fedtail-logs-t")
            self.assertIn("can't be written", err.getvalue())
            self.assertEqual(diag._writable(Path(d) / "ok", prof), Path(d) / "ok")
            with mock.patch("tempfile.gettempdir", return_value=str(blocker)):
                self.assertIsNone(diag._writable(bad, prof))
            import os
            import stat
            if hasattr(os, "getuid"):  # the fallback is the owner's only
                mode = stat.S_IMODE(os.stat(Path(d) / "fedtail-logs-t").st_mode)
                self.assertEqual(mode, 0o700)
                loose = Path(d) / "fedtail-logs-u"
                loose.mkdir(mode=0o777)
                os.chmod(loose, 0o777)
                with mock.patch("sys.stderr", io.StringIO()), \
                        mock.patch("tempfile.gettempdir", return_value=d):
                    self.assertEqual(diag._writable(bad, types.SimpleNamespace(profile="u")),
                                     loose)
                self.assertEqual(stat.S_IMODE(os.stat(loose).st_mode), 0o700)  # tightened
                trap = Path(d) / "fedtail-logs-v"  # a link someone left: not followed
                trap.symlink_to(Path(d) / "ok")
                with mock.patch("tempfile.gettempdir", return_value=d):
                    self.assertIsNone(diag._writable(bad, types.SimpleNamespace(profile="v")))
                with mock.patch("os.getuid", return_value=os.getuid() + 1), \
                        mock.patch("tempfile.gettempdir", return_value=d):  # someone else's
                    self.assertIsNone(diag._writable(bad, prof))



class NapTest(unittest.TestCase):
    def nap(self, seconds, jumps=0.0, woken=False):
        from fedtail.core.app import Core
        core = mock.Mock(NAP_STEP=30)
        core._wake = mock.Mock()
        t = {"wall": 1000.0, "mono": 0.0}

        def wait(timeout):  # time passes as the wait says; a suspend adds wall time
            t["mono"] += timeout
            t["wall"] += timeout + jumps
            return woken
        core._wake.wait.side_effect = wait
        return Core._nap(core, seconds, clock=lambda: t["wall"], mono=lambda: t["mono"]), \
            core._wake.wait.call_count

    def test_plain_wait_in_steps(self):
        self.assertEqual(self.nap(90), (False, 3))

    def test_a_suspend_ends_it(self):
        self.assertEqual(self.nap(90, jumps=3600), (True, 1))

    def test_a_wake_ends_it(self):
        self.assertEqual(self.nap(90, woken=True), (False, 1))



class DeletedElsewhereTest(unittest.TestCase):
    def test_gone_already_is_done(self):
        from tests.test_slow import Base

        class T(Base):
            def runTest(self):
                pass
        t = T()
        t.addCleanup = self.addCleanup
        core, w = t.make()
        from tests.fakes import ME, status
        w.add(status("090", ME, minute=1), home=True)
        core.poll_once()
        st = core.store.get_status("090")
        gone = api_mod.ApiError(404, "Record not found")
        with mock.patch.object(core.api, "delete_status", side_effect=gone):
            core.delete(st).result()
        self.assertIsNone(core.store.get_status("090"))
        with mock.patch.object(core.api, "delete_status",
                               side_effect=api_mod.ApiError(500, "down")), \
                self.assertRaises(api_mod.ApiError):
            core.delete(st).result()


if __name__ == "__main__":
    unittest.main()


class PollStateTest(unittest.TestCase):
    """27.10: a lane opened, nothing new for half a minute — no word whether the round
    was still going or the network was gone. The status line now says which."""

    def test_the_words_for_each_state(self):
        from unittest import mock

        from fedtail import i18n
        from fedtail.frontends.common import sidebar
        i18n.setup("en")
        view = mock.Mock()
        view.slow_minutes.return_value = 0
        at = time.mktime((2026, 10, 27, 14, 32, 0, 0, 0, -1))
        for st, words in (({}, ""),
                          ({"busy": True, "ok_at": None, "failing": 0}, "updating"),
                          ({"busy": False, "ok_at": at, "failing": 0}, "updated at 14:32"),
                          ({"busy": True, "ok_at": at, "failing": 2}, "since 14:32"),
                          ({"busy": False, "ok_at": None, "failing": 1}, "doesn't answer")):
            view.poll_state.return_value = st
            got = sidebar.status_words(view)
            self.assertIn(words, got) if words else self.assertEqual(got, "")
        view.poll_state.side_effect = AttributeError
        self.assertEqual(sidebar.poll_words(view), "")

    def test_a_round_says_it_began_and_ended_and_counts_failures(self):
        from fedtail.core.app import Core
        core = Core.__new__(Core)
        seen = []
        core.emit = lambda name, payload=None: seen.append((name, payload))
        core.api = object()
        core.cfg = {"debug": {}}
        core._poll_count = 0
        core._poll_failures = 0
        core._poll_once = lambda: None
        Core.poll_once(core)
        self.assertEqual([p for n, p in seen if n == "poll_state"], [True, False])
        self.assertEqual(core.poll_state()["failing"], 0)
        self.assertIsNotNone(core.poll_state()["ok_at"])

        def down():
            raise OSError("no network")
        core._poll_once = down
        with self.assertRaises(OSError):
            Core.poll_once(core)
        self.assertEqual(core.poll_state(), {"busy": False, "ok_at": core._last_poll_ok,
                                             "failing": 1})

    def test_busy_from_the_start_until_the_first_round_ends(self):
        """The curtain's opossum swings from the window's first frame: a Core is busy
        (starting) from its making, through connecting, until its first round is over —
        and not after a connect that failed (nothing is coming)."""
        import tempfile
        from pathlib import Path

        from fedtail.core import auth, config, paths
        from fedtail.core.app import Core

        from . import fakes
        from .fakes import FakeApi
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        FakeApi.world = world = fakes.World()
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False}})
        p = paths.resolve("t", config=str(Path(tmp.name) / "c.toml"),
                          data=str(Path(tmp.name) / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        self.addCleanup(core.shutdown)
        seen = []
        core.events.on("poll_state", lambda _n, on: seen.append(on))
        self.assertTrue(core.poll_state()["busy"])  # made, nothing asked yet
        core.connect().result(timeout=10)
        self.assertTrue(core.poll_state()["busy"])  # connected: the lanes still coming
        self.assertEqual(seen, [True])
        core.poll_once()
        self.assertFalse(core.poll_state()["busy"])
        self.assertEqual(seen[-1], False)
        # connecting anew later (the network back): not "starting" again
        core.connect().result(timeout=10)
        self.assertFalse(core.poll_state()["busy"])

        # a connect that fails: busy no more, and said so
        world.fail_auth = True
        other = Core(cfg, p, api_class=FakeApi)
        self.addCleanup(other.shutdown)
        said = []
        other.events.on("poll_state", lambda _n, on: said.append(on))
        self.assertTrue(other.poll_state()["busy"])
        with self.assertRaises(api_mod.ApiError):
            other.connect().result(timeout=10)
        self.assertFalse(other.poll_state()["busy"])
        self.assertEqual(said, [True, False])

        # logged out: the login comes first — nothing is being got
        p.auth_file.unlink()
        out = Core(cfg, p, api_class=FakeApi)
        self.addCleanup(out.shutdown)
        self.assertFalse(out.logged_in)
        self.assertFalse(out.poll_state()["busy"])


class SecretFileTest(unittest.TestCase):
    def test_two_writers_at_once(self):
        """A secret file written by two threads at once (the sync key: a round's own and
        the window's, 29.10): neither fails, the file is one of them whole, the owner's
        only, and no temporary file is left."""
        import json
        import os
        import stat
        import threading
        from pathlib import Path

        from fedtail.core import auth
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "sync.key"
            errors = []

            def write(n):
                try:
                    for i in range(40):
                        auth.save(f, {"key": f"{n}-{i}"})
                except Exception as e:  # noqa: BLE001 — what the test is about
                    errors.append(e)
            threads = [threading.Thread(target=write, args=(n,)) for n in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()
            self.assertEqual(errors, [])
            self.assertTrue(json.loads(f.read_text("utf-8"))["key"].endswith("-39"))
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["sync.key"])
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(f.stat().st_mode), 0o600)


class OfflineTest(unittest.TestCase):
    """30.10, a laptop's network gone: every round asked each of twenty sources in turn,
    each failing alike, each said to the user (its words told apart by an object's
    address), and the round counted as fine — no backoff. Now the first "no way to the
    server" stops the round, it is said once an outage, and the rounds wait longer."""

    def setUp(self):
        from pathlib import Path

        from fedtail import i18n
        from fedtail.core import auth, config, paths
        from fedtail.core.app import Core

        from . import fakes
        from .fakes import FakeApi
        i18n.setup("en")
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        FakeApi.world = fakes.World()
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False},
                                  "lanes": {"enabled": fakes.CLASSIC_LANES}})
        p = paths.resolve("t", config=str(Path(tmp.name) / "c.toml"),
                          data=str(Path(tmp.name) / "d"))
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        self.core = core = Core(cfg, p, api_class=FakeApi)
        self.addCleanup(core.shutdown)
        core.connect().result(timeout=10)
        core._loop_round()
        self.errors = []
        core.events.on("error", lambda _n, e: self.errors.append(e))

    def _cut(self, host=None):
        """Every request of the account's api fails as with no network."""
        real, asked = self.core.api, []

        class Down:
            def __getattr__(self, name):
                got = getattr(real, name)
                if not callable(got):
                    return got

                def fail(*a, **k):
                    asked.append(name)
                    e = requests.ConnectionError("Failed to resolve (NameResolutionError at "
                                                 f"0x{len(asked):x})")
                    if host:
                        e.request = requests.Request("GET", f"https://{host}/x").prepare()
                    raise e
                return fail
        self.core.api = Down()
        return real, asked

    def test_one_failure_stops_the_round_and_is_said_once(self):
        core = self.core
        real, asked = self._cut()
        core._loop_round()
        first = len(asked)
        self.assertLessEqual(first, 2, asked)  # not each source in turn
        self.assertEqual(len(self.errors), 1, self.errors)
        self.assertIn("No connection", self.errors[0])
        self.assertEqual(core.poll_state()["failing"], 1)
        core._loop_round()
        core._loop_round()
        self.assertEqual(len(self.errors), 1, "said once an outage")
        self.assertGreater(core.backoff(), 0)  # the rounds wait longer
        core.api = real  # back
        core._loop_round()
        self.assertEqual(core.poll_state()["failing"], 0)
        self.assertEqual(core.backoff(), 0)
        self.assertIsNone(core._offline_since)

    def test_another_servers_failure_stops_nothing(self):
        """An RSS site or another server's lane out of reach: that source fails, said,
        the round goes on."""
        self.assertFalse(self.core._cut_off(ValueError("x")))
        e = requests.ConnectionError("refused")
        e.request = requests.Request("GET", "https://elsewhere.example/feed").prepare()
        self.assertFalse(self.core._cut_off(e))
        e.request = requests.Request("GET", "https://example.test/api").prepare()
        self.assertTrue(self.core._cut_off(e))

    def test_the_same_failure_is_not_told_apart_by_an_address(self):
        core = self.core
        core.emit("error", "home: Failed (NameResolutionError at 0x7f9a42c35950)")
        core.emit("error", "home: Failed (NameResolutionError at 0x7f9a42c356d0)")
        self.assertEqual(len(self.errors), 1)
