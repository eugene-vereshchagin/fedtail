"""The one door the Kotlin side knocks on.

Kotlin calls module-level functions here through Chaquopy and gets JSON back (a str):
plain values cross the bridge both ways, nothing of Python's lives on in Kotlin. Every
call that can fail answers {"error": "…"} instead of raising, so a screen shows the
reason and the app lives on.

The core is the repository's fedtail/ package, unchanged. What a screen needs comes
from the web interface's own JSON layer (frontends/web/server.py, class Web): the same
lanes, cards, "new below" divider and read rules the windows and the browser page use
(they all stand on frontends/common/lane.py) — the phone is one more face of them, not
a copy of their logic.

    start(files_dir, cache_dir, lang, demo)  where the files go; the core is made
    info()                                   versions, TLS, the database (first screen)
    state()                                  logged in? which server, which account
    login_begin(server) / login_finish(code) OAuth: back to fedtail://oauth, or a code
    open()                                   connect, start polling → me + lanes
    lanes() / lane(name, keep)               the sidebar; a lane's cards
    read(ids) / refresh() / pause(on)        marks; a round now; out of sight
    wait(since, seconds)                     blocks until something changed → version
    thread(id)                               a thread as a tree: numbers and depths
    post(body) / act(action, id)             write or answer; like, boost, bookmark
    config_text() / config_save(text)        the config file, edited in the app
    sync_*                                   sync with the other devices (core/sync)

demo: a made-up world instead of a server (tools/showcase.py, the one every screenshot
of fedtail shows), in a profile of its own — for the emulator's screenshots in CI.
"""

import json
import os
import platform
import threading
import time

REDIRECT = "fedtail://oauth"
DEMO_SERVER = "https://example.test"

_started = None
_lock = threading.Lock()
_s = {"core": None, "web": None, "demo": False, "profile": None}


def _answer(fn):
    """Run fn() → JSON of its value, or of {"error": …} (logged with its trace)."""
    try:
        return json.dumps(fn(), ensure_ascii=False)
    except Exception as e:  # noqa: BLE001 — the screen says what broke
        import logging
        logging.getLogger("fedtail.android").exception("bridge")
        return json.dumps({"error": f"{e.__class__.__name__}: {e}"}, ensure_ascii=False)


# ---- the stage ------------------------------------------------------------------------

def start(files_dir, cache_dir, lang="", demo=False):
    """Set the stage for the core and make it; → info() as JSON."""
    global _started
    t = time.monotonic()
    os.environ["XDG_CONFIG_HOME"] = os.path.join(files_dir, "config")
    os.environ["XDG_DATA_HOME"] = os.path.join(files_dir, "data")
    os.environ["XDG_CACHE_HOME"] = cache_dir
    os.environ.setdefault("HOME", files_dir)
    if lang:  # the phone's language, for ui.language = "auto"
        os.environ["LANG"] = os.environ["LC_ALL"] = f"{lang}.UTF-8"
    for d in ("config", "data"):
        os.makedirs(os.path.join(files_dir, d), exist_ok=True)
    _started = t
    with _lock:
        _make(bool(demo))
    return info()


def _make(demo):
    from fedtail import i18n
    from fedtail.core import auth, config, paths
    from fedtail.core.app import Core
    from fedtail.frontends.web.server import Web
    old = _s["core"]
    if old is not None:
        old.shutdown()
    profile = "demo" if demo else None
    where = paths.resolve(profile)
    where.ensure()
    cfg, _warnings = config.load(where.config_file)
    i18n.setup(cfg["ui"]["language"])
    kw = {}
    if demo:
        # the made-up posts come unread, so the demo shows "new below" and marks working
        cfg["feed"]["first_run_mark_read"] = False
        from tests.fakes import FakeApi
        from tools import showcase
        FakeApi.worlds = {}  # one world for every server: the showcase's
        FakeApi.world = showcase.world()
        kw["api_class"] = FakeApi
        if not auth.load(where.auth_file):
            auth.save(where.auth_file, {"server": DEMO_SERVER, "token": "demo"})
    core = Core(cfg, where, **kw)
    _s.update(core=core, web=Web(core, None), demo=demo, profile=profile)


