"""The connection to someone else's server goes to the address that was checked
(core/remote.py Adapter): no DNS rebinding a post's picture into the home network."""

import http.server
import socket
import threading
import unittest
from unittest import mock

import requests

from fedtail.core import remote


class _Seen(http.server.BaseHTTPRequestHandler):
    hosts = []

    def do_GET(self):  # noqa: N802 — http.server's name
        _Seen.hosts.append(self.headers.get("Host"))
        body = b"picture"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_a):
        pass


class PinnedTest(unittest.TestCase):
    def setUp(self):
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Seen)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.port = self.srv.server_address[1]
        _Seen.hosts = []
        self.real = socket.getaddrinfo

    def answers(self, *addrs):
        """getaddrinfo for pics.example: these addresses, one per lookup, the last kept."""
        left = list(addrs)

        def fake(host, port, *a, **k):
            if host != "pics.example":
                return self.real(host, port, *a, **k)
            addr = left.pop(0) if len(left) > 1 else left[0]
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (addr, port))]
        return mock.patch("socket.getaddrinfo", fake)

    def test_rebinding_after_the_check_is_refused(self):
        """The check hears a public address, the connection a moment later 127.0.0.1:
        refused at the connection — the name is resolved once, there."""
        with self.answers("93.184.216.34", "127.0.0.1"), \
                self.assertRaises(requests.RequestException) as e:
            remote.open_url(requests.Session(), f"http://pics.example:{self.port}/a.png",
                            timeout=5, schemes=("http",))
        self.assertIn("not a public address", str(e.exception))
        self.assertEqual(_Seen.hosts, [])  # nothing reached the machine

    def test_the_checked_address_is_the_one_connected_to(self):
        """A name checked public (here: this machine, let through) is connected to at
        that address, the name kept for the Host header (and a certificate)."""
        with self.answers("127.0.0.1"), mock.patch.object(remote, "_public_ip",
                                                           lambda _a: True):
            s = requests.Session()
            with remote.open_url(s, f"http://pics.example:{self.port}/a.png", timeout=5,
                                 schemes=("http",)) as r:
                self.assertEqual(remote.read(r, 1024), b"picture")
            self.assertIsInstance(s.get_adapter("https://x"), remote.Adapter)  # kept on it
        self.assertEqual(_Seen.hosts, [f"pics.example:{self.port}"])

    def test_own_hosts_and_literals(self):
        own = {"home.lan"}
        self.assertIsNone(remote._addresses("home.lan", 443, own))  # the user's: as is
        with self.assertRaises(remote.Refused):
            remote._addresses("127.0.0.1", 80, set())
        with self.assertRaises(remote.Refused):
            remote._addresses("[::1]", 80, set())
        self.assertEqual(remote._addresses("93.184.216.34", 80, set()), ["93.184.216.34"])
        with self.assertRaises(remote.Refused):
            remote._addresses("router.local", 80, set())
        self.assertIs(remote.pinned(requests), remote.pinned(requests))  # the module: ours


if __name__ == "__main__":
    unittest.main()
