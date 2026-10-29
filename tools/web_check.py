"""A walk through the web interface on a fake server: the page in a real browser at a
desktop's and a phone's width, every lane, the ≡ menu and a post's ⋯ menu (and what's in
them), the editor, a thread, a profile, the picture viewer — a screenshot of each, and
what the page's console said. What went wrong goes to errors.txt.

    python3 tools/web_check.py OUT_DIR [--real[=PROFILE]]

--real: your own account, read-only, instead of the fake server (tools/real.py).

With Playwright (python3 tools/devenv.py) it clicks through all of that; without it, a
Chromium or Chrome found on the system takes one screenshot of the page; with neither,
only the server's answers are checked (the page, the API, the menus' code)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import real  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="fedtail-web-")
REAL = real.snapshot(_tmp)  # before XDG_* point at the temporary folder
os.environ["XDG_CONFIG_HOME"] = str(Path(_tmp) / "config")
os.environ["XDG_DATA_HOME"] = str(Path(_tmp) / "data")

ERRORS, NOTES = [], []


def make_core():
    if REAL:
        core = real.core(REAL, real.config(REAL))
        core.connect().result()
        core.poll_once()
        return core
    from fedtail.core import auth, config, paths
    from fedtail.core.app import Core
    from tests import fakes
    from tests.fakes import BOB, ME, FakeApi, status
    FakeApi.world = w = fakes.World()
    mine = w.add(status("001", ME, minute=1, text="мой <b>пост</b>", vis="public"), home=True)
    w.add(status("002", BOB, mine["id"], "ME", minute=2, text="ответ мне"), home=True,
          mention=True)
    for i in range(3, 25):
        st = status(f"{i:03d}", BOB, minute=i, vis="public",
                    text=f"пост номер {i} " + "текст " * (i % 9 + 3))
        if i % 4 == 0:
            st["media_attachments"] = [{"id": f"m{i}", "type": "image",
                                        "url": f"https://img.example/{i}.png",
                                        "preview_url": f"https://img.example/{i}s.png",
                                        "description": "картинка"}]
        w.add(st, home=True)
    # a post far taller than the screen: read once its end has been on screen (it never
    # reached "90% in view" and stayed unread for good, 29.10)
    w.add(status("030", BOB, minute=30, vis="public",
                 text="<p>" + "<br>".join(f"длинная строка {n}" for n in range(120)) + "</p>"),
          home=True)
    w.act("a1", "favourite", BOB, st=mine, minute=5)
    # what a lived-in account has and an empty one hides: a list (26.10 — columns
    # broke on the first account with one), a followed tag
    w.lists["7"] = {"id": "7", "title": "Друзья", "exclusive": False,
                    "replies_policy": "list", "members": set()}
    w.followed_tags.add("linux")
    cfg, _ = config.validate({"feed": {"first_run_mark_read": False}})
    p = paths.resolve("web", config=str(Path(_tmp) / "c.toml"), data=str(Path(_tmp) / "d"))
    auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
    core = Core(cfg, p, api_class=FakeApi)
    core._origin_json = lambda url: None
    core.connect().result()
    core.poll_once()
    return core


def http_checks(base, key):
    from fedtail.frontends.web import server as web

    def get(path):
        r = urllib.request.Request(base + path, headers={"Cookie": f"{web.COOKIE}={key}"})
        with urllib.request.urlopen(r, timeout=30) as resp:
            return resp.read().decode()
    page = get("/")
    for wanted in ('id="more"', 'id="menu"', 'id="write"', 'id="lanes"', 'id="compose"',
                   'id="viewer"', 'id="cmdline"'):
        if wanted not in page:
            ERRORS.append(f"the page has no {wanted}")
    js = get("/app.js")
    for fn in ("function postMenu", "function mainMenu", "function compose",
               "function selectLane", "function openThread", "function openAccount"):
        if fn not in js:
            ERRORS.append(f"app.js has no {fn}")
    paths = ["/api/me", "/api/lanes", "/api/lane?name=home"]
    if not REAL:  # the fake world's post; your account's: whatever home has first
        paths.append("/api/thread?id=002")
    else:
        try:
            rows = json.loads(get("/api/lane?name=home")).get("rows") or []
            first = next((r.get("id") or (r.get("post") or {}).get("id") for r in rows
                          if isinstance(r, dict) and (r.get("id") or r.get("post"))), None)
            if first:
                paths.append(f"/api/thread?id={first}")
        except Exception:  # noqa: BLE001 — said by the lane's own check above
            pass
    for path in paths:
        try:
            json.loads(get(path))
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"{path}: {e}")


def with_playwright(base, key, out):
    from playwright.sync_api import sync_playwright
    exe = os.environ.get("FEDTAIL_CHROMIUM")
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(**({"executable_path": exe} if exe else {}))
        except Exception:  # noqa: BLE001 — no browser of its own: the system's
            found = _chromium()
            if not found:
                raise
            browser = pw.chromium.launch(executable_path=found)
        for label, size in (("desktop", (1280, 860)), ("phone", (390, 844))):
            page = browser.new_page(viewport={"width": size[0], "height": size[1]})
            if not REAL:  # pictures and faces of the fake world: drawn here, no network
                # (and fedtail's /pic for them: its fetch can't reach the fake world)
                page.route(lambda url: not url.startswith(base) or "/pic?" in url,
                           lambda route: route.fulfill(status=200, content_type="image/png",
                                                       body=_png(route.request.url)))
            page.on("console", lambda m, label=label: m.type in ("error", "warning") and
                    (NOTES if "Failed to load resource" in m.text else ERRORS).append(
                        f"{label} console {m.type}: {m.text}"))
            # a picture another server didn't give (502, 404, 429) is the network's
            # business, not the page's: noted, not an error
            page.on("pageerror", lambda e, label=label: ERRORS.append(f"{label} page error: {e}"))
            # fedtail's own answers failing are the page's problem, whatever the page made
            # of them (26.10: a 502 from /api/columns only hid ❯, and the console note of
            # it went to the network's notes above)
            page.on("response", lambda r, label=label: "/api/" in r.url and r.status >= 500
                    and ERRORS.append(f"{label} {r.request.method} {r.url.split('?')[0]}"
                                      f" -> {r.status}"))
            page.goto(base + "/?k=" + key)
            page.wait_for_selector(".post, article, #posts > *", timeout=10000)
            page.wait_for_timeout(800)
            page.screenshot(path=str(out / f"{label}-01-home.png"))
            if label == "desktop":
                read_by_scrolling(page, base, key)
            if label == "phone":
                page.click("#menu")
                page.wait_for_timeout(400)
                page.screenshot(path=str(out / "phone-02-lanes.png"))
                page.keyboard.press("Escape")
                page.close()
                continue
            lanes = page.eval_on_selector_all("#lanes a[data-lane]",
                                              "els => els.map(e => e.dataset.lane)")
            NOTES.append("lanes: " + ", ".join(lanes))
            for name in lanes:
                page.click(f'#lanes a[data-lane="{name}"]')
                page.wait_for_timeout(500)
                page.screenshot(path=str(out / f"desktop-02-lane-{name}.png"))
            page.click('#lanes a[data-lane="home"]' if "home" in lanes else "#refresh")
            page.wait_for_timeout(400)
            main_menu(page, out)
            walk_places(page, out)
            # Ctrl+F: a word every fake post has, and one none has
            page.click("#posts")
            page.keyboard.press("Control+f")
            # your account: the longest word of the first post on screen
            word = "пост номер 1" if not REAL else page.evaluate(
                "(() => { const t = (document.querySelector('#posts .post .body') || {})"
                ".innerText || ''; return t.split(/\\s+/).filter(w => /^[\\p{L}]{4,}$/u"
                ".test(w)).sort((a, b) => b.length - a.length)[0] || ''; })()")
            page.fill("#find-q", word)
            page.wait_for_timeout(700)
            if word and page.locator("#posts .post.found").count() == 0:
                ERRORS.append(f"Ctrl+F: nothing marked for a word the lane has ({word!r}) — "
                              f"lane {page.evaluate('state.lane')}, "
                              f"{page.locator('#posts .post').count()} posts on screen")
            page.screenshot(path=str(out / "desktop-09-find.png"))
            # "Deeper" (what's stored, not only shown) and "in every lane", as the windows
            page.click("#find-deeper")
            page.wait_for_timeout(700)
            page.check("#find-every")
            page.fill("#find-q", "пост")
            page.wait_for_timeout(900)
            if not page.inner_text("#find-count").strip():
                ERRORS.append("find in every lane: no count for a word the posts have")
            page.screenshot(path=str(out / "desktop-09b-find-everywhere.png"))
            page.uncheck("#find-every")
            page.keyboard.press("Escape")
            # the sidebar's sections fold and unfold (kept for every window)
            group = page.locator("#lanes button.group").first
            if group.count():
                before = page.locator("#lanes a[data-lane]:visible").count()
                group.click()
                page.wait_for_timeout(500)
                if page.locator("#lanes a[data-lane]:visible").count() >= before:
                    ERRORS.append("sidebar: a folded section still shows its lanes")
                page.screenshot(path=str(out / "desktop-09c-folded.png"))
                page.locator("#lanes button.group").first.click()
                page.wait_for_timeout(500)
            else:
                ERRORS.append("sidebar: no section headings")
            more = page.locator("#posts article.post button", has_text="⋯").first
            if more.count():
                more.click()
                page.wait_for_timeout(300)
                NOTES.append("⋯ menu: " + " | ".join(page.locator("#pop button, #pop a")
                                                      .all_inner_texts()))
                page.screenshot(path=str(out / "desktop-04-post-menu.png"))
                # a link of the menu, done through the server: "call into the thread"
                # opens the editor with "@" in it
                invite = page.locator("#pop button", has_text="Позвать в тред")
                if invite.count():
                    invite.first.click()
                    page.wait_for_timeout(800)
                    if not page.is_visible("#compose") or \
                            page.input_value("#text").strip() != "@":
                        ERRORS.append("⋯ → Позвать в тред: the editor didn't open with @")
                    else:
                        page.screenshot(path=str(out / "desktop-04b-invite.png"))
                    page.click("#compose-close")
                page.mouse.click(5, 5)
            else:
                ERRORS.append("no ⋯ button on a post")
            page.click("#write")
            page.wait_for_timeout(300)
            page.screenshot(path=str(out / "desktop-05-compose.png"))
            page.click("#poll-toggle")
            page.click("#sched-toggle")
            page.wait_for_timeout(200)
            if page.locator("#pollbox input").count() < 2:
                ERRORS.append("editor: the poll has no choices to fill in")
            page.screenshot(path=str(out / "desktop-05b-compose-poll.png"))
            page.click("#poll-toggle")
            # the line under the text: #CamelCase for screen readers; then the preview
            page.fill("#text", "привет #fedtailrocks")
            page.wait_for_timeout(900)
            if page.is_hidden("#compose-hint"):
                ERRORS.append("editor: no #CamelCase hint for a flat tag")
            page.click("#preview")
            page.wait_for_timeout(500)
            if not page.is_visible("#preview-dlg") or \
                    "fedtailrocks" not in page.inner_text("#preview-body"):
                ERRORS.append("editor: the preview didn't show the text")
            page.screenshot(path=str(out / "desktop-05c-preview.png"))
            page.click("#preview-back")
            page.once("dialog", lambda d: d.accept())  # "Throw this text away?"
            page.click("#discard")
            page.wait_for_timeout(300)
            if page.is_visible("#compose"):
                ERRORS.append("editor: Discard left the editor open")
            page.click("#write")
            page.wait_for_timeout(300)
            if page.input_value("#text"):
                ERRORS.append("editor: Discard kept the draft")
            page.click("#compose-close")
            img = page.locator("#posts article.post img[src*='img.example'], "
                                "#posts article.post .media img").first
            if img.count():
                img.click()
                page.wait_for_timeout(400)
                page.screenshot(path=str(out / "desktop-06-viewer.png"))
                if not page.inner_text("#viewer-save").strip():
                    ERRORS.append("viewer: no Save")
                page.keyboard.press("z")  # the picture at its own size, as the windows'
                page.wait_for_timeout(200)
                page.screenshot(path=str(out / "desktop-06b-viewer-full.png"))
                page.keyboard.press("Escape")
                page.mouse.click(5, 5)
            columns(page, out)
            page.close()
        browser.close()


def columns(page, out):
    """❯: lanes side by side — Home, Replies, Activity at first; a lane picked on the
    left joins them; a click in a column brings it into focus; ✕ takes one away; ❯
    again — one lane."""
    if page.is_hidden("#cols-btn"):
        ERRORS.append("columns: no ❯ on the bar")
        return
    if page.is_visible("#side"):
        page.click("#back")  # a profile or a place open at the side: the columns wide
    page.click("#cols-btn")
    page.wait_for_timeout(1200)
    n = page.locator("#cols > .col, #cols > #main").count()
    if n < 1:
        ERRORS.append("columns: none after ❯")
        return
    if n < 2:  # left so last time (an account's own set may be one lane): add one
        NOTES.append("columns: one column remembered — another added for the walk")
    page.screenshot(path=str(out / "desktop-10-columns.png"))
    lanes = page.eval_on_selector_all("#lanes a[data-lane]",
                                      "els => els.map(e => e.dataset.lane)")
    shown = page.evaluate("cols.names")
    extra = next((x for x in lanes if x not in shown), None)
    if extra:
        page.click(f'#lanes a[data-lane="{extra}"]')
        page.wait_for_timeout(900)
        if page.locator("#cols > .col, #cols > #main").count() != n + 1:
            ERRORS.append(f"columns: a lane picked on the left ({extra}) didn't join them")
    n = page.locator("#cols > .col, #cols > #main").count()
    pane = page.locator("#cols > .col .colhead h2").first
    if pane.count():
        name = page.locator("#cols > .col").first.get_attribute("data-lane")
        pane.click()
        page.wait_for_timeout(900)
        if page.evaluate("state.lane") != name:
            ERRORS.append(f"columns: a click on {name}'s header didn't bring it into focus")
    if page.locator("#cols > .col").count() and not page.locator(
            "#cols > .col .colposts > *").count():
        ERRORS.append("columns: a column beside the focused one is empty")
    page.screenshot(path=str(out / "desktop-10b-columns-focus.png"))
    before = page.locator("#cols > .col, #cols > #main").count()
    page.locator("#coltools button[aria-label]").last.click()  # ✕ on the focused one
    page.wait_for_timeout(900)
    if page.locator("#cols > .col, #cols > #main").count() != before - 1:
        ERRORS.append("columns: ✕ didn't take the column away")
    page.click("#cols-btn")
    page.wait_for_timeout(600)
    if page.locator("#cols").count():
        ERRORS.append("columns: ❯ again didn't go back to one lane")


def didnt_load(what, body):
    """A place that didn't load: an error — but your account's server saying "too many
    requests" (429) is its limit, not ours: a note."""
    if REAL and ("429" in body or "rate limit" in body):
        NOTES.append(f"{what}: the server's rate limit (429) — not checked")
    else:
        ERRORS.append(f"{what}: didn't load: {body[:200]}")


