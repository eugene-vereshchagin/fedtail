"""A network failure in words (core/neterr.py), and the sync server's errors saying them:
a typo in the address ("no such name") must not come out as a bare "ConnectionError"."""

import socket
import unittest
from unittest import mock

import requests

from fedtail import i18n
from fedtail.core import neterr
from fedtail.core.sync.backends import BackendError, HttpBackend


def _wrapped(cls, inner, text):
    """As requests raises it: its error, raised from urllib3's, raised from the socket's."""
    try:
        try:
            raise inner
        except Exception as e:
            raise cls(text) from e
    except cls as e:
        return e


class KindTest(unittest.TestCase):
    def test_each_kind(self):
        no_name = _wrapped(requests.ConnectionError, socket.gaierror(
            -2, "Name or service not known"),
            "HTTPSConnectionPool(host='fedsync.gmesg.online', port=443): Max retries exceeded "
            "(Caused by NameResolutionError(\"Failed to resolve 'fedsync.gmesg.online'\"))")
        self.assertEqual(neterr.kind(no_name), "no_name")
        refused = _wrapped(requests.ConnectionError, ConnectionRefusedError(
            111, "Connection refused"), "Max retries exceeded")
        self.assertEqual(neterr.kind(refused), "refused")
        self.assertEqual(neterr.kind(requests.ConnectTimeout("x")), "timeout")
        self.assertEqual(neterr.kind(requests.ReadTimeout("x")), "timeout")
        self.assertEqual(neterr.kind(requests.exceptions.SSLError("bad cert")), "tls")
        self.assertEqual(neterr.kind(requests.ConnectionError("read timed out")), "timeout")
        self.assertEqual(neterr.kind(requests.ConnectionError("reset by peer")), "down")
        self.assertEqual(neterr.kind(OSError("Network is unreachable")), "down")
        self.assertEqual(neterr.kind(ValueError("not the network")), "")

    def test_words_name_the_host_in_both_languages(self):
        for lang in ("ru", "en"):
            i18n.setup(lang)
            for k in ("no_name", "refused", "timeout", "tls", "down"):
                got = i18n._("net_" + k, host="h.example")
                self.assertIn("h.example", got, (lang, k))
                self.assertNotEqual(got, "net_" + k)
        i18n.setup("en")
        self.assertIn("a typo", neterr.words(_wrapped(
            requests.ConnectionError, socket.gaierror(-2, "Name or service not known"),
            "x"), "fedsync.gmesg.online"))
        self.assertIn("cannot reach", neterr.words(ValueError("?"), "h"))


class SyncServerSaysItTest(unittest.TestCase):
    def test_a_typo_in_the_address(self):
        i18n.setup("en")
        s = mock.Mock(headers={})
        err = _wrapped(requests.ConnectionError, socket.gaierror(
            -2, "Name or service not known"), "NameResolutionError")
        s.get.side_effect = err
        s.post.side_effect = err
        b = HttpBackend("https://fedsync.gmesg.online/", "https://me.example", "t", session=s)
        for call in (lambda: b.pull("", "d1"), lambda: b.push(b"x", "d1")):
            with self.assertRaises(BackendError) as got:
                call()
            text = str(got.exception)
            self.assertIn('cannot find the server "fedsync.gmesg.online"', text)
            self.assertNotIn("ConnectionError", text)
            self.assertEqual(got.exception.kind, "other")


if __name__ == "__main__":
    unittest.main()
