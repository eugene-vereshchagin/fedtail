"""The Textual application: lanes on the left, posts on the right, the command
line at the bottom. Keys as in the window: j / k, Enter — the thread, r — reply,
f — like, b — boost, m — bookmark, n — a new post, x — the lane read, Esc — back."""

import logging
import threading
import webbrowser

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Input, Label, ListItem, ListView, Static

from ...core.model import real
from ...i18n import _
from .model import Commands, lane_label, show_post

log = logging.getLogger(__name__)

STYLE = {"num": "bold magenta", "alias": "cyan", "who": "bold", "name": "dim",
         "time": "dim", "boost": "green", "direct": "yellow", "muted": "dim",
         "unread": "bold green"}


def _cmd_line():
    """The command line. Focusing it must not select what "r" put there (Textual
    selects on focus by default): what's typed goes after "#a3f ", not over it."""
    try:
        return Input(placeholder=_("tui_cmd_hint"), id="cmd", select_on_focus=False)
    except TypeError:  # an older Textual, which doesn't select anyway
        return Input(placeholder=_("tui_cmd_hint"), id="cmd")


def render(shown):
    """Shown → one rich Text block."""
    t = Text()
    for i, (kind, part) in enumerate(shown.head):
        if i:
            t.append(" ")
        t.append(part, style=STYLE.get(kind, ""))
    if shown.context:
        t.append("\n" + shown.context, style="italic dim")
    if shown.cw:
        t.append("\n" + shown.cw, style="yellow")
    for line in shown.body:
        t.append("\n" + line)
    if shown.foot:
        t.append("\n" + shown.foot, style="dim")
    return t


class PostItem(ListItem):
    def __init__(self, status, text, key=None):
        super().__init__(Static(text, classes="post"))
        self.status = status
        self.key = key


class LaneItem(ListItem):
    def __init__(self, name, title, n):
        super().__init__(Label(self._text(title, n)))
        self.lane = name

    @staticmethod
    def _text(title, n):
        t = Text(title, style="bold" if n else "")
        if n:
            t.append(f" {n}", style="bold green")
        return t

    def update(self, title, n):
        self.query_one(Label).update(self._text(title, n))


class Ui:
    """What both screens need: run a core future, hear back in the UI thread."""

    def later(self, fut, ok=None, fail=None):
        app = self.app

        def done(f):
            if f.cancelled():
                return
            exc = f.exception()
            if exc is not None:
                app.in_ui(fail or app.show_error, str(exc))
            elif ok:
                app.in_ui(ok, f.result())
        fut.add_done_callback(done)
        return fut


class PostsMixin(Ui):
    def current(self):
        lv = self.query_one("#posts", ListView)
        item = lv.highlighted_child
        return item.status if isinstance(item, PostItem) else None

    def action_cursor_down(self):
        self.query_one("#posts", ListView).action_cursor_down()

    def action_cursor_up(self):
        self.query_one("#posts", ListView).action_cursor_up()

    def action_fav(self):
        st = self.current()
        if st:
            self.later(self.app.core.favourite(st), ok=self.status_changed)

    def action_boost(self):
        st = self.current()
        if st and real(st).get("visibility") in ("public", "unlisted"):
            self.later(self.app.core.boost(st), ok=self.status_changed)

    def action_bookmark(self):
        st = self.current()
        if st:
            self.later(self.app.core.bookmark(st), ok=self.status_changed)

    def action_reply(self):
        st = self.current()
        if not st:
            return
        alias = self.app.core.short_ids([st]).get(real(st)["id"])
        cmd = self.query_one("#cmd", Input)
        cmd.value = f"#{alias} " if alias else ""
        cmd.cursor_position = len(cmd.value)
        cmd.focus()

    def action_open(self):
        st = self.current()
        if st:
            self.app.push_screen(ThreadScreen(real(st)["id"]))

    def action_profile(self):
        st = self.current()
        if st:
            self.app.push_screen(ProfileScreen(real(st)["account"]["id"]))

    def action_browser(self):
        st = self.current()
        url = real(st).get("url") if st else None
        if url:
            webbrowser.open(url)

    def status_changed(self, st):
        self.app.refresh_lane()


