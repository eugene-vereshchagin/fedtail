"""What the tests share: the server module loaded from its file, a temporary folder, a
live server on a free port with a counting fake for the token check, and raw sockets."""

import http.client
import importlib.util
import json
import shutil
import socket
import tempfile
import threading
import unittest
from pathlib import Path

SERVER_FILE = Path(__file__).resolve().parent.parent / "fedtail_sync.py"
GOOD = {"t-me": "1", "t-me2": "1", "t-you": "2"}  # token → account id at me.example


def load_server():
    """fedtail_sync.py as a module (it is a single file, not a package)."""
    import sys
    mod = sys.modules.get("fedtail_sync")
    if mod is None:
        spec = importlib.util.spec_from_file_location("fedtail_sync", SERVER_FILE)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["fedtail_sync"] = mod
        spec.loader.exec_module(mod)
    return mod


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="fedtail-sync-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.mod = load_server()


class Live(Tmp):
    """A server with the options given; `self.calls` — the tokens it checked."""

    def start(self, verify=None, **cfg):
        self.calls = []

        def fake(host, token):
            self.calls.append(token)
            return GOOD.get(token)
        conf = {"db": str(self.tmp / "s.db"), "instances": ["me.example"],
                "listen": "127.0.0.1:0", **cfg}
        self.app = self.mod.Server(conf, verify=verify or fake)
        self.addCleanup(self.app.db.close)
        self.httpd = self.mod.make_http_server(self.app)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)
        return self.app

    def call(self, method, path, token=None, body=None, headers=None,
             instance="https://me.example"):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        h = dict(headers or {})
        if token:
            h.setdefault("Authorization", f"Bearer {token}")
            h.setdefault("X-Fedtail-Instance", instance)
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        data = r.read()
        c.close()
        try:
            return r.status, json.loads(data)
        except ValueError:
            return r.status, data

    def raw(self, data, wait=5.0, half_close=False):
        """Bytes sent as they are; → what came back before the server closed."""
        s = socket.create_connection(("127.0.0.1", self.port), timeout=wait)
        s.sendall(data)
        if half_close:
            s.shutdown(socket.SHUT_WR)  # "that's all I send"
        out = b""
        try:
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                out += chunk
        except TimeoutError:
            out += b"<still open>"
        except ConnectionError:
            pass
        s.close()
        return out

    @staticmethod
    def closed_within(sock, seconds):
        sock.settimeout(seconds)
        try:
            return sock.recv(1) == b""
        except TimeoutError:
            return False
        except ConnectionError:
            return True
