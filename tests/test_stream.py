"""The live stream: a tiny WebSocket server on localhost, the real client against it."""

import base64
import hashlib
import json
import socket
import struct
import threading
import time
import unittest

from fedtail.core import auth, config, paths, stream
from fedtail.core.app import Core

from .test_core import TmpDir

GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC11B85"


def _frame(opcode, payload, fin=True):
    n = len(payload)
    head = bytes([(0x80 if fin else 0) | opcode])
    if n < 126:
        head += bytes([n])
    elif n < 65536:
        head += bytes([126]) + struct.pack("!H", n)
    else:
        head += bytes([127]) + struct.pack("!Q", n)
    return head + payload


class Server(threading.Thread):
    """Accepts connections; on each: checks the handshake, then runs script(conn)."""

    def __init__(self, script):
        super().__init__(daemon=True)
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        self.script = script
        self.requests = []
        self.received = []  # (opcode, payload) the client sent, unmasked

    def run(self):
        while True:
            try:
                conn, _a = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self.serve, args=(conn,), daemon=True).start()

    def serve(self, conn):
        data = b""
        while b"\r\n\r\n" not in data:
            data += conn.recv(4096)
        head = data.decode()
        self.requests.append(head)
        key = next(line.split(":", 1)[1].strip() for line in head.split("\r\n")
                   if line.lower().startswith("sec-websocket-key"))
        accept = base64.b64encode(hashlib.sha1((key + GUID).encode()).digest()).decode()
        conn.sendall(("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                      f"Connection: Upgrade\r\nSec-WebSocket-Accept: {accept}\r\n\r\n").encode())
        threading.Thread(target=self.listen, args=(conn,), daemon=True).start()
        try:
            self.script(conn)
        except OSError:
            pass

    def listen(self, conn):
        buf = b""

        def read(n):
            nonlocal buf
            while len(buf) < n:
                chunk = conn.recv(4096)
                if not chunk:
                    raise OSError("closed")
                buf += chunk
            out, buf = buf[:n], buf[n:]
            return out
        try:
            while True:
                b0, b1 = read(2)
                n = b1 & 0x7F
                if n == 126:
                    n = struct.unpack("!H", read(2))[0]
                mask = read(4)
                assert b1 & 0x80, "client frames must be masked"
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(read(n)))
                self.received.append((b0 & 0x0F, payload))
        except OSError:
            pass

    def close(self):
        self.sock.close()


def wait(cond, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


class StreamTest(unittest.TestCase):
    def test_events_ping_and_fragments(self):
        def script(conn):
            msg = json.dumps({"stream": ["user"], "event": "update", "payload": "{}"}).encode()
            conn.sendall(_frame(0x9, b"hi"))  # a ping: the client must pong
            conn.sendall(_frame(0x1, msg))
            half = len(msg) // 2  # the same, in two fragments
            conn.sendall(_frame(0x1, msg[:half], fin=False) + _frame(0x0, msg[half:]))
            conn.sendall(_frame(0x1, json.dumps({"event": "delete", "payload": "1"}).encode()))
            time.sleep(5)
        srv = Server(script)
        srv.start()
        self.addCleanup(srv.close)
        got = []
        s = stream.Stream(f"ws://127.0.0.1:{srv.port}", "SECRET", got.append,
                          streams=("user", "user:notification"))
        s.start()
        self.addCleanup(s.stop)
        self.assertTrue(wait(lambda: len(got) == 3), got)
        self.assertEqual(got, ["update", "update", "delete"])
        head = srv.requests[0]
        self.assertIn("GET /api/v1/streaming?stream=user HTTP/1.1", head)
        self.assertIn("Authorization: Bearer SECRET", head)
        self.assertNotIn("SECRET", head.split("\r\n")[0])  # never in the url
        self.assertTrue(wait(lambda: (0xA, b"hi") in srv.received))
        sub = [json.loads(p) for op, p in srv.received if op == 0x1]
        self.assertEqual(sub, [{"type": "subscribe", "stream": "user:notification"}])

    def test_reconnects_after_close(self):
        def script(conn):
            conn.sendall(_frame(0x1, json.dumps({"event": "notification"}).encode()))
            conn.sendall(_frame(0x8, struct.pack("!H", 1001)))
            conn.close()
        srv = Server(script)
        srv.start()
        self.addCleanup(srv.close)
        got = []
        old = stream.BACKOFF
        stream.BACKOFF = (0.05,)
        self.addCleanup(lambda: setattr(stream, "BACKOFF", old))
        s = stream.Stream(f"ws://127.0.0.1:{srv.port}", "t", got.append)
        s.start()
        self.addCleanup(s.stop)
        self.assertTrue(wait(lambda: len(srv.requests) >= 2 and len(got) >= 2))

    def test_refused_handshake(self):
        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        self.addCleanup(sock.close)

        def answer():
            conn, _a = sock.accept()
            conn.recv(4096)
            conn.sendall(b"HTTP/1.1 401 Unauthorized\r\nContent-Length: 0\r\n\r\n")
            conn.close()
        threading.Thread(target=answer, daemon=True).start()
        with self.assertRaises(stream.StreamError):
            stream.WebSocket(f"ws://127.0.0.1:{sock.getsockname()[1]}/x", {})

    def test_streaming_url_from_instance(self):
        from fedtail.core.api import Capabilities, capabilities_from_instance
        caps = capabilities_from_instance({"urls": {"streaming_api": "wss://s.example"}})
        self.assertEqual(caps.streaming, "wss://s.example")
        self.assertEqual(Capabilities().streaming, "")


class CoreStreamTest(TmpDir):
    def test_core_wakes_the_poller_and_off_means_off(self):
        from . import fakes
        from .fakes import FakeApi

        def script(conn):
            conn.sendall(_frame(0x1, json.dumps({"event": "notification"}).encode()))
            conn.sendall(_frame(0x1, json.dumps({"event": "filters_changed"}).encode()))
            time.sleep(3)
        srv = Server(script)
        srv.start()
        self.addCleanup(srv.close)
        for mode, wakes in (("off", 0), ("auto", 1)):
            FakeApi.world = fakes.World()
            cfg, _ = config.validate({"poll": {"stream": mode}})
            p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / mode))
            auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
            core = Core(cfg, p, api_class=FakeApi)
            self.addCleanup(core.shutdown)
            core.connect().result()
            core.api.has_stream = True
            core._stream_url = lambda: f"ws://127.0.0.1:{srv.port}"  # this test's server
            woke = []
            core._poll_soon = lambda w=woke: w.append(1)
            core._start_stream()
            if wakes:
                self.assertTrue(wait(lambda w=woke: len(w) == 1))
                time.sleep(0.2)
            else:
                time.sleep(0.3)
                self.assertIsNone(getattr(core, "_stream", None))
            self.assertEqual(len(woke), wakes)  # filters_changed wakes nothing