class ThreadScreen(Screen, PostsMixin):
    BINDINGS = [Binding("escape,q", "app.pop_screen", _("tui_back")),
                Binding("j", "cursor_down", show=False), Binding("k", "cursor_up", show=False),
                Binding("r", "reply", _("reply")), Binding("f", "fav", _("fav")),
                Binding("b", "boost", _("boost")), Binding("m", "bookmark", _("bookmark")),
                Binding("o", "browser", _("open_browser"), show=False),
                Binding("p", "profile", _("tui_profile")),
                Binding("colon", "command", ":", show=False)]

    def __init__(self, status_id):
        super().__init__()
        self.status_id = status_id

    def compose(self) -> ComposeResult:
        yield Static(_("tui_thread_loading"), id="title")
        yield ListView(id="posts")
        yield _cmd_line()
        yield Footer()

    def on_mount(self):
        self.query_one("#posts", ListView).focus()
        self.load()

    def load(self):
        self.later(self.app.core.thread(self.status_id), ok=self.fill)

    async def fill(self, nodes):
        core = self.app.core
        lv = self.query_one("#posts", ListView)
        width = max(30, self.size.width - 6)
        short = core.short_ids([n.status for n in nodes])
        unread = core.unread_ids([(None, n.status) for n in nodes])
        items, focus = [], 0
        for i, n in enumerate(nodes):
            pad = "  " * min(n.depth, 8)
            shown = show_post(core, n.status, short.get(real(n.status)["id"]),
                              n.status["id"] in unread, n.number, width - len(pad))
            text = render(shown)
            if pad:
                text = Text("\n").join(Text(pad) + line for line in text.split())
            items.append(PostItem(n.status, text, key=n.status["id"]))
            if real(n.status)["id"] == self.status_id:
                focus = i
        root = real(nodes[0].status) if nodes else None
        self.query_one("#title", Static).update(
            _("tui_thread_title", who="@" + root["account"]["acct"], n=len(nodes) - 1)
            if root else "")
        await lv.clear()
        await lv.extend(items)
        lv.index = focus
        if core.cfg["read"]["mark_read"] != "manual":
            core.mark_read([n.status["id"] for n in nodes])

    def action_command(self):
        self.query_one("#cmd", Input).focus()

    def status_changed(self, st):
        self.load()

    async def on_input_submitted(self, e: Input.Submitted):
        e.stop()
        await self.app.run_line(e.input, self)


class ProfileScreen(Screen, PostsMixin):
    """Someone's profile: who, the bio, follows you or not; F — follow / unfollow;
    their posts below (Enter — a thread)."""

    BINDINGS = [Binding("escape,q", "app.pop_screen", _("tui_back")),
                Binding("j", "cursor_down", show=False), Binding("k", "cursor_up", show=False),
                Binding("F", "follow", _("follow")),
                Binding("r", "reply", _("reply")), Binding("f", "fav", _("fav")),
                Binding("b", "boost", _("boost")), Binding("m", "bookmark", _("bookmark")),
                Binding("o", "browser", _("open_browser"), show=False),
                Binding("colon", "command", ":", show=False)]

    def __init__(self, acc_id):
        super().__init__()
        self.acc_id = acc_id
        self.acc, self.rel = None, {}

    def compose(self) -> ComposeResult:
        yield Static(_("tui_thread_loading"), id="title")
        yield Static("", id="about")
        yield ListView(id="posts")
        yield _cmd_line()
        yield Footer()

    def on_mount(self):
        core = self.app.core
        self.query_one("#posts", ListView).focus()
        self.later(core.account(self.acc_id), ok=self.got_account)
        if not core.me or self.acc_id != core.me["id"]:
            self.later(core.relationship(self.acc_id), ok=self.got_relation,
                       fail=lambda _e: None)
        self.later(core.account_statuses(self.acc_id), ok=self.fill)

    def got_account(self, acc):
        self.acc = acc
        self.show_about()

    def got_relation(self, rel):
        self.rel = rel or {}
        self.show_about()

    def show_about(self):
        acc = self.acc
        if not acc:
            return
        from ...core.model import html_to_text
        head = Text(acc.get("display_name") or acc.get("username", ""), style="bold")
        head.append(f"  @{acc.get('acct', '')}", style="cyan")
        self.query_one("#title", Static).update(head)
        t = Text()
        bits = [_(key, n=acc[field]) for key, field in
                (("posts_n", "statuses_count"), ("followers_n", "followers_count"),
                 ("following_n", "following_count")) if field in acc]
        if self.rel.get("followed_by"):
            bits.append(_("acc_follows_you"))
        if self.rel.get("following"):
            bits.append("✓ " + _("tui_you_follow"))
        t.append(" · ".join(bits), style="dim")
        note = html_to_text(acc.get("note") or "").strip()
        if note:
            t.append("\n" + note)
        for f in acc.get("fields") or []:
            t.append("\n" + f.get("name", "") + ": ", style="bold")
            t.append(html_to_text(f.get("value", "")))
        self.query_one("#about", Static).update(t)

    async def fill(self, page):
        core = self.app.core
        lv = self.query_one("#posts", ListView)
        width = max(30, self.size.width - 6)
        short = core.short_ids(page)
        items = [PostItem(st, render(show_post(core, st, short.get(real(st)["id"]), width=width,
                                               parent=core.parent_of(st))), key=st["id"])
                 for st in page]
        await lv.clear()
        await lv.extend(items)
        if items:
            lv.index = 0

    def action_follow(self):
        on = not self.rel.get("following")
        self.later(self.app.core.follow(self.acc_id, on),
                   ok=lambda _r: (self.app.notify(_("cmd_followed" if on else "cmd_unfollowed",
                                                    who=(self.acc or {}).get("acct", "?"))),
                                  self.later(self.app.core.relationship(self.acc_id),
                                             ok=self.got_relation)))

    def action_command(self):
        self.query_one("#cmd", Input).focus()

    def status_changed(self, st):
        self.later(self.app.core.account_statuses(self.acc_id), ok=self.fill)

    async def on_input_submitted(self, e: Input.Submitted):
        e.stop()
        await self.app.run_line(e.input, self)


