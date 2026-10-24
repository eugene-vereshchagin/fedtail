"""Sync (core/sync) when things go wrong: a server that refuses, is full, is gone or
answers nonsense; a folder half-synced; a blob that isn't ours; the cryptography
package missing; another device's batch that names a thread or lanes this one can't
apply — each leaves the window working and says what happened."""

import json
import sys
import unittest
from unittest import mock

import requests

from fedtail.core.sync import backends, crypto, engine

from .test_sync import Devices, need_crypto


class Resp:
    def __init__(self, status=200, body=None):
        self.status_code = status
        self._body = body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


class Session:
    def __init__(self, answer):
        self.headers = {}
        self.answer = answer

    def _go(self, *_a, **_k):
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    post = get = _go


class HttpBackendTest(unittest.TestCase):
    def backend(self, answer):
        return backends.HttpBackend("https://sync.test/", "me@x.test", "T",
                                    session=Session(answer))

    def test_answers_become_kinds(self):
        for status, kind in ((401, "auth"), (403, "auth"), (413, "full"), (507, "full"),
                             (404, "gone"), (500, "other")):
            with self.assertRaises(backends.BackendError) as e:
                self.backend(Resp(status)).push(b"x", "dev")
            self.assertEqual(e.exception.kind, kind, status)

    def test_network_and_nonsense(self):
        for call in (lambda b: b.push(b"x", "dev"), lambda b: b.pull(0, "dev")):
            with self.assertRaisesRegex(backends.BackendError, "ConnectionError"):
                call(self.backend(requests.ConnectionError("down")))
        for body in (ValueError("not json"), {"no": "blobs"}, {"blobs": [{"seq": "x"}]}):
            with self.assertRaisesRegex(backends.BackendError, "not understood"):
                self.backend(Resp(200, body)).pull(None, "dev")
        got = self.backend(Resp(200, {"blobs": [], "last": 7, "more": False})).pull("3", "d")
        self.assertEqual(got, ([], 7, False))


