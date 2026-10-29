"""A walk through the terminal interface (Textual) on a fake server, headless: every
lane, a thread, a profile, Activity, follow requests, the pictures screen, the command
line, every key of the bindings — a screenshot (SVG, open it in a browser) of each, and
whether the pictures in the lane were drawn; which terminal graphics, picture viewer and
mpv this machine has (notes.txt, "media —"). What went wrong goes to errors.txt.

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
    poll = status("030", BOB, minute=30, vis="public", text="опрос")
    poll["poll"] = {"id": "p30", "expires_at": "2099-01-01T00:00:00.000Z", "expired": False,
                    "multiple": True, "votes_count": 3, "voters_count": 2, "voted": False,
                    "own_votes": [], "emojis": [],
                    "options": [{"title": "да", "votes_count": 2},
                                {"title": "нет", "votes_count": 1}]}
    w.add(poll, home=True)
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
    NOTES.append(f"pictures in the lane: {pictures.how(pictures.mode(core.cfg))}")
    sample = pictures.text(png(64, 40, (200, 40, 40)), 16, 4) if pictures.available() \
        else None
    NOTES.append("pictures: a sample drawn, "
                 + ("by chafa" if sample is not None and "▀" not in sample.plain
                    else "in half blocks" if sample is not None else "not at all"))
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
        # ui.start_lane = "none": the curtain first, as the windows open; Enter: a lane
        from fedtail.frontends.tui.app import CURTAIN
        if await wait(pilot, lambda: app.lane is not None or any(
                getattr(i, "key", None) == CURTAIN for i in app.query_one("#posts").children),
                "the start: a lane or the curtain") and app.lane is None:
            shot("00-curtain")
            app.query_one("#posts").focus()
            await pilot.press("enter")
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
        # the ⋯ menu of a post, the ≡ menu, and every place in it (common/places.py)
        from fedtail.frontends.tui.screens import MenuScreen, PlaceScreen
        posts.focus()
        posts.index = 0
        await pilot.press("full_stop")
        if await wait(pilot, lambda: isinstance(app.screen, MenuScreen), "⋯ menu"):
            NOTES.append("⋯ menu: " + " | ".join(app.screen.labels()))
            shot("07-post-menu")
            await pilot.press("escape")
        await pilot.press("g")
        if await wait(pilot, lambda: isinstance(app.screen, MenuScreen), "≡ menu"):
            NOTES.append("≡ menu: " + " | ".join(app.screen.labels()))
            shot("08-main-menu")
            await pilot.press("escape")
        places = [v[1] for it in app.main_menu_items() if it != "-"
                  for v in [it[1]] if v[0] == "place"]
        for name in places:
            app.open_thing({"page": name})
            if not await wait(pilot, lambda: isinstance(app.screen, PlaceScreen) and
                              app.screen.page is not None, f"place {name}"):
                while app.screen is not app.screen_stack[0]:
                    app.pop_screen()
                continue
            await pilot.pause(0.4)
            shot(f"09-place-{name}")
            for i in range(len(app.screen.page.tabs) - 1):
                await pilot.press("right_square_bracket")
                await pilot.pause(0.5)
                shot(f"09-place-{name}-{i + 1}")
            await pilot.press("escape")
            await pilot.pause(0.2)
        await parity_walk(app, pilot, wait, shot)
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


async def parity_walk(app, pilot, wait, shot):
    """What the terminal caught up with the windows on (docs/src/parity.toml): a poll's
    screen (looked at, never voted), the editor's preview, a thread's head with every
    warning open, a sidebar section folded and back, the find keys (N, D, E, Esc), J,
    the ≡ Debugging submenu. Read-only: nothing here writes to a server."""
    from textual.widgets import ListView

    from fedtail.frontends.tui.app import GroupItem, PostItem, ThreadScreen
    from fedtail.frontends.tui.more import PollScreen, PreviewScreen
    from fedtail.frontends.tui.screens import AskScreen, ComposeScreen, MenuScreen
    from fedtail.model import real as real_post

    async def back():
        while app.screen is not app.screen_stack[0]:
            await pilot.press("escape")
            await pilot.pause(0.1)

    try:
        await app.select_lane("home")
        await pilot.pause(0.4)
        posts = app.query_one("#posts", ListView)
        polls = [n for n, i in enumerate(posts.children)
                 if isinstance(i, PostItem) and real_post(i.entry).poll is not None]
        if polls:
            posts.focus()
            posts.index = polls[0]
            await pilot.press("u")
            if await wait(pilot, lambda: isinstance(app.screen, PollScreen), "poll"):
                await pilot.press("space")
                await pilot.pause(0.2)
                shot("10-poll")
                await pilot.press("r")
                await pilot.pause(0.2)
                shot("10-poll-results")
            await back()
        else:
            NOTES.append("parity: no post with a poll in the lane")
        app.push_screen(ComposeScreen(text="**жирный**\n---\nвторой"))
        if await wait(pilot, lambda: isinstance(app.screen, ComposeScreen), "editor"):
            await pilot.pause(0.3)
            shot("11-compose")
            await pilot.press("ctrl+r")
            if await wait(pilot, lambda: isinstance(app.screen, PreviewScreen), "preview"):
                await pilot.pause(0.3)
                shot("11-preview")
                await pilot.press("escape")
            app.screen.action_extras()
            if await wait(pilot, lambda: isinstance(app.screen, MenuScreen), "extras"):
                NOTES.append("📎 menu: " + " | ".join(app.screen.labels()))
                shot("11-extras")
        await back()
        posts.focus()
        posts.index = len(posts.children) - 1
        await pilot.press("enter")
        if await wait(pilot, lambda: isinstance(app.screen, ThreadScreen), "thread"):
            await pilot.pause(0.5)
            await pilot.press("c")
            await pilot.pause(0.3)
            shot("12-thread-head")
            NOTES.append("thread head: " + str(app.screen.info))
        await back()
        lanes = app.query_one("#lanes", ListView)
        heads = [i for i, it in enumerate(lanes.children) if isinstance(it, GroupItem)]
        if heads:
            lanes.focus()
            lanes.index = heads[-1]
            await pilot.press("enter")
            await pilot.pause(0.3)
            shot("13-section-folded")
            await pilot.press("enter")
            await pilot.pause(0.3)
        app.query_one("#posts", ListView).focus()
        await pilot.press("ctrl+f")
        if await wait(pilot, lambda: isinstance(app.screen, AskScreen), "find"):
            await pilot.press(*"пост")
            await pilot.press("enter")
            await pilot.pause(0.3)
            for key in ("ctrl+f", "N", "D", "J"):
                await pilot.press(key)
                await pilot.pause(0.3)
            await pilot.press("E")
            if await wait(pilot, lambda: isinstance(app.screen, MenuScreen), "find everywhere"):
                shot("14-find-everywhere")
            await back()
            await pilot.press("escape")
        app.debug_menu()
        if await wait(pilot, lambda: isinstance(app.screen, MenuScreen), "≡ Debugging"):
            NOTES.append("≡ Debugging: " + " | ".join(app.screen.labels()))
            shot("15-debug-menu")
        await back()
    except Exception:  # noqa: BLE001
        ERRORS.append("parity walk: " + traceback.format_exc(limit=6))
        await back()


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
    # real pictures and video: what this machine's terminal and programs allow (the
    # terminal the self-check was started from; textual-image asks it only on a tty)
    from fedtail.frontends.tui import termcaps
    NOTES.extend("media — " + x for x in termcaps.summary())
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
