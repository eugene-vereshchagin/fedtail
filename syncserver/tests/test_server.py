"""fedtail-sync doing its job: whose journal is whose, the limits an honest client meets,
the token check, old journals going, the config and the program itself."""

import http.client
import io
import json
import logging
import socket
import threading
import time
import unittest
from contextlib import redirect_stdout
from unittest import mock

from .live import Live, Tmp


class JournalTest(Live):
    def setUp(self):
        super().setUp()
        self.start(quota_mb=1, max_blob_kb=64)

    def test_whose_journal_is_whose(self):
        self.assertEqual(self.call("GET", "/v1"), (200, {"fedtail-sync": 1}))
        self.assertEqual(self.call("GET", "/v1/"), (200, {"fedtail-sync": 1}))
        self.assertEqual(self.call("GET", "/.well-known/fedtail-sync")[0], 404)  # gone
        self.assertEqual(self.call("POST", "/v1/blobs", "t-me", b"one",
                                   {"X-Fedtail-Device": "d1"}), (200, {"seq": 1}))
        self.assertEqual(self.call("POST", "/v1/blobs", "t-me2", b"two",
                                   {"X-Fedtail-Device": "d2"})[0], 200)
        self.assertEqual(self.call("POST", "/v1/blobs", "t-you", b"theirs")[0], 200)
        code, got = self.call("GET", "/v1/blobs?after=0&exclude=d1", "t-me")
        self.assertEqual(code, 200)
        self.assertEqual([b["device"] for b in got["blobs"]], ["d2"])  # not d1, not you
        self.assertEqual(got["last"], 2)
        self.assertEqual(self.call("GET", "/v1/blobs?after=2", "t-me")[1]["blobs"], [])
        self.assertEqual(self.call("DELETE", "/v1/blobs", "t-me"), (200, {"deleted": 2}))
        self.assertEqual(len(self.call("GET", "/v1/blobs", "t-you")[1]["blobs"]), 1)

    def test_pages(self):
        for i in range(5):
            self.call("POST", "/v1/blobs", "t-me", f"b{i}".encode(), {"X-Fedtail-Device": "a"})
        code, got = self.call("GET", "/v1/blobs?after=0&limit=2", "t-me")
        self.assertEqual((len(got["blobs"]), got["last"], got["more"]), (2, 2, True))
        got = self.call("GET", "/v1/blobs?after=4&limit=0", "t-me")[1]  # at least one
        self.assertEqual((len(got["blobs"]), got["more"]), (1, False))
        # the asker's own blobs aren't sent, but the cursor moves past them
        got = self.call("GET", "/v1/blobs?after=0&exclude=a", "t-me")[1]
        self.assertEqual((got["blobs"], got["last"]), ([], 5))

    def test_strangers_refused(self):
        self.assertEqual(self.call("GET", "/v1/blobs")[0], 401)
        self.assertEqual(self.call("GET", "/v1/blobs", "nope")[0], 401)
        self.assertEqual(self.call("GET", "/v1/blobs", "t-me",
                                   instance="https://else.example")[0], 403)
        self.assertEqual(self.call("GET", "/v1/blobs", "t-me",
                                   instance="http://me.example")[0], 401)  # not https
        self.assertEqual(self.call("GET", "/v1/blobs", headers={
            "Authorization": "Basic dDp0", "X-Fedtail-Instance": "me.example"})[0], 401)

    def test_the_quota_and_the_size(self):
        self.assertEqual(self.call("POST", "/v1/blobs", "t-me", b"x" * 70 * 1024)[0], 413)
        for _ in range(17):
            self.call("POST", "/v1/blobs", "t-me", b"x" * 60 * 1024)
        self.assertEqual(self.call("POST", "/v1/blobs", "t-me", b"x" * 60 * 1024)[0], 507)
        self.assertEqual(self.call("POST", "/v1/blobs", "t-you", b"x" * 60 * 1024)[0], 200)

    def test_put_checks_on_its_own_too(self):
        with self.assertRaises(self.mod.Refused) as e:
            self.app.put("1@me.example", "d", b"")
        self.assertEqual(e.exception.status, 400)
        with self.assertRaises(self.mod.Refused) as e:
            self.app.put("1@me.example", "d", b"x" * 65 * 1024)
        self.assertEqual(e.exception.status, 413)

    def test_an_empty_body_is_refused(self):
        self.assertEqual(self.call("POST", "/v1/blobs", "t-me", b"")[0], 400)

    def test_a_body_cut_short_by_the_client(self):
        out = self.raw(b"POST /v1/blobs HTTP/1.1\r\nAuthorization: Bearer t-me\r\n"
                       b"X-Fedtail-Instance: me.example\r\nContent-Length: 100\r\n\r\nabc",
                       half_close=True)
        self.assertIn(b" 400 ", out)
        self.assertIn(b"shorter than promised", out)

    def test_other_methods_arent_served(self):
        self.assertEqual(self.call("PUT", "/v1/blobs", "t-me", b"x")[0], 501)