class FolderBackendTest(unittest.TestCase):
    def test_gone_and_half_synced(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            gone = backends.FolderBackend(Path(d) / "nowhere")
            with self.assertRaises(backends.BackendError) as e:
                gone.push(b"x", "aaaaaaaa")
            self.assertEqual(e.exception.kind, "gone")
            f = backends.FolderBackend(d)
            other = Path(d) / "bbbbbbbb"
            other.mkdir()
            (other / "000000000001.fts").write_bytes(b"one")
            (other / "000000000002.fts").mkdir()  # still arriving: can't be read
            (other / "000000000003.fts").write_bytes(b"three")
            blobs, cursor, more = f.pull(None, "aaaaaaaa")
            self.assertEqual((blobs, cursor, more), ([b"one"], {"bbbbbbbb": 1}, False))


@need_crypto
class CryptoTest(unittest.TestCase):
    def test_without_the_package(self):
        with mock.patch.dict(sys.modules, {"cryptography.hazmat.primitives.ciphers.aead":
                                           None}):
            self.assertFalse(crypto.available())
            with self.assertRaises(crypto.CryptoMissing):
                crypto.seal(crypto.new_key(), {})
        key = crypto.new_key()
        blob = crypto.seal(key, {"a": 1})
        with mock.patch.dict(sys.modules, {"cryptography.exceptions": None}):
            with self.assertRaises(crypto.CryptoMissing):
                crypto.unseal(key, blob)

    def test_bad_text_too_big_and_a_broken_key_file(self):
        with self.assertRaisesRegex(ValueError, "not a sync key"):
            crypto.key_from_text("1111-1111")  # not base32 at all
        key = crypto.new_key()
        with self.assertRaisesRegex(crypto.BadBlob, "too big"):
            crypto.unseal(key, crypto.seal(key, {"x": "a" * (crypto.MAX_PLAIN + 10)}))
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "sync.key"
            f.write_text("{not json", "utf-8")
            self.assertIsNone(crypto.load_key(f))
            f.write_text(json.dumps({"key": "short"}), "utf-8")
            self.assertIsNone(crypto.load_key(f))


@need_crypto
class EngineTest(Devices):
    def sync(self, core):
        return core.sync

    def test_nothing_recorded_for_what_is_off(self):
        s = self.sync(self.desk)
        s.what = set()
        s.record_draft("reply:1")
        s.record_activity([("1", "s", "")])
        s.record_thread("r", "sub")
        self.assertEqual(self.desk.store.sync_pending(10), [])
        s.what = set(engine.WHAT)
        s.record_activity([("", "s", "")])  # nothing with an id: nothing recorded
        s.record_thread("r", "nonsense")
        self.assertEqual(self.desk.store.sync_pending(10), [])

    def test_a_draft_of_pictures_only_doesnt_travel(self):
        s = self.sync(self.desk)
        self.desk.store.save_draft("new", {"text": "", "media": [["/a.png", ""]]})
        s.record_draft("new")
        s._flush_drafts()
        self.assertEqual(self.desk.store.sync_pending(10), [])

    def test_the_thread_starts_once_and_stops(self):
        s = self.sync(self.desk)
        with mock.patch.object(s, "step") as step:
            s.start()
            first = s._thread
            s.start()
            self.assertIs(s._thread, first)
            s.stop()
        self.assertFalse(first.is_alive())
        self.assertEqual(step.call_args_list[-1], mock.call(pull=False))

    def test_a_failing_round_is_logged_not_raised(self):
        s = self.sync(self.desk)
        with mock.patch.object(s, "step", side_effect=RuntimeError("boom")), \
                self.assertLogs("fedtail.core.sync.engine", "ERROR"):
            s._round()

    def test_backend_troubles_are_told_once(self):
        s = self.sync(self.desk)
        for kind, words in (("auth", "refused"), ("full", "quota"), ("other", "boom")):
            bad = mock.Mock(where="x", pull=mock.Mock(
                side_effect=backends.BackendError(kind, "boom")))
            with mock.patch.object(s, "backend", return_value=bad), \
                    mock.patch.object(crypto, "load_key", return_value=None):
                self.assertIsNone(s.step())
            self.assertIn(words, self.desk.sync_status()["last"]["error"].lower())
        errors = [p for n, p in self.desk.events_seen if n == "error"]
        self.assertEqual(len(errors), 3)
        with mock.patch.object(crypto, "load_key", return_value=None), \
                mock.patch.object(crypto, "available", return_value=False):
            self.assertIsNone(s.step())
        self.assertIn("cryptography", self.desk.sync_status()["last"]["error"])

    def test_a_server_needs_a_login_first(self):
        s = self.sync(self.desk)
        s.cfg = dict(s.cfg, folder="", url="https://sync.test")
        self.assertEqual(s.kind(), "server")
        self.assertIsNone(s.backend())
        self.assertIsNone(s.step())  # a round without a backend: nothing done
        self.assertIn("log", self.desk.sync_status()["last"]["error"].lower())
        (self.desk.paths.data_dir / "sync_auth.json").write_text(
            json.dumps({"instance": "me@x.test", "token": "T"}), "utf-8")
        b = s.backend()
        self.assertIsInstance(b, backends.HttpBackend)
        self.assertEqual(b.url, "https://sync.test")

    def test_a_blob_that_isnt_ours_is_skipped(self):
        self.desk.mark_read(["1"])
        self.desk.sync_now()
        self.phone.sync_join(self.desk.sync_key())
        junk = self.tmp / "meet" / "cccccccc"
        junk.mkdir()
        (junk / "000000000001.fts").write_bytes(b"not a blob at all")
        with self.assertLogs("fedtail.core.sync.engine", "WARNING"):
            self.assertEqual(self.phone.sync_now(), (0, 1))

    def test_a_batch_with_what_cant_be_applied(self):
        s = self.sync(self.phone)
        with mock.patch.object(self.phone, "apply_thread_state",
                               side_effect=RuntimeError("gone")), \
                mock.patch.object(self.phone, "apply_lanes_state",
                                  side_effect=RuntimeError("bad")), \
                self.assertLogs("fedtail.core.sync.engine", "WARNING") as logs:
            n = s.apply({"d": "other", "ops": [
                "not an op", {"t": "root", "s": "sub", "at": 5},
                {"k": "list_order", "v": ["a"], "at": 5}]})
        self.assertEqual(n, 2)  # the thread and the lanes: the junk op is no op
        self.assertEqual(len(logs.output), 2)


if __name__ == "__main__":
    unittest.main()
