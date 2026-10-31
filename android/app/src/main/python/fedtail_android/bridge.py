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
    hub()                                    every lane by kind, its count, its first unread
    pin(names)                               which lanes are the overview's tiles, in order
    read(ids) / refresh() / pause(on)        marks; a round now; out of sight
    lane_clear(name, confirmed)              "Clear" over a lane of events only
    wait(since, seconds)                     blocks until something changed → version
    thread(id)                               a thread as a tree: numbers and depths
    post(body) / act(action, id)             write or answer; like, boost, bookmark
    menu(id) / thread_act(action, id)        a card's ⋯: its state; follow or leave the thread
    resolve(url)                             a link in a post: a thread here, or the browser
    command(line, confirmed) / command_preview(line)   Point's command line (ui.command_line)
    settings() / setting_set(…) / settings_apply()   the settings page: the config's options
                                             by chapter, written into the file one at a time
    config_text() / config_save(text)        the config file, edited in the app
    places() / page(name, arg, tab, cursor)  every place of the ≡ menu (common/places.py:
                                             search, lists, silence, the server, help…) as data
    place_act(act, confirmed, values, answer)   a place's button, a form sent, a line typed
    post_menu(id) / link(url, confirmed, chosen)  a card's ⋯ as the windows have it, each
                                             item done the windows' way (common/links.py)
    account(id, show) / profile_act(…)       a profile and its buttons (common/profile.py)
    upload(path, name) / vote(id, choices) / editor()   attachments, polls, the editor's facts

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

def start(files_dir, cache_dir, lang="", demo=False, logs=False, device_json=None):
    """Set the stage for the core and make it; → info() as JSON. logs: the desktop's
    session logs and crash traces (diag.setup) in the profile's data folder — the app
    asks for them; the tests on a desktop don't. device_json: the phone's facts
    (SelfCheck.kt's deviceFacts) — the log's header, the bug report and the issue's
    draft say the phone and its Android, not "Linux" and a kernel."""
    global _started
    from fedtail import diag
    t = time.monotonic()
    diag.running("android", json.loads(device_json) if device_json else None)
    os.environ["XDG_CONFIG_HOME"] = os.path.join(files_dir, "config")
    os.environ["XDG_DATA_HOME"] = os.path.join(files_dir, "data")
    os.environ["XDG_CACHE_HOME"] = cache_dir
    os.environ.setdefault("HOME", files_dir)
    if lang:  # the phone's language, for ui.language = "auto"
        os.environ["LANG"] = os.environ["LC_ALL"] = f"{lang}.UTF-8"
    for d in ("config", "data"):
        os.makedirs(os.path.join(files_dir, d), exist_ok=True)
    _started = t
    _s["cache_dir"] = cache_dir
    _s["logs"] = bool(logs)
    with _lock:
        _make(bool(demo))
    return info()


def _make(demo):
    from fedtail import i18n
    from fedtail.core import auth, config, paths
    from fedtail.core.app import Core
    from fedtail.frontends.web import server as web_server
    from fedtail.frontends.web.server import Web
    web_server.PIC_THROUGH = False  # the phone loads pictures by their own addresses
    old = _s["core"]
    if old is not None:
        old.shutdown()
    for lock in _s.get("held") or ():  # the merged profiles' locks: theirs again
        lock.close()
    _s["held"] = []
    profile = "demo" if demo else None
    where = paths.resolve(profile)
    where.ensure()
    cfg, _warnings = config.load(where.config_file)
    if _phone_defaults(where):
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
    if _s.get("logs") and not _s.get("logging"):
        from fedtail import diag
        diag.setup(where, cfg)
        diag.session_header(where.profile)
        _s["logging"] = True
    core = Core(cfg, where, **kw)
    held = []
    if not demo:  # "all accounts in one window" (ui.merge or the menu): the desktop's way
        from fedtail.__main__ import merge_accounts
        core, held = merge_accounts(core, where.profile)
    _s.update(core=core, web=Web(core, None), demo=demo, profile=profile, held=held)


# what the phone does otherwise than the desktop: written into the config file once (the
# example the core writes says the desktop's defaults); after that the file is the truth
PHONE_DEFAULTS = {("window", "command_line"): "false"}  # Point's line: off, a word away
PHONE_MARK = "phone_defaults"


def _phone_defaults(where):
    import re
    mark = where.data_dir / PHONE_MARK
    if mark.exists() or not where.config_file.exists():
        return False
    text = where.config_file.read_text("utf-8")
    for (section, key), value in PHONE_DEFAULTS.items():
        head = re.search(rf"^\[{section}\]\s*$", text, re.M)
        if head is None:
            continue
        nxt = re.search(r"^\[", text[head.end():], re.M)
        end = head.end() + (nxt.start() if nxt else len(text[head.end():]))
        body = re.sub(rf"^{key} = .*$", f"{key} = {value}", text[head.end():end], count=1,
                      flags=re.M)
        text = text[:head.end()] + body + text[end:]
    where.config_file.write_text(text, "utf-8")
    mark.write_text("1\n", "utf-8")
    return True


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
            out["store"] = core.store_counts()
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
        net = core.cfg.get("net") or {}
        return {"logged_in": bool(core.logged_in), "demo": _s["demo"],
                "server": a.get("server", ""),
                "acct": a.get("acct", ""),  # ours: auth.json, not a server's answer
                # net.proxy_at_login: the login screen's proxy field, and what it holds
                "proxy_at_login": bool(net.get("proxy_at_login")),
                "proxy": str(net.get("proxy") or "")}
    return _answer(get)


# ---- logging in -------------------------------------------------------------------------

def login_begin(server, proxy=None):
    """→ {"url", "redirect"}: open url in a browser. redirect true — the server sends the
    code straight back to fedtail://oauth; false — it shows the code, to be pasted
    (a server that wouldn't take the app's address). proxy: the login screen's proxy
    field (net.proxy_at_login), None — no such field."""
    def go():
        core = _core()
        server_ = (server or "").strip()
        if not server_:
            raise ValueError("no server")
        if proxy is not None:
            core.set_proxy(proxy)
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
    return _answer(_plain(go))


