"""The ways into each interface, for the scenario (tests/scenario.py).

A driver does a step the way a person would in that interface, as near as a test can
get: the web page's own HTTP calls; the terminal's host and keys; the windows' link
handler, buttons and editor. Where an interface has no way at all, the driver raises
Cant — and the report says so.

Every driver answers:
    lane(name)               the posts shown, ids in the order shown
    menu(post)               the ⋯ menu as words (scenario.menu_keys)
    button(action, post)     a button under the post: fav, boost, bookmark
    thread(post)             the thread: [(id, depth)] in the order shown
    link(action, post)       a ⋯ menu item, saying yes to "sure?"
    reply(post, text)        write a reply and send it
    profile(account)         the profile's buttons, as keys (common/profile.py)
    profile_act(account, k)  press one
    command(line)            the Point command line
    read_all(lane)           "all read"
"""

from __future__ import annotations

import http.client
import json
import threading
import time

from fedtail.core.view import View
from fedtail.frontends.common import actions
from fedtail.frontends.common import profile as prof
from fedtail.frontends.common.commands import Commands
from fedtail.frontends.common.links import Links
from fedtail.model import real

from .scenario import Cant, menu_keys

# a profile's button of the interfaces that draw the head's details as a place (web,
# terminal, phone): the windows show them in the profile's tab itself
PLACES_ONLY = {"details"}


def wait_until(cond, timeout=10):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


class Driver:
    name = "?"
    config = {}

    def start(self, core, world):
        self.core, self.w = core, world

    def settle(self):
        """Let what was started finish (background futures, the event loop)."""
        time.sleep(0.05)

    def stop(self):
        pass


# ---- the reference: frontends/common, directly --------------------------------------

class RecordingHost:
    """A window as common/links.py and common/profile.py see it: says yes to every
    question, writes what the editor gets, waits for every future."""

    def __init__(self, view):
        self.view = view
        self.said, self.opened, self.composing = [], [], None

    def call(self, fut, ok=None, fail=None):
        try:
            got = fut.result(timeout=30)
        except Exception as e:  # noqa: BLE001
            (fail or self.error)(str(e))
            return
        if ok is not None:
            ok(got)

    def status(self, text):
        self.said.append(str(text))

    def error(self, text):
        self.said.append("error: " + str(text))

    def confirm(self, _title, _text, then):
        then()

    def ask_text(self, _title, _question, then, text="", allow_empty=False):
        then(text)

    def open_url(self, url):
        self.opened.append(("url", url))

    def open_thread(self, sid):
        self.opened.append(("thread", sid))

    def open_account(self, acc_id):
        self.opened.append(("account", acc_id))

    def open_tag(self, tag):
        self.opened.append(("tag", tag))

    def resolve_link(self, url):
        self.opened.append(("resolve", url))

    def copy_handle(self, handle):
        self.opened.append(("copy", handle))

    def put_alias(self, alias):
        self.opened.append(("alias", alias))

    def compose(self, reply_to=None, invite=False, edit=None, quote=None, text=None):
        self.composing = {"reply_to": reply_to, "invite": invite, "edit": edit,
                          "quote": quote, "text": text}

    def read_up_to(self, sid):
        v = self.view
        lane = "home"
        ids = [e.id for _i, e in v.entries(lane)]
        if sid in ids:
            v.mark_read(ids[:ids.index(sid) + 1])

    def show_history(self, post):
        self.opened.append(("history", post.id))

    def report(self, post):
        self.opened.append(("report", post.id))

    def open_reactions(self, post, kind):
        self.opened.append((kind, post.id))

    def open_quotes(self, post):
        self.opened.append(("quotes", post.id))

    def redrafted(self, d):
        self.composing = {"redraft": d}


def full_ctx(view, entry_in_thread=False):
    """The ⋯ menu's context a whole window gives (GTK's: lists, the long form,
    translation where the server has it, a reply with a quote)."""
    me = view.me
    return actions.Ctx(cfg=view.cfg, me_id=me.id if me else None, supports=view.supports,
                       subscribed=view.subscribed, thread_quiet=view.thread_quiet,
                       lists=True, long_form=bool(view.cfg["feed"].get("long_form", True)),
                       translate=bool(getattr(view.caps, "translation", False)),
                       quote_reply=True, in_thread=entry_in_thread)


