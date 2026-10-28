"""Diagnostics: logs, crash traces, stack dumps, resource stats, bug reports.

fedtail is meant to stay open for days. When it falls over, hangs or grows fat,
the files here are what you send for a diagnosis. Until 1.0 everything is on by
default and verbose (`[debug]` in the config tones it down).

Where: the profile's data folder, logs/ (debug.log_dir/<profile>/ if set)
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
import gc
import io
import json
import logging
import logging.handlers
import os
import platform
import re
import shutil
import signal
import sys
import tarfile
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

try:
    import resource  # not on Windows
except ImportError:
    resource = None

log = logging.getLogger("fedtail.diag")

FORMAT = "%(asctime)s.%(msecs)03d %(levelname)-7s [%(threadName)s] %(name)s: %(message)s"
DATEFMT = "%Y-%m-%d %H:%M:%S"
LEVELS = {"debug": logging.DEBUG, "info": logging.INFO, "warning": logging.WARNING}

_state = {"dir": None, "stacks": None, "crash": None, "providers": {}, "stats_thread": None,
          "cpu": None, "rss_warned": 0, "on": True, "trend": None, "census": {},
          "census_on": False, "started": time.monotonic(), "last_stats": None}


def is_on():
    """The debugging mode of this run (after setup())."""
    return _state.get("on", True)


def enabled(cfg, forced=False):
    """Is the debugging mode on? debug.mode: "on", "off" or "auto" — on for
    development versions (X.Y.Z.devN, i.e. a git checkout between releases), off for
    releases and the one-file builds made from them. --debug turns it on whatever the
    config says."""
    if forced:
        return True
    mode = ((cfg or {}).get("debug") or {}).get("mode", "auto")
    if mode != "auto":
        return mode == "on"
    from . import __version__
    return ".dev" in __version__


def logs_dir(paths, cfg=None):
    """The profile's log folder: the one in use, or where debug.log_dir puts it.
    By default (and always with debugging off) the profile's data folder, logs/ —
    the menu opens it, nothing goes into the home folder."""
    if _state["dir"] is not None:
        return _state["dir"]
    where = ((cfg or {}).get("debug") or {}).get("log_dir", DEFAULT_LOG_DIR)
    if where == OLD_LOG_DIR:  # the default before 0.11, written into many configs
        where = DEFAULT_LOG_DIR
    if not where or (cfg is not None and not enabled(cfg)):
        return paths.data_dir / "logs"
    return Path(os.path.expanduser(where)) / paths.profile


DEFAULT_LOG_DIR = ""
OLD_LOG_DIR = "~/fedtail-logs"
# what a log folder holds that is ours to delete (nothing else in it is touched)
# (fedtail.log*: the single log file of the first versions)
OUR_LOGS = ("2[0-9][0-9][0-9]-*.log", "latest.log", "crash.log", "stacks.log", "version",
            "fedtail.log", "fedtail.log.[0-9]*", "memory-*.txt")


def _remove_ours(folder):
    """Our log files in folder gone; the folder too if that leaves it empty."""
    for pattern in OUR_LOGS:
        for f in folder.glob(pattern):
            try:
                if f.is_symlink() or f.is_file():
                    f.unlink()
            except OSError:
                pass
    try:
        folder.rmdir()  # only when empty
    except OSError:
        pass


def _forget_old_logs(paths, folder):
    """Logs of another version are no use any more: a fresh version starts clean.
    Also the logs the old default left in ~/fedtail-logs/<profile>/."""
    from . import version
    now = version.info()["version"].replace(" (dirty)", "")
    mark = folder / "version"
    try:
        before = mark.read_text("utf-8").strip()
    except OSError:
        before = None
    if before != now:
        if before is not None or any(folder.glob("2[0-9][0-9][0-9]-*.log")):
            _remove_ours(folder)
            folder.mkdir(parents=True, exist_ok=True)
        try:
            mark.write_text(now + "\n", "utf-8")
        except OSError:
            pass
    old = Path(os.path.expanduser(OLD_LOG_DIR)) / paths.profile
    if old.is_dir() and old.resolve() != folder.resolve():
        _remove_ours(old)
        try:
            old.parent.rmdir()  # ~/fedtail-logs itself, once no profile is left in it
        except OSError:
            pass


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
        self.path.touch()
        self._link_latest()
        self.stream = open(self.path, "a", encoding="utf-8")  # noqa: SIM115
        self.hour = now.strftime("%Y%m%d%H")
        self._prune()

    def _link_latest(self):
        """latest.log → the file being written: a symlink, or — where symlinks need a
        right nobody has (Windows without developer mode) — a hard link, the same file
        under a second name. Made before the file is opened for writing: Windows won't
        link a file someone holds open."""
        latest = self.folder / "latest.log"
        try:
            if latest.is_symlink() or latest.exists():
                latest.unlink()
        except OSError:  # held open elsewhere (an editor): the old one stays
            return
        try:
            latest.symlink_to(self.path.name)
        except OSError:
            try:
                os.link(self.path, latest)
            except OSError:  # neither (FAT, a network share): no latest.log
                pass

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
_QUERY = re.compile(r"((?:https?://|url: |\s/)[^\s?'\"<>]*)\?[^\s'\"<>)]+")


def hide_queries(text):
    """An address's query out of a log line: what a request's error says ("…with url:
    /api/v2/search?q=what I looked for") or a picture's signed address. The API's own
    lines show their few paging parameters on their own (api._SAFE_PARAMS)."""
    return _QUERY.sub(r"\1?…", text)


class NoQueries(logging.Filter):
    """Every log line, whoever wrote it, without query strings (see hide_queries)."""

    def filter(self, record):
        msg = record.getMessage()
        if "?" in msg:
            record.msg, record.args = hide_queries(msg), None
        return True


def _writable(folder, paths):
    """The log folder if it can be written to; else one in the temporary folder (a
    data folder made read-only, a full disk); None — nowhere at all."""
    import tempfile
    for where in (folder, Path(tempfile.gettempdir()) / f"fedtail-logs-{paths.profile}"):
        try:
            where.mkdir(parents=True, exist_ok=True)
            probe = where / ".write-test"
            probe.write_text("", "utf-8")
            probe.unlink()
            if where != folder:
                print(f"fedtail: {folder} can't be written to: the logs go to {where}",
                      file=sys.stderr)
            return where
        except OSError:
            continue
    return None


def setup(paths, cfg, console_debug=False):
    """Logging to session files (and warnings to the terminal), crash traces,
    stack dumps on SIGUSR1, uncaught exceptions of every thread into the log.
    With the debugging mode off (debug.mode): warnings and errors only, in the data
    folder, a few MB at most; crash traces stay."""
    d = cfg.get("debug", {})
    on = enabled(cfg, console_debug)
    _state["on"] = on
    _state["dir"] = None
    folder = _writable(logs_dir(paths, cfg), paths)
    if folder is not None:
        _forget_old_logs(paths, folder)
    _state["dir"] = folder

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    fmt = logging.Formatter(FORMAT, DATEFMT)

    if folder is None:  # nowhere to write: the terminal alone (said there once)
        fh = None
    elif on:
        fh = SessionLog(folder, max_mb=d.get("log_mb", 10), keep_mb=d.get("keep_mb", 500))
        fh.setLevel(LEVELS.get(d.get("level", "debug"), logging.DEBUG))
    else:  # an ordinary user's run: what went wrong, nothing else
        fh = SessionLog(folder, max_mb=1, keep_mb=5)
        fh.setLevel(logging.WARNING)
    if fh is not None:
        fh.setFormatter(fmt)
        fh.addFilter(NoQueries())
        root.addHandler(fh)

    ch = logging.StreamHandler(sys.stderr)
    ch.setLevel(logging.DEBUG if console_debug else logging.WARNING)
    ch.setFormatter(logging.Formatter("fedtail: %(levelname)s %(name)s: %(message)s"))
    ch.addFilter(NoQueries())
    root.addHandler(ch)
    _state["console"] = ch
    # chatty libraries: their debug lines say nothing we don't log ourselves
    for name in ("urllib3", "requests", "PIL"):
        logging.getLogger(name).setLevel(logging.WARNING)

    if folder is None:
        print("fedtail: no folder for the logs can be written to: logging to the terminal "
              "only", file=sys.stderr)
        sys.excepthook = _excepthook
        threading.excepthook = _thread_excepthook
        return None
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


def quiet_console():
    """No more log lines on the terminal: a full-screen terminal interface (the TUI) owns
    it, and a traceback printed over it scrambles the screen. The log file keeps them."""
    ch = _state.get("console")
    if ch is not None:
        logging.getLogger().removeHandler(ch)
        _state["console"] = None


# ---- what this process is: the interface it draws and, on a phone, the device -----------
# Said once at start (__main__ for the desktop's interfaces, the Android bridge for the
# phone); the session header, the bug report and the issue's draft all read it from here,
# so none of them says what the config wished instead of what runs (`--ui web` with
# ui.frontend = "qt", the phone).
_running = {"interface": "", "device": {}}
# a phone's facts fit for a public issue (the bug report, private, carries them all)
PUBLIC_DEVICE = ("android", "device", "abi", "screen", "app")


def running(interface, device=None):
    """Says what this process is.

    Args:
        interface: "qt", "gtk", "tui", "web", "cli" or "android".
        device: a phone's facts as its app gathers them ({"device": "Google Pixel 8",
            "android": "15 (API 35)", "abi", "memory", "screen", "app", …}); None on a
            desktop, where the system says it itself.
    """
    _running["interface"] = str(interface or "")
    _running["device"] = {str(k): str(v) for k, v in (device or {}).items() if v not in
                          (None, "")}


def interface(cfg=None):
    """The interface this process draws; before anyone said — the config's wish."""
    return _running["interface"] or ((cfg or {}).get("ui") or {}).get("frontend", "?")