def login_finish(code):
    def go():
        me = _s["web"].core.acc(_core().finish_login((code or "").strip()).result(60))
        return {"acct": me.handle if me is not None else ""}  # ours: the phone's word for it
    return _answer(_plain(go))


def _plain(fn):
    """The login screen shows the error under the button: the core's ValueError is
    already a sentence for a person ("can't reach …"), not "ValueError: …"."""
    def run():
        try:
            return fn()
        except ValueError as e:
            return {"error": str(e)}
    return run


# ---- reading ----------------------------------------------------------------------------

def open():  # noqa: A001 — what Kotlin calls it
    """Connect and start polling (once). → {"me", "lanes"}."""
    def go():
        core = _core()
        if core.me is None:
            core.connect().result(120)
        if getattr(core, "_poller", None) is None:  # a background round made it: no poller
            # the poller's first round before the first screen: it opens filled, not
            # empty (and not racing a round of its own)
            done = threading.Event()
            core.events.on("first_poll_done", lambda _n, _p: done.set())
            core.start_polling()
            if getattr(core, "_poll_count", 0) == 0:  # else round 1 was a background one
                done.wait(60)
        web = _s["web"]
        me = web.me()
        out = {k: me.get(k) for k in ("me", "handle", "server", "version", "order",
                                      "start_at", "mark_read", "visibility", "sensitive_media",
                                      "expand_cw", "dwell_ms")}
        out["command_line"] = bool(core.cfg["ui"]["command_line"])
        out["prefetch"] = core.cfg["feed"].get("prefetch", "previews")  # pictures ahead
        out["overview"] = core.cfg["phone"]["overview"]
        out["layout"] = core.cfg["phone"]["layout"]
        out["push"] = core.cfg["phone"]["push"]
        out["merged"] = bool(_s["web"].merged())
        out["accounts"] = sum(1 for p in _profiles() if p["logged_in"])
        return {"me": out, "lanes": web.lanes()}
    return _answer(go)


def _profiles():
    from fedtail.core import profiles
    try:
        return profiles.listing()
    except Exception:  # noqa: BLE001 — one account then
        return []


def lanes():
    return _answer(lambda: _s["web"].lanes())


def lane(name, keep=False):
    """A lane's cards as the browser page gets them, each with its text as plain words
    too (the screens draw text; links and emojis come in a later step)."""
    def go():
        got = _s["web"].lane(name, bool(keep))
        _texts(got.get("posts", []))
        if got.get("empty_browse") and not got.get("posts"):
            # a browsed lane its server gives nothing for: said in the lane (the windows')
            from fedtail.i18n import _
            got["info"] = _("browse_empty")
        return got
    return _answer(go)


def on_screen(ids_json):
    """The posts on the phone's screen: their numbers asked again in a while → {ok}."""
    return _answer(lambda: _s["web"].on_screen(json.loads(ids_json or "[]")))


def stood(lane, key, end=False):
    """The card on top of the phone's screen, the scroll standing (LaneModel.stood):
    where the lane opens next time, here and in every other interface; end — at the
    lane's end → {ok}."""
    return _answer(lambda: _s["web"].stood(lane, key, bool(end)))


def lane_set(body_json):
    """A lane's switches from its header (the windows' and the page's): all / posts only /
    unread only, a conversation a card, the media funnel → {ok}; reload the lane."""
    return _answer(lambda: _s["web"].lane_set(json.loads(body_json or "{}")))


def find(name, query):
    """The posts of a lane with every word (common/find.py) → {ids, text}."""
    return _answer(lambda: _s["web"].find(name, query or ""))


def find_everywhere(query):
    """What's stored in every lane → {hits: [{lane, item, id, title}], text}."""
    return _answer(lambda: _s["web"].find_everywhere(query or ""))


def find_deeper(name, query):
    """Further back than the lane shows: it grows down to an older match → {more, total,
    text}; reload the lane."""
    return _answer(lambda: _s["web"].find_deeper(name, query or ""))


def reveal(name, index):
    """The lane loaded down to a match "in every lane" found further back than it shows
    (the windows' find) → {grew}."""
    return _answer(lambda: _s["web"].reveal(name, index))


def demo_happen(what, target, text):
    """The demo world only (the UI tests on the emulator, androidTest): something done
    elsewhere while a screen shows it, brought by a round as from a server — "answer":
    someone answers target in its thread (the thread open on screen grows by itself, as
    tests/scenario.py's watch_thread holds every interface to). → {id}."""
    def go():
        if not _s.get("demo"):
            raise RuntimeError("the demo world only")
        from datetime import UTC, datetime

        from tests.fakes import FakeApi, status
        w = FakeApi.world
        if what != "answer" or target not in w.statuses:
            raise ValueError(f"{what} {target}")
        parent = w.statuses[target]
        sid = str(max(int(i) for i in w.statuses if i.isdigit()) + 1)  # newer than any
        st = status(sid, parent["account"], target, parent["account"]["id"], vis="public",
                    text=text)
        st["created_at"] = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        w.add(st, home=True)
        _core().poll_once()
        return {"id": sid}
    return _answer(go)


def poll_refresh(post_id):
    """Fresh counts for a post's poll → the card."""
    def go():
        return _texts([_s["web"].poll_refresh(post_id)])[0]
    return _answer(go)


def place_act(act_json, confirmed=False, values_json=None, answer=None):
    """A place's button (act = [place, key, data]), with the place's form (values) and a
    line typed when it asked for one (answer): → {message, confirm, ask, open, compose,
    copy, refresh}."""
    def go():
        act = json.loads(act_json)
        body = {"act": act, "confirmed": bool(confirmed)}
        if values_json:
            body["values"] = json.loads(values_json)
        if answer is not None:
            body["answer"] = str(answer)
        got = _s["web"].place_act(body)
        if got.get("reload"):  # another account: the core was made anew for it
            _s["core"] = _s["web"].core._core if hasattr(_s["web"].core, "_core") \
                else _s["web"].core
        return got
    return _answer(go)


# ---- every place: what the windows' ≡ menu opens, as data (common/places.py) -------------