class FedtailApp(App, PostsMixin):
    CSS = """
    #lanes { width: 26; border-right: solid $primary-background; }
    #main { width: 1fr; }
    #title { height: 1; padding: 0 1; background: $primary-background; }
    #posts > ListItem { padding: 0 1 1 1; }
    #cmd { dock: bottom; }
    .post { width: 1fr; }
    """
    BINDINGS = [Binding("q", "quit", _("quit")),
                Binding("j", "cursor_down", show=False), Binding("k", "cursor_up", show=False),
                Binding("r", "reply", _("reply")), Binding("f", "fav", _("fav")),
                Binding("b", "boost", _("boost")), Binding("m", "bookmark", _("bookmark")),
                Binding("n", "new", _("write")), Binding("x", "all_read", _("tui_all_read")),
                Binding("R", "refresh", _("refresh"), show=False),
                Binding("o", "browser", _("open_browser"), show=False),
                Binding("p", "profile", _("tui_profile")),
                Binding("tab", "switch", _("tui_switch"), show=False),
                Binding("colon", "command", ":", show=False),
                Binding("escape", "escape", show=False)]

    def __init__(self, core, instance=None):
        super().__init__()
        self.core = core
        self._instance = instance
        self.cmds = Commands(core)
        self.lane = None
        self._ui_thread = None
        tcfg = core.cfg.get("tui", {})
        self.lanes_width = int(tcfg.get("lanes_width", 26))
        self._theme_wanted = tcfg.get("theme", "")
        self._redraw_pending = False

    # ---- threads -------------------------------------------------------------------
    def in_ui(self, fn, *args):
        """Run fn(*args) in the interface's thread, from wherever."""
        if threading.get_ident() == self._ui_thread:
            self.call_next(fn, *args)
        else:
            try:
                self.call_from_thread(fn, *args)
            except RuntimeError:  # the app is gone
                pass

    def show_error(self, message):
        self.notify(str(message)[:300], severity="error", timeout=8)

    # ---- layout --------------------------------------------------------------------
    def compose(self) -> ComposeResult:
        with Horizontal():
            yield ListView(id="lanes")
            with Vertical(id="main"):
                yield Static("fedtail", id="title")
                yield ListView(id="posts")
        yield _cmd_line()
        yield Footer()

    def on_mount(self):
        self._ui_thread = threading.get_ident()
        self.title = "fedtail"
        self.query_one("#lanes").styles.width = self.lanes_width
        if self._theme_wanted:
            try:
                self.theme = self._theme_wanted
            except Exception as e:  # noqa: BLE001 — an unknown name: Textual's default
                log.warning("tui.theme %s: %s", self._theme_wanted, e)
        if self._instance is not None:
            self._instance.listen(lambda _m: None)
        self.core.events.on("lanes_updated", lambda _n, p: self.in_ui(self.lanes_updated, p))
        self.core.events.on("error", lambda _n, p: self.in_ui(self.show_error, p))
        if not self.core.logged_in:
            self.push_screen(LoginScreen())
            return
        self.begin()

    def begin(self):
        self.query_one("#title", Static).update(_("tui_connecting"))
        self.later(self.core.connect(), ok=self.connected,
                   fail=lambda e: self.show_error(_("tui_connect_failed", err=e)))

    async def connected(self, me):
        self.sub_title = "@" + me["acct"]
        await self.fill_lanes()
        self.core.start_polling()
        want = self.core.get_state("lane")
        names = list(self.core.lane_by_name)
        if names:
            await self.select_lane(want if want in names else names[0])
        self.query_one("#posts", ListView).focus()

    async def fill_lanes(self):
        lv = self.query_one("#lanes", ListView)
        await lv.clear()
        items = []
        for name in self.core.lane_by_name:
            title, n = lane_label(self.core, name, self.lanes_width - 2)
            items.append(LaneItem(name, title, n))
        await lv.extend(items)

    def update_lane_counts(self):
        for item in self.query_one("#lanes", ListView).children:
            if isinstance(item, LaneItem):
                item.update(*lane_label(self.core, item.lane, self.lanes_width - 2))

    async def select_lane(self, name):
        self.lane = name
        self.core.set_active_lane(name)
        self.core.set_state("lane", name)
        lanes = self.query_one("#lanes", ListView)
        for i, item in enumerate(lanes.children):
            if isinstance(item, LaneItem) and item.lane == name:
                if lanes.index != i:
                    lanes.index = i
        await self.refresh_posts(first=True)

    async def refresh_posts(self, first=False):
        core, name = self.core, self.lane
        if name is None:
            return
        lv = self.query_one("#posts", ListView)
        entries = core.lane_entries(name)
        if core.cfg["feed"]["order"] == "newest_first":
            entries = list(reversed(entries))
        keep = getattr(lv.highlighted_child, "key", None)
        unread = core.unread_ids(entries)
        short = core.short_ids([st for _i, st in entries])
        width = max(30, lv.size.width - 4 if lv.size.width else 76)
        items = []
        for item_id, st in entries:
            shown = show_post(core, st, short.get(real(st)["id"]), st["id"] in unread,
                              width=width, parent=core.parent_of(st))
            items.append(PostItem(st, render(shown), key=item_id))
        title = core.lane_title(name) or _("lane_" + name)
        self.query_one("#title", Static).update(
            Text(title, style="bold") + Text(f"  {_('tui_unread', n=len(unread))}"
                                             if unread else "", style="dim"))
        await lv.clear()
        await lv.extend(items)
        if not items:
            return
        keys = [it.key for it in items]
        if keep in keys and not first:
            lv.index = keys.index(keep)
        else:
            lv.index = self._start_index(entries, unread)
        self.update_lane_counts()

    def _start_index(self, entries, unread):
        """feed.start_at: the first unread (oldest first) or the newest."""
        newest = 0 if self.core.cfg["feed"]["order"] == "newest_first" else len(entries) - 1
        if self.core.cfg["feed"]["start_at"] == "newest" or not unread:
            return newest
        for i, (_item, st) in enumerate(entries):
            if st["id"] in unread:
                if self.core.cfg["feed"]["order"] == "newest_first":
                    continue  # the last unread in this order is the oldest one
                return i
        return max(i for i, (_x, st) in enumerate(entries) if st["id"] in unread)

    async def lanes_updated(self, per_lane):
        if set(per_lane) - set(self._lane_names()):
            await self.fill_lanes()
        if self.lane in per_lane and not self._redraw_pending:
            self._redraw_pending = True
            try:
                await self.refresh_posts()
            finally:
                self._redraw_pending = False
        else:
            self.update_lane_counts()

    def _lane_names(self):
        return [i.lane for i in self.query_one("#lanes", ListView).children
                if isinstance(i, LaneItem)]

    def refresh_lane(self):
        self.call_next(self.refresh_posts)

    # ---- events --------------------------------------------------------------------
    async def on_list_view_selected(self, e: ListView.Selected):
        e.stop()
        if e.list_view.id == "lanes" and isinstance(e.item, LaneItem):
            await self.select_lane(e.item.lane)
            self.query_one("#posts", ListView).focus()
        elif e.list_view.id == "posts" and self.screen is self.screen_stack[0]:
            self.action_open()
        elif e.list_view.id == "posts" and isinstance(self.screen, ProfileScreen):
            self.screen.action_open()

    def on_list_view_highlighted(self, e: ListView.Highlighted):
        if e.list_view.id != "posts" or not isinstance(e.item, PostItem):
            return
        if self.core.cfg["read"]["mark_read"] == "on_scroll":
            sid = e.item.status["id"]
            if sid in self.core.unread_ids([(None, e.item.status)]):
                self.core.mark_read([sid])
                self.update_lane_counts()

    async def on_input_submitted(self, e: Input.Submitted):
        await self.run_line(e.input, self)

    async def run_line(self, field, where):
        line = field.value.strip()
        if not line:
            where.query_one("#posts", ListView).focus()
            return
        fut, message = self.cmds.run(line)
        if fut is None:
            self.notify(message, severity="warning" if message != _("cmd_help") else
                        "information", timeout=12)
            return
        field.disabled = True

        def ok(result):
            field.disabled = False
            field.value = ""
            if isinstance(result, tuple) and result[0] == "thread":
                self.push_screen(ThreadScreen(result[1]))
            elif isinstance(result, tuple) and result[0] == "profile":
                self.push_screen(ProfileScreen(result[1]["id"]))
            elif isinstance(result, tuple) and result[0] == "delete":
                self.later(self.core.delete(result[1]), ok=lambda _r: self.notify(_("deleted")))
            elif isinstance(result, str):
                self.notify(result)
            elif isinstance(result, dict):  # a post went out
                self.notify(message or _("sent"))
            where.query_one("#posts", ListView).focus()

        def fail(err):
            field.disabled = False
            self.show_error(_("send_failed_text", err=err))
        self.later(fut, ok=ok, fail=fail)

    # ---- actions -------------------------------------------------------------------
    def action_new(self):
        cmd = self.query_one("#cmd", Input)
        cmd.value = ""
        cmd.focus()

    def action_command(self):
        self.query_one("#cmd", Input).focus()

    def action_switch(self):
        lanes, posts = self.query_one("#lanes", ListView), self.query_one("#posts", ListView)
        (posts if lanes.has_focus else lanes).focus()

    def action_escape(self):
        cmd = self.query_one("#cmd", Input)
        if cmd.has_focus:
            self.query_one("#posts", ListView).focus()

    def action_refresh(self):
        self.core.poll_now()
        self.notify(_("refresh"))

    def action_all_read(self):
        if self.lane:
            entries = self.core.lane_entries(self.lane)
            self.core.mark_read(sorted(self.core.unread_ids(entries)))
            self.refresh_lane()


class LoginScreen(Screen, Ui):
    """No token yet: the server, then the code the browser shows (OAuth, as in the window)."""

    BINDINGS = [Binding("escape", "app.quit", _("quit"))]

    def compose(self) -> ComposeResult:
        yield Static(_("tui_login_server"), id="ask")
        yield Input(placeholder="example.social", id="answer")
        yield Static("", id="url")
        yield Footer()

    def on_mount(self):
        self.step = "server"
        self.query_one("#answer", Input).focus()

    def on_input_submitted(self, e: Input.Submitted):
        e.stop()
        value = e.value.strip()
        if not value:
            return
        if self.step == "server":
            self.later(self.app.core.begin_login(value), ok=self.got_url)
        else:
            self.later(self.app.core.finish_login(value), ok=self.done)

    def got_url(self, url):
        self.step = "code"
        self.query_one("#ask", Static).update(_("tui_login_code"))
        self.query_one("#url", Static).update(url)
        field = self.query_one("#answer", Input)
        field.value = ""
        field.placeholder = _("tui_code")
        try:
            webbrowser.open(url)
        except Exception:  # noqa: BLE001 — no browser here: the link is on the screen
            pass

    def done(self, _me):
        self.app.pop_screen()
        self.app.begin()
