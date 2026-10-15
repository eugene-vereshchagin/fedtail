"""One window per profile.

The first instance listens on a unix socket in the profile's data dir.
A second instance connects, says "raise" and exits.
"""

import os
import socket
import threading


class SingleInstance:
    def __init__(self, path):
        self.path = str(path)
        self.sock = None
        self.on_message = None

    def poke_existing(self):
        """True if another instance answered (and was asked to show itself)."""
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        try:
            s.connect(self.path)
            s.sendall(b"raise\n")
            return True
        except (FileNotFoundError, ConnectionRefusedError, socket.timeout, OSError):
            return False
        finally:
            s.close()

    def listen(self, on_message):
        self.on_message = on_message
        try:
            os.unlink(self.path)  # stale socket from a crash
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.path)
        os.chmod(self.path, 0o600)
        self.sock.listen(4)
        threading.Thread(target=self._loop, name="fedtail-instance", daemon=True).start()

    def _loop(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(2)
                try:
                    msg = conn.recv(64).decode("utf-8", "replace").strip()
                except OSError:
                    continue
            if msg and self.on_message:
                self.on_message(msg)

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