def read_by_scrolling(page, base, key):
    """Home scrolled through to its end: every post read, the tall one too (the windows'
    rule, common/lane.py seen())."""
    import json
    import urllib.request

    def unread():
        r = urllib.request.Request(base + "/api/lane?name=home&keep=1",
                                   headers={"Cookie": f"fedtail_web={key}"})
        with urllib.request.urlopen(r, timeout=20) as resp:
            return {p["sid"] for p in json.loads(resp.read())["posts"] if p["unread"]}
    if "030" not in unread():
        NOTES.append("reading: the tall post was read before scrolling (already marked)")
    for _ in range(60):  # the wheel down, a screen at a time, to the end
        page.evaluate("() => { const b = document.querySelector('#posts');"
                      " b.scrollTop += b.clientHeight * 0.8; }")
        page.wait_for_timeout(120)
    page.wait_for_timeout(1500)  # the look after the scroll, and the read sent
    left = unread()
    if "030" in left:
        ERRORS.append("reading: the post taller than the screen stayed unread after "
                      "scrolling past it")
    elif left:
        ERRORS.append(f"reading: Home read through by the wheel, still unread: {sorted(left)}")
    NOTES.append(f"reading: unread after scrolling Home through: {sorted(left) or 'none'}")


def main_menu(page, out):
    """≡: a window over the page — the everyday buttons on top, the groups (the windows'
    submenus) at the left, a group's items beside them; every place of the menu is in
    some group; Esc closes it."""
    page.click("#more")
    page.wait_for_timeout(300)
    if page.is_hidden("#menuwin"):
        ERRORS.append("≡: the menu window didn't open")
        return
    groups = page.locator("#menu-groups button")
    seen = []
    for i in range(groups.count()):
        groups.nth(i).hover()
        page.wait_for_timeout(80)
        items = page.locator("#menu-items button").all_inner_texts()
        if not items:
            ERRORS.append(f"≡: the group {groups.nth(i).inner_text()!r} is empty")
        seen += items
        NOTES.append(f"≡ {groups.nth(i).inner_text()}: " + " | ".join(items))
        page.screenshot(path=str(out / f"desktop-03-main-menu-{i}.png"))
    places = page.evaluate(
        "(state.me.places || []).filter(p => !['help', 'news', 'about'].includes(p.name))"
        ".map(p => p.title.endsWith('…') ? p.title : p.title + ' …')")
    lost = [x for x in places if x not in seen]
    if lost:
        ERRORS.append("≡: places in no group: " + ", ".join(lost))
    if groups.count() < 4:
        ERRORS.append(f"≡: {groups.count()} group(s) — the menu is one long list again?")
    page.keyboard.press("Escape")
    page.wait_for_timeout(150)
    if page.is_visible("#menuwin"):
        ERRORS.append("≡: Esc didn't close the menu window")
    # a place from it: a window over the page, not the column at the right
    page.click("#more")
    page.locator("#menu-groups button").first.click()
    page.locator("#menu-items button").first.click()
    page.wait_for_timeout(700)
    if "floating" not in (page.get_attribute("#side", "class") or ""):
        ERRORS.append("≡ → a place: not in a window over the page")
    page.screenshot(path=str(out / "desktop-03b-place-window.png"))
    page.evaluate("closeSide()")