def places():
    """The ≡ menu's places: [{name, title}] — search, lists, silence, the server…; with
    ui.arts_mode on, first a line saying so (name "", as the windows' menu marks it)."""
    def go():
        from fedtail.i18n import _
        out = _s["web"].place_menu()
        if _core().cfg["ui"].get("arts_mode"):
            out = [{"name": "", "title": _("tender_arts"), "tip": _("tender_arts_tip")}] + out
        return out
    return _answer(go)


def page(name, arg="", tab="", cursor=""):
    """A place as the windows and the browser page draw it: {name, title, arg, hint,
    tabs, tab, rows: [{kind: item|post|account|heading|html, title, line, key, buttons,
    post?, account?, html?}], form: [{name, label, value, kind, choices, tip}], submit,
    more, empty}. A post row's card comes with its words, as a lane's."""
    def go():
        got = _s["web"].page(name, arg or "", tab or "", cursor or "")
        _texts([r["post"] for r in got["rows"] if r.get("post")])
        return got
    return _answer(go)


# ---- a card's ⋯ as the windows have it, a profile ----------------------------------------

def post_menu(post_id):
    """{subscribed, muted, own, items: [{kind: link|open|copy|separator|quote_reply|lists|
    long_form|translate, label, url, text, page?}]} — common/actions.menu, in its order."""
    return _answer(lambda: _s["web"].post_menu(post_id))


def link(url, confirmed=False, chosen_json=None, shown_json=None):
    """A fedtail: link of the ⋯ menu (edit, delete, mute, report, translate…), done the
    windows' way: → {message, confirm, choose, open, compose, copy, alias, read,
    refresh}; asked again with confirmed / chosen ({key, ticked}) when it asked. shown:
    the ids of the cards on screen — "read up to here" counts over them (here, by the one
    rule) and says which it marked ("read")."""
    def go():
        chosen = json.loads(chosen_json) if chosen_json else None
        shown = json.loads(shown_json) if shown_json else ()
        got = _s["web"].link(url, bool(confirmed), chosen, shown)
        compose = got.get("compose")
        if compose and compose.get("text"):
            compose["text"] = str(compose["text"])
        return got
    return _answer(go)


def account(acc_id, show=None):
    """A profile: {account, relation, meta, note_line, actions: [{key, label, tip,
    primary}], shows, show_tip, posts} — the web page's, cards with their words."""
    def go():
        got = _s["web"].account(acc_id, show or None)
        _texts(got.get("posts", []))
        return got
    return _answer(go)


def account_more(acc_id, show=None, max_id="", cursor=""):
    """A profile's next posts: my server's, then their own server's (Web.account_more)
    → {posts, max_id, older: {label, cursor} or null}."""
    def go():
        got = _s["web"].account_more(acc_id, show or None, max_id or "", cursor or "")
        _texts(got.get("posts", []))
        return got
    return _answer(go)


def profile_act(acc_id, key, answer=None, confirmed=False, chosen_json=None):
    """A profile's button (follow, mute for a while, a note, lists…) → as link()."""
    def go():
        chosen = json.loads(chosen_json) if chosen_json else None
        return _s["web"].profile_act(acc_id, key, answer, bool(confirmed), chosen)
    return _answer(go)


# ---- writing: attachments, polls, what the editor knows ----------------------------------

def upload(path, name=""):
    """A picture or a video the phone handed over (copied into the app's cache first):
    kept for the post to come → {"token", "size"}; the file in the cache goes."""
    def go():
        with _builtin_open(path, "rb") as f:
            data = f.read()
        try:
            os.remove(path)
        except OSError:
            pass
        return _s["web"].upload(data, name or os.path.basename(path))
    return _answer(go)


def _builtin_open(path, mode):
    import builtins
    return builtins.open(path, mode)


def vote(post_id, choices_json):
    """A poll answered: choices are the options' numbers → the card as it is now."""
    def go():
        got = _s["web"].vote(post_id, json.loads(choices_json or "[]"))
        return _texts([got])[0]
    return _answer(go)


def editor():
    """The editor's facts: the server's limits, the languages to pick from, the poll's
    lengths, spell checking on or off, the default visibility."""
    def go():
        facts = _s["web"].editor_facts()
        facts["visibility"] = _core().default_visibility()
        return facts
    return _answer(go)


def draft_start(reply_to="", quote="", edit="", invite=False):
    """The editor's start: the draft kept for it, or the reply's mentions (Web)."""
    return _answer(lambda: _s["web"].draft_start(reply_to or "", quote or "", edit or "",
                                                 bool(invite)))


def draft_save(key, snap_json):
    return _answer(lambda: _s["web"].draft_save(key, json.loads(snap_json or "{}")))


def draft_drop(key):
    return _answer(lambda: _s["web"].draft_drop(key))


def preview(body_json):
    """The post as it will read (Qt's preview): {title, head, cw, parts: [html], back,
    send} — the parts as safe HTML."""
    return _answer(lambda: _s["web"].preview(json.loads(body_json or "{}")))


def complete(before):
    """#tags, @names, :emoji: for what is being typed (Web.complete)."""
    return _answer(lambda: _s["web"].complete(before))


# ---- the server's announcements (ui.announcements = "banner"): the windows' strip --------

ANNOUNCE_QUICK = ("👍", "❤️", "😂", "🎉")  # reactions offered under each (qt/announce.py)


def announcements():
    """The announcements not dismissed yet, oldest first, for the strip over the lanes
    (the windows' AnnounceBar) → {"items": [{id, text, head, reactions: [{name, count,
    me}]}], "ok", "tip"}; none when ui.announcements is "off"."""
    def go():
        from fedtail.i18n import _
        from fedtail.model.text import html_to_text
        core = _core()
        if core.cfg["ui"]["announcements"] == "off":
            return {"items": []}
        got = list(_s["web"].core.announcements().result() or ())  # the View's: Announcement
        reacting = core.supports("announcement_reactions")
        out = []
        for i, a in enumerate(got):
            more = f" · {_('announce_more', n=len(got) - 1)}" if i == 0 and len(got) > 1 else ""
            stamp = a.published.astimezone().strftime("%d.%m.%Y") if a.published else ""
            have = {r.name: r for r in a.reactions}
            names = list(have) + [e for e in ANNOUNCE_QUICK if e not in have] if reacting \
                else []
            out.append({"id": a.id, "text": html_to_text(a.html or "").strip(),
                        "head": f"📢 {_('announce_title')} {stamp}{more}".strip(),
                        "reactions": [{"name": n, "count": have[n].count if n in have else 0,
                                       "me": bool(have[n].me) if n in have else False}
                                      for n in names
                                      if n in have or len(n) <= 4]})
        return {"items": out, "ok": _("announce_ok"), "tip": _("tip_announce_ok")}
    return _answer(go)