def device():
    """A phone's facts (a copy), {} on a desktop."""
    return dict(_running["device"])


def system_lines(cfg=None, public=False):
    """The system in a few lines, the same wherever it's told: fedtail and Python, then a
    phone's model and Android or a desktop's OS and session, then the interface.
    public: only what may go into a public issue (a phone's memory, notifications and
    the like stay in the private report)."""
    from . import version
    lines = [f"fedtail {version.full()}", f"Python {platform.python_version()}"]
    dev = _running["device"]
    if dev:
        keys = PUBLIC_DEVICE if public else tuple(dev)
        lines += [f"{k} {dev[k]}" for k in keys if k in dev]
    else:
        lines += [f"{platform.system()} {platform.release()} ({platform.machine()})",
                  f"desktop {os.environ.get('XDG_CURRENT_DESKTOP', '') or '—'} "
                  f"{os.environ.get('XDG_SESSION_TYPE', '')}".strip()]
    lines.append(f"interface {interface(cfg)}")
    if getattr(sys, "frozen", False):
        lines.append("one-file build")
    return lines


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
    if _running["interface"]:
        lines["ui"] = _running["interface"]
    lines.update({k: v for k, v in _running["device"].items()})
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


def _windows_memory():
    """{"VmRSS", "VmHWM"} in kB from GetProcessMemoryInfo — Windows' /proc/self/status."""
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
    c = Counters()
    c.cb = ctypes.sizeof(c)
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    get = getattr(k32, "K32GetProcessMemoryInfo", None) or ctypes.windll.psapi.GetProcessMemoryInfo
    get.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    get.restype = wintypes.BOOL
    if not get(k32.GetCurrentProcess(), ctypes.byref(c), c.cb):
        return {}
    return {"VmRSS": c.WorkingSetSize // 1024, "VmHWM": c.PeakWorkingSetSize // 1024}


def _fd_kinds():
    """Open files by kind (socket, pipe, anon_inode, file…): sockets piling up is a
    connection not closed, files piling up a file not closed."""
    kinds = {}
    for fd in os.listdir("/proc/self/fd"):
        try:
            target = os.readlink(f"/proc/self/fd/{fd}")
        except OSError:
            continue
        kind = target.split(":", 1)[0] if ":" in target and not target.startswith("/") \
            else ("dev" if target.startswith("/dev/") else "file")
        kinds[kind] = kinds.get(kind, 0) + 1
    return kinds


def trim_memory():
    """Memory Python and Qt freed back to the system (glibc keeps it otherwise: after a
    night of lanes built and let go, the process stays at its peak). Returns the MB the
    resident size went down by, or None where there's no such call (not glibc)."""
    try:
        import ctypes
        libc = ctypes.CDLL("libc.so.6")
    except (OSError, AttributeError):
        return None
    before = _proc_status().get("VmRSS") or 0
    gc.collect()
    libc.malloc_trim(0)
    after = _proc_status().get("VmRSS") or 0
    return round((before - after) / 1024, 1)


def _proc_status():
    out = {}
    if os.name == "nt":
        try:
            return _windows_memory()
        except Exception:  # noqa: BLE001 — stats are a nicety
            return {}
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            key, _sep, val = line.partition(":")
            if key in ("VmRSS", "VmHWM", "Threads"):
                out[key] = int(val.split()[0])
    except OSError:
        pass
    return out


def smaps():
    """{"uss_mb", "pss_mb"} of this process (Linux: /proc/self/smaps_rollup); {} elsewhere.
    USS — the pages only this process has, what it would give back: the number that
    says how heavy fedtail itself is (RSS counts the shared libraries whole)."""
    try:
        text = Path("/proc/self/smaps_rollup").read_text()
    except OSError:
        return {}
    kb = {}
    for line in text.splitlines():
        key, _sep, rest = line.partition(":")
        parts = rest.split()
        if parts and parts[0].isdigit():
            kb[key.strip()] = int(parts[0])
    out = {}
    uss = kb.get("Private_Clean", 0) + kb.get("Private_Dirty", 0)
    if uss:
        out["uss_mb"] = round(uss / 1024, 1)
    if "Pss" in kb:
        out["pss_mb"] = round(kb["Pss"] / 1024, 1)
    return out


def stats():
    """One snapshot: memory, CPU since the last snapshot, threads, files, providers."""
    now = time.monotonic()
    cpu = time.process_time()  # user + system time of this process, on every system
    maxrss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss if resource else 0
    prev = _state["cpu"]
    _state["cpu"] = (now, cpu)
    st = _proc_status()
    rss_mb = round((st.get("VmRSS") or maxrss) / 1024, 1)
    out = {
        "rss_mb": rss_mb,
        **smaps(),
        "peak_mb": round(st.get("VmHWM", maxrss) / 1024, 1),
        "cpu_s": round(cpu, 1),
        "py_objects": len(gc.get_objects()),  # growing for hours: Python-side leak
        "cpu_pct": round(100 * (cpu - prev[1]) / max(now - prev[0], 1e-6), 1) if prev else None,
        "threads": threading.active_count(),
    }
    from . import leaks
    for k, v in leaks.gc_stats().items():
        out[f"gc.{k}"] = v
    try:
        out["fds"] = len(os.listdir("/proc/self/fd"))
        out["fds_by_kind"] = _fd_kinds()
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
    _state["last_stats"] = s
    log.info("stats %s", json.dumps(s, ensure_ascii=False))
    rss = s["rss_mb"]
    # warn once per doubling past the threshold, so a leak is visible but not spammy
    if rss_warn_mb and rss > rss_warn_mb and rss > 2 * _state["rss_warned"]:
        _state["rss_warned"] = rss
        log.warning("memory: %s MB resident (warning threshold %s MB)", rss, rss_warn_mb)
    return s


def census(name, counts):
    """Counts by kind (see leaks.Census): logged against the last and the first count
    of that name. The window feeds its widget classes here from the GUI thread."""
    from . import leaks
    c = _state["census"].get(name)
    if c is None:
        c = _state["census"][name] = leaks.Census(name)
    return c.take(counts)


def trend(s):
    """One stats snapshot into the leak watch: warnings (logged) and a summary line."""
    t = _state["trend"]
    if t is None:
        return []
    warnings = t.add(s)
    log.info("trend over %.1f h %s", t.hours(), json.dumps(t.summary(), ensure_ascii=False))
    return warnings


def check_now(rss_warn_mb=1500, objects=None):
    """Stats, trend and (in the debugging mode, or when asked) the Python object census,
    now — the stats thread's job, also run from the Debug menu."""
    from . import leaks
    s = log_stats(rss_warn_mb)
    trend(s)
    if objects if objects is not None else _state["census_on"]:
        t = time.monotonic()
        census("python", leaks.python_objects())
        log.debug("census python took %.0f ms", (time.monotonic() - t) * 1000)
    return s


def session_summary():
    """The last line of a session: how long, how big it got, what grew."""
    t = _state["trend"]
    s = _state["last_stats"] or {}
    st = _proc_status()
    hours = (time.monotonic() - _state["started"]) / 3600
    bits = {"hours": round(hours, 2), "rss_mb": round((st.get("VmRSS") or 0) / 1024, 1),
            "peak_mb": round((st.get("VmHWM") or 0) / 1024, 1),
            "cpu_s": round(time.process_time(), 1)}
    for k in ("freezes.count", "freezes.worst_ms", "core.polls"):
        if k in s:
            bits[k] = s[k]
    log.info("session summary %s", json.dumps(bits, ensure_ascii=False))
    if t is not None and t.history:
        log.info("session trend %s", json.dumps(t.summary(), ensure_ascii=False))
    return bits


def start_stats(cfg):
    d = cfg.get("debug", {})
    minutes = float(d.get("stats_minutes", 5))
    if _state["stats_thread"]:
        return
    from . import leaks
    _state["trend"] = leaks.Trend(int(d.get("leak_samples", 12)))
    _state["census_on"] = bool(d.get("object_census", True)) and is_on()
    if d.get("tracemalloc", False):
        leaks.start_tracing()
    if minutes <= 0 or not _state.get("on", True):
        if d.get("trim_memory", True):  # no stats, but the memory still goes back
            def trim_loop():
                while True:
                    time.sleep(600)
                    try:
                        trim_memory()
                    except Exception:  # noqa: BLE001 — a nicety, never a crash
                        log.debug("trim failed", exc_info=True)
            t = threading.Thread(target=trim_loop, name="fedtail-trim", daemon=True)
            _state["stats_thread"] = t
            t.start()
        return

    def loop():
        stats()  # baseline for the CPU percentage
        while True:
            time.sleep(minutes * 60)
            try:
                if d.get("trim_memory", True):
                    freed = trim_memory()
                    if freed:
                        log.info("memory: %.1f MB given back to the system", freed)
                check_now(int(d.get("rss_warn_mb", 1500)))
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


# ---- freezes of the GUI thread ----------------------------------------------------------
# where the toolkit's loop runs (app.exec(), app.run()): a stack ending there is the
# toolkit's own work — laying out, painting, shaping text
EVENT_LOOP = ("frontends/qt/__init__.py", "frontends/gtk/__init__.py")
_busy = []  # what the GUI thread is doing now, outermost first (labels from busy())


class busy:
    """with diag.busy("lane home: draw"): …  — names what the GUI thread is doing, so
    a freeze in the log says which of our jobs it fell into."""

    def __init__(self, label):
        self.label = label

    def __enter__(self):
        _busy.append(self.label)
        return self

    def __exit__(self, *_):
        if _busy and _busy[-1] == self.label:
            _busy.pop()
        return False


def _short_stack(frame, depth=10):
    """The innermost frames as "file.py:123 func", innermost last."""
    out = []
    for fs in traceback.extract_stack(frame)[-depth:]:
        name = fs.filename.replace("\\", "/")
        if "/fedtail/" in name:
            name = "fedtail/" + name.rsplit("/fedtail/", 1)[1]
        else:
            name = name.rsplit("/", 1)[-1]
        out.append(f"{name}:{fs.lineno} {fs.name}")
    return out


class StallMeter:
    """Freezes shorter than the watchdog's seconds: the GUI thread calls tick() from a
    timer every `interval` s; a thread of its own notices when the ticks stop for more
    than `stall_ms` and looks at what the GUI thread is busy with right then — the
    Python stack and the busy() labels — a few times during a long one. When the ticks
    come back, one line says how long the window froze and where. A stack that ends
    in the event loop means Qt itself was busy: laying out, painting, shaping text."""

    SAMPLES_AT = (1, 3, 8)  # in units of stall_ms into the freeze

    def __init__(self, stall_ms, interval=0.1):
        self.stall = stall_ms / 1000.0
        self.interval = interval
        self.last = time.monotonic()
        self.gui = threading.get_ident()
        self.samples = []
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.count = 0
        self.total_ms = 0.0
        self.worst_ms = 0.0

    def start(self):
        if self.stall <= 0:
            return
        self.gui = threading.get_ident()
        threading.Thread(target=self._run, name="fedtail-stalls", daemon=True).start()

    def stop(self):
        self._stop.set()

    def tick(self):
        now = time.monotonic()
        gap = now - self.last - self.interval
        self.last = now
        with self._lock:
            samples, self.samples = self.samples, []
        if self.stall <= 0 or gap < self.stall:
            return
        ms = gap * 1000
        self.count += 1
        self.total_ms += ms
        self.worst_ms = max(self.worst_ms, ms)
        where, seen = [], set()
        for labels, stack in samples:
            key = (tuple(labels), tuple(stack[-4:]))
            if key in seen:
                continue
            seen.add(key)
            inside = " > ".join(labels) or "-"
            frames = " <- ".join(reversed(stack)) if stack else "?"
            if stack and not labels and any(e in stack[-1] for e in EVENT_LOOP):
                inside = "the toolkit itself (layout, painting, text)"
            where.append(f"[{inside}] {frames}")
        log.warning("GUI froze %.0f ms%s", ms,
                    (": " + " || ".join(where)) if where else " (not caught in the act)")

    def _run(self):
        taken = 0
        while not self._stop.wait(0.05):
            late = time.monotonic() - self.last - self.interval
            if late < self.stall:
                taken = 0
                continue
            if taken < len(self.SAMPLES_AT) and late >= self.stall * self.SAMPLES_AT[taken]:
                taken += 1
                frame = sys._current_frames().get(self.gui)
                sample = (list(_busy), _short_stack(frame) if frame is not None else [])
                with self._lock:
                    self.samples.append(sample)

    def counts(self):
        return {"count": self.count, "total_ms": round(self.total_ms),
                "worst_ms": round(self.worst_ms)}


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


def _toolkits():
    """The toolkits loaded in this process, with their versions (only those already
    imported: asking must not load one)."""
    out = []
    if "PySide6.QtCore" in sys.modules:
        try:
            from PySide6.QtCore import qVersion
            out.append(f"Qt {qVersion()}")
        except Exception:  # noqa: BLE001
            pass
    gi = sys.modules.get("gi.repository.Gtk")
    if gi is not None:
        try:
            out.append(f"GTK {gi.get_major_version()}.{gi.get_minor_version()}."
                       f"{gi.get_micro_version()}")
            adw = sys.modules.get("gi.repository.Adw")
            out.append(f"libadwaita {adw.get_major_version()}.{adw.get_minor_version()}"
                       if adw is not None else "libadwaita not used")
        except Exception:  # noqa: BLE001
            pass
    if "textual" in sys.modules:
        out.append(f"textual {getattr(sys.modules['textual'], '__version__', '?')}")
    return out


def changed_options(cfg):
    """{"section.key": value} of the options that differ from the defaults."""
    from .core.config import DEFAULTS
    out = {}
    for section, values in (cfg or {}).items():
        base = DEFAULTS.get(section)
        if not isinstance(values, dict) or not isinstance(base, dict):
            continue
        for key, val in values.items():
            if key not in base or base[key] != val:
                out[f"{section}.{key}"] = val
    return out


def debug_context(paths, cfg, ui):
    """In the debugging mode (a dev version): what --bug-report would add, written into
    the log right away — so the log file alone is enough to send. The system summary,
    the options changed from the defaults and the config file itself (it holds no
    token; auth.json and the database never go anywhere)."""
    if not is_on():
        return
    log.info("==== for a bug report (the debugging mode: this log alone is enough)\n"
             "frontend %s\n%s", ui, _system_summary(paths).rstrip())
    log.info("options changed from the defaults: %s",
             json.dumps(changed_options(cfg), ensure_ascii=False, default=str))
    try:
        text = paths.config_file.read_text("utf-8")
    except OSError:
        text = ""
    if text.strip():
        log.info("config file %s:\n%s", paths.config_file, text.rstrip())


# ---- bug report ----------------------------------------------------------------------------------
REPORT_SKIP = {"auth.json", "state.db", "state.db-wal", "state.db-shm", "sync.key",
               "sync_auth.json", "sync_invite.json", "sync_webdav.json"}


def bug_report(paths, dest_dir=None, cfg=None, hours=48):
    """A .tar.gz with the logs of the last `hours`, crash and stack files, the config
    and a system summary. Never the token or the database. Returns the archive path."""
    dest = Path(dest_dir or Path.home())
    name = f"fedtail-report-{paths.profile}-{datetime.now():%Y%m%d-%H%M%S}.tar.gz"
    out = dest / name
    folder = logs_dir(paths, cfg)
    since = time.time() - hours * 3600
    summary = _system_summary(paths, cfg)
    with tarfile.open(out, "w:gz") as tar:
        if folder.exists():
            for f in sorted(folder.iterdir()):
                # latest.log: the link (a hard one on Windows), not a second copy
                if f.is_file() and not f.is_symlink() and f.name not in REPORT_SKIP \
                        and f.name != "latest.log" \
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


def _system_summary(paths, cfg=None):
    lines = system_lines(cfg) + [
             f"python {sys.version}", f"platform {platform.platform()}",
             f"profile {paths.profile}", f"config {paths.config_file}",
             f"data {paths.data_dir}"]
    for mod in ("PySide6", "requests", "urllib3"):
        try:
            m = __import__(mod)
            lines.append(f"{mod} {getattr(m, '__version__', '?')}")
        except Exception as e:
            lines.append(f"{mod} missing ({e.__class__.__name__})")
    lines += _toolkits()
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