class AccountLimitTest(Live):
    def test_one_account_has_its_limit_whatever_its_addresses(self):
        self.start(requests_per_minute=3, client_ip_header="X-Real-IP")
        codes = [self.call("GET", "/v1/blobs", "t-me",
                           headers={"X-Real-IP": f"198.51.100.{i}"})[0] for i in range(5)]
        self.assertEqual(codes, [200, 200, 200, 429, 429])
        self.assertEqual(self.call("GET", "/v1/blobs", "t-you")[0], 200)  # others aren't

    def test_a_zero_limit_is_no_limit(self):
        w = self.mod.Window(0)
        self.assertTrue(all(w.hit("k") for _ in range(1000)))
        self.assertEqual(w.counts, {})

    def test_the_minute_passes(self):
        w = self.mod.Window(1)
        with mock.patch.object(self.mod.time, "monotonic", return_value=1000.0):
            self.assertEqual([w.hit("k"), w.hit("k")], [True, False])
        with mock.patch.object(self.mod.time, "monotonic", return_value=1061.0):
            self.assertTrue(w.hit("k"))


class TokenCacheTest(Live):
    def test_known_and_refused_tokens_are_remembered(self):
        self.start()
        for _ in range(3):
            self.call("GET", "/v1/blobs", "t-me")
            self.call("GET", "/v1/blobs", "bad")
        self.assertEqual(sorted(self.calls), ["bad", "t-me"])
        # a token is believed for TOKEN_TTL; after it, asked again
        later = time.monotonic() + self.mod.TOKEN_TTL + 1
        with mock.patch.object(self.mod.time, "monotonic", return_value=later):
            self.call("GET", "/v1/blobs", "t-me")
        self.assertEqual(self.calls.count("t-me"), 2)

    def test_the_cache_is_pruned(self):
        self.start()
        gone = time.monotonic() - 1
        self.app._tokens = {f"h{i}": (None, gone) for i in range(10_001)}
        self.call("GET", "/v1/blobs", "t-me")
        self.assertEqual(len(self.app._tokens), 1)

    def test_the_real_check_is_asked_of_the_named_server(self):
        app = self.mod.Server({"db": ":memory:", "instances": ["me.example"]})
        self.addCleanup(app.db.close)
        with mock.patch.object(self.mod.Server, "fetch_account", return_value="7") as f:
            self.assertEqual(app._verify_at_instance("me.example", "tok"), "7")
        f.assert_called_once_with("https://me.example/api/v1/accounts/verify_credentials",
                                  "tok", public_only=False)
        star = self.mod.Server({"db": ":memory:", "instances": ["*"]})
        self.addCleanup(star.db.close)
        with mock.patch.object(self.mod.Server, "fetch_account", return_value="7") as f:
            star._verify_at_instance("x.example", "tok")
        self.assertTrue(f.call_args.kwargs["public_only"])  # "*": public addresses only