def announcement_dismiss(aid):
    """"Got it": the server remembers it (other clients stop showing it too) → {ok}."""
    def go():
        _core().dismiss_announcement(str(aid)).result()
        return {"ok": True}
    return _answer(go)


def announcement_react(aid, name, on):
    """A reaction to an announcement put on or taken off → {ok}."""
    def go():
        _core().react_announcement(str(aid), str(name), bool(on)).result()
        return {"ok": True}
    return _answer(go)


def quote_lines(text):
    """A post's words as a quote for the answer (the ⋯ menu's "Quote in reply"): each line
    under post.quote_prefix, the leading @mentions left out (the reply has its own) →
    {text} — the windows' way (model/text.quote_lines)."""
    def go():
        from fedtail.model.text import quote_lines as ql
        prefix = _core().cfg["post"].get("quote_prefix", "> ") or "> "
        return {"text": ql(str(text or ""), prefix, strip_mentions=True)}
    return _answer(go)


def compose_check(body_json):
    """As the text is typed: characters of the limit, a chain's parts, hints."""
    return _answer(lambda: _s["web"].compose_check(json.loads(body_json or "{}")))


def format_text(body_json):
    """A formatting button (post.format_bar, common/markup.py — the windows' own) on the
    text: {name, text, start, end} → {text, start, end}; positions are Kotlin's (UTF-16).
    The buttons themselves come with editor(): "format_bar"."""
    return _answer(lambda: _s["web"].format_text(json.loads(body_json or "{}")))


def add_language(code):
    """The editor's "Another language…": a code it lists from then on → {code, label}."""
    return _answer(lambda: _s["web"].add_language(code))


# the overview's sections, in the order "read in a row" walks them: what is addressed to
# you first, then what you follow, then the lists; lanes without counts are only browsed —
# each lane's by its rule (common/sidebar.hub_kind), never its name
PEEK = 90


def hub():
    """The overview of every lane: {"sections": [{"key": you|reading|lists|browse,
    "lanes": [{name, title, unread, peek}]}], "order": [lanes with news, in reading order],
    "unread", "with_news"}. peek: who and what of the lane's first unread post."""
    def go():
        from fedtail.frontends.common import sidebar
        core = _core()
        view = _s["web"].core
        sections = {k: [] for k in ("you", "reading", "lists", "browse")}
        group = ""
        for pos, x in enumerate(_s["web"].lanes()):
            name = x["name"]
            group = x.get("group") or group  # the set's section: given on its first lane
            lane = core.lane_by_name.get(name)
            lazy = lane is None or lane.lazy or lane.source is None
            kind = sidebar.hub_kind(view, name)
            unread = 0 if kind == "browse" else int(x["unread"] or 0)
            sections[kind].append({"name": name, "title": x["title"], "unread": unread,
                                   # where the set puts it (lanes.preset, the sidebar's
                                   # order) and under which of its sections
                                   "pos": pos, "group": group if x.get("section") else "",
                                   # "of them new": what the last update brought
                                   "fresh": int(x.get("fresh") or 0) if unread else 0,
                                   # a lane holds its newest feed.render_limit posts: as many
                                   # unread means there may be more past them ("300+")
                                   "capped": unread >= core.cfg["feed"]["render_limit"],
                                   "peek": sidebar.peek(view, name, PEEK)
                                   if unread and not lazy else ""})
        # within a section the lanes stand as the set has them (lanes.preset)
        walk = [x for k in ("you", "reading", "lists") for x in sections[k]]
        every = [x for v in sections.values() for x in v]
        return {"sections": [{"key": k, "lanes": v} for k, v in sections.items() if v],
                "pinned": [n for n in core.pinned_tiles() if any(x["name"] == n for x in every)],
                "order": [x["name"] for x in walk if x["unread"]],
                "unread": sum(x["unread"] for x in walk),
                "with_news": sum(1 for x in walk if x["unread"]),
                "fresh": sum(x["fresh"] for x in walk),
                "slow": _slow_words(core)}
    return _answer(go)


def _slow_words(core):
    """How fresh the lanes are and slow mode, for the overview's top: "⟳ updating the
    lanes…", "updated at 14:32 · slow · next at 14:45"; "" before the first round."""
    from fedtail.frontends.common import sidebar
    return sidebar.status_words(core)


def pin(names_json):
    """The tiles of the overview, in their order (the core keeps them and sync carries
    them to the other devices: sync.tiles). [] — every counted lane is a tile."""
    def go():
        _core().set_pinned_tiles(list(json.loads(names_json or "[]")))
        return {"ok": True}
    return _answer(go)


def older(name, ahead=False):
    """"Earlier" at a lane's top: older posts from the server (as the windows' button;
    history counts as read). → {"n": how many came}. ahead: the button came in sight —
    core.older_ahead decides (reading.older_ahead); "asked": False when it didn't."""
    return _answer(lambda: _s["web"].older(name, bool(ahead)))


def read(ids_json, lane=None):
    """Seen on screen: post ids, and event rows' keys ("event:<id>": the events seen up to
    it, LaneModel.read) → {ok}. lane: "mark all read" over it — its events seen too."""
    return _answer(lambda: _s["web"].read([str(i) for i in json.loads(ids_json or "[]")],
                                          lane or None))


def lane_read(name):
    """"Mark all read" over a lane, as the windows' button: every post of it (not only
    the ones loaded on the phone), its events seen too → {ok, n}."""
    def go():
        web = _s["web"]
        ids = web.core.mark_lane_read(web._lane_name(name))
        return {"ok": True, "n": len(ids)}
    return _answer(go)


