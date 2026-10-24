"""The Mastodon protocol's corners beyond tests/test_stream.py and test_protocols.py: the
WebSocket client byte by byte over a stand-in socket (long frames, masks, stalls,
handshakes gone wrong, a proxy's CONNECT), the stream's own loop when the server goes
quiet, and the adapter's answers to odd server data."""

import json
import struct
import sys
import unittest
from unittest import mock

from fedtail.protocols.base import ServerError
from fedtail.protocols.mastodon import adapter, counters, probe, stream
from fedtail.protocols.mastodon.api import ApiError


class Sock:
    """recv() hands out `chunks` in order (an exception in the list is raised there);
    what is sent is kept."""

    def __init__(self, *chunks):
        self.chunks = list(chunks)
        self.sent = b""
        self.closed = False
        self.timeout = None

    def recv(self, _n):
        if not self.chunks:
            return b""
        c = self.chunks.pop(0)
        if isinstance(c, BaseException):
            raise c
        return c

    def sendall(self, data):
        self.sent += data

    def close(self):
        self.closed = True

    def settimeout(self, t):
        self.timeout = t


def ws_over(sock):
    ws = stream.WebSocket.__new__(stream.WebSocket)
    ws.sock, ws.buf = sock, b""
    import threading
    ws._send_lock = threading.Lock()
    return ws


def frame(opcode, payload, fin=True, mask=None):
    n = len(payload)
    head = bytes([(0x80 if fin else 0) | opcode])
    mbit = 0x80 if mask else 0
    if n < 126:
        head += bytes([mbit | n])
    elif n < 65536:
        head += bytes([mbit | 126]) + struct.pack("!H", n)
    else:
        head += bytes([mbit | 127]) + struct.pack("!Q", n)
    if mask:
        payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        head += mask
    return head + payload