class FetchAccountTest(Tmp):
    """Server.fetch_account against small servers on localhost."""

    def serve(self, status, body=b"", raw=None):
        """One answer, then gone. → the URL to ask."""
        srv = socket.create_server(("127.0.0.1", 0))
        self.addCleanup(srv.close)

        def answer():
            conn, _ = srv.accept()
            conn.recv(65536)
            if raw is not None:
                conn.sendall(raw)
            else:
                conn.sendall(f"HTTP/1.1 {status} X\r\nContent-Length: {len(body)}\r\n"
                             f"Connection: close\r\n\r\n".encode() + body)
            conn.close()
        threading.Thread(target=answer, daemon=True).start()
        return f"http://127.0.0.1:{srv.getsockname()[1]}/api/v1/accounts/verify_credentials"

    def test_who(self):
        self.assertEqual(self.mod.Server.fetch_account(self.serve(200, b'{"id": 5}'), "t"), "5")
        self.assertIsNone(self.mod.Server.fetch_account(self.serve(200, b'["x"]'), "t"))
        self.assertIsNone(self.mod.Server.fetch_account(self.serve(200, b'{"id": ""}'), "t"))

    def test_refused_tokens_and_broken_servers(self):
        self.assertIsNone(self.mod.Server.fetch_account(self.serve(401), "t"))
        self.assertIsNone(self.mod.Server.fetch_account(self.serve(403), "t"))
        for url in (self.serve(500), self.serve(200, b"not json"),
                    self.serve(0, raw=b"garbage\r\n\r\n")):
            with self.assertRaises(self.mod.Refused) as e:
                self.mod.Server.fetch_account(url, "t")
            self.assertEqual(e.exception.status, 502)

    def test_nobody_there(self):
        s = socket.create_server(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        with self.assertRaises(self.mod.Refused):
            self.mod.Server.fetch_account(f"http://127.0.0.1:{port}/x", "t")

    def test_only_web_addresses(self):
        for url in ("file:///etc/passwd", "ftp://x.example/", "data:,{}"):
            with self.assertRaises(self.mod.Refused):
                self.mod.Server.fetch_account(url, "t")

    def test_https_public_only_goes_through_its_own_connection(self):
        """The public-only opener is the one used for https:// with "*" (a TLS handshake
        with something that isn't TLS fails: what matters is that it gets that far)."""
        srv = socket.create_server(("127.0.0.1", 0))
        self.addCleanup(srv.close)
        threading.Thread(target=lambda: srv.accept()[0].close(), daemon=True).start()
        made = []
        real = self.mod._PublicOnlyHTTPS

        class Spy(real):
            def __init__(self, *a, **k):
                made.append(a)
                super().__init__(*a, **k)
        with mock.patch.object(self.mod, "_PublicOnlyHTTPS", Spy):
            with self.assertRaises(self.mod.Refused):
                self.mod.Server.fetch_account(
                    f"https://127.0.0.1:{srv.getsockname()[1]}/x", "t", public_only=True)
        self.assertTrue(made)


class NamesTest(Tmp):
    def test_hosts(self):
        h = self.mod.host_of
        self.assertEqual(h("https://X.Example/"), "x.example")
        self.assertEqual(h("social.example:8443"), "social.example:8443")
        self.assertIsNone(h(None))
        self.assertIsNone(h("https://x.example/path"))

    def test_public_addresses(self):
        self.assertFalse(self.mod.is_public_ip("not an address"))
        self.assertTrue(self.mod.is_public_ip("2606:4700:4700::1111"))
        with mock.patch.object(self.mod.socket, "getaddrinfo", side_effect=OSError("no dns")):
            self.assertFalse(self.mod.public_host("x.example"))
        with mock.patch.object(self.mod.socket, "getaddrinfo", return_value=[]):
            self.assertFalse(self.mod.public_host("x.example"))
        info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443)),
                (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 443))]
        with mock.patch.object(self.mod.socket, "getaddrinfo", return_value=info):
            self.assertFalse(self.mod.public_host("half.example:443"))  # one is LAN
        with mock.patch.object(self.mod.socket, "getaddrinfo", return_value=info[:1]):
            self.assertTrue(self.mod.public_host("x.example"))

    def test_the_real_address(self):
        r = self.mod.real_ip
        self.assertEqual(r("127.0.0.1", "203.0.113.9"), "203.0.113.9")
        self.assertEqual(r("::1", " 2001:db8::1 "), "2001:db8::1")
        self.assertEqual(r("203.0.113.5", "198.51.100.1"), "203.0.113.5")  # not from a proxy
        self.assertEqual(r("127.0.0.1", "nonsense"), "127.0.0.1")
        self.assertEqual(r("127.0.0.1", None), "127.0.0.1")
        self.assertEqual(r("/run/sync.sock", "198.51.100.1"), "/run/sync.sock")  # no IP


class ExpireTest(Tmp):
    def test_old_journals_go_and_the_count_follows(self):
        app = self.mod.Server({"db": str(self.tmp / "s.db"), "instances": [], "keep_days": 7})
        self.addCleanup(app.db.close)
        app.put("1@x", "a", b"old" * 100)
        app.put("1@x", "a", b"new")
        app.put("2@x", "b", b"old too")
        app.db.execute("UPDATE blobs SET at = ? WHERE data != ?",
                       (int(time.time()) - 8 * 86400, b"new"))
        with self.assertLogs("fedtail-sync", "INFO") as logs:
            app.expire()
        self.assertIn("expired 2", logs.output[0])
        self.assertEqual(app.db.execute("SELECT data FROM blobs").fetchall(), [(b"new",)])
        self.assertEqual((app.used, app.total), ({"1@x": 3}, 3))
        app.expire()  # nothing old: nothing said
        keep = self.mod.Server({"db": str(self.tmp / "s.db"), "instances": []})
        self.addCleanup(keep.db.close)
        keep.expire()  # keep_days = 0: kept for ever
        self.assertEqual(keep.total, 3)


