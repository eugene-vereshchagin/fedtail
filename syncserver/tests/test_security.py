"""fedtail-sync faces the internet: each way to hang it, flood it, fill it or turn it
against someone, tried on a live server on localhost."""

import http.client
import http.server
import json
import socket
import threading
import time
import unittest
from unittest import mock

from .live import Live, Tmp, load_server


class HangingTest(Live):
    def test_a_silent_connection_is_dropped(self):
        self.start(timeout_seconds=1)
        s = socket.create_connection(("127.0.0.1", self.port))
        self.addCleanup(s.close)
        t = time.monotonic()
        self.assertTrue(self.closed_within(s, 4))
        self.assertLess(time.monotonic() - t, 4)

    def test_a_trickling_client_is_cut_all_the_same(self):
        self.start(timeout_seconds=1)
        s = socket.create_connection(("127.0.0.1", self.port))
        self.addCleanup(s.close)
        s.sendall(b"GET /v1 HTTP/1.1\r\n")
        t = time.monotonic()
        cut = False
        while time.monotonic() - t < 6:
            time.sleep(0.5)  # each byte well under the timeout
            try:
                s.sendall(b"X")
            except OSError:
                cut = True
                break
        self.assertTrue(cut or self.closed_within(s, 1))
        self.assertLess(time.monotonic() - t, 5)  # cut at about twice the timeout

    def test_connections_over_the_cap_are_closed_at_the_door(self):
        self.start(max_connections=2, timeout_seconds=5)
        hold = [socket.create_connection(("127.0.0.1", self.port)) for _ in range(2)]
        for s in hold:
            self.addCleanup(s.close)
        time.sleep(0.3)  # both taken in
        extra = socket.create_connection(("127.0.0.1", self.port))
        self.addCleanup(extra.close)
        self.assertTrue(self.closed_within(extra, 2))
        for s in hold:
            s.close()
        time.sleep(0.3)
        self.assertEqual(self.call("GET", "/v1")[0], 200)  # the slots come back

    def test_a_body_shorter_than_promised_doesnt_hold_a_thread(self):
        self.start(timeout_seconds=1)
        out = self.raw(b"POST /v1/blobs HTTP/1.1\r\nAuthorization: Bearer t-me\r\n"
                       b"X-Fedtail-Instance: me.example\r\nContent-Length: 100\r\n\r\nabc",
                       wait=5)
        self.assertNotIn(b"<still open>", out)
        self.assertEqual(self.app.total, 0)


class BodyTest(Live):
    def setUp(self):
        super().setUp()
        self.start(max_blob_kb=1)

    def post_raw(self, headers):
        head = b"POST /v1/blobs HTTP/1.1\r\nAuthorization: Bearer t-me\r\n" \
               b"X-Fedtail-Instance: me.example\r\n" + headers + b"\r\n"
        return self.raw(head, wait=3)

    def test_strange_lengths_are_refused(self):
        self.assertIn(b" 400 ", self.post_raw(b"Content-Length: -1\r\n"))
        self.assertIn(b" 400 ", self.post_raw(b"Content-Length: abc\r\n"))
        self.assertIn(b" 400 ", self.post_raw(b"Content-Length: 99999999999999999999\r\n"))
        self.assertIn(b" 411 ", self.post_raw(b""))
        self.assertIn(b" 411 ", self.post_raw(b"Transfer-Encoding: chunked\r\n"))
        self.assertIn(b" 413 ", self.post_raw(b"Content-Length: 5000\r\n"))  # unread
        self.assertEqual(self.app.total, 0)

    def test_bad_numbers_and_ids_are_refused(self):
        for q in ("after=-1", "after=1e9", "after=" + "9" * 30, "limit=abc",
                  "exclude=../../x", "a=1&" * 20):
            self.assertEqual(self.call("GET", "/v1/blobs?" + q, "t-me")[0], 400, q)
        code, _ = self.call("POST", "/v1/blobs", "t-me", b"x",
                            {"X-Fedtail-Device": "<script>"})
        self.assertEqual(code, 400)
        self.assertEqual(self.call("GET", "/v1/blobs?after=" + "9" * 19, "t-me")[0], 200)

    def test_a_long_token_is_not_even_checked(self):
        self.assertEqual(self.call("GET", "/v1/blobs", "x" * 600)[0], 401)
        self.assertEqual(self.calls, [])