class WebSocketTest(unittest.TestCase):
    def test_ssl_context_with_and_without_certifi(self):
        with mock.patch.dict(sys.modules, {"certifi": None}):
            self.assertIsNotNone(stream._ssl_context())
        import ssl
        roots = ssl.get_default_verify_paths().cafile or ""
        fake = mock.Mock(where=lambda: roots)
        with mock.patch.dict(sys.modules, {"certifi": fake}), \
                mock.patch.object(stream.ssl, "create_default_context") as make:
            stream._ssl_context()
        make.assert_called_once_with(cafile=roots)  # requests' own roots

    def test_same_site_and_proxy(self):
        self.assertFalse(stream.same_site("", "https://a.test"))
        self.assertTrue(stream.same_site("streaming.a.test", "https://a.test"))
        with mock.patch("urllib.request.proxy_bypass", side_effect=OSError), \
                mock.patch("urllib.request.getproxies", return_value={"all": "http://p:3"}):
            self.assertEqual(stream.proxy_for("wss", "a.test"), "http://p:3")

    def test_send_lengths_are_framed_and_masked(self):
        for n, marker in ((10, 10), (200, 126), (70000, 127)):
            s = Sock()
            ws_over(s).send(0x1, b"x" * n)
            self.assertEqual(s.sent[1] & 0x7F, marker)
            self.assertTrue(s.sent[1] & 0x80)  # a client always masks

    def test_frames_of_every_length_and_masked(self):
        big = b"y" * 70000
        s = Sock(frame(0x1, b"m" * 300), frame(0x1, big), frame(0x1, b"hi", mask=b"\1\2\3\4"))
        ws = ws_over(s)
        self.assertEqual(ws.frame(), (0x1, b"m" * 300))
        self.assertEqual(ws.frame(), (0x1, big))
        self.assertEqual(ws.frame(), (0x1, b"hi"))

    def test_bad_frames(self):
        too_big = bytes([0x81, 127]) + struct.pack("!Q", 17 * 1024 * 1024)
        with self.assertRaisesRegex(stream.StreamError, "too big"):
            ws_over(Sock(too_big)).frame()
        with self.assertRaisesRegex(stream.StreamError, "stalled"):
            ws_over(Sock(bytes([0x81, 10]), TimeoutError())).frame()
        with self.assertRaisesRegex(stream.StreamError, "closed"):
            ws_over(Sock(bytes([0x81]))).frame()

    def test_close_never_raises(self):
        s = Sock()
        s.sendall = mock.Mock(side_effect=OSError)
        s.close = mock.Mock(side_effect=OSError)
        ws_over(s).close()

    def test_handshake(self):
        ws = ws_over(Sock(b"HTTP/1.1 101 Switching\r\nSec-WebSocket-Accept: wrong\r\n"
                          b"Server: cdn\r\n\r\n"))
        from urllib.parse import urlsplit
        with self.assertLogs("fedtail.protocols.mastodon.stream", "INFO") as logs:
            ws._handshake(urlsplit("wss://a.test:8443/api?x=1"), {"A": "b"}, 7)
        self.assertIn("going on", logs.output[0])  # the 101 says it's open: trusted
        self.assertEqual(ws.sock.timeout, 7)
        self.assertIn(b"GET /api?x=1 HTTP/1.1\r\nHost: a.test:8443", ws.sock.sent)
        with self.assertRaisesRegex(stream.StreamError, "during handshake"):
            ws_over(Sock(b"HTTP/1.1 10"))._read_until(b"\r\n\r\n")
        with self.assertRaisesRegex(stream.StreamError, "too long"):
            ws_over(Sock(*[b"x" * 4096] * 20))._read_until(b"\r\n\r\n")

    def test_connect_ws_wss_and_through_a_proxy(self):
        with self.assertRaisesRegex(stream.StreamError, "not a websocket"):
            stream.WebSocket("https://a.test/", {})
        plain = Sock()
        wrapped = Sock()
        ctx = mock.Mock(wrap_socket=mock.Mock(return_value=wrapped))
        with mock.patch.object(stream, "proxy_for", return_value=None), \
                mock.patch.object(stream.socket, "create_connection", return_value=plain), \
                mock.patch.object(stream, "_ssl_context", return_value=ctx), \
                mock.patch.object(stream.WebSocket, "_handshake",
                                  side_effect=stream.StreamError("refused")):
            with self.assertRaises(stream.StreamError):
                stream.WebSocket("wss://a.test/", {})
        self.assertTrue(wrapped.closed)  # a failed handshake closes what it opened
        with mock.patch.object(stream, "proxy_for", return_value="http://p:3128"), \
                mock.patch.object(stream, "_tunnel", return_value=plain) as tun, \
                mock.patch.object(stream.WebSocket, "_handshake"):
            ws = stream.WebSocket("ws://a.test/", {})
        tun.assert_called_once_with("http://p:3128", "a.test", 80)
        self.assertIs(ws.sock, plain)

    def test_tunnel(self):
        with self.assertRaisesRegex(stream.StreamError, "socks5"):
            stream._tunnel("socks5://p:1080", "a.test", 443)
        ok = Sock(b"HTTP/1.1 200 Connection established\r\n\r\n")
        tls = Sock(b"HTTP/1.1 200 OK\r\n\r\n")
        ctx = mock.Mock(wrap_socket=mock.Mock(return_value=tls))
        with mock.patch.object(stream.socket, "create_connection", return_value=ok), \
                mock.patch.object(stream, "_ssl_context", return_value=ctx):
            got = stream._tunnel("https://u%40x:p%3A@proxy.test", "a.test", 443)
        self.assertIs(got, tls)  # an https proxy: TLS to it first
        self.assertIn(b"CONNECT a.test:443 HTTP/1.1", tls.sent)
        self.assertIn(b"Proxy-Authorization: Basic ", tls.sent)
        import base64
        cred = tls.sent.split(b"Basic ")[1].split(b"\r\n")[0]
        self.assertEqual(base64.b64decode(cred), b"u@x:p:")
        for answer, words in ((b"", "no answer"), (b"HTTP/1.1 407 Auth\r\n\r\n", "refused")):
            s = Sock(answer)
            with mock.patch.object(stream.socket, "create_connection", return_value=s):
                with self.assertRaisesRegex(stream.StreamError, words):
                    stream._tunnel("proxy.test:3128", "a.test", 443)
            self.assertTrue(s.closed)