def lane_clear(name, confirmed=False):
    """"Clear" over a lane of events only: every notification, on the server too →
    {confirm} first, then {refresh}."""
    return _answer(lambda: _s["web"].lane_clear(name, bool(confirmed)))


def refresh():
    """⟳ / the pull: a round now, answered when it is over (a minute at most) with how
    it went — {"ok", "message": "Updated: 3 new"…} (common/results.refresh_text, the
    windows' words)."""
    def go():
        return _s["web"].refresh()
    return _answer(go)


def pause(on):
    def go():
        _core().pause_polling(bool(on))
        return {"ok": True}
    return _answer(go)


def network(wifi):
    """The phone's network changed (or the app came back): phone.stream says whether
    the live stream runs — "always", "wifi" (only on Wi-Fi), "off"."""
    def go():
        core = _core()
        mode = (core.cfg.get("phone") or {}).get("stream", "always")
        want = mode == "always" or (mode == "wifi" and bool(wifi))
        core.stream_allowed(want)
        return {"ok": True, "stream": want}
    return _answer(go)


def theme():
    """The phone's colours: the theme of ui.theme (the windows' files, the web page's
    reading of them) → {"name", "light", "colors": {bg, card, text, muted, line, accent,
    accent-text, unread, ctx, danger}}; colors {} — the phone's own light or dark."""
    def go():
        web = _s["web"]
        colors, light, _family = web.theme_colors()
        return {"name": web.theme_name(), "light": light, "colors": colors,
                "font": _theme_fonts(web.theme_name())}
    return _answer(go)


# the phone's buttons that have a theme picture: the app's word → iconpack's name
PICTURES = {"reply": "reply", "boost": "boost", "like": "star", "liked": "star_full",
            "bookmark": "bookmark", "more": "more", "refresh": "refresh", "send": "send",
            "write": "edit", "menu": "menu", "attach": "attach", "poll": "poll",
            "close": "close", "settings": "settings", "thread": "thread"}


def pictures():
    """The theme's own pictures for the phone's buttons (iconpack: its set, coloured as
    [pictures] says, the windows' own): {word: {"svg": text} | {"png": path}}; {} — the
    theme has no set of its own (system, words: the phone's icons)."""
    def go():
        from types import SimpleNamespace

        from fedtail.frontends import iconpack, themefile
        web = _s["web"]
        try:
            theme, _w = themefile.load(web.theme_name())
        except Exception:  # noqa: BLE001 — the phone's icons
            return {}
        if not iconpack.uses_set(iconpack.mode(_core().cfg, theme.get("shape"))):
            return {}
        pset = iconpack.for_theme(SimpleNamespace(icon_dirs=theme.get("icon_dirs") or (),
                                                  pictures=theme.get("pictures") or {}))
        colors, _light, _f = web.theme_colors()
        accent = colors.get("accent") or "#1f5fa8"
        out = {}
        for word, name in PICTURES.items():
            pic = iconpack.picture(pset, name, accent, True, colors.get("card"))
            if pic is None:
                continue
            out[word] = {"svg": pic.text} if pic.kind == "svg" else {"png": pic.path}
        return out
    return _answer(go)


def _theme_fonts(name):
    """The theme's fonts as files the phone can load: the first family of [font] family
    (and mono) that comes with fedtail (data/themes/fonts: PT Sans, IBM Plex, Nunito…) —
    the phone has none of Tahoma or DejaVu; → {"text": {regular, bold, italic,
    bold_italic}, "mono": {…}, "scale": post_scale}, a style with no file of its own
    left out ({} — the phone's own font)."""
    import re
    from pathlib import Path

    from fedtail.frontends import themefile
    try:
        theme, _w = themefile.load(name)
    except Exception:  # noqa: BLE001 — the phone's font then
        return {}
    font = theme.get("font") or {}
    files = [Path(f) for f in themefile.builtin_fonts()]

    def squash(text):
        return re.sub(r"[^a-z0-9]", "", text.lower())

    def styles(family_list):
        for fam in str(family_list or "").split(","):
            want = squash(fam)
            mine = [f for f in files if squash(f.stem.split("-")[0]) == want]
            if not mine:
                continue
            out = {}
            for f in mine:
                rest = f.stem.lower()
                bold, italic = "bold" in rest, "italic" in rest
                key = ("bold_italic" if italic else "bold") if bold else \
                    ("italic" if italic else "regular")
                out.setdefault(key, str(f))
            if "regular" in out:
                return out
        return {}
    got = {k: v for k, v in (("text", styles(font.get("family"))),
                             ("mono", styles(font.get("mono")))) if v}
    if got and font.get("post_scale"):
        got["scale"] = float(font["post_scale"])
    return got


def notes(since):
    """What to tell the phone's notification shade since the note numbered `since`
    (notifytext's words, by notify.privacy): {"notes": [{title, body, lane, thread}],
    "n": the newest note's number, "when_focused", "enabled"}."""
    def go():
        from fedtail.frontends.common import sidebar
        got, n = _s["web"].notes_since(int(since))
        core = _core()
        cfg = core.cfg["notify"]
        # the number on the launcher's icon (ui.icon_count — the windows' tray number);
        # launchers that show numbers take it from the notes
        view = _s["web"].core
        names = [x["name"] for x in _s["web"].lanes()]
        count = sidebar.icon_total(view, core.cfg, sidebar.counts(view, names)) \
            if core.cfg["ui"].get("icon_count") else 0
        return {"notes": got, "n": n, "enabled": bool(cfg.get("enabled", True)),
                "when_focused": bool(cfg.get("when_focused", False)), "count": int(count)}
    return _answer(go)


def act_as(post_id, tag, action):
    """★ / ♻ / ↩ from another account (all accounts in one): → {message} or, for a
    reply, {compose: {reply_to}, post: the post as that account sees it}."""
    def go():
        got = _s["web"].act_as(post_id, tag, action)
        if got.get("post"):
            _texts([got["post"]])
        return got
    return _answer(go)


def themes():
    """≡ → Try a theme: {current, configured, themes: [{name, label, on}], title}."""
    return _answer(lambda: _s["web"].themes())


def try_theme(name):
    """A theme for this run (the config stays): the phone repaints from theme()."""
    return _answer(lambda: _s["web"].try_theme(name))