class Reference(Driver):
    """What frontends/common decides, with nothing in between."""
    name = "common"

    def start(self, core, world):
        super().start(core, world)
        self.view = View(core)
        self.host = RecordingHost(self.view)
        self.links = Links(self.view, self.host)

    def lane(self, name):
        self.view.set_active_lane(name)
        return [e.id for _i, e in self.view.entries(name)]

    def menu(self, sid):
        p = self.view.by_id(sid)
        short = self.view.short_ids([p]).get(real(p).id)
        unread = p.id in self.view.unread([p])
        return menu_keys([(it.kind, it.url) for it in actions.menu(
            p, full_ctx(self.view), short, unread)])

    def button(self, action, sid):
        self.links.open(f"fedtail:{action}/{sid}")

    def link(self, action, sid):
        self.links.open(f"fedtail:{action}/{sid}")

    def thread(self, sid):
        nodes = self.view.thread(sid).result(timeout=10)
        return [(n.post.id, n.depth) for n in nodes]

    def reply(self, sid, text):
        from fedtail.frontends.common import compose as cc
        self.links.open(f"fedtail:reply/{sid}")
        parent = self.host.composing["reply_to"]
        start = cc.start(self.view, cc.draft_key(self.view, parent), parent)
        self.view.post(start.text + text, start.visibility, parent).result(timeout=10)

    def profile(self, acc_id):
        acc = self.view.account(acc_id).result(timeout=10)
        rel = self.view.relationship(acc_id).result(timeout=10)
        own = bool(self.view.me and acc.id == self.view.me.id)
        return [a.key for a in prof.actions(acc, rel, own, self.view.cfg, self.view.supports,
                                            lists=True, collections=True)]

    def profile_act(self, acc_id, key):
        acc = self.view.account(acc_id).result(timeout=10)
        rel = self.view.relationship(acc_id).result(timeout=10)
        prof.do(key, acc, rel, self.view, self.host, lambda _r: None)

    def command(self, line):
        fut, message = Commands(self.view).run(line)
        if fut is None:
            raise Cant(message)
        fut.result(timeout=10)

    def read_all(self, lane):
        self.view.mark_lane_read(lane)


# ---- the web page: its own HTTP calls --------------------------------------------------

def post_vis(post, mine):
    """The editor's "who sees it" for a reply, as app.js picks it: the narrower of the
    post's and my default."""
    order = ["public", "unlisted", "followers", "direct"]
    return order[max(order.index(post.get("visibility", "followers")),
                     order.index(mine) if mine in order else 2)]