class FloodTest(Live):
    def test_one_address_has_its_limit(self):
        self.start(requests_per_minute_per_ip=5)
        codes = [self.call("GET", "/v1")[0] for _ in range(7)]
        self.assertEqual(codes[:5], [200] * 5)
        self.assertEqual(codes[5:], [429, 429])

    def test_random_tokens_cant_make_it_hammer_a_server(self):
        self.start(verifications_per_minute_per_ip=3)
        codes = [self.call("GET", "/v1/blobs", f"junk{i}")[0] for i in range(10)]
        self.assertEqual(len(self.calls), 3)  # asked the fediverse server 3 times only
        self.assertEqual(codes.count(429), 7)
        # a known token isn't asked again
        self.start(verifications_per_minute_per_ip=3)
        for _ in range(10):
            self.assertEqual(self.call("GET", "/v1/blobs", "t-me")[0], 200)
        self.assertEqual(self.calls, ["t-me"])

    def test_many_addresses_hit_the_overall_cap(self):
        self.start(verifications_per_minute=4, client_ip_header="CF-Connecting-IP")
        for i in range(10):
            self.call("GET", "/v1/blobs", f"junk{i}",
                      headers={"CF-Connecting-IP": f"203.0.113.{i}"})
        self.assertEqual(len(self.calls), 4)

    def test_the_proxy_header_is_believed_only_when_named(self):
        self.start(requests_per_minute_per_ip=3)
        codes = [self.call("GET", "/v1", headers={"CF-Connecting-IP": f"203.0.113.{i}"})[0]
                 for i in range(5)]
        self.assertEqual(codes.count(429), 2)  # not named: everyone is 127.0.0.1
        self.start(requests_per_minute_per_ip=3, client_ip_header="CF-Connecting-IP")
        codes = [self.call("GET", "/v1", headers={"CF-Connecting-IP": f"203.0.113.{i}"})[0]
                 for i in range(5)]
        self.assertEqual(codes.count(429), 0)
        junk = [self.call("GET", "/v1", headers={"CF-Connecting-IP": "not an ip"})[0]
                for _ in range(4)]
        self.assertEqual(junk.count(429), 1)  # nonsense in it: the peer counts

    def test_the_window_never_grows_without_end(self):
        w = load_server().Window(5, max_keys=100)
        for i in range(500):
            w.hit(f"k{i}")
        self.assertLessEqual(len(w.counts), 100)


class DiskTest(Live):
    def test_the_whole_server_has_a_cap(self):
        self.start(quota_mb=1, total_mb=1, max_blob_kb=64)
        blob = b"x" * 60 * 1024
        while self.call("POST", "/v1/blobs", "t-me", blob)[0] == 200:
            pass
        code, err = self.call("POST", "/v1/blobs", "t-you", blob)
        self.assertEqual(code, 507)
        self.assertIn("full", err["error"])
        # the count survives a restart, and a wipe gives the room back
        used = self.app.total
        again = load_server().Server({"db": str(self.tmp / "s.db"), "instances": []})
        self.addCleanup(again.db.close)
        self.assertEqual(again.total, used)
        self.assertEqual(self.call("DELETE", "/v1/blobs", "t-me")[0], 200)
        self.assertEqual(self.app.total, 0)
        self.assertEqual(self.call("POST", "/v1/blobs", "t-you", blob)[0], 200)


class ErrorTest(Live):
    def test_a_failure_inside_says_nothing_of_itself(self):
        def boom(host, token):
            raise RuntimeError("secret detail /srv/fedtail-sync/sync.db")
        self.start(verify=boom)
        with self.assertLogs("fedtail-sync", "ERROR"):
            code, body = self.call("GET", "/v1/blobs", "t-me")
        self.assertEqual((code, body), (500, {"error": "internal error"}))


class TokenCheckTest(Tmp):
    """How the server asks a fediverse server whose a token is."""

    def setUp(self):
        super().setUp()
        self.hits = []
        hits = self.hits

        class Instance(http.server.BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                hits.append(self.path)
                if self.path.startswith("/redirect"):
                    self.send_response(302)
                    self.send_header("Location", "/lan-secret")
                    self.end_headers()
                elif self.path.startswith("/huge-id"):
                    body = json.dumps({"id": "9" * 500}).encode()
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(body)
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b'{"id": "42"}')

            def log_message(self, *a):
                pass
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Instance)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def test_no_redirect_is_followed(self):
        with self.assertRaises(self.mod.Refused) as e:
            self.mod.Server.fetch_account(self.base + "/redirect", "tok")
        self.assertEqual(e.exception.status, 502)
        self.assertNotIn("/lan-secret", self.hits)  # the token went nowhere else

    def test_an_answer_is_taken_only_in_its_shape(self):
        self.assertEqual(self.mod.Server.fetch_account(self.base + "/ok", "tok"), "42")
        self.assertIsNone(self.mod.Server.fetch_account(self.base + "/huge-id", "tok"))

    def test_star_talks_to_public_addresses_only_even_after_the_name_check(self):
        conn = self.mod._PublicOnlyHTTPS("rebinding.example", 443)
        plain = socket.create_connection(("127.0.0.1", self.srv.server_address[1]))

        def connected(c):
            c.sock = plain
        with mock.patch.object(http.client.HTTPSConnection, "connect", connected):
            with self.assertRaises(self.mod.NotPublic):
                conn.connect()
        self.assertEqual(plain.fileno(), -1)  # closed
        self.assertFalse(self.mod.is_public_ip("10.0.0.1"))
        self.assertFalse(self.mod.is_public_ip("::1"))
        self.assertFalse(self.mod.is_public_ip("169.254.169.254"))
        self.assertTrue(self.mod.is_public_ip("1.1.1.1"))

    def test_star_refuses_lan_and_odd_hosts(self):
        app = self.mod.Server({"db": ":memory:", "instances": ["*"]}, verify=lambda h, t: "1")
        self.addCleanup(app.db.close)
        for host in ("localhost", "127.0.0.1", "[::1]", "10.1.2.3", "169.254.169.254"):
            self.assertFalse(app.allowed_host(host), host)
        for given in ("https://x.example/../y", "x.example/path", "a b.example",
                      "user@x.example", "http://x.example", "x.example?q=1"):
            self.assertIsNone(self.mod.host_of(given), given)


if __name__ == "__main__":
    unittest.main()
