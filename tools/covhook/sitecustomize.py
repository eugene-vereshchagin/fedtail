"""Line coverage of every fedtail process of a self-check run, the windows included.

tools/selfcheck.py --night puts this folder first on PYTHONPATH and sets
FEDTAIL_COVERAGE to a folder: then every Python it starts — the tests, the tours, the
Qt and GTK windows they open, the web server — notes which lines of fedtail/ ran
(sys.monitoring, Python 3.12+) and leaves them in FEDTAIL_COVERAGE/hits-<pid>.json:
every 20 seconds, at exit, on SIGTERM (a step whose time ran out) and from
fedtail's own quick exit (sys.fedtail_coverage_flush, called by __main__._leave).
tools/coverage_lite.py --report puts them together.

Without FEDTAIL_COVERAGE (or on an older Python) it does nothing at all, and the
system's own sitecustomize, if there is one, still runs.
"""

import json
import os
import sys
import threading

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PKG = os.path.join(ROOT, "fedtail") + os.sep


class Recorder:
    """Which lines of fedtail/ ran in this process: {file: {line}}."""

    def __init__(self, prefix=PKG):
        self.prefix = prefix
        self.hit = {}
        self.lock = threading.Lock()
        self.tool = None

    def start(self):
        mon = getattr(sys, "monitoring", None)
        if mon is None:
            return False
        for tool in (mon.COVERAGE_ID, 4, 5):  # another coverage tool may hold the first
            try:
                mon.use_tool_id(tool, "fedtail-coverage")
            except ValueError:
                continue
            self.tool = tool
            break
        if self.tool is None:
            return False
        prefix, hit = self.prefix, self.hit

        def on_line(code, line):
            f = code.co_filename
            if f.startswith(prefix):
                lines = hit.get(f)
                if lines is None:
                    lines = hit[f] = set()
                lines.add(line)
            return mon.DISABLE

        def on_start(code, _offset):
            return None if code.co_filename.startswith(prefix) else mon.DISABLE

        mon.register_callback(self.tool, mon.events.LINE, on_line)
        mon.register_callback(self.tool, mon.events.PY_START, on_start)
        mon.set_events(self.tool, mon.events.LINE | mon.events.PY_START)
        return True

    def stop(self):
        if self.tool is not None:
            sys.monitoring.set_events(self.tool, 0)
            sys.monitoring.free_tool_id(self.tool)
            self.tool = None

    def snapshot(self):
        """{"fedtail/core/app.py": [lines]}: paths from the checkout, with "/"."""
        cut = len(os.path.dirname(self.prefix.rstrip(os.sep))) + 1
        with self.lock:
            items = list(self.hit.items())
        return {f[cut:].replace(os.sep, "/"): sorted(lines) for f, lines in items}

    def save(self, path):
        data = self.snapshot()
        tmp = f"{path}.tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f)
            os.replace(tmp, path)
        except OSError:
            pass


def _install(folder):
    rec = Recorder()
    if not rec.start():
        return
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"hits-{os.getpid()}.json")

    def flush():
        rec.save(path)
    sys.fedtail_coverage_flush = flush
    import atexit
    atexit.register(flush)

    def every():
        while True:
            stop.wait(20)
            flush()
    stop = threading.Event()
    threading.Thread(target=every, name="coverage-flush", daemon=True).start()
    try:
        import signal
        if signal.getsignal(signal.SIGTERM) in (signal.SIG_DFL, None):
            def on_term(signum, _frame):
                flush()
                signal.signal(signum, signal.SIG_DFL)
                os.kill(os.getpid(), signum)
            signal.signal(signal.SIGTERM, on_term)
    except (ValueError, OSError, AttributeError):  # not the main thread, or Windows
        pass


def _chain():
    """The sitecustomize this one hides (Debian has one): run it too."""
    here = os.path.dirname(os.path.abspath(__file__))
    for d in sys.path:
        if not d or os.path.abspath(d) == here:
            continue
        f = os.path.join(d, "sitecustomize.py")
        if os.path.isfile(f):
            try:
                with open(f, encoding="utf-8") as src:
                    exec(compile(src.read(), f, "exec"), {"__name__": "sitecustomize",
                                                         "__file__": f})
            except Exception:  # noqa: BLE001 — theirs failing must not stop ours
                pass
            break


_chain()
if os.environ.get("FEDTAIL_COVERAGE"):
    _install(os.environ["FEDTAIL_COVERAGE"])