def _core():
    if _s["core"] is None:
        raise RuntimeError("start() first")
    return _s["core"]


def info():
    """{'version', 'python', 'abi', 'ssl', 'store', 'profiles', 'sync', 'started_ms'}
    — or {'error', 'trace'}: the screen shows either."""
    out = {"python": platform.python_version(), "abi": platform.machine()}
    try:
        import ssl
        out["ssl"] = ssl.OPENSSL_VERSION
        from fedtail import version
        from fedtail.core import paths
        out["version"] = version.full()
        core = _s["core"]
        if core is not None:
            out["store"] = core.store.diag_counts()
            out["language"] = core.cfg["ui"]["language"]
        base = paths.data_base()
        out["profiles"] = sorted(p.name for p in base.iterdir() if p.is_dir()) \
            if base.is_dir() else []
        from fedtail.core.sync import crypto
        out["sync"] = crypto.available()
        out["demo"] = _s["demo"]
    except Exception as e:  # noqa: BLE001 — the screen says what broke, the app lives on
        import traceback
        out["error"] = f"{e.__class__.__name__}: {e}"
        out["trace"] = traceback.format_exc(limit=8)
    if _started is not None:
        out["started_ms"] = round((time.monotonic() - _started) * 1000)
    return json.dumps(out, ensure_ascii=False)


def state():
    def get():
        core = _core()
        a = core.auth or {}
        return {"logged_in": bool(core.logged_in), "demo": _s["demo"],
                "server": a.get("server", ""), "acct": a.get("acct", "")}
    return _answer(get)


# ---- logging in -------------------------------------------------------------------------

def login_begin(server):
    """→ {"url", "redirect"}: open url in a browser. redirect true — the server sends the
    code straight back to fedtail://oauth; false — it shows the code, to be pasted
    (a server that wouldn't take the app's address)."""
    def go():
        core = _core()
        server_ = (server or "").strip()
        if not server_:
            raise ValueError("no server")
        try:
            url = core.begin_login(server_, redirect=REDIRECT).result(60)
            return {"url": url, "redirect": True}
        except ValueError:
            raise  # http:// on the internet: not tried another way
        except Exception as e:  # noqa: BLE001 — refused the address: the pasted code then
            import logging
            logging.getLogger("fedtail.android").info("login with %s refused (%s): code",
                                                      REDIRECT, e)
            url = core.begin_login(server_).result(60)
            return {"url": url, "redirect": False}
    return _answer(go)


def login_finish(code):
    def go():
        me = _core().finish_login((code or "").strip()).result(60)
        return {"acct": me.get("acct", "")}
    return _answer(go)


# ---- reading ----------------------------------------------------------------------------

def open():  # noqa: A001 — what Kotlin calls it
    """Connect and start polling (once). → {"me", "lanes"}."""
    def go():
        core = _core()
        if core.me is None:
            core.connect().result(120)
            # the poller's first round before the first screen: it opens filled, not
            # empty (and not racing a round of its own)
            done = threading.Event()
            core.events.on("first_poll_done", lambda _n, _p: done.set())
            core.start_polling()
            done.wait(60)
        web = _s["web"]
        me = web.me()
        return {"me": {k: me.get(k) for k in ("me", "handle", "server", "version", "order",
                                                "start_at", "mark_read", "visibility")},
                "lanes": web.lanes()}
    return _answer(go)


def lanes():
    return _answer(lambda: _s["web"].lanes())


def lane(name, keep=False):
    """A lane's cards as the browser page gets them, each with its text as plain words
    too (the screens draw text; links and emojis come in a later step)."""
    def go():
        got = _s["web"].lane(name, bool(keep))
        _texts(got.get("posts", []))
        return got
    return _answer(go)