class PlumbingTest(Live):
    def test_a_thread_that_wont_start_gives_its_slot_back(self):
        self.start(max_connections=1)
        a, b = socket.socketpair()
        self.addCleanup(a.close)
        self.addCleanup(b.close)
        with mock.patch("socketserver.ThreadingMixIn.process_request",
                        side_effect=RuntimeError("no threads left")):
            with self.assertRaises(RuntimeError):
                self.httpd.process_request(a, ("127.0.0.1", 1))
        self.assertTrue(self.httpd.slots.acquire(blocking=False))  # the one slot is free
        self.httpd.slots.release()

    def test_cut_never_fails(self):
        s = socket.socket()
        s.close()
        self.mod.cut(s)  # closed already: nothing to do, nothing raised
        a, b = socket.socketpair()
        self.mod.cut(a)
        self.assertEqual(b.recv(1), b"")
        a.close()
        b.close()

    def test_a_dropped_client_is_one_quiet_line(self):
        self.start()
        with self.assertLogs("fedtail-sync", "DEBUG") as logs:
            try:
                raise ConnectionResetError
            except ConnectionResetError:
                self.httpd.handle_error(None, ("198.51.100.4", 5))
        self.assertIn("198.51.100.4: connection error", logs.output[0])

    def test_listening_beyond_this_machine_is_warned_about(self):
        app = self.mod.Server({"db": ":memory:", "instances": [], "listen": "0.0.0.0:0"})
        self.addCleanup(app.db.close)
        with self.assertLogs("fedtail-sync", "WARNING") as logs:
            srv = self.mod.make_http_server(app)
        srv.server_close()
        self.assertIn("plain HTTP", logs.output[0])
        named = self.mod.Server({"db": ":memory:", "instances": [], "listen": "localhost:0"})
        self.addCleanup(named.db.close)
        self.mod.make_http_server(named).server_close()  # a name: nothing to judge

    @unittest.skipUnless(socket.has_ipv6, "no IPv6 here")
    def test_ipv6(self):
        try:
            self.start(listen="[::1]:0")
        except OSError:
            self.skipTest("::1 can't be bound here")
        c = http.client.HTTPConnection("::1", self.port, timeout=5)
        c.request("GET", "/v1")
        self.assertEqual(json.loads(c.getresponse().read()), {"fedtail-sync": 1})
        c.close()


class ConfigTest(Tmp):
    def test_an_older_config_still_starts(self):
        cfg = self.tmp / "s.toml"
        cfg.write_text('instances = ["me.example"]\npublic_url = "https://x.example"\n')
        with self.assertLogs("fedtail-sync", "WARNING"):
            self.assertEqual(self.mod.load_config(cfg), {"instances": ["me.example"]})
        cfg.write_text('instancez = ["me.example"]\n')
        with self.assertRaises(SystemExit):
            self.mod.load_config(cfg)


class MainTest(Tmp):
    """The program: options, the config file, starting, the hourly clean-up, stopping."""

    def run_main(self, *argv):
        made = []
        real = self.mod.make_http_server

        def fake(app):
            srv = real(app)
            made.append((app, srv))
            srv.serve_forever = mock.Mock(side_effect=KeyboardInterrupt)  # Ctrl+C at once
            return srv
        with mock.patch.object(self.mod, "make_http_server", fake), \
                mock.patch.object(logging, "basicConfig"):
            self.mod.main(list(argv))
        app, srv = made[0]
        self.addCleanup(app.db.close)
        return app, srv

    def test_from_a_config_file(self):
        cfg = self.tmp / "c.toml"
        cfg.write_text(f'listen = "127.0.0.1:0"\ndb = "{self.tmp / "a.db"}"\n'
                       'instances = ["me.example"]\nkeep_days = 3\n')
        with self.assertLogs("fedtail-sync", "INFO") as logs, \
                mock.patch.object(self.mod.Server, "expire") as expire:
            app, srv = self.run_main("--config", str(cfg))
        self.assertEqual((app.allowed, app.cfg["keep_days"]), ({"me.example"}, 3))
        expire.assert_called()  # the clean-up ran (and stopped with the server)
        self.assertTrue(any("serving me.example" in line for line in logs.output))
        self.assertEqual(srv.socket.fileno(), -1)  # closed on the way out

    def test_from_the_command_line_and_nobody_served(self):
        with self.assertLogs("fedtail-sync", "WARNING") as logs:
            app, _ = self.run_main("--listen", "127.0.0.1:0", "--db", str(self.tmp / "b.db"))
        self.assertIn("no instances allowed", logs.output[0])
        app, _ = self.run_main("--listen", "127.0.0.1:0", "--db", str(self.tmp / "c.db"),
                               "--instance", "a.example", "--instance", "b.example")
        self.assertEqual(app.allowed, {"a.example", "b.example"})

    def test_version(self):
        out = io.StringIO()
        with redirect_stdout(out), self.assertRaises(SystemExit):
            self.mod.main(["--version"])
        self.assertIn(f"fedtail-sync {self.mod.__version__} (protocol 1)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
