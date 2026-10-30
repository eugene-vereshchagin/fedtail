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


def _answer(stuck_after):
    """What the running copy says to a second one: "ok <pid>", or "hung <pid>" when its
    window hasn't answered its watchdog for stuck_after seconds (diag.gui_stuck_for)."""
    from .. import diag
    stuck = diag.gui_stuck_for()
    word = "hung" if stuck_after and stuck >= stuck_after else "ok"
    return f"{word} {os.getpid()}".encode()


def end_process(pid, wait=5.0):
    """A hung first copy ended: asked (SIGTERM: it quits as from the menu if it can),
    then made to (SIGKILL) after `wait` seconds. → True once it is gone."""
    import signal
    import time
    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError, OSError):
        return True
    end = time.monotonic() + wait
    while time.monotonic() < end:
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError, OSError):
            return True
        time.sleep(0.2)
    try:
        os.kill(pid, getattr(signal, "SIGKILL", signal.SIGTERM))
    except (ProcessLookupError, PermissionError, OSError):
        return True
    time.sleep(0.5)
    return True


class SingleInstance:
    def __init__(self, path):
        self.path = str(path)
        self.sock = None
        self.listener = None
        self.on_message = None
        self.stuck_after = 0  # listen(): a window stuck this long answers "hung"
        self.hung_pid = None  # poke_existing(): the running copy said it hangs

    def poke_existing(self, message="raise"):
        """True if another instance answered (and was asked to show itself — or, with
        "open URL", to open that link). A copy whose window hangs says so: False then,
        and hung_pid is its process (ended by the caller, window.hung_copy_seconds). A
        copy that says nothing back (one before 0.22) counts as answering."""
        data = message.encode("utf-8")[:4000]
        self.hung_pid = None
        if WINDOWS:
            from multiprocessing.connection import Client
            sent = False
            try:
                with Client(_pipe_name(self.path), family="AF_PIPE",
                            authkey=_pipe_key(self.path)) as c:
                    c.send_bytes(data)
                    sent = True
                    got = c.recv_bytes(64) if c.poll(3) else b""
            except (OSError, EOFError, AuthenticationError):
                return sent  # sent, the answer lost: it is there
            return self._took(got)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(2)
        try:
            s.connect(self.path)
            s.sendall(data + b"\n")
        except (TimeoutError, FileNotFoundError, ConnectionRefusedError, OSError):
            s.close()
            return False
        try:
            s.settimeout(3)
            got = s.recv(64)
        except OSError:
            got = b""
        finally:
            s.close()
        return self._took(got)

    def _took(self, got):
        parts = got.decode("ascii", "replace").split()
        if len(parts) == 2 and parts[0] == "hung" and parts[1].isdigit():
            self.hung_pid = int(parts[1])
            return False
        return True

    def listen(self, on_message, stuck_after=0):
        """Answer the copies started after this one: on_message(text) with what they
        ask; stuck_after > 0 — when the window has hung that long, they're told so
        (and end this one) instead."""
        self.on_message = on_message
        self.stuck_after = stuck_after
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
                    said = _answer(self.stuck_after)
                    conn.send_bytes(said)
            except (OSError, EOFError, AuthenticationError):
                if self.listener is None:
                    return
                continue
            if said.startswith(b"hung"):
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
                    said = _answer(self.stuck_after)
                    conn.sendall(said)
                except OSError:
                    continue
            if said.startswith(b"hung"):
                continue  # the second copy ends this one: nothing to show
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
