"""Diagnostics: logs, crash traces, stack dumps, resource stats, bug reports.

fedtail is meant to stay open for days. When it falls over, hangs or grows fat,
the files here are what you send for a diagnosis. Until 1.0 everything is on by
default and verbose (`[debug]` in the config tones it down).

Where: debug.log_dir/<profile>/, ~/fedtail-logs/default/ unless set otherwise
("" — the profile's data dir, logs/):

    2026-10-16_15-04-12.log   the log: every request with its timing, polls, user
                     actions, errors with tracebacks, stats every few minutes. A new
                     file at every start and every hour (or debug.log_mb); the
                     oldest go once there are more than debug.keep_mb of them.
    latest.log       a link to the file being written — the one to send
    crash.log        Python's faulthandler: the stacks of all threads if the
                     process dies on a fatal signal (a segfault inside Qt, say)
    stacks.log       stacks of all threads on demand (`kill -USR1 <pid>`, the
                     menu, or by itself when the window freezes)

`python3 -m fedtail --bug-report` packs all that, plus versions and the config,
into one archive. The token (auth.json) and the database never go in. Logs
carry API paths, ids and timings, never post texts or the token.

No Qt in here: the frontend adds its own bits (Qt messages, a freeze watchdog)
through `add_stats()` and the module's loggers.
"""

import faulthandler
import io
import json
import logging
import logging.handlers
import os
import platform
import resource
import shutil
import signal
import sys
import tarfile
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

log = logging.getLogger("fedtail.diag")

FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"
LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING}

_state = {"dir": None, "stacks": None, "crash": None, "providers": {}, "stats_thread": None,
          "cpu": None, "rss_warned": 0, "on": True}


def is_on():
    """The debugging mode of this run (after setup())."""
    return _state.get("on", True)


def enabled(cfg, forced=False):
    """Is the debugging mode on? debug.mode: "on", "off" or "auto" — on for
    versions before 1.0 and for development builds, off for releases from 1.0.
    --debug turns it on whatever the config says."""
    if forced:
        return True
    mode = ((cfg or {}).get("debug") or {}).get("mode", "auto")
    if mode != "auto":
        return mode == "on"
    from . import __version__
    try:
        major = int(__version__.split(".")[0])
    except ValueError:
        major = 0
    return major < 1 or ".dev" in __version__


def logs_dir(paths, cfg=None):
    """The profile's log folder: the one in use, or where debug.log_dir puts it.
    With debugging off, a small log of warnings stays in the data folder, logs/."""
    if _state["dir"] is not None:
        return _state["dir"]
    where = ((cfg or {}).get("debug") or {}).get("log_dir", DEFAULT_LOG_DIR)
    if not where or (cfg is not None and not enabled(cfg)):
        return paths.data_dir / "logs"
    return Path(os.path.expanduser(where)) / paths.profile


DEFAULT_LOG_DIR = "~/fedtail-logs"


class SessionLog(logging.Handler):
    """One file per start and per hour (and per log_mb): YYYY-MM-DD_HH-MM-SS.log,
    latest.log pointing at the current one; old files go once the folder holds
    more than keep_mb of them. Small files, easy to find, easy to send."""

    def __init__(self, folder, max_mb=10, keep_mb=500):
        super().__init__()
        self.folder = Path(folder)
        self.max_bytes = int(max_mb * 1024 * 1024)
        self.keep_bytes = int(keep_mb * 1024 * 1024)
        self.stream = None
        self.hour = None
        self.path = None
        self._open()

    def _open(self):
        if self.stream:
            self.stream.close()
        now = datetime.now()
        name = f"{now:%Y-%m-%d_%H-%M-%S}.log"
        n = 1
        while (self.folder / name).exists():  # two in one second: don't overwrite
            n += 1
            name = f"{now:%Y-%m-%d_%H-%M-%S}-{n}.log"
        self.path = self.folder / name
        self.stream = open(self.path, "a", encoding="utf-8")  # noqa: SIM115
        self.hour = now.strftime("%Y%m%d%H")
        latest = self.folder / "latest.log"
        try:
            if latest.is_symlink() or latest.exists():
                latest.unlink()
            latest.symlink_to(self.path.name)
        except OSError:  # no symlinks here (Windows without the right): fine
            pass
        self._prune()

    def _prune(self):
        files = sorted((f for f in self.folder.glob("2[0-9][0-9][0-9]-*.log")
                        if f.is_file() and not f.is_symlink() and f != self.path),
                       key=lambda f: f.stat().st_mtime, reverse=True)
        total = self.path.stat().st_size if self.path and self.path.exists() else 0
        for f in files:
            total += f.stat().st_size
            if total > self.keep_bytes:
                try:
                    f.unlink()
                except OSError:
                    pass

    def emit(self, record):
        try:
            msg = self.format(record)
            if self.hour != datetime.now().strftime("%Y%m%d%H") or \
                    self.stream.tell() > self.max_bytes:
                self.stream.write("---- continued in the next file\n")
                self._open()
            self.stream.write(msg + "\n")
            self.stream.flush()
        except Exception:  # noqa: BLE001 — logging must never take the app down
            self.handleError(record)

    def close(self):
        try:
            if self.stream:
                self.stream.close()
                self.stream = None
        finally:
            super().close()


