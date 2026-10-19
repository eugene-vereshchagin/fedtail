"""Long runs: is something growing that shouldn't?

fedtail is kept open for days, so a leak shows as a number that only goes up. Three
tools, all fed from the stats thread (diag.start_stats) or the Debug menu:

* Trend — every stats line goes in; a tracked number that rose on each of the last
  `samples` lines, by more than noise, gets one warning ("possible leak: …, +N/h
  over H h"), and again each time its growth since the start doubles. Every line
  also gets a short "trend" summary: start, now and the rate per hour.
* Census — counts by kind (Python objects by type, Qt widgets by class): what grew
  since the last count and since the first, the biggest movers first. That is the
  answer to "rss went up — of what?".
* tracemalloc — on demand (or from the start, debug.tracemalloc): where Python
  allocated the memory it holds, and what grew since the first snapshot, written to
  a file next to the logs.

No Qt here: the window feeds its widget census from the GUI thread itself.
"""

import gc
import logging
import time
import tracemalloc
from collections import Counter
from datetime import datetime
from pathlib import Path

log = logging.getLogger("fedtail.leaks")

# what is watched for steady growth, and how much growth over the window is just
# noise. Store rows (statuses, items) grow on purpose until pruning, so they are only
# summarised, never warned about.
WATCH = {"rss_mb": 20, "py_objects": 20_000, "threads": 2, "fds": 5,
         "qt.widgets": 200, "qt.rows": 60, "qt.tabs": 3, "qt.images_mem": 100,
         "qt.images_mb": 20, "core.lane_cache": 20, "core.pool_queue": 20,
         "core.bg_queue": 20, "core.parents_inflight": 20, "core.replies_inflight": 20,
         "core.honest_checked": 500, "gc.uncollectable": 1}
SUMMARY_ONLY = ("core.statuses", "core.items", "core.read", "core.db_mb")
WARMUP_S = 30 * 60  # lanes fill, caches warm up: no verdicts in the first half hour


class Trend:
    def __init__(self, samples=12, warmup_s=WARMUP_S, clock=time.monotonic):
        self.samples = max(3, int(samples))
        self.warmup_s = warmup_s
        self.clock = clock
        self.t0 = None
        self.start = {}   # metric -> first value
        self.history = {}  # metric -> [(t, value)], the last `samples` + 1
        self.warned = {}  # metric -> growth since start when last warned

    def add(self, stats):
        """One stats line in; the warnings it gives (also logged)."""
        now = self.clock()
        if self.t0 is None:
            self.t0 = now
        out = []
        for key in list(WATCH) + list(SUMMARY_ONLY):
            v = stats.get(key)
            if not isinstance(v, (int, float)) or isinstance(v, bool):
                continue
            self.start.setdefault(key, v)
            h = self.history.setdefault(key, [])
            h.append((now, v))
            del h[:-(self.samples + 1)]
            if key in WATCH:
                why = self._verdict(key, h, now)
                if why:
                    out.append(why)
        for w in out:
            log.warning("possible leak: %s", w)
        return out

    def _verdict(self, key, h, now):
        if now - self.t0 < self.warmup_s or len(h) <= self.samples:
            return None
        values = [v for _t, v in h]
        if any(b <= a for a, b in zip(values, values[1:], strict=False)):
            return None  # not up on every line: it breathes, that's fine
        if values[-1] - values[0] < WATCH[key]:
            return None  # up, but by crumbs
        grown = values[-1] - self.start[key]
        last = self.warned.get(key)
        if last is not None and grown < 2 * last:
            return None
        self.warned[key] = grown
        hours = (h[-1][0] - h[0][0]) / 3600
        return (f"{key} rose on each of the last {self.samples} checks: "
                f"{_n(values[0])} -> {_n(values[-1])} "
                f"({_signed(self.rate(key))}/h over {hours:.1f} h; "
                f"{_signed(grown)} since start)")

    def rate(self, key):
        """Per hour over the window: least squares, so one spike doesn't make a trend."""
        h = self.history.get(key) or []
        if len(h) < 2:
            return 0.0
        ts = [(t - h[0][0]) / 3600 for t, _v in h]
        vs = [v for _t, v in h]
        mt, mv = sum(ts) / len(ts), sum(vs) / len(vs)
        den = sum((t - mt) ** 2 for t in ts)
        return sum((t - mt) * (v - mv) for t, v in zip(ts, vs, strict=True)) / den if den else 0.0

    def summary(self):
        """{metric: "start→now (±per hour over the session; ±per hour lately)"}. The
        rate beside start→now is over the same span: it used to be the last dozen
        minutes' (245→763 MB over 7.8 h read "+1950/h" — three minutes of scrolling)."""
        out = {}
        hours = self.hours()
        for key, h in self.history.items():
            if not h:
                continue
            first, now = self.start[key], h[-1][1]
            overall = (now - first) / hours if hours > 0 else 0.0
            text = f"{_n(first)}->{_n(now)} ({_signed(overall)}/h"
            mins = (h[-1][0] - h[0][0]) / 60
            if len(h) > 2 and hours * 60 > mins * 1.5:  # a window shorter than the session
                text += f"; last {mins:.0f} min {_signed(self.rate(key))}/h"
            out[key] = text + ")"
        return out

    def hours(self):
        return 0.0 if self.t0 is None else (self.clock() - self.t0) / 3600