def merge(on):
    """All accounts in one window, on or off (the windows' menu item; kept in the main
    profile's state): the core made anew at once — the screens then start again."""
    def go():
        web = _s["web"]
        if bool(on) != web.merged():
            web.toggle_merge()
        with _lock:
            _make(_s["demo"])
        return {"merged": _s["web"].merged(), "reload": True}
    return _answer(go)


def push_on(endpoint, p256dh, auth):
    """UnifiedPush gave the app an address (its distributor's, on some server of the
    user's choice): my server pushes there from now on, encrypted to the phone's key
    (the connector's own; it decrypts). A push only wakes the app for a round."""
    def go():
        if not str(endpoint or "").startswith("https://"):
            raise ValueError("endpoint")
        _core().push_subscribe(str(endpoint), str(p256dh), str(auth)).result(60)
        return {"ok": True}
    return _answer(go)


def push_off():
    """No more pushes to this phone (phone.push = "off", the distributor gone)."""
    def go():
        _core().push_unsubscribe().result(60)
        return {"ok": True}
    return _answer(go)


def ready(files_dir, cache_dir, lang=""):
    """The core for a background round: made if this process has none yet (the app
    closed, the system woke it for the round); → {"logged_in"}."""
    def go():
        if _s["core"] is None:
            start(files_dir, cache_dir, lang, False, True)
        return {"logged_in": bool(_core().auth)}
    return _answer(go)


def background_round(since):
    """One round now, here (called off the main thread, the poller paused while the
    app is out of sight) → notes(since): what came meanwhile, for the shade."""
    def go():
        core = _core()
        if core.auth:
            if core.me is None:  # the system made the process for this round: connect
                core.connect().result(120)
            if core.slow_due():  # slow mode: a push or the system's round waits its turn
                core.poll_once()
        return json.loads(notes(since))
    return _answer(go)


def wait(since, seconds=25):
    """Blocks (call it off the main thread) until something in the lanes changed, a
    poll round began or ended, or the time is up. → the version now: different from
    `since` — reload; the same — status() for the overview's line only."""
    web = _s["web"]
    seen = getattr(web, "poll_seq", 0)
    return int(web.wait(int(since), float(seconds), poll_since=seen))


def status():
    """The overview's line: "⟳ updating the lanes…", "updated at 14:32 · slow · …"."""
    def go():
        from fedtail.frontends.common import sidebar
        core = _s["web"].core
        return {"text": _slow_words(core), "busy": sidebar.polling(core),
                # an open thread grew (replies from other servers) or a post in it changed
                "threads": getattr(_s["web"], "thread_seq", 0)}
    return _answer(go)


def _texts(posts):
    from fedtail.model.text import html_to_text
    for p in posts:
        p["text"] = html_to_text(p.get("html") or "")
        ctx = p.get("context")
        if ctx and ctx.get("text"):
            ctx["text"] = ctx["text"].strip()
    return posts


# ---- a thread, writing ------------------------------------------------------------------

def thread_progress(post_id):
    """threads.thread_progress: {"text", "bar", "stage"} of fetching the open thread's
    replies from its author's server ("" — nothing going on)."""
    return _answer(lambda: _s["web"].thread_progress(post_id))


def thread(post_id, at="post"):
    """The whole thread around a post: depth-first, each card with its /N and depth;
    "focus" — where it stands (at: "post" / "first_unread", common/links.py THREAD_AT)."""
    def go():
        got = _s["web"].thread(post_id, at or "post")
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


# ---- Point's command line (ui.command_line; off on the phone unless the file says on) ------

def command_preview(line):
    """What Enter would do with the line, in words ("" for an empty one)."""
    def go():
        from fedtail.frontends.common.commands import preview
        return {"text": preview(_s["web"].core, line or "")}  # the model view, as Qt's
    return _answer(go)


def command(line, confirmed=False):
    """→ {"ok", "message"?, "open": {"thread"|"account"}?, "confirm"?: ask, then again
    with confirmed} — the web page's own call."""
    return _answer(lambda: _s["web"].command(line or "", bool(confirmed)))


# ---- a card's ⋯ menu, links in posts ---------------------------------------------------

def menu(post_id):
    """What a card's ⋯ needs to say: {"subscribed", "muted", "own", "url"}."""
    def go():
        got = _s["web"].post_menu(post_id)
        url = next((x["url"] for x in got["items"] if x.get("kind") == "open" and x.get("url")),
                   "")
        return {k: got[k] for k in ("subscribed", "muted", "own")} | {"url": url}
    return _answer(go)


def thread_act(action, post_id):
    """sub / unsub / mute / unmute the thread a post is in → {"message"}."""
    return _answer(lambda: _s["web"].thread_act(action, post_id))


def resolve(url):
    """A link tapped in a post: {"found": "thread", "id"} when my server knows it as a
    post, {"found": "media", "kind", "url"} for a video or sound file (the own player,
    media.links_in_player — common/links.py decides, as for the windows), else
    {"found": "account"|None} — the screen opens the browser then."""
    def go():
        from fedtail.frontends.common.links import media_link
        kind = media_link(url)
        if kind and _core().cfg["ui"].get("links_in_player", True):
            return {"found": "media", "kind": kind, "url": url}
        try:
            return _s["web"].resolve(url)
        except Exception:  # noqa: BLE001 — unknown or slow: the browser
            return {"found": None}
    return _answer(go)


# ---- the settings page: the config file's options, one control each --------------------
# The file stays the truth: every change is written into it (config_update.set_option —
# the user's notes and order stay), checked first; the core is made anew once, when the
# page is left (settings_apply). Chapters, order and explanations are the example file's
# in the file's language; the desktop's terminal and browser chapters aren't shown here.
# Only what the phone does something with: the terminal's, the browser's and the command
# line's chapters stay off, and so do sound and notifications (no sound here; notifications
# come later, with their own settings); of [ui] and [debug] — the few the phone heeds
# (the rest is the Qt and GTK windows': fonts, docks, columns, the GTK header bar…).
NOT_ON_PHONE = {"tui", "web", "cli", "sound"}
ONLY_ON_PHONE = {
    "ui": {"language", "start_lane", "command_line", "expand_cw", "arts_mode", "links_in_app",
           "theme", "announcements"},
    # the shade heeds these; how the desktop shows a note (backend) is the desktop's
    "notify": {"enabled", "lanes", "except", "privacy", "when_focused", "filtered"},
    "debug": {"level", "mode"},
}