# ---- setup ---------------------------------------------------------------------------
def setup(paths, cfg, console_debug=False):
    """Logging to session files (and warnings to the terminal), crash traces,
    stack dumps on SIGUSR1, uncaught exceptions of every thread into the log.
    With the debugging mode off (debug.mode): warnings and errors only, in the data
    folder, a few MB at most; crash traces stay."""
    d = cfg.get("debug", {})
    on = enabled(cfg, console_debug)
    _state["on"] = on
    _state["dir"] = None
    folder = logs_dir(paths, cfg)
    folder.mkdir(parents=True, exist_ok=True)
    _state["dir"] = folder

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter(FORMAT, DATEFMT)

    if on:
        fh = SessionLog(folder, max_mb=d.get("log_mb", 10), keep_mb=d.get("keep_mb", 500))
        fh.setLevel(LEVELS.get(d.get("level", "debug"), logging.DEBUG))
    else:  # an ordinary user's run: what went wrong, nothing else
        fh = SessionLog(folder, max_mb=1, keep_mb=5)
        fh.setLevel(logging.WARNING)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.DEBUG if console_debug else logging.WARNING)
    ch.setFormatter(logging.Formatter("fedtail: %(levelname)s %(name)s: %(message)s"))
    root.addHandler(ch)
    # chatty libraries: their debug lines say nothing we don't log ourselves
    for name in ("urllib3", "requests", "PIL"):
        logging.getLogger(name).setLevel(logging.WARNING)

    # a fatal crash (segfault in Qt, say) still leaves the stacks behind
    _state["crash"] = open(folder / "crash.log", "a", encoding="utf-8")  # noqa: SIM115
    _state["crash"].write(f"\n=== {_stamp()} pid {os.getpid()} started\n")
    _state["crash"].flush()
    faulthandler.enable(file=_state["crash"], all_threads=True)
    _state["stacks"] = open(folder / "stacks.log", "a", encoding="utf-8")  # noqa: SIM115
    if hasattr(signal, "SIGUSR1"):
        try:
            faulthandler.register(signal.SIGUSR1, file=_state["stacks"], all_threads=True)
        except (ValueError, RuntimeError):  # not the main thread (tests)
            pass

    sys.excepthook = _excepthook
    threading.excepthook = _thread_excepthook
    return folder


def session_header(profile, extra=None):
    from . import version
    info = version.info()
    lines = {
        "fedtail": info["version"], "commit": info["commit"], "date": info["date"],
        "python": platform.python_version(), "platform": platform.platform(),
        "pid": os.getpid(), "profile": profile, "argv": " ".join(sys.argv[1:]),
        "desktop": os.environ.get("XDG_CURRENT_DESKTOP", ""),
        "session": os.environ.get("XDG_SESSION_TYPE", ""),
    }
    lines.update(extra or {})
    log.info("==== session start: %s", json.dumps(lines, ensure_ascii=False))