class Census:
    """Counts by kind, compared with the last count and the first one."""

    def __init__(self, name, top=12):
        self.name, self.top = name, top
        self.first = None
        self.last = None

    def take(self, counts):
        """counts: {kind: n}. Returns the line (also logged), or None the first time."""
        counts = Counter(counts)
        if self.first is None:
            self.first = self.last = counts
            log.info("census %s: %d kinds, %d in all (baseline)", self.name, len(counts),
                     sum(counts.values()))
            return None
        since_last = _movers(counts, self.last, self.top)
        since_first = _movers(counts, self.first, self.top)
        self.last = counts
        line = (f"census {self.name}: {sum(counts.values())} in all; since last: "
                f"{since_last or 'no change'}; since start: {since_first or 'no change'}")
        log.info("%s", line)
        return line


def _movers(now, before, top):
    diff = Counter(now)
    diff.subtract(before)
    moved = sorted(((k, d) for k, d in diff.items() if d), key=lambda kd: -abs(kd[1]))
    return ", ".join(f"{k} {_signed(d)}" for k, d in moved[:top])


def python_objects():
    """Python objects by type, "module.Type" for anything not built in. Walks every
    object the collector knows: a few hundred ms with a million of them, so it runs
    on the stats thread, every stats interval, in the debugging mode only."""
    out = Counter()
    for o in gc.get_objects():
        t = type(o)
        mod = t.__module__
        out[t.__qualname__ if mod == "builtins" else f"{mod}.{t.__qualname__}"] += 1
    return out


def gc_stats():
    """Objects the collector couldn't free (a growing number is a real leak), and how
    many are waiting in each generation."""
    g0, g1, g2 = gc.get_count()
    st = gc.get_stats()
    return {"uncollectable": sum(x["uncollectable"] for x in st) + len(gc.garbage),
            "gen0": g0, "gen1": g1, "gen2": g2, "collections_gen2": st[2]["collections"]}


# ---- tracemalloc ------------------------------------------------------------------------
_trace = {"first": None}
FRAMES = 10


def tracing():
    return tracemalloc.is_tracing()


def start_tracing(frames=FRAMES):
    """Every allocation from now on is traced (Python gets slower and uses about twice
    the memory meanwhile: for a hunt, not for every day)."""
    if not tracemalloc.is_tracing():
        tracemalloc.start(frames)
        _trace["first"] = None
        log.info("memory tracing on (%d frames)", frames)


def stop_tracing():
    if tracemalloc.is_tracing():
        tracemalloc.stop()
        _trace["first"] = None
        log.info("memory tracing off")


def snapshot(folder, top=40):
    """Write memory-<time>.txt in folder: who holds the most, and what grew since the
    first snapshot of this tracing. Returns the file. Only code locations go in — no
    data, so no post texts and no token."""
    if not tracemalloc.is_tracing():
        raise RuntimeError("memory tracing is off")
    snap = tracemalloc.take_snapshot().filter_traces((
        tracemalloc.Filter(False, tracemalloc.__file__),
        tracemalloc.Filter(False, "<frozen importlib._bootstrap>"),
        tracemalloc.Filter(False, "<frozen importlib._bootstrap_external>"),
        tracemalloc.Filter(False, "<unknown>")))
    first = _trace["first"]
    if first is None:
        _trace["first"] = snap
    current, peak = tracemalloc.get_traced_memory()
    lines = [f"fedtail memory snapshot {datetime.now():%Y-%m-%d %H:%M:%S}",
             f"traced now {current / 1048576:.1f} MB, peak {peak / 1048576:.1f} MB",
             "", f"== top {top} by size (file:line)"]
    for st in snap.statistics("lineno")[:top]:
        lines.append(f"{st.size / 1024:10.1f} KiB {st.count:9d} blocks  {st.traceback}")
    if first is not None:
        lines += ["", f"== grew most since the first snapshot (top {top})"]
        for st in snap.compare_to(first, "lineno")[:top]:
            lines.append(f"{st.size_diff / 1024:+10.1f} KiB {st.count_diff:+9d} blocks  "
                         f"{st.traceback}")
        lines += ["", "== where the biggest grower was allocated from"]
        biggest = snap.compare_to(first, "traceback")[:1]
        for st in biggest:
            lines += ["  " + x for x in st.traceback.format()]
    else:
        lines += ["", "(the first snapshot: the next one will say what grew since this one)"]
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    out = folder / f"memory-{datetime.now():%Y-%m-%d_%H-%M-%S}.txt"
    out.write_text("\n".join(lines) + "\n", "utf-8")
    log.info("memory snapshot: %s (traced %.1f MB)", out.name, current / 1048576)
    return out


def _n(v):
    return f"{v:g}" if isinstance(v, float) else str(v)


def _signed(v):
    if isinstance(v, float):
        v = round(v, 1)
        return f"{v:+g}"
    return f"{v:+d}"
