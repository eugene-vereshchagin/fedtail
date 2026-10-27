"""One scenario, every interface: do the same things in Qt, GTK, the web page and the
terminal, on the same made-up server, and compare what each showed and what each did.

The words of an interface (tools/parity.py) say what it offers; this says what it
*does*. Every step goes through the interface's own way in — the web page's HTTP API,
the terminal's host and keys, the windows' link handler and editor — and ends on the
fake server (tests/fakes.py) and in the core. A driver per interface (tests/drivers.py)
knows the way in; the reference one does every step through frontends/common directly:
what the shared code says should happen.

    STEPS            what to do, in order, with what each step shows (an observation)
    make_world()     the server every run starts from
    summary(core, w) what was done, read off the server and the core at the end
    run(driver)      → Trace(observations, summary, problems)
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field

from fedtail.core import auth, config, paths
from fedtail.core.app import Core

from . import fakes
from .fakes import BOB, ME, FakeApi, status

ALICE = fakes.acct("A", "alice@other.example")

# the step ids are what the report's rows say
STEPS = [
    ("lane_home", "lane", "home"),
    ("menu_bob", "menu", "010"),
    ("menu_mine", "menu", "030"),
    ("like", "button", "fav", "010"),
    ("boost", "button", "boost", "011"),
    ("bookmark", "button", "bookmark", "010"),
    ("thread", "thread", "022"),
    ("follow_thread", "link", "sub", "020"),
    ("mute_thread", "link", "mutethread", "012"),
    ("reply", "reply", "011", "scenario: a reply"),
    ("profile", "profile", "B"),
    ("follow_bob", "profile_act", "B", "follow"),
    ("delete_mine", "link", "delete", "030"),
    ("command_boost", "command", "! #{012}"),
    ("read_up_to", "link", "readupto", "012"),
    ("lane_replies", "lane", "replies"),
    ("all_read", "read_all", "replies"),
]


def make_world():
    w = fakes.World()
    w.add(status("010", BOB, minute=10, vis="public", text="bob writes"), home=True)
    w.add(status("011", ALICE, minute=11, vis="public", text="alice writes"), home=True)
    w.add(status("012", BOB, minute=12, vis="public", text="bob again"), home=True)
    w.add(status("020", BOB, minute=20, vis="public", text="a thread starts"), home=True)
    w.add(status("021", ALICE, "020", "B", minute=21, vis="public", text="alice answers"))
    w.add(status("022", ME, "021", "A", minute=22, vis="public", text="i answer alice"))
    w.add(status("023", BOB, "022", "ME", minute=23, vis="public", text="bob answers me"),
          home=True, mention=True)
    w.add(status("030", ME, minute=30, vis="public", text="mine, to be deleted"), home=True)
    return w


def make_core(tmp, **over):
    """A core on a fresh fake server, connected and polled once (nothing on it is read:
    feed.first_run_mark_read = false)."""
    FakeApi.world = make_world()
    # read marks by hand only: what a window marks read as it shows posts depends on how
    # big it is (a terminal reads what's under the cursor) — not what's compared here
    user = {"feed": {"first_run_mark_read": False, "complete_threads": False},
            "read": {"mark_read": "manual"}, "sound": {"enabled": "off"},
            "lanes": {"enabled": fakes.CLASSIC_LANES}}
    for k, v in over.items():
        user.setdefault(k, {}).update(v)
    cfg, _w = config.validate(user)
    p = paths.resolve("t", config=f"{tmp}/c.toml", data=f"{tmp}/d")
    auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
    core = Core(cfg, p, api_class=FakeApi)
    core._origin_json = lambda url: None  # never another server
    core.connect().result(timeout=10)
    core.poll_once()
    return core, FakeApi.world


def summary(core, w):
    """What the steps did, as the server and the core saw it: comparable across runs."""
    st = w.statuses
    posted = [(t, v, r) for t, v, r, _md in w.posted]
    return {
        "liked": sorted(i for i, s in st.items() if s.get("favourited")),
        "boosted": sorted(i for i, s in st.items() if s.get("reblogged")),
        "bookmarked": sorted(i for i, s in st.items() if s.get("bookmarked")),
        "posted": posted,
        "gone": sorted({"030"} - set(st)),
        "following": sorted(w.following),
        "subscribed": sorted(r for r in ("020",) if core.subscribed(st.get(r) or {"id": r})),
        "quiet_threads": sorted(r for r in ("012",) if core.thread_quiet(st.get(r) or {"id": r})),
        "unread_home": sorted(core.unread_ids(core.lane_entries("home"))),
        "unread_replies": core.unread_count("replies"),
    }


@dataclass
class Trace:
    """What one interface did: what each step showed, what was done in the end, and
    the steps it couldn't do at all."""
    name: str
    shown: dict = field(default_factory=dict)
    done: dict = field(default_factory=dict)
    cant: dict = field(default_factory=dict)  # step -> why


class Cant(Exception):
    """A driver's way of saying: this interface has no way to do this step."""


def fill(text, core):
    """{012} in a step's text: that post's short id, as the command line takes it."""
    if "{" not in text:
        return text
    import re
    def short(m):
        post = core.by_id(m.group(1)) if hasattr(core, "by_id") else None
        ids = core.short_ids([post]) if post is not None else {}
        return ids.get(m.group(1), m.group(1))
    return re.sub(r"\{(\w+)\}", short, text)


def run(driver, steps=STEPS):
    """Every step through the driver, on a fresh server. Returns a Trace."""
    trace = Trace(driver.name)
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        core, w = make_core(tmp, **driver.config)
        try:
            driver.start(core, w)
            from fedtail.core.view import View
            view = View(core)
            for step in steps:
                sid, kind, *args = step
                args = [fill(a, view) if isinstance(a, str) else a for a in args]
                try:
                    shown = getattr(driver, kind)(*args)
                except Cant as e:
                    trace.cant[sid] = str(e) or "—"
                    continue
                if shown is not None:
                    trace.shown[sid] = shown
            driver.settle()
            trace.done = summary(core, w)
        finally:
            driver.stop()
            core.shutdown()
    return trace


def compare(ref, other):
    """The differences of other from the reference: [(step or "done:<key>", ref, other)]."""
    out = []
    for sid, *_rest in STEPS:
        if sid in other.cant:
            out.append((sid, ref.shown.get(sid, "done"), "can't: " + other.cant[sid]))
        elif sid in ref.shown and ref.shown[sid] != other.shown.get(sid):
            out.append((sid, ref.shown[sid], other.shown.get(sid)))
    for k, v in ref.done.items():
        if other.done.get(k) != v:
            out.append(("done:" + k, v, other.done.get(k)))
    return out


def menu_keys(items):
    """A ⋯ menu as comparable words: the link's action, or the item's kind."""
    from fedtail.frontends.common.links import parse
    out = []
    for kind, url in items:
        if kind == "separator":
            continue
        if kind == "link":
            link = parse(url)
            out.append(link.action if link else "link?")
        else:
            out.append(kind)
    return out
