"""How the federation is doing, as fedtail sees it: what my server answers and how fast,
and what keeps failing — on my server and on the servers posts point at.

Kept in memory for the run (nothing on disk, nothing sent anywhere). Requests are
grouped by what they ask, ids folded ("/api/v1/statuses/:id/context"), so a 404 that
comes back every ten minutes is one row with a count, not a wall of lines. No query
strings and no tokens are kept: the path, the status, the time.

Fed by api.Api._req (my servers) and remote.open_url (everyone else). Read by
Core.federation_status() for the window's "Federation status" dialog.
"""

import re
import threading
import time
from collections import deque

# an id in a path: a ULID, a snowflake, a UUID, a percent-encoded something
_ID = re.compile(r"^(?:[0-9A-HJKMNP-TV-Z]{26}|\d{4,}|[0-9a-f]{8}-[0-9a-f-]{27}|"
                 r"[0-9a-f]{16,}|.*%[0-9A-Fa-f]{2}.*)$")
_NAMED = {"tags", "tag", "users", "statuses", "objects", "notes", "@"}  # what follows: a name
KEEP_LATENCIES = 500
KEEP_EXAMPLES = 1


def shape(path):
    """'/api/v1/statuses/01M5…/context' → '/api/v1/statuses/:id/context'; the query
    dropped. For remote addresses (no /api/): the first two segments and :… for the rest
    — a server's paths say who they are, not what fedtail asked."""
    path = (path or "").split("?", 1)[0].split("#", 1)[0]
    parts = path.split("/")
    out = []
    for i, p in enumerate(parts):
        if p.startswith("@"):
            out.append("@:name")
        elif _ID.match(p) or (i and parts[i - 1] in _NAMED and p):
            out.append(":id")
        else:
            out.append(p)
    shaped = "/".join(out)
    if not shaped.startswith("/api/") and len(out) > 3:
        shaped = "/".join(out[:3]) + "/…"
    return shaped or "/"


class Row:
    __slots__ = ("count", "first", "last", "outcome", "example", "kind")

    def __init__(self, kind, outcome, example, now):
        self.kind, self.outcome, self.example = kind, outcome, example
        self.count, self.first, self.last = 0, now, now


class Recorder:
    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.Lock()
        self.started = clock()
        self.problems = {}  # (host, method, shape, outcome) -> Row
        self.latency = {}   # host -> deque of seconds (successful answers)
        self.counts = {}    # host -> [answers, failures]

    def note(self, host, method, path, outcome, seconds=None, kind="mine"):
        """One answer. outcome: an HTTP status (int) or the kind of failure ("timeout",
        "ConnectionError", "refused: not a public address"…). kind: "mine" (my server's
        API) or "remote" (another server, no token)."""
        host = (host or "?").lower()
        ok = isinstance(outcome, int) and outcome < 400
        now = self.clock()
        with self.lock:
            c = self.counts.setdefault(host, [0, 0, kind])
            c[0] += 1
            if ok:
                if seconds is not None:
                    self.latency.setdefault(host, deque(maxlen=KEEP_LATENCIES)).append(seconds)
                return
            c[1] += 1
            path = (path or "").split("?", 1)[0]
            key = (host, method, shape(path), outcome)
            row = self.problems.get(key)
            if row is None:
                row = self.problems[key] = Row(kind, outcome, path, now)
            row.count += 1
            row.last, row.example = now, path

    def snapshot(self):
        """Plain data for the dialog (and tests): {"since", "hosts": [...], "problems":
        [...]} — the worst first."""
        with self.lock:
            hosts = []
            for host, (n, bad, kind) in self.counts.items():
                lat = sorted(self.latency.get(host) or ())
                hosts.append({"host": host, "kind": kind, "answers": n, "failures": bad,
                              "median_ms": round(1000 * lat[len(lat) // 2]) if lat else None,
                              "p95_ms": round(1000 * lat[min(len(lat) - 1,
                                                             int(len(lat) * 0.95))])
                              if lat else None})
            problems = [{"host": h, "method": m, "path": p, "outcome": o, "count": r.count,
                         "first": r.first, "last": r.last, "example": r.example,
                         "kind": r.kind}
                        for (h, m, p, o), r in self.problems.items()]
        hosts.sort(key=lambda x: (x["kind"] != "mine", -x["failures"], x["host"]))
        problems.sort(key=lambda x: (x["kind"] != "mine", -x["count"], -x["last"]))
        return {"since": self.started, "hosts": hosts, "problems": problems}

    def clear(self):
        with self.lock:
            self.problems.clear()
            self.latency.clear()
            self.counts.clear()
            self.started = self.clock()


def outcome_of(exc):
    """A failure's name for the table: timeout, connection, refused (why), or its class."""
    name = exc.__class__.__name__
    if "Timeout" in name or isinstance(exc, TimeoutError):
        return "timeout"
    if "Connection" in name:
        return "no connection"
    if name == "Refused":
        return f"refused: {exc}"
    if "SSL" in name:
        return "TLS error"
    return name


REC = Recorder()  # one per run: every account's server and every other server in it