def _on_phone(o):
    from fedtail.core.config import internal_place
    section = internal_place(o.section, o.key)[0]  # the program's section of it
    return section not in NOT_ON_PHONE and \
        (section not in ONLY_ON_PHONE or o.key in ONLY_ON_PHONE[section])


def settings():
    """The desktop's settings window, as data (frontends/common/settings.py — the same
    chapters, names, explanations and choices; only what the phone heeds): →
    {"chapters": [{"title", "options": [{section, key, kind, title, about, value,
    default, choices: [[value, words]], changed, group, minimum}]}]}."""
    def go():
        from fedtail.frontends.common import settings as common
        out = []
        for ch in common.model(_s["web"].core):
            opts = [{"section": o.section, "key": o.key, "kind": o.kind, "title": o.title,
                     "about": o.about, "value": o.value, "default": o.default,
                     "choices": [[v, w] for v, w in o.choices], "changed": o.changed,
                     "group": o.group, "minimum": o.minimum}
                    for o in ch.options if _on_phone(o)]
            if opts:
                out.append({"title": ch.title, "options": opts})
        return {"chapters": out}
    return _answer(go)


def setting_set(section, key, value_json):
    """One option into the file — the desktop's way (core/config_edit: that one line,
    checked, config.toml.bak); null puts the default back. → {"ok", "value"} or {"error"}."""
    def go():
        from fedtail.frontends.common import settings as common
        value = json.loads(value_json)
        common.save(_s["web"].core, {(section, key): common.UNSET if value is None else value})
        _s["settings_changed"] = True
        now = common.option(common.model(_s["web"].core), f"{section}.{key}")
        return {"ok": True, "value": now.value if now else value,
                "changed": bool(now and now.changed)}
    return _answer(go)


def settings_apply():
    """Leaving the settings page: if anything changed, the core is made anew with the
    file (the screens open again). → {"restarted"}."""
    def go():
        if not _s.pop("settings_changed", False):
            return {"restarted": False}
        with _lock:
            _make(_s["demo"])
        return {"restarted": True}
    return _answer(go)


# ---- the self-check (dev builds): this phone, this account, read-only -------------------
# Each step reads — the server is asked, nothing is posted, liked or marked; it says ok
# or what broke, and how long it took. The report is the desktop's bug report (the logs,
# the config, the system — never the token or the database) with the steps added.
CHECKS = ("core", "server", "hub", "lanes", "browse", "thread", "pictures", "link",
          "places", "menus", "profile", "find", "editor", "notes", "theme", "slow",
          "settings", "sync")


def selfcheck_steps():
    return json.dumps(list(CHECKS))


def selfcheck_step(name):
    """One step → {"name", "ok", "ms", "detail"}."""
    t = time.monotonic()
    try:
        detail = _CHECK[name]()
        ok = True
    except Exception as e:  # noqa: BLE001 — the report says what broke
        import logging
        logging.getLogger("fedtail.android").exception("selfcheck %s", name)
        detail, ok = f"{e.__class__.__name__}: {e}", False
    return json.dumps({"name": name, "ok": ok, "ms": round((time.monotonic() - t) * 1000),
                       "detail": detail}, ensure_ascii=False)


def _check_core():
    got = json.loads(info())
    if got.get("error"):
        raise RuntimeError(got["error"])
    return (f"fedtail {got['version']}, Python {got['python']} {got['abi']}, "
            f"{got['ssl']}, db {got.get('store')}")


def _check_server():
    me = _s["web"].me()
    if not me.get("handle"):
        raise RuntimeError("not logged in")
    return f"@{me['handle']} on {me.get('server')}"


def _check_hub():
    got = json.loads(hub())
    if "error" in got:
        raise RuntimeError(got["error"])
    return f"{got['unread']} new in {got['with_news']} lanes; tiles {got['pinned'] or 'all'}"


def _lanes(lazy):
    core, out = _core(), []
    for x in _s["web"].lanes():
        lane = core.lane_by_name.get(x["name"])
        if lane is None or bool(lane.lazy or lane.source is None) != lazy:
            continue
        t = time.monotonic()
        got = _s["web"].lane(x["name"], True)
        out.append(f"{x['name']} {len(got.get('posts', []))} posts "
                   f"{round((time.monotonic() - t) * 1000)} ms")
    return "; ".join(out) or "none"


def _first_post(want=lambda p: True):
    for x in _s["web"].lanes():
        try:
            posts = _s["web"].lane(x["name"], True).get("posts", [])
        except Exception:  # noqa: BLE001
            continue
        for p in posts:
            if want(p):
                return p
    return None


def _check_thread():
    p = _first_post()
    if p is None:
        return "no posts to try"
    got = _s["web"].thread(p["sid"])
    return f"#{p.get('alias')}: {len(got.get('posts', []))} posts"


def _check_pictures():
    import requests

    from fedtail.core import remote
    from fedtail.version import USER_AGENT
    p = _first_post(lambda x: x.get("media") or (x.get("account") or {}).get("avatar"))
    if p is None:
        return "no pictures to try"
    urls = [m.get("preview") or m.get("url") for m in p.get("media", [])][:2]
    urls += [(p.get("account") or {}).get("avatar")]
    out = []
    for url in [u for u in urls if u]:
        t = time.monotonic()
        # never with the token, and the way the app itself fetches them (core/remote.py:
        # public addresses only, each redirect checked, the size capped)
        with remote.open_url(requests, url, timeout=20,
                             headers={"User-Agent": USER_AGENT}) as r:
            r.raise_for_status()
            got = remote.read(r, 16 * 1024 * 1024)
        out.append(f"{len(got) // 1024} KB {round((time.monotonic() - t) * 1000)} ms")
    return "; ".join(out)


def _check_link():
    p = _first_post(lambda x: x.get("url"))
    if p is None:
        return "no post with an address"
    got = _s["web"].resolve(p["url"])
    return f"{p['url'].split('/')[2]} → {got.get('found')}"