class Web(Driver):
    """The web page as a browser drives it: the same requests app.js makes."""
    name = "web"

    def start(self, core, world):
        super().start(core, world)
        from fedtail.frontends.web import server as web
        self.web = web
        self.key = "k" * 24
        self.srv = web.make_server(core, "127.0.0.1", 0, self.key)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.port = self.srv.server_address[1]

    def stop(self):
        self.srv.shutdown()
        self.srv.server_close()

    def req(self, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        headers = {"Cookie": f"{self.web.COOKIE}={self.key}"}
        if body is not None:
            headers.update({"X-Fedtail": "1", "Content-Type": "application/json"})
            conn.request("POST", path, json.dumps(body), headers)
        else:
            conn.request("GET", path, headers=headers)
        r = conn.getresponse()
        data = json.loads(r.read() or b"{}")
        conn.close()
        if r.status != 200:
            raise AssertionError(f"{path}: {r.status} {data}")
        return data

    def lane(self, name):
        self.req("/api/active", {"name": name})
        return [p["id"] for p in self.req(f"/api/lane?name={name}")["posts"]]

    def menu(self, sid):
        got = self.req(f"/api/post_menu?id={sid}")
        return menu_keys([(it["kind"], it["url"]) for it in got["items"]])

    def button(self, action, sid):
        verb = {"fav": "like", "boost": "share", "bookmark": "bookmark"}[action]
        self.req("/api/act", {"action": verb, "id": sid})

    def link(self, action, sid):
        url = f"fedtail:{action}/{sid}"
        # as the page: the cards it shows go along ("read up to here" counts over them)
        shown = [p["id"] for p in self.req("/api/lane?name=home")["posts"]]
        got = self.req("/api/link", {"url": url, "shown": shown})
        if "confirm" in got:  # the page asks "sure?" and sends it again
            got = self.req("/api/link", {"url": url, "confirmed": True, "shown": shown})

    def thread(self, sid):
        return [(p["id"], p.get("depth", 0)) for p in self.req(f"/api/thread?id={sid}")["posts"]]

    def reply(self, sid, text):
        got = self.req("/api/link", {"url": f"fedtail:reply/{sid}"})
        c = got.get("compose") or {}
        if c.get("reply_to") != sid:
            raise Cant("the reply editor didn't open")
        # the editor starts with the post's reply_prefix (the mentions), as app.js does
        post = next(p for p in self.req("/api/lane?name=home")["posts"] if p["sid"] == sid)
        self.req("/api/post", {"text": (post.get("reply_prefix") or "") + text,
                               "reply_to": sid,
                               "visibility": post_vis(post, self.req("/api/me")["visibility"])})

    def profile(self, acc_id):
        # "details" opens what the windows show in the profile tab's head itself
        return [a["key"] for a in self.req(f"/api/account?id={acc_id}")["actions"]
                if a["key"] not in PLACES_ONLY]

    def profile_act(self, acc_id, key):
        got = self.req("/api/profile_act", {"id": acc_id, "key": key})
        if "confirm" in got:
            self.req("/api/profile_act", {"id": acc_id, "key": key, "confirmed": True})

    def command(self, line):
        got = self.req("/api/command", {"line": line})
        if got.get("confirm"):
            got = self.req("/api/command", {"line": line, "confirm": True})
        if not got.get("ok"):
            raise Cant(got.get("message") or "refused")

    def read_all(self, lane):
        ids = [p["id"] for p in self.req(f"/api/lane?name={lane}")["posts"]]
        self.req("/api/read", {"ids": ids})


# ---- the terminal: the Textual app, headless, its keys and screens ----------------------

class Tui(Driver):
    """The terminal as a person drives it: the app runs headless (Textual's pilot) in
    an event loop of its own; each step presses its keys there."""
    name = "tui"

    @staticmethod
    def can_run():
        try:
            import textual  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def why_not():
        return "no Textual (pip install textual)"

    def start(self, core, world):
        import asyncio
        import concurrent.futures
        super().start(core, world)
        self.loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(target=self.loop.run_forever, daemon=True,
                                       name="scenario-tui")
        self._loop_thread.start()
        ready = concurrent.futures.Future()
        # one task holds the app from start to end (Textual's context lives in it); each
        # step is a coroutine it awaits from a queue
        def begin():
            self.task = self.loop.create_task(self._main(ready))
        self.loop.call_soon_threadsafe(begin)
        ready.result(60)

    async def _main(self, ready):
        import asyncio

        from fedtail.frontends.tui.app import FedtailApp, LaneItem
        self.queue = asyncio.Queue()
        self.app = FedtailApp(self.core)
        try:
            async with self.app.run_test(size=(140, 50)) as pilot:
                self.pilot = pilot
                await self.until(lambda: any(isinstance(i, LaneItem)
                                             for i in self.app.query_one("#lanes").children))
                ready.set_result(True)
                while True:
                    coro, fut = await self.queue.get()
                    if coro is None:
                        fut.set_result(None)
                        return
                    try:
                        fut.set_result(await coro)
                    except BaseException as e:  # noqa: BLE001 — handed to the step
                        fut.set_exception(e)
        except BaseException as e:  # noqa: BLE001
            if not ready.done():
                ready.set_exception(e)

    def run(self, coro, timeout=60):
        import concurrent.futures
        fut = concurrent.futures.Future()
        self.loop.call_soon_threadsafe(self.queue.put_nowait, (coro, fut))
        return fut.result(timeout)

    async def until(self, cond, timeout=10):
        import asyncio
        end = asyncio.get_running_loop().time() + timeout
        while asyncio.get_running_loop().time() < end:
            await self.pilot.pause(0.05)
            try:
                if cond():
                    return True
            except Exception:  # noqa: BLE001 — not there yet
                pass
        raise AssertionError("tui: not reached")

    def stop(self):
        import asyncio
        try:
            self.run(None, timeout=30)

            async def finished():
                await asyncio.wait([self.task], timeout=30)  # the app's exit played out
            asyncio.run_coroutine_threadsafe(finished(), self.loop).result(40)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self._loop_thread.join(10)

    def settle(self):
        self.run(self.pilot.pause(0.3))
        time.sleep(0.2)

    async def _home_at(self, sid, lane="home"):
        from textual.widgets import ListView
        app = self.app
        while len(app.screen_stack) > 1:
            app.pop_screen()
            await self.pilot.pause(0.05)
        if app.lane != lane:
            await app.select_lane(lane)
        await self.pilot.pause(0.2)
        posts = app.query_one("#posts", ListView)
        ids = [getattr(getattr(i, "entry", None), "id", None) for i in posts.children]
        if sid not in ids:
            raise Cant(f"{sid} isn't in {lane}")
        posts.focus()
        posts.index = ids.index(sid)
        await self.pilot.pause(0.1)

    def lane(self, name):
        async def go():
            await self.app.select_lane(name)
            await self.pilot.pause(0.3)
            return [i.entry.id for i in self.app.query_one("#posts").children
                    if hasattr(i, "entry")]
        return self.run(go())

    def _menu(self, sid):
        async def go():
            from fedtail.frontends.tui.screens import MenuScreen
            await self._home_at(sid)
            await self.pilot.press("full_stop")
            await self.until(lambda: isinstance(self.app.screen, MenuScreen))
            return self.app.screen
        return self.run(go())

    def menu(self, sid):
        screen = self._menu(sid)
        items = [(v.kind, v.url) for x in screen.items if x != "-" for v in [x[1]]]
        self.run(self._dismiss(screen, None))
        return menu_keys(items)

    async def _dismiss(self, screen, value):
        screen.dismiss(value)
        await self.pilot.pause(0.2)

    def button(self, action, sid):
        key = {"fav": "f", "boost": "b", "bookmark": "m"}[action]

        async def go():
            await self._home_at(sid)
            await self.pilot.press(key)
            await self.pilot.pause(0.3)
        self.run(go())

    def link(self, action, sid):
        from fedtail.frontends.common.links import parse
        screen = self._menu(sid)
        found = [v for x in screen.items if x != "-" for v in [x[1]]
                 if v.kind == "link" and parse(v.url) and parse(v.url).action == action]
        if not found:
            self.run(self._dismiss(screen, None))
            raise Cant(f"no {action} in the ⋯ menu")

        async def go():
            from fedtail.frontends.tui.screens import ConfirmScreen
            await self._dismiss(screen, found[0])
            await self.pilot.pause(0.2)
            if isinstance(self.app.screen, ConfirmScreen):
                await self.pilot.press("y")
            await self.pilot.pause(0.4)
        self.run(go())

    def thread(self, sid):
        async def go():
            from fedtail.frontends.tui.app import ThreadScreen
            for lane in ("home", "replies", "my_posts"):
                try:
                    await self._home_at(sid, lane)
                    break
                except Cant:
                    continue
            else:  # not in a lane: through the command line, as a person would
                self.app.push_screen(ThreadScreen(sid))
            if not isinstance(self.app.screen, ThreadScreen):
                await self.pilot.press("enter")
            await self.until(lambda: isinstance(self.app.screen, ThreadScreen) and
                             len(self.app.screen.query_one("#posts").children) > 0)
            got = [(i.entry.id, getattr(i, "depth", 0))
                   for i in self.app.screen.query_one("#posts").children]
            self.app.pop_screen()
            return got
        return self.run(go())

    def reply(self, sid, text):
        async def go():
            await self._home_at(sid)
            before = len(self.w.posted)
            await self.pilot.press("r")
            await self.pilot.pause(0.1)
            await self.pilot.press(*text)
            await self.pilot.press("enter")
            await self.until(lambda: len(self.w.posted) > before)
        self.run(go())

    def _profile(self, acc_id):
        async def go():
            from fedtail.frontends.tui.app import ProfileScreen
            while len(self.app.screen_stack) > 1:
                self.app.pop_screen()
            self.app.push_screen(ProfileScreen(acc_id))
            await self.until(lambda: isinstance(self.app.screen, ProfileScreen) and
                             self.app.screen.acc is not None and
                             self.app.screen.rel is not None)
            return self.app.screen
        return self.run(go())

    def profile(self, acc_id):
        screen = self._profile(acc_id)
        keys = [a.key for a in screen.buttons() if a.key not in PLACES_ONLY]  # as Web's
        self.run(self._pop())
        return keys

    async def _pop(self):
        self.app.pop_screen()
        await self.pilot.pause(0.1)

    def profile_act(self, acc_id, key):
        screen = self._profile(acc_id)
        keys = [a.key for a in screen.buttons()]
        if key not in keys or keys.index(key) >= 9:
            raise Cant(f"no {key} among the profile's 1…9")

        async def go():
            from fedtail.frontends.tui.screens import ConfirmScreen
            await self.pilot.press(str(keys.index(key) + 1))
            await self.pilot.pause(0.3)
            if isinstance(self.app.screen, ConfirmScreen):
                await self.pilot.press("y")
            await self.pilot.pause(0.3)
            self.app.pop_screen()
        self.run(go())

    def command(self, line):
        async def go():
            from textual.widgets import Input
            while len(self.app.screen_stack) > 1:
                self.app.pop_screen()
            cmd = self.app.query_one("#cmd", Input)
            cmd.focus()
            cmd.value = line
            await self.pilot.press("enter")
            await self.pilot.pause(0.5)
        self.run(go())

    def read_all(self, lane):
        async def go():
            await self.app.select_lane(lane)
            self.app.query_one("#posts").focus()
            await self.pilot.press("x")
            await self.pilot.pause(0.3)
        self.run(go())


# ---- the Qt window: its link handler, its cards, its editor, offscreen ----------------

class _Window(Driver):
    """What the Qt and GTK drivers share: the window's own link handler (the card's
    buttons and ⋯ items are fedtail: links handed to it), "sure?" answered yes."""

    def pump(self, seconds=0.0, until=None, timeout=10.0):
        end = time.monotonic() + (timeout if until else seconds)
        while time.monotonic() < end:
            self._events()
            if until is not None:
                try:
                    if until():
                        return True
                except Exception:  # noqa: BLE001 — not there yet
                    pass
            time.sleep(0.01)
        if until is not None:
            raise AssertionError(f"{self.name}: not reached")
        return True

    def settle(self):
        self.pump(0.4)

    def button(self, action, sid):
        self.win.on_link(f"fedtail:{action}/{sid}")
        self.pump(0.3)

    def link(self, action, sid):
        self.win.on_link(f"fedtail:{action}/{sid}")
        self.pump(0.4)

    def command(self, line):
        self._command(line)
        self.pump(0.5)

    def read_all(self, lane):
        self.lane(lane)
        self._read_all(lane)
        self.pump(0.3)


class Qt(_Window):
    """The Qt window, offscreen (QT_QPA_PLATFORM=offscreen)."""
    name = "qt"

    @staticmethod
    def can_run():
        try:
            import os
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PySide6.QtWidgets import QApplication  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def why_not():
        return "no PySide6"

    def _events(self):
        self.qapp.processEvents()

    def start(self, core, world):
        super().start(core, world)
        from PySide6.QtWidgets import QApplication, QMessageBox

        from fedtail.frontends.qt import theme as themes
        from fedtail.frontends.qt.bridge import Bridge
        from fedtail.frontends.qt.window import MainWindow
        self.qapp = QApplication.instance() or QApplication([])
        # "sure?" — yes, as a person who means it would answer
        self._question = QMessageBox.question
        QMessageBox.question = staticmethod(
            lambda *a, **k: QMessageBox.StandardButton.Yes)
        self.bridge = Bridge(core)
        self.win = MainWindow(core, self.bridge, themes.apply(self.qapp, core.cfg))
        self.win.images.get = lambda *a, **k: None  # no network
        self.win.show()
        self.win.start()
        # the lanes come with the connection; a lane's widget only when it is chosen
        # (the start lane may be another: the profile's last one)
        self.pump(until=lambda: core.me is not None and "home" in self.win.lane_items,
                  timeout=30)
        self.win.select_lane("home")
        self.pump(until=lambda: "home" in self.win.lane_widgets, timeout=20)

    def stop(self):
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.question = self._question
        self.win.quitting = True
        self.win.tray = None
        self.win.hide()
        self.win.deleteLater()
        self.pump(0.2)

    def _lane_rows(self, name):
        w = self.win.lane_widgets[name]
        if hasattr(w, "refresh"):
            w.refresh()
        self.pump(0.2)
        view = w.view
        return [view.rows[k] for k in view.order
                if getattr(view.rows[k], "status_id", None) is not None]

    def lane(self, name):
        self.win.select_lane(name)
        self.pump(until=lambda: name in self.win.lane_widgets)
        return [r.spec.entry.id for r in self._lane_rows(name)]

    def _row(self, sid):
        for r in self._lane_rows("home"):
            if r.spec.entry.id == sid:
                return r
        raise Cant(f"{sid} isn't in home")

    def menu(self, sid):
        from fedtail.frontends.common import actions
        r = self._row(sid)
        # the row itself makes the menu (PostRow); its .card is only the frame
        ctx = (r if hasattr(r, "_actions_ctx") else r.card)._actions_ctx()
        return menu_keys([(it.kind, it.url) for it in actions.menu(
            r.spec.entry, ctx, short_id=r.spec.extra.get("short_id"), unread=r.spec.unread)])

    def thread(self, sid):
        from fedtail.frontends.qt.feed import ThreadWidget
        self.win.on_link(f"fedtail:thread/{sid}")

        def rows():
            w = self.win.tabs.currentWidget()
            if not isinstance(w, ThreadWidget):
                return []
            v = w.view
            return [v.rows[k] for k in v.order
                    if getattr(v.rows[k], "status_id", None) is not None]
        self.pump(until=lambda: rows())
        self.pump(0.3)
        got = [(r.spec.entry.id, r.spec.depth) for r in rows()]
        tabs = self.win.tabs
        tabs.removeTab(tabs.currentIndex())
        return got

    def reply(self, sid, text):
        self.win.on_link(f"fedtail:reply/{sid}")
        self.pump(until=lambda: getattr(self.win, "open_composes", []))
        dlg = self.win.open_composes[-1]
        dlg.text.setPlainText(dlg.text.toPlainText() + text)
        before = len(self.w.posted)
        dlg.send()
        self.pump(until=lambda: len(self.w.posted) > before)

    def _profile(self, acc_id):
        from fedtail.frontends.qt.feed import AccountWidget
        self.win.on_link(f"fedtail:account/{acc_id}")
        self.pump(until=lambda: isinstance(self.win.tabs.currentWidget(), AccountWidget)
                  and self.win.tabs.currentWidget().acc is not None)
        self.pump(0.5)  # the relation comes after
        return self.win.tabs.currentWidget()

    def profile(self, acc_id):
        from fedtail.frontends.common import profile as prof
        w = self._profile(acc_id)
        keys = [a.key for a in prof.actions(w.acc, w.relation, w.mine, self.core.cfg,
                                            self.core.supports,
                                            lists=self.win.ctx.fill_list_menu is not None,
                                            collections=True)]
        if w.mine:
            keys.insert(0, "edit_profile")
        return keys

    def profile_act(self, acc_id, key):
        from PySide6.QtWidgets import QPushButton

        from fedtail.frontends.common import profile as prof
        w = self._profile(acc_id)
        acts = {a.key: a.label for a in prof.actions(w.acc, w.relation, w.mine, self.core.cfg,
                                                     self.core.supports, lists=True,
                                                     collections=True)}
        label = acts.get(key)
        btn = next((b for b in w.findChildren(QPushButton) if b.text() == label), None)
        if btn is None:
            raise Cant(f"no button {label!r}")
        btn.click()
        self.pump(0.5)

    def _command(self, line):
        bar = self.win.cmdline
        if bar is None:
            raise Cant("no command line")
        bar.edit.setText(line)
        bar.run()

    def _read_all(self, lane):
        self.win.lane_widgets[lane].mark_all_read()


class Gtk(_Window):
    """The GTK window (needs a display: xvfb-run, as the GTK smoke test)."""
    name = "gtk"

    @staticmethod
    def can_run():
        import os
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return False
        try:
            from fedtail.frontends.gtk import gi_setup  # noqa: F401
            return True
        except Exception:  # noqa: BLE001 — no GTK 4 here
            return False

    @staticmethod
    def why_not():
        import os
        if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            return "no display (run under xvfb-run, as the self-check does)"
        return "no GTK 4 (python3-gi, gir1.2-gtk-4.0)"

    def _events(self):
        from fedtail.frontends.gtk.gi_setup import GLib
        ctx = GLib.MainContext.default()
        while ctx.pending():
            ctx.iteration(False)

    def start(self, core, world):
        super().start(core, world)
        from fedtail.core.view import View
        from fedtail.frontends.gtk import theme as themes
        from fedtail.frontends.gtk.bridge import Bridge
        from fedtail.frontends.gtk.window import MainWindow
        self.view = View(core)
        self.win = MainWindow(None, core, self.view, Bridge(self.view), themes.apply(core.cfg))
        self.win.confirm = lambda _t, _x, then: then()  # "sure?" — yes
        self.win.present()
        self.win.start()
        self.pump(until=lambda: self.win.lane_rows, timeout=30)
        self.win.select_lane("home")  # a lane's view is made when it is chosen
        self.pump(until=lambda: "home" in self.win.lane_views, timeout=20)

    def stop(self):
        self.win.quitting = True
        self.win.close()
        self.win.destroy()
        self.pump(0.2)

    def _lane(self, name):
        self.win.select_lane(name)
        self.pump(until=lambda: name in self.win.lane_views)
        lv = self.win.lane_views[name]
        lv.refresh()
        self.pump(0.3)
        return lv

    def lane(self, name):
        lv = self._lane(name)
        return [lv.specs[k].entry.id for k in lv.keys
                if lv.specs[k].entry is not None]

    def menu(self, sid):
        from fedtail.frontends.common import actions
        lv = self._lane("home")
        key = next((k for k in lv.keys if lv.specs[k].entry is not None
                    and lv.specs[k].entry.id == sid), None)
        if key is None:
            raise Cant(f"{sid} isn't in home")
        sp = lv.specs[key]
        card = lv.rows.get(key)
        ctx = card._actx() if card is not None else full_ctx(self.view)
        return menu_keys([(it.kind, it.url) for it in actions.menu(
            sp.entry, ctx, short_id=sp.extra.get("short_id"), unread=sp.unread)])

    def thread(self, sid):
        from fedtail.frontends.gtk.window import _cards
        self.win.on_link(f"fedtail:thread/{sid}")
        self.pump(until=lambda: sid in self.win.threads and list(_cards(self.win.threads[sid])))
        self.pump(0.3)
        got = [(c.entry.id, getattr(c, "depth", 0)) for c in _cards(self.win.threads[sid])]
        self.win.close_thread(sid)
        return got

    def reply(self, sid, text):
        self.win.on_link(f"fedtail:reply/{sid}")
        self.pump(until=lambda: self.win.composer is not None)
        c = self.win.composer
        c.buffer.set_text(c._text() + text)
        before = len(self.w.posted)
        c.send()
        self.pump(until=lambda: len(self.w.posted) > before)

    def profile(self, acc_id):
        from fedtail.frontends.common import profile as prof
        acc = self.view.account(acc_id).result(10)
        rel = self.view.relationship(acc_id).result(10)
        me = self.view.me
        return [a.key for a in prof.actions(acc, rel, bool(me and me.id == acc_id),
                                            self.core.cfg, self.view.supports, lists=True,
                                            collections=True)]

    def profile_act(self, acc_id, key):
        from fedtail.frontends.common import profile as prof
        acc = self.view.account(acc_id).result(10)
        rel = self.view.relationship(acc_id).result(10)
        prof.do(key, acc, rel, self.view, self.win, lambda _r: None)
        self.pump(0.5)

    def _command(self, line):
        bar = getattr(self.win, "cmdline", None)
        if bar is None:
            raise Cant("no command line")
        bar.entry.set_text(line)
        bar.run()

    def _read_all(self, lane):
        self._lane(lane)
        self.win.read_current_lane()
