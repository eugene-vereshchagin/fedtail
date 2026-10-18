"""One window per profile.

The first instance listens; a second one connects, says "raise" and exits.
Linux and the like: a unix socket in the profile's data dir. Windows: a named
pipe named after that path (multiprocessing.connection, no extra packages).
"""

import hashlib
import os
import socket
import threading
from multiprocessing import AuthenticationError

WINDOWS = os.name == "nt"


def _pipe_name(path):
    return r"\\.\pipe\fedtail-" + hashlib.sha1(str(path).lower().encode()).hexdigest()[:16]


def _pipe_key(path, make=False):
    """Windows: the pipe's secret, next to where the socket would be (the profile's own
    data folder). Only who can read that folder can talk to the window — another user
    of the computer can't send it "open <file>", nor pose as it."""
    import os
    import secrets
    from pathlib import Path
    f = Path(str(path)).with_name("instance.key")
    try:
        key = f.read_bytes()
        if len(key) >= 32:
            return key
    except OSError:
        pass
    if not make:
        return None
    key = secrets.token_bytes(32)
    try:
        f.unlink(missing_ok=True)
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(key)
    except OSError:
        return None
    return key


class SingleInstance:
    def __init__(self, path):
        self.path = str(path)
        self.sock = None
        self.listener = None
        self.on_message = None

    def poke_existing(self, message="raise"):
        """True if another instance answered (and was asked to show itself — or, with
        "open URL", to open that link)."""
        data = message.encode("utf-8")[:4000]
        if WINDOWS:
            from multiprocessing.connection import Client
            try:
                with Client(_pipe_name(self.path), family="AF_PIPE",
                            authkey=_pipe_key(self.path)) as c:
                    c.send_bytes(data)
                return True
            except (OSError, EOFError, AuthenticationError):
                return False
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        try:
            s.connect(self.path)
            s.sendall(data + b"\n")
            return True
        except (TimeoutError, FileNotFoundError, ConnectionRefusedError, OSError):
            return False
        finally:
            s.close()

    def listen(self, on_message):
        self.on_message = on_message
        if WINDOWS:
            from multiprocessing.connection import Listener
            self.listener = Listener(_pipe_name(self.path), family="AF_PIPE",
                                     authkey=_pipe_key(self.path, make=True))
            threading.Thread(target=self._pipe_loop, name="fedtail-instance",
                             daemon=True).start()
            return
        try:
            os.unlink(self.path)  # stale socket from a crash
        except FileNotFoundError:
            pass
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.bind(self.path)
        os.chmod(self.path, 0o600)
        self.sock.listen(4)
        threading.Thread(target=self._loop, name="fedtail-instance", daemon=True).start()

    def _pipe_loop(self):
        while self.listener is not None:
            try:
                with self.listener.accept() as conn:  # a wrong key fails in accept()
                    msg = conn.recv_bytes(4096).decode("utf-8", "replace").strip()
            except (OSError, EOFError, AuthenticationError):
                if self.listener is None:
                    return
                continue
            if msg and self.on_message:
                self.on_message(msg)

    def _loop(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            with conn:
                conn.settimeout(2)
                try:
                    msg = conn.recv(4096).decode("utf-8", "replace").strip()
                except OSError:
                    continue
            if msg and self.on_message:
                self.on_message(msg)

    def close(self):
        if self.listener is not None:
            listener, self.listener = self.listener, None
            try:
                listener.close()
            except OSError:
                pass
        if self.sock:
            self.sock.close()
            self.sock = None
            try:
                os.unlink(self.path)
            except FileNotFoundError:
                pass