def _stamp():
    return datetime.now().strftime(DATEFMT)


def _excepthook(kind, value, tb):
    logging.getLogger("fedtail.crash").critical(
        "uncaught exception\n%s", "".join(traceback.format_exception(kind, value, tb)))
    sys.__excepthook__(kind, value, tb)


def _thread_excepthook(args):
    logging.getLogger("fedtail.crash").critical(
        "uncaught exception in thread %s\n%s", args.thread.name if args.thread else "?",
        "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))


# ---- stacks on demand ----------------------------------------------------------------------
def thread_stacks():
    """Readable stacks of every thread, for the log."""
    names = {t.ident: t.name for t in threading.enumerate()}
    out = []
    for ident, frame in sys._current_frames().items():
        out.append(f"--- thread {names.get(ident, ident)}\n" +
                   "".join(traceback.format_stack(frame)))
    return "\n".join(out)


def dump_stacks(reason):
    """Into the log (readable) and stacks.log (faulthandler's raw form)."""
    log.warning("thread stacks (%s):\n%s", reason, thread_stacks())
    f = _state["stacks"]
    if f:
        f.write(f"\n=== {_stamp()} {reason}\n")
        f.flush()
        faulthandler.dump_traceback(file=f, all_threads=True)
        f.flush()


# ---- resource stats ------------------------------------------------------------------------
def add_stats(name, fn):
    """fn() -> {key: number}; logged with every stats line (the core's caches,
    the window's widget count, …). Errors in a provider are logged, not raised."""
    _state["providers"][name] = fn


def _proc_status():
    out = {}
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            key, _sep, val = line.partition(":")
            if key in ("VmRSS", "VmHWM", "Threads"):
                out[key] = int(val.split()[0])
    except OSError:
        pass
    return out


def stats():
    """One snapshot: memory, CPU since the last snapshot, threads, files, providers."""
    now = time.monotonic()
    ru = resource.getrusage(resource.RUSAGE_SELF)
    cpu = ru.ru_utime + ru.ru_stime
    prev = _state["cpu"]
    _state["cpu"] = (now, cpu)
    st = _proc_status()
    rss_mb = round((st.get("VmRSS") or ru.ru_maxrss) / 1024, 1)
    out = {
        "rss_mb": rss_mb,
        "peak_mb": round(st.get("VmHWM", ru.ru_maxrss) / 1024, 1),
        "cpu_s": round(cpu, 1),
        "cpu_pct": round(100 * (cpu - prev[1]) / max(now - prev[0], 1e-6), 1) if prev else None,
        "threads": threading.active_count(),
    }
    try:
        out["fds"] = len(os.listdir("/proc/self/fd"))
    except OSError:
        pass
    for name, fn in list(_state["providers"].items()):
        try:
            for k, v in (fn() or {}).items():
                out[f"{name}.{k}"] = v
        except Exception as e:  # a broken provider must not break the stats
            out[f"{name}.error"] = str(e)[:80]
    return out


def log_stats(rss_warn_mb=1500):
    s = stats()
    log.info("stats %s", json.dumps(s, ensure_ascii=False))
    rss = s["rss_mb"]
    # warn once per doubling past the threshold, so a leak is visible but not spammy
    if rss_warn_mb and rss > rss_warn_mb and rss > 2 * _state["rss_warned"]:
        _state["rss_warned"] = rss
        log.warning("memory: %s MB resident (warning threshold %s MB)", rss, rss_warn_mb)
    return s


def start_stats(cfg):
    d = cfg.get("debug", {})
    minutes = float(d.get("stats_minutes", 5))
    if minutes <= 0 or _state["stats_thread"] or not _state.get("on", True):
        return

    def loop():
        stats()  # baseline for the CPU percentage
        while True:
            time.sleep(minutes * 60)
            try:
                log_stats(int(d.get("rss_warn_mb", 1500)))
            except Exception:
                log.exception("stats failed")

    t = threading.Thread(target=loop, name="fedtail-stats", daemon=True)
    _state["stats_thread"] = t
    t.start()


# ---- freeze watchdog --------------------------------------------------------------------------
class Watchdog:
    """The GUI thread calls beat() every second (from a timer). If the beats stop
    for `seconds`, the stacks of all threads go to the log once — that is where
    a hang shows what it was waiting on — and recovery is logged too."""

    def __init__(self, seconds):
        self.seconds = seconds
        self.last = time.monotonic()
        self.stuck_since = None
        self._stop = threading.Event()

    def beat(self):
        now = time.monotonic()
        if self.stuck_since is not None:
            log.warning("GUI thread responsive again after %.1f s", now - self.stuck_since)
            self.stuck_since = None
        self.last = now

    def start(self):
        if self.seconds <= 0:
            return
        threading.Thread(target=self._run, name="fedtail-watchdog", daemon=True).start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.wait(1.0):
            idle = time.monotonic() - self.last
            if idle > self.seconds and self.stuck_since is None:
                self.stuck_since = self.last
                dump_stacks(f"GUI thread hasn't answered for {idle:.1f} s")


# ---- timing helper ------------------------------------------------------------------------------
class timed:
    """with timed("poll", warn_s=30): …  — debug line with the duration, a warning
    if it took longer than warn_s."""

    def __init__(self, what, logger=None, warn_s=None):
        self.what, self.log, self.warn_s = what, logger or log, warn_s

    def __enter__(self):
        self.t = time.monotonic()
        return self

    def __exit__(self, kind, *_):
        self.seconds = time.monotonic() - self.t
        level = logging.WARNING if self.warn_s and self.seconds > self.warn_s else logging.DEBUG
        self.log.log(level, "%s took %.2f s%s", self.what, self.seconds,
                     " (failed)" if kind else "")
        return False


# ---- bug report ----------------------------------------------------------------------------------
REPORT_SKIP = {"auth.json", "state.db", "state.db-wal", "state.db-shm"}


def bug_report(paths, dest_dir=None, cfg=None, hours=48):
    """A .tar.gz with the logs of the last `hours`, crash and stack files, the config
    and a system summary. Never the token or the database. Returns the archive path."""
    dest = Path(dest_dir or Path.home())
    name = f"fedtail-report-{paths.profile}-{datetime.now():%Y%m%d-%H%M%S}.tar.gz"
    out = dest / name
    folder = logs_dir(paths, cfg)
    since = time.time() - hours * 3600
    summary = _system_summary(paths)
    with tarfile.open(out, "w:gz") as tar:
        if folder.exists():
            for f in sorted(folder.iterdir()):
                if f.is_file() and not f.is_symlink() and f.name not in REPORT_SKIP \
                        and (not f.name[:1].isdigit() or f.stat().st_mtime >= since):
                    tar.add(f, arcname=f"logs/{f.name}")
        if paths.config_file.exists():
            tar.add(paths.config_file, arcname="config.toml")
        data = summary.encode("utf-8")
        info = tarfile.TarInfo("system.txt")
        info.size = len(data)
        info.mtime = int(time.time())
        tar.addfile(info, io.BytesIO(data))
    return out


def _system_summary(paths):
    from . import version
    lines = [f"fedtail {version.full()}", f"python {sys.version}",
             f"platform {platform.platform()}",
             f"desktop {os.environ.get('XDG_CURRENT_DESKTOP', '')} "
             f"{os.environ.get('XDG_SESSION_TYPE', '')}",
             f"profile {paths.profile}", f"config {paths.config_file}",
             f"data {paths.data_dir}"]
    for mod in ("PySide6", "requests", "urllib3"):
        try:
            m = __import__(mod)
            lines.append(f"{mod} {getattr(m, '__version__', '?')}")
        except Exception as e:
            lines.append(f"{mod} missing ({e.__class__.__name__})")
    try:
        lines.append(f"state.db {paths.db_file.stat().st_size // 1024} KB")
    except OSError:
        pass
    try:
        usage = shutil.disk_usage(paths.data_dir)
        lines.append(f"disk free {usage.free // (1024 * 1024)} MB")
    except OSError:
        pass
    lines.append("stats " + json.dumps(stats(), ensure_ascii=False))
    return "\n".join(lines) + "\n"