def _check_settings():
    got = json.loads(settings())
    if "error" in got:
        raise RuntimeError(got["error"])
    return f"{sum(len(c['options']) for c in got['chapters'])} options in " \
           f"{len(got['chapters'])} chapters"


def _check_sync():
    st = _core().sync_status()
    if st is None:
        return "off"
    last = st.get("last") or {}
    if last.get("error"):
        raise RuntimeError(last["error"])
    return f"{st.get('backend')} {st.get('where')}, pending {st.get('pending')}, " \
           f"last {last.get('at', '—')}"


# places that write or wait on a person: not opened by the self-check
NOT_CHECKED = {"login", "issue", "probe", "profile_edit", "report"}


def _check_places():
    """Every place of ≡ opened (reading only): how many rows each, how long."""
    out, bad = [], []
    for x in _s["web"].place_menu():
        name = x["name"]
        if not name or name in NOT_CHECKED:
            continue
        t = time.monotonic()
        try:
            got = _s["web"].page(name)
            out.append(f"{name} {len(got.get('rows', []))} "
                       f"{round((time.monotonic() - t) * 1000)} ms")
        except Exception as e:  # noqa: BLE001 — every place tried, the broken ones said
            bad.append(f"{name}: {e.__class__.__name__}: {e}")
    if bad:
        raise RuntimeError("; ".join(bad))
    return "; ".join(out)


def _check_menus():
    """A few cards' ⋯ menus: what each offers (nothing in them is done)."""
    out = []
    for x in _s["web"].lanes()[:4]:
        try:
            posts = _s["web"].lane(x["name"], True).get("posts", [])
        except Exception:  # noqa: BLE001
            continue
        for p in posts[:2]:
            got = _s["web"].post_menu(p["sid"])
            out.append(str(len(got.get("items", []))))
    return ("items: " + ", ".join(out)) if out else "no posts to try"


def _check_profile():
    """The first post's author: the profile, its buttons and the next page of posts."""
    p = _first_post(lambda x: (x.get("account") or {}).get("id"))
    if p is None:
        return "no posts to try"
    acc_id = p["account"]["id"]
    got = _s["web"].account(acc_id)
    more = ""
    if got.get("older") and not got["older"].get("cursor"):
        nxt = _s["web"].account_more(acc_id, None, got.get("max_id", ""), "")
        more = f", next page {len(nxt.get('posts', []))}"
    return f"@{(got.get('account') or {}).get('handle')}: {len(got.get('posts', []))} posts" \
        f"{more}"


def _check_find():
    p = _first_post(lambda x: len((x.get("text") or "").split()) > 2)
    if p is None:
        return "no words to look for"
    word = max(p["text"].split(), key=len)[:20]
    lanes_now = _s["web"].lanes()
    lane = next((x["name"] for x in lanes_now if x["start"]), lanes_now[0]["name"])
    got = _s["web"].find(lane, word)
    every = _s["web"].find_everywhere(word)
    return f"{word!r}: {len(got.get('ids', []))} here, {len(every.get('hits', []))} lanes"


def _check_editor():
    """What the editor shows (nothing is sent): its facts, the hints, completion."""
    facts = _s["web"].editor_facts()
    hint = _s["web"].compose_check({"text": "#selfchecktag " + "x" * 40})
    tags = _s["web"].complete("#a")
    return f"{len(facts.get('languages', []))} languages, limit {hint.get('limit')}, " \
        f"camel hint {'yes' if hint.get('camel') else 'no'}, {len(tags.get('items', []))} tags"


def _check_notes():
    got, n = _s["web"].notes_since(-1)
    cfg = _core().cfg["notify"]
    return f"notes {n}, enabled {cfg.get('enabled', True)}, privacy {cfg.get('privacy')}"


def _check_theme():
    got = json.loads(theme())
    if "error" in got:
        raise RuntimeError(got["error"])
    return f"{got.get('name')}, {len(got.get('colors', {}))} colours, " \
        f"{'light' if got.get('light') else 'dark'}"


def _check_slow():
    from fedtail.frontends.common import sidebar
    core = _core()
    fresh = sum(sidebar.fresh(core, x["name"]) for x in _s["web"].lanes())
    slow = core.slow_minutes()
    return f"slow mode {slow or 'off'}{(' · ' + sidebar.slow_words(core)) if slow else ''}, " \
        f"of them new {fresh}"


_CHECK = {"core": _check_core, "server": _check_server, "hub": _check_hub,
          "lanes": lambda: _lanes(False), "browse": lambda: _lanes(True),
          "thread": _check_thread, "pictures": _check_pictures, "link": _check_link,
          "places": _check_places, "menus": _check_menus, "profile": _check_profile,
          "find": _check_find, "editor": _check_editor, "notes": _check_notes,
          "theme": _check_theme, "slow": _check_slow,
          "settings": _check_settings, "sync": _check_sync}


def selfcheck_report(results_json, device_json):
    """The steps and the phone's facts into the log folder, then the desktop's bug report
    (diag.bug_report: logs, config, system; no token, no database) → {"path"}."""
    def go():
        from datetime import datetime

        from fedtail import diag
        core = _core()
        folder = diag.logs_dir(core.paths, core.cfg)
        folder.mkdir(parents=True, exist_ok=True)
        lines = [f"self-check {datetime.now():%Y-%m-%d %H:%M:%S}"]
        lines += [f"{k}: {v}" for k, v in json.loads(device_json or "{}").items()]
        for r in json.loads(results_json or "[]"):
            lines.append(f"{'ok ' if r.get('ok') else 'BAD'} {r.get('name'):9} "
                         f"{r.get('ms', 0):6} ms  {r.get('detail', '')}")
        (folder / "selfcheck.txt").write_text("\n".join(lines) + "\n", "utf-8")
        dest = os.path.join(_s.get("cache_dir") or str(core.paths.data_dir), "reports")
        os.makedirs(dest, exist_ok=True)
        for old in os.listdir(dest):  # one report at a time: the last one
            os.remove(os.path.join(dest, old))
        return {"path": str(diag.bug_report(core.paths, dest, core.cfg))}
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


