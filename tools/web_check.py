"""A walk through the web interface on a fake server: the page in a real browser at a
desktop's and a phone's width, every lane, the ≡ menu and a post's ⋯ menu (and what's in
them), the editor, a thread, a profile, the picture viewer — a screenshot of each, and
what the page's console said. What went wrong goes to errors.txt.

    python3 tools/web_check.py OUT_DIR [--real[=PROFILE]]

--real: your own account, read-only, instead of the fake server (tools/real.py).

With Playwright (pip install playwright) it clicks through all of that; without it, a
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
    w.act("a1", "favourite", BOB, st=mine, minute=5)
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
    for path in ("/api/me", "/api/lanes", "/api/lane?name=home", "/api/thread?id=002"):
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
                page.route(lambda url: not url.startswith(base),
                           lambda route: route.fulfill(status=200, content_type="image/png",
                                                       body=_png(route.request.url)))
            page.on("console", lambda m, label=label: m.type in ("error", "warning") and
                    ERRORS.append(f"{label} console {m.type}: {m.text}"))
            page.on("pageerror", lambda e, label=label: ERRORS.append(f"{label} page error: {e}"))
            page.goto(base + "/?k=" + key)
            page.wait_for_selector(".post, article, #posts > *", timeout=10000)
            page.wait_for_timeout(800)
            page.screenshot(path=str(out / f"{label}-01-home.png"))
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
            page.click("#more")
            page.wait_for_timeout(300)
            NOTES.append("≡ menu: " + " | ".join(page.locator("#pop button, #pop a")
                                                  .all_inner_texts()))
            page.screenshot(path=str(out / "desktop-03-main-menu.png"))
            page.keyboard.press("Escape")
            page.mouse.click(5, 5)
            more = page.locator("#posts article.post button", has_text="⋯").first
            if more.count():
                more.click()
                page.wait_for_timeout(300)
                NOTES.append("⋯ menu: " + " | ".join(page.locator("#pop button, #pop a")
                                                      .all_inner_texts()))
                page.screenshot(path=str(out / "desktop-04-post-menu.png"))
                page.mouse.click(5, 5)
            else:
                ERRORS.append("no ⋯ button on a post")
            page.click("#write")
            page.wait_for_timeout(300)
            page.screenshot(path=str(out / "desktop-05-compose.png"))
            page.click("#compose-close")
            img = page.locator("#posts article.post img[src*='img.example'], "
                                "#posts article.post .media img").first
            if img.count():
                img.click()
                page.wait_for_timeout(400)
                page.screenshot(path=str(out / "desktop-06-viewer.png"))
                page.keyboard.press("Escape")
                page.mouse.click(5, 5)
            page.close()
        browser.close()


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
    subprocess.run([exe, "--headless=new", "--disable-gpu", "--window-size=1280,860",
                    "--virtual-time-budget=6000", f"--screenshot={out / 'desktop-01-home.png'}",
                    base + "/?k=" + key], capture_output=True, timeout=90)
    NOTES.append(f"one screenshot by {exe} (Playwright clicks through the menus too)")


def main():
    out = Path(next((a for a in sys.argv[1:] if not a.startswith("--")), "web-check"))
    out.mkdir(parents=True, exist_ok=True)
    from fedtail import i18n
    from fedtail.frontends.web import server as web
    i18n.setup("ru")
    core = make_core()
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