def read(ids_json):
    return _answer(lambda: _s["web"].read(list(json.loads(ids_json or "[]"))))


def refresh():
    def go():
        _core().poll_now()
        return {"ok": True}
    return _answer(go)


def pause(on):
    def go():
        _core().pause_polling(bool(on))
        return {"ok": True}
    return _answer(go)


def wait(since, seconds=25):
    """Blocks (call it off the main thread) until something in the lanes changed, or
    the time is up. → the version now: different from `since` — reload."""
    return int(_s["web"].wait(int(since), float(seconds)))


def _texts(posts):
    from fedtail.model.text import html_to_text
    for p in posts:
        p["text"] = html_to_text(p.get("html") or "")
        ctx = p.get("context")
        if ctx and ctx.get("text"):
            ctx["text"] = ctx["text"].strip()
    return posts


# ---- a thread, writing ------------------------------------------------------------------

def thread(post_id):
    """The whole thread around a post: depth-first, each card with its /N and depth."""
    def go():
        got = _s["web"].thread(post_id)
        _texts(got.get("posts", []))
        return got
    return _answer(go)


def post(body_json):
    """A new post or a reply: {"text", "reply_to"?, "visibility"?, "cw"?} — the web
    page's own call (visibility: a reply is never wider than what it answers)."""
    return _answer(lambda: _s["web"].post(json.loads(body_json or "{}")))


def act(action, post_id):
    """like / share / bookmark, toggled; → the card as it is now."""
    def go():
        got = _s["web"].act(action, post_id)
        return _texts([got])[0]
    return _answer(go)


# ---- the config, edited in the app (no settings pages: the file itself) ------------------

def config_text():
    def go():
        from fedtail.core import config
        core = _core()
        path = core.paths.config_file
        config.load(path)  # the commented example is written if there's none yet
        return {"text": path.read_text("utf-8"), "path": str(path)}
    return _answer(go)


def config_save(text):
    """Checked before it is written: a broken file never lands. Saved → the core is made
    anew with it (the screens open again). → {"ok"} or {"error"} saying what is wrong."""
    def go():
        import tomllib

        from fedtail.core import config
        try:
            config.validate(tomllib.loads(text))
        except tomllib.TOMLDecodeError as e:
            raise ValueError(f"TOML: {e}") from None
        path = _core().paths.config_file
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text, "utf-8")
        os.replace(tmp, path)
        with _lock:
            _make(_s["demo"])
        return {"ok": True}
    return _answer(go)


# ---- sync with the account's other devices ----------------------------------------------

def sync_status():
    """→ {"enabled", "key", "login", "where", "pending", "last": {at, error}}."""
    def go():
        core = _core()
        st = core.sync_status()
        if st is None:
            return {"enabled": False, "key": bool(core.sync_key())}
        return {"enabled": True, **st}
    return _answer(go)


def sync_login_begin():
    """The sync server's own token (read:accounts only): → {"url"} — its page shows a
    code, sync_login_finish takes it."""
    def go():
        pending = _core().sync_login_begin()
        _s["sync_pending"] = pending
        return {"url": pending["url"]}
    return _answer(go)


def sync_login_finish(code):
    def go():
        pending = _s.get("sync_pending")
        if not pending:
            raise RuntimeError("sync_login_begin() first")
        _core().sync_login_end(pending, (code or "").strip())
        _s["sync_pending"] = None
        return {"instance": pending["instance"]}
    return _answer(go)


def sync_key():
    return _answer(lambda: {"key": _core().sync_key() or ""})


def sync_join(text):
    return _answer(lambda: {"kid": _core().sync_join(text)})


def sync_now():
    def go():
        done = _core().sync_now()
        return {"sent": done[0], "got": done[1]} if done else {"failed": True}
    return _answer(go)
