"""A walk through the terminal interface (Textual) on a fake server, headless: every
lane, a thread, a profile, Activity, follow requests, the pictures screen, the command
line, every key of the bindings — a screenshot (SVG, open it in a browser) of each, and
whether the pictures in the lane were drawn. What went wrong goes to errors.txt.

    python3 tools/tui_check.py OUT_DIR [--real[=PROFILE]]

--real: your own account, read-only, instead of the fake server (tools/real.py)."""

from __future__ import annotations

import asyncio
import io
import os
import sys
import tempfile
import traceback
from concurrent.futures import Future
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tools import real  # noqa: E402

_tmp = tempfile.mkdtemp(prefix="fedtail-tui-")
REAL = real.snapshot(_tmp)  # before XDG_* point at the temporary folder
os.environ["XDG_CONFIG_HOME"] = str(Path(_tmp) / "config")
os.environ["XDG_DATA_HOME"] = str(Path(_tmp) / "data")

ERRORS, NOTES = [], []


def png(w, h, rgb):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), rgb).save(buf, "PNG")
    return buf.getvalue()


def make_core():
    if REAL:
        return real.core(REAL, real.config(REAL)), None
    from fedtail.core import auth, config, paths
    from fedtail.core.app import Core
    from tests import fakes
    from tests.fakes import BOB, ME, FakeApi, status
    FakeApi.world = w = fakes.World()
    mine = w.add(status("001", ME, minute=1, text="мой пост", vis="public"), home=True)
    w.add(status("002", BOB, mine["id"], "ME", minute=2, text="ответ мне"), home=True,
          mention=True)
    for i in range(3, 30):
        st = status(f"{i:03d}", BOB, minute=i, vis="public",
                    text=f"пост номер {i} — " + "текст " * (i % 9 + 3))
        if i % 3 == 0:
            st["media_attachments"] = [{"id": f"m{i}", "type": "image",
                                        "url": f"https://img.example/{i}.png",
                                        "preview_url": f"https://img.example/{i}s.png"}]
        w.add(st, home=True)
    w.act("a0", "follow", BOB, minute=1)
    w.act("a1", "favourite", BOB, st=mine, minute=5)
    w.requests.append(fakes.acct("Q", "quinn@example.org"))
    cfg, _ = config.validate({"feed": {"first_run_mark_read": False},
                              "lanes": {"enabled": ["home", "replies", "mentions", "activity",
                                                    "requests", "local"]}})
    p = paths.resolve("tui", config=str(Path(_tmp) / "c.toml"), data=str(Path(_tmp) / "d"))
    auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
    core = Core(cfg, p, api_class=FakeApi)
    core._origin_json = lambda url: None
    return core, w


async def walk(out):
    from textual.widgets import ListView

    from fedtail.frontends.tui import pictures
    from fedtail.frontends.tui.app import (
        FedtailApp,
        PictureScreen,
        PostItem,
        ProfileScreen,
        ThreadScreen,
    )
    from fedtail.model import real as real_post
    NOTES.append(f"pictures.available() = {pictures.available()}"
                 + ("" if pictures.available() else " — Pillow (python3-pil) is missing: "
                    "no pictures in the terminal at all"))
    core, w = make_core()
    app = FedtailApp(core)

    def fake_bytes(url):  # the pictures: made here, no network
        f = Future()
        f.set_result(png(80, 50, (40 + len(url) * 3 % 200, 120, 160)))
        return f
    if not REAL:
        app.core.media_bytes = fake_bytes

    async def wait(pilot, cond, what, timeout=8):
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while loop.time() < end:
            await pilot.pause(0.05)
            try:
                if cond():
                    return True
            except Exception:  # noqa: BLE001
                pass
        ERRORS.append(f"not reached: {what}")
        return False

    def shot(name):
        try:
            app.save_screenshot(f"{name}.svg", str(out))
        except Exception as e:  # noqa: BLE001
            ERRORS.append(f"screenshot {name}: {e}")

    async with app.run_test(size=(140, 45)) as pilot:
        core.poll_once()
        await wait(pilot, lambda: app.lane is not None, "a lane opened")
        await pilot.pause(1.0)
        shot("01-start")
        drawn = [i for i in app.query_one("#posts").children
                 if isinstance(i, PostItem) and i.has_picture]
        with_pics = [i for i in app.query_one("#posts").children
                     if isinstance(i, PostItem) and getattr(real_post(i.entry), "media", None)]
        NOTES.append(f"lane {app.lane}: {len(with_pics)} posts with pictures, "
                     f"{len(drawn)} drawn in the lane")
        if pictures.available() and with_pics and not drawn:
            ERRORS.append("pictures: the lane has posts with pictures, none drawn")
        for name in app._lane_names():
            await app.select_lane(name)
            await pilot.pause(0.6)
            shot(f"02-lane-{name}")
        await app.select_lane("home")
        await pilot.pause(0.4)
        posts = app.query_one("#posts", ListView)
        posts.focus()
        posts.index = 0
        for key, screen, label in (("enter", ThreadScreen, "thread"),
                                   ("p", ProfileScreen, "profile")):
            await pilot.press(key)
            if await wait(pilot, lambda s=screen: isinstance(app.screen, s), label):
                await pilot.pause(0.6)
                shot(f"03-{label}")
                await pilot.press("escape")
                await pilot.pause(0.3)
        pics = [n for n, i in enumerate(posts.children)
                if isinstance(i, PostItem) and getattr(real_post(i.entry), "media", None)]
        if pics:
            posts.index = pics[0]
            await pilot.press("v")
            if await wait(pilot, lambda: isinstance(app.screen, PictureScreen), "pictures"):
                await pilot.pause(0.8)
                shot("04-pictures")
                await pilot.press("escape")
        await pilot.press("colon")
        await pilot.pause(0.2)
        await pilot.press(*"?")
        await pilot.press("enter")
        await pilot.pause(0.6)
        shot("05-command-help")
        await pilot.press("escape")
        # every key the main screen offers: none may raise
        for b in app.BINDINGS:
            if b.key in ("q", "tab", "colon", "escape") or "request" in b.action:
                continue
            for key in b.key.split(","):
                try:
                    await pilot.press(key)
                    await pilot.pause(0.15)
                    while app.screen is not app.screen_stack[0]:
                        await pilot.press("escape")
                        await pilot.pause(0.1)
                except Exception:  # noqa: BLE001
                    ERRORS.append(f"key {key} ({b.action}): " + traceback.format_exc(limit=5))
        shot("06-after-keys")
        await pilot.press("q")
    core.shutdown()


def main():
    out = Path(next((a for a in sys.argv[1:] if not a.startswith("--")), "tui-check"))
    out.mkdir(parents=True, exist_ok=True)
    try:
        import textual
        NOTES.append(f"textual {textual.__version__}")
    except ImportError:
        (out / "errors.txt").write_text("textual is not installed (python3-textual or "
                                        "pip install textual)\n", "utf-8")
        print("textual is not installed")
        return 2
    from fedtail import i18n
    i18n.setup("ru")
    try:
        asyncio.run(walk(out))
    except Exception:  # noqa: BLE001
        ERRORS.append(traceback.format_exc())
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