class StreamLoopTest(unittest.TestCase):
    def make(self, ws, streams=("user",)):
        st = stream.Stream("wss://a.test", "T", lambda e: got.append(e), streams)
        got = []
        st.events = got
        st.ws = ws
        return st

    def test_quiet_server_pinged_then_dropped(self):
        ws = mock.Mock()
        ws.frame.side_effect = [TimeoutError(), (0x1, b"\xff\xfe"), (0x1, b"not json"),
                                (0x2, b"bin"), (0x1, json.dumps({"event": "update"}).encode()),
                                TimeoutError(), TimeoutError()]
        st = self.make(ws, ("user", "direct"))
        with mock.patch.object(stream, "WebSocket", return_value=ws):
            with self.assertRaisesRegex(stream.StreamError, "no answer to ping"):
                st._session()
        ws.send.assert_any_call(0x9, b"fedtail")
        ws.send.assert_any_call(0x1, json.dumps({"type": "subscribe",
                                                 "stream": "direct"}).encode())
        self.assertEqual(st.events, ["update"])

    def test_a_failure_while_stopping_ends_the_loop(self):
        st = self.make(None)

        def fail():
            st.stop_event.set()
            raise OSError("gone")
        st._session = fail
        st.run()
        self.assertEqual(st.failures, 0)


class AdapterCornersTest(unittest.TestCase):
    def test_media_with_odd_numbers(self):
        m = adapter.media({"id": "1", "type": "video",
                           "meta": {"focus": {"x": "left", "y": 0},
                                    "original": {"duration": "long"}}})
        self.assertIsNone(m.focus)
        self.assertEqual(m.duration, 0.0)

    def test_a_quote_of_a_boost_is_the_boosted_post(self):
        inner = {"id": "B1", "account": {"id": "A", "acct": "a"}, "content": "",
                 "reblog": {"id": "P", "account": {"id": "C", "acct": "c"},
                            "content": "<p>x</p>"}}
        q = adapter.quote({"quote": {"state": "accepted", "quoted_status": inner}})
        self.assertEqual(q.post.id, "P")

    def test_notices_and_relationships(self):
        a = adapter.activity({"id": "1", "type": "admin.report",
                              "report": {"comment": "spam bot"},
                              "created_at": "2026-01-01T00:00:00Z"})
        self.assertIn("spam bot", a.notice)
        r = adapter.relationship({"languages": ["ru", "en"]})
        self.assertEqual(r.languages, ("ru", "en"))
        self.assertIsNone(adapter.relationship({}).languages)

    def test_held_back_and_silenced(self):
        h = adapter.held_back({"id": "R", "account": {"id": "A", "acct": "a"},
                               "notifications_count": 3,
                               "last_status": {"id": "S", "account": {"id": "A", "acct": "a"},
                                               "content": "<p>x</p>"}})
        self.assertEqual((h.count, h.last.id), (3, "S"))
        s = adapter.silenced({"muted": [{"id": "M", "acct": "m"}, "junk"],
                              "blocked": [{"id": "B", "acct": "b"}], "domains": ["bad.test"]})
        self.assertEqual(([a.id for a in s.muted], [a.id for a in s.blocked], s.domains),
                         (["M"], ["B"], ("bad.test",)))
        self.assertEqual(adapter.silenced(None).muted, ())


class ProbeCountersTest(unittest.TestCase):
    def test_probe_says_an_error(self):
        api = mock.Mock()
        api.get.side_effect = ApiError(500, "boom")
        self.assertEqual(probe._ask(api, "k", "/p", None), ("error", "HTTP 500"))
        self.assertTrue(issubclass(ApiError, ServerError))

    def test_counters_of_the_same_post(self):
        st = {"uri": "https://far/s/1", "replies_count": 1, "favourites_count": 2,
              "reblogs_count": 0}
        self.assertIsNone(counters.merge(st, dict(st)))  # nothing new there
        self.assertIsNone(counters.merge(st, None))
        self.assertIsNone(counters.merge(st, {"uri": "other"}))
        self.assertEqual(counters.merge(st, dict(st, favourites_count=9))["favourites_count"],
                         9)


if __name__ == "__main__":
    unittest.main()