def walk_places(page, out):
    """Every place of the ≡ menu (common/places.py) in the side panel, each of its tabs:
    a screenshot each, and an error where one didn't load; a link inside the help."""
    from fedtail.i18n import _
    failed = _("web_load_error", err="").strip()
    names = page.evaluate("(state.me.places || []).map(p => p.name)")
    names += [n for n in ("help", "news") if n not in names]
    NOTES.append("places: " + ", ".join(names))
    for n in names:
        page.evaluate(f"openPlace({json.dumps(n)})")
        page.wait_for_timeout(700)
        body = page.inner_text("#side-body")
        if failed and failed in body or body.strip() == "…":
            didnt_load(f"place {n}", body)
        page.screenshot(path=str(out / f"desktop-07-place-{n}.png"))
        tabs = page.locator("#side-body .tabs button")
        labels = tabs.all_inner_texts()  # a click redraws the panel: by words, not index
        for i, label in enumerate(labels):
            tab = page.locator("#side-body .tabs button", has_text=label).first
            if not tab.count():
                ERRORS.append(f"place {n}: the tab {label!r} went after a click")
                continue
            tab.click()
            page.wait_for_timeout(500)
            body = page.inner_text("#side-body")
            if failed and failed in body:
                didnt_load(f"place {n}, tab {label}", body)
            page.screenshot(path=str(out / f"desktop-07-place-{n}-{i}.png"))
    page.evaluate("openPlace('help')")
    page.wait_for_timeout(600)
    inner = page.locator('#side-body a[href^="fedtail:help/"]')
    if inner.count():
        inner.first.click()
        page.wait_for_timeout(600)
        if page.locator("#side-body h1, #side-body h2").count() == 0:
            ERRORS.append("help: a link inside the help opened no page")
        page.screenshot(path=str(out / "desktop-08-help-link.png"))
    else:
        ERRORS.append("help: no links between its pages")
    page.evaluate("closeSide()")


