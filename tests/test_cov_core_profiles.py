"""Profiles (core/profiles.py) and the one-window-per-profile lock (core/instance.py): the
card of a profile, starting another fedtail (and the relaunch helper waiting for this
one to go), and the Windows named-pipe lock — run here over a unix socket in its place."""

import json
import multiprocessing.connection as mpc
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from fedtail.core import instance, paths, profiles


class ProfilesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        p = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.tmp / "c"),
                                         "XDG_DATA_HOME": str(self.tmp / "d")})
        p.start()
        self.addCleanup(p.stop)

    def test_card_that_cant_be_written_and_one_that_is_not_a_card(self):
        w = paths.resolve("one")
        w.ensure()
        (w.data_dir / profiles.CARD).mkdir()  # a folder where the card goes
        with self.assertLogs("fedtail.core.profiles", "WARNING"):
            profiles.remember(w, {"acct": "a"}, "https://x.test")
        other = paths.resolve("two")
        other.ensure()
        other.config_file.write_text("[ui]\n", "utf-8")
        (other.data_dir / profiles.CARD).write_text(json.dumps(["not", "a", "card"]), "utf-8")
        got = {p["name"]: p for p in profiles.listing()}
        self.assertEqual(got["two"]["acct"], "")

    def test_command(self):
        with mock.patch.object(sys, "frozen", True, create=True):
            self.assertEqual(profiles.command("w"), ([sys.executable, "--profile", "w"], None))
        argv, cwd = profiles.command("w")
        self.assertEqual(argv[1:], ["-m", "fedtail", "--profile", "w"])
        with mock.patch.object(Path, "exists", return_value=False):
            self.assertEqual(profiles.command("w")[1], None)  # installed: no checkout

    def test_launch(self):
        with mock.patch.object(profiles.subprocess, "Popen") as popen:
            profiles.RUN_FLAGS[:] = ["--ui", "tui"]
            self.addCleanup(profiles.RUN_FLAGS.clear)
            profiles.launch("w")
            argv = popen.call_args[0][0]
            self.assertEqual(argv[-2:], ["--ui", "tui"])
            self.assertTrue(popen.call_args[1]["start_new_session"])
            with mock.patch.object(profiles.paths, "WINDOWS", True):
                profiles.launch("w", after=0.5, wait_for=123)
            argv = popen.call_args[0][0]
            self.assertEqual(argv[:2], [sys.executable, "-c"])
            self.assertIn("pid, after, argv, cwd = 123, 0.5", argv[2])
            self.assertEqual(popen.call_args[1]["creationflags"], 0x00000208)

    def test_the_relaunch_helper_waits_for_the_old_process(self):
        """The helper itself, run for real: it starts the program once the process it
        waits for has gone."""
        mark = self.tmp / "started"
        sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.6)"])
        argv = [sys.executable, "-c", f"open({str(mark)!r}, 'w').write(str(__import__("
                                      "'time').time()))"]
        code = profiles._RELAUNCH.format(pid=sleeper.pid, after=0.0, argv=argv,
                                         cwd=str(self.tmp))
        t0 = time.time()
        helper = subprocess.Popen([sys.executable, "-c", code])
        sleeper.wait()
        gone = time.time()
        helper.wait(timeout=30)
        for _ in range(100):
            if mark.exists() and mark.read_text():
                break
            time.sleep(0.05)
        self.assertGreaterEqual(float(mark.read_text()), gone - 0.2)
        self.assertGreater(gone - t0, 0.3)


class _UnixPipes:
    """multiprocessing.connection with AF_PIPE turned into AF_UNIX at the same name:
    the Windows code path, on a unix socket."""

    def __init__(self, folder):
        self.folder = folder
        self._listener, self._client = mpc.Listener, mpc.Client  # the real ones

    def where(self, name):
        return str(self.folder / name.rsplit("-", 1)[-1])

    def listener(self, name, family, authkey):
        return self._listener(self.where(name), family="AF_UNIX", authkey=authkey)

    def client(self, name, family, authkey):
        return self._client(self.where(name), family="AF_UNIX", authkey=authkey)


class InstanceTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_pipe_key(self):
        sock = self.tmp / "instance.sock"
        self.assertIsNone(instance._pipe_key(sock))  # none yet, and not asked to make it
        key = instance._pipe_key(sock, make=True)
        self.assertEqual(len(key), 32)
        self.assertEqual(instance._pipe_key(sock), key)
        if os.name != "nt":  # Windows has no such modes: the profile's folder is the user's
            self.assertEqual((self.tmp / "instance.key").stat().st_mode & 0o777, 0o600)
        self.assertIsNone(instance._pipe_key(self.tmp / "missing" / "x.sock", make=True))

    def test_the_windows_pipe(self):
        pipes = _UnixPipes(self.tmp)
        with mock.patch.object(instance, "WINDOWS", True), \
                mock.patch.object(mpc, "Listener", pipes.listener), \
                mock.patch.object(mpc, "Client", pipes.client):
            first = instance.SingleInstance(self.tmp / "instance.sock")
            got = []
            first.listen(got.append)
            second = instance.SingleInstance(self.tmp / "instance.sock")
            self.assertTrue(second.poke_existing("open https://x.test/1"))
            for _ in range(100):
                if got:
                    break
                time.sleep(0.02)
            self.assertEqual(got, ["open https://x.test/1"])
            # a stranger without the key is turned away, and the window goes on listening
            stranger = threading.Thread(target=lambda: self._wrong_key(pipes))
            stranger.start()
            stranger.join(5)
            self.assertTrue(second.poke_existing())
            for _ in range(100):
                if len(got) == 2:
                    break
                time.sleep(0.02)
            self.assertEqual(got[-1], "raise")
            first.close()
            first.close()  # twice is fine
            self.assertFalse(second.poke_existing())

    def _wrong_key(self, pipes):
        try:
            pipes.client(instance._pipe_name(str(self.tmp / "instance.sock")), "AF_PIPE",
                         b"x" * 32).send_bytes(b"open evil")
        except (OSError, EOFError, mpc.AuthenticationError):
            pass

    def test_the_pipe_loop_ends_when_closed_while_waiting(self):
        si = instance.SingleInstance(self.tmp / "s.sock")

        def closed_meanwhile():
            si.listener = None  # close() ran while accept() waited
            raise OSError("closed")
        si.listener = mock.Mock(accept=mock.Mock(side_effect=closed_meanwhile))
        si._pipe_loop()  # returns instead of spinning
        self.assertIsNone(si.listener)

    def test_a_pipe_listener_that_fails_to_close(self):
        si = instance.SingleInstance(self.tmp / "s.sock")
        si.listener = mock.Mock(close=mock.Mock(side_effect=OSError("busy")))
        si.close()
        self.assertIsNone(si.listener)

    def test_socket_loop_over_bad_connections(self):
        si = instance.SingleInstance(self.tmp / "s.sock")
        got = []
        si.on_message = got.append
        conn = mock.MagicMock()
        conn.__enter__.return_value = conn
        conn.recv.side_effect = OSError("reset")
        si.sock = mock.Mock(accept=mock.Mock(side_effect=[(conn, None), OSError("closed")]))
        si._loop()  # a broken connection is skipped, a closed socket ends the loop
        self.assertEqual(got, [])
        si.sock = mock.Mock()
        si.close()  # the socket file never made: nothing to remove
        self.assertIsNone(si.sock)

    def test_a_real_socket_with_nothing_said(self):
        si = instance.SingleInstance(self.tmp / "s.sock")
        got = []
        si.listen(got.append)
        self.addCleanup(si.close)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(str(self.tmp / "s.sock"))
        s.close()  # connected and said nothing: no message
        self.assertTrue(instance.SingleInstance(self.tmp / "s.sock").poke_existing("hi"))
        for _ in range(100):
            if got:
                break
            time.sleep(0.02)
        self.assertEqual(got, ["hi"])


if __name__ == "__main__":
    unittest.main()
