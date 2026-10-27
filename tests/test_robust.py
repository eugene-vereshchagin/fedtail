"""What the network may throw at fedtail (docs/*/dev/robustness.md): a page that isn't
JSON (a captive portal), an answer too big to read, rounds failing again and again."""

import io
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