def _png(url):
    import struct
    import zlib
    w, h = 160, 100
    c = (60 + len(url) * 7 % 160, 120, 170)
    raw = b"".join(b"\0" + bytes(c) * w for _ in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _chromium():
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable",
                 "chrome", "msedge"):
        found = shutil.which(name)
        if found:
            return found
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
        if os.path.exists(p):
            return p
    return None


def with_chromium(base, key, out):
    exe = _chromium()
    if not exe:
        NOTES.append("no Playwright, no Chromium/Chrome: the server's answers only")
        return
    # the page keeps a connection open for news (it never "finishes loading"), so the
    # browser may wait for ever and take none: it gets 20 s
    shot = out / "desktop-01-home.png"
    with tempfile.TemporaryDirectory() as prof:
        p = subprocess.Popen([exe, "--headless=new", "--disable-gpu", "--no-first-run",
                              f"--user-data-dir={prof}", "--window-size=1280,860",
                              "--virtual-time-budget=6000", f"--screenshot={shot}",
                              base + "/?k=" + key],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        end = time.monotonic() + 20
        while time.monotonic() < end and p.poll() is None and not shot.exists():
            time.sleep(0.5)
        time.sleep(1)
        if p.poll() is None:
            p.kill()
            p.wait(10)
    if shot.exists():
        NOTES.append(f"one screenshot by {exe} (Playwright clicks through the menus too: "
                     "python3 tools/devenv.py)")
    else:
        NOTES.append(f"{exe} took no screenshot in 20 s (the page never ends loading "
                     "for it); python3 tools/devenv.py — "
                     "and the walk clicks through all of it")


def main():
    out = Path(next((a for a in sys.argv[1:] if not a.startswith("--")), "web-check"))
    out.mkdir(parents=True, exist_ok=True)
    from fedtail import i18n
    from fedtail.frontends.web import server as web
    i18n.setup("ru")
    try:
        core = make_core()
    except Exception as e:  # noqa: BLE001 — your server unreachable, a login gone…
        (out / "errors.txt").write_text(f"no start: {type(e).__name__}: {e}\n", "utf-8")
        print(f"no start: {e}")
        return 1
    key = web.load_key(core.paths.data_dir)
    srv = web.make_server(core, "127.0.0.1", 0, key)
    srv.handle_error = lambda *a: None  # a browser dropping a connection: not a problem
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        http_checks(base, key)
        try:
            import playwright  # noqa: F401
            with_playwright(base, key, out)
        except ImportError:
            with_chromium(base, key, out)
    except Exception:  # noqa: BLE001
        ERRORS.append(traceback.format_exc(limit=8))
    finally:
        srv.shutdown()
        core.shutdown()
    if REAL:
        ERRORS[:] = [e for e in ERRORS if real.READ_ONLY not in e]
    (out / "notes.txt").write_text("\n".join(NOTES) + "\n", "utf-8")
    (out / "errors.txt").write_text("\n\n".join(ERRORS) + "\n" if ERRORS else "none\n",
                                    "utf-8")
    print("\n".join(NOTES))
    print(f"{len(ERRORS)} problems; {out}")
    return 1 if ERRORS else 0


if __name__ == "__main__":
    sys.exit(main())