class StreamPlaceTest(TmpDir):
    def test_the_token_goes_to_my_server_over_tls_only(self):
        from . import fakes
        from .fakes import FakeApi
        FakeApi.world = fakes.World()
        cfg, _ = config.validate({})
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        auth.save(p.auth_file, {"server": "https://example.org", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        self.addCleanup(core.shutdown)
        for announced, want in (("", "wss://example.org"),
                                ("wss://streaming.example.org", "wss://streaming.example.org"),
                                ("https://example.org", "wss://example.org"),
                                ("ws://example.org", "wss://example.org"),  # never plain
                                ("wss://attacker.example", "wss://example.org")):
            core.caps.streaming = announced
            self.assertEqual(core._stream_url(), want, announced)
        core.auth = dict(core.auth, server="http://example.org")
        self.assertIsNone(core._stream_url())  # a plain-http server: polling only
        self.assertTrue(stream.same_site("wss://streaming.example.org", "https://social.example.org"))
        self.assertFalse(stream.same_site("wss://example.net", "https://example.org"))

    def test_the_stream_goes_through_the_proxy(self):
        import os
        from unittest import mock
        with mock.patch.dict(os.environ, {"https_proxy": "http://u:p%40@127.0.0.1:1",
                                          "no_proxy": "nearby.example"}, clear=True):
            self.assertEqual(stream.proxy_for("wss", "far.example"),
                             "http://u:p%40@127.0.0.1:1")
            self.assertIsNone(stream.proxy_for("wss", "nearby.example"))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(stream.proxy_for("wss", "far.example"))
        with self.assertRaises(stream.StreamError):  # SOCKS: not this way
            stream._tunnel("socks5://127.0.0.1:1", "far.example", 443)
        # a CONNECT proxy: asked to open the way, with the login from its address
        got = []

        def proxy(conn):
            got.append(conn.recv(4096).decode())
            conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
        srv = Plain(proxy)
        srv.start()
        self.addCleanup(srv.close)
        sock = stream._tunnel(f"http://u:p%40@127.0.0.1:{srv.port}", "far.example", 443)
        sock.close()
        self.assertTrue(got[0].startswith("CONNECT far.example:443 HTTP/1.1"))
        self.assertIn("Proxy-Authorization: Basic " + base64.b64encode(b"u:p@").decode(),
                      got[0])


class Plain(threading.Thread):
    """A bare TCP server: script(conn) once."""

    def __init__(self, script):
        super().__init__(daemon=True)
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen()
        self.port = self.sock.getsockname()[1]
        self.script = script

    def run(self):
        try:
            conn, _a = self.sock.accept()
        except OSError:
            return
        with conn:
            self.script(conn)

    def close(self):
        self.sock.close()


if __name__ == "__main__":
    unittest.main()
