"""The Textual application: lanes on the left, posts on the right, the command
line at the bottom. Keys as in the window: j / k, Enter — the thread, r — reply,
f — like, b — boost, m — bookmark, . — the post's ⋯ menu, n — a line to post, w — the
editor, x — the lane read, g — the ≡ menu (every place: search, lists, silence, help…),
/ — search, Ctrl+F — find in the lane, Esc — back; [ / ] or 1…9 — another lane,
h / l — to the lanes / the posts, Tab — between them; v — the post's pictures full
screen (drawn with half blocks, see pictures.py). What a menu item, a profile's button
or a link does is the windows' (common/links.py, common/profile.py) through TuiHost
(host.py); the places are common/places.py's (screens.py)."""

import asyncio
import logging
import threading
import webbrowser

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Input, Label, ListItem, ListView, Static

from ...core.view import View
from ...i18n import _
from ...model import real
from ...model.text import html_to_text, snippet
from ..richtext import openable
from . import pictures
from .model import (
    Commands,
    DeleteGuard,
    lane_label,
    ordered_lanes,
    show_activity,
    show_post,
    show_request,
    start_lane,
)

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
    def __init__(self, entry, text, key=None):
        self.body = Static(text, classes="post")  # kept: a picture comes in later
        super().__init__(self.body)
        self.entry = entry  # a Post or a Share
        self.key = key
        self.text = text
        self.has_picture = False

    def set_picture(self, pic):
        """The post's first picture under its text (tui.pictures = "inline")."""
        self.has_picture = pic is not None
        self.body.update(self.text + Text("\n") + pic if pic is not None else self.text)


class ActivityItem(ListItem):
    """A row of the "Activity" lane: someone liked, shared, followed, mentioned…"""

    def __init__(self, activity, text):
        super().__init__(Static(text, classes="post"))
        self.activity = activity
        self.key = activity.id


class RequestItem(ListItem):
    """Someone asking to follow me: a — accept, d — reject."""

    def __init__(self, account, text):
        super().__init__(Static(text, classes="post"))
        self.account = account
        self.key = account.id


def first_picture(entry):
    """The first picture of a post (Post or Share) worth drawing, or None."""
    for m in real(entry).media:
        if m.kind in ("image", "gifv", "video") and (m.preview or m.url):
            return m
    return None


class PictureScreen(Screen):
    """A post's pictures over everything: ← / → through them, o — the original in the
    browser, Esc — back. Drawn with half blocks as big as the terminal allows."""

    BINDINGS = [Binding("escape,q,v", "app.pop_screen", _("tui_back")),
                Binding("left,h,k", "step(-1)", "←"), Binding("right,l,j", "step(1)", "→"),
                Binding("o", "original", _("open_browser"))]
    CSS = """
    PictureScreen { align: center middle; }
    PictureScreen #pic { width: auto; height: auto; }
    PictureScreen #pic-title { dock: top; height: 1; padding: 0 1;
                               background: $primary-background; }
    PictureScreen #pic-alt { dock: bottom; height: auto; max-height: 4; padding: 0 1; }
    """

    def __init__(self, media):
        super().__init__()
        self.media = list(media)
        self.at = 0

    def compose(self) -> ComposeResult:
        yield Static("", id="pic-title")
        yield Static("…", id="pic")
        yield Static("", id="pic-alt")
        yield Footer()

    def on_mount(self):
        self.show()

    def on_resize(self, _event):
        self.show()

    def show(self):
        m = self.media[self.at]
        n = len(self.media)
        self.query_one("#pic-title", Static).update(
            _("tui_picture_of", i=self.at + 1, n=n) if n > 1 else _("tui_picture"))
        self.query_one("#pic-alt", Static).update(Text(m.alt or "", style="dim"))
        pic = self.query_one("#pic", Static)
        if not pictures.available():
            pic.update(_("tui_no_pil"))
            return
        pic.update("…")
        cols = max(10, self.size.width - 2)
        rows = max(4, self.size.height - 4 - (2 if m.alt else 0))
        url = m.url if m.kind == "image" and m.url else (m.preview or m.url)
        at = self.at

        def done(f):
            try:
                data = f.result()
            except Exception as e:  # noqa: BLE001 — said on the screen
                self.app.in_ui(self._put, at, _("tui_picture_failed", err=e))
                return
            drawn = pictures.blocks(data, cols, rows)
            self.app.in_ui(self._put, at, drawn if drawn is not None else
                           _("tui_picture_failed", err="?"))
        self.app.core.media_bytes(url).add_done_callback(done)

    def _put(self, at, what):
        if at == self.at and self.is_attached:
            self.query_one("#pic", Static).update(what)

    def action_step(self, d):
        if len(self.media) > 1:
            self.at = (self.at + d) % len(self.media)
            self.show()

    def action_original(self):
        m = self.media[self.at]
        url = m.remote_url or m.url
        if url and openable(url):
            webbrowser.open(url)


class LaneItem(ListItem):
    def __init__(self, name, title, n):
        # kept by reference: a count can come before the item is mounted, when a query
        # for its Label finds nothing yet (and that error took the whole app down)
        self.label = Label(self._text(title, n))
        super().__init__(self.label)
        self.lane = name

    @staticmethod
    def _text(title, n):
        t = Text(title, style="bold" if n else "")
        if n:
            t.append(f" {n}", style="bold green")
        return t

    def update(self, title, n):
        self.label.update(self._text(title, n))


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
        if isinstance(item, ActivityItem):  # a like, a mention…: the post it is about
            return item.activity.post
        return item.entry if isinstance(item, PostItem) else None

    def current_item(self):
        return self.query_one("#posts", ListView).highlighted_child

    def action_pictures(self):
        st = self.current()
        media = [m for m in real(st).media if m.kind in ("image", "gifv", "video")
                 and (m.preview or m.url)] if st else []
        if media:
            self.app.push_screen(PictureScreen(media))
        elif st:
            self.app.notify(_("tui_no_pictures"))

    def action_cursor_down(self):
        self.query_one("#posts", ListView).action_cursor_down()

    def action_cursor_up(self):
        self.query_one("#posts", ListView).action_cursor_up()

    def action_fav(self):
        st = self.current()
        if st:
            self.later(self.app.core.like(st), ok=self.status_changed)

    def action_boost(self):
        st = self.current()
        if st and real(st).visibility in ("public", "unlisted"):
            self.later(self.app.core.share(st), ok=self.status_changed)

    def action_bookmark(self):
        st = self.current()
        if st:
            self.later(self.app.core.bookmark(st), ok=self.status_changed)

    def action_reply(self):
        st = self.current()
        if not st:
            return
        alias = self.app.core.short_ids([st]).get(real(st).id)
        cmd = self.query_one("#cmd", Input)
        cmd.value = f"#{alias} " if alias else ""
        cmd.cursor_position = len(cmd.value)
        cmd.focus()

    def action_open(self):
        st = self.current()
        if st:
            self.app.push_screen(ThreadScreen(real(st).id))

    def action_profile(self):
        item = self.current_item()
        if isinstance(item, ActivityItem) and item.activity.who is not None:
            self.app.push_screen(ProfileScreen(item.activity.who.id))
            return
        if isinstance(item, RequestItem):
            self.app.push_screen(ProfileScreen(item.account.id))
            return
        st = self.current()
        if st:
            self.app.push_screen(ProfileScreen(real(st).author.id))

    def action_browser(self):
        st = self.current()
        url = real(st).url if st else None
        if url and openable(url):  # the web only: never a file or a share from a post
            webbrowser.open(url)
        elif url:
            self.app.notify(_("link_refused"))

    def status_changed(self, st):
        self.app.refresh_lane()

    def action_post_menu(self):
        st = self.current()
        if st is not None:
            self.app.post_menu(st, self)

    def action_editor(self):
        st = self.current()
        self.app.host.compose(reply_to=st)


class ThreadScreen(Screen, PostsMixin):
    BINDINGS = [Binding("escape,q", "app.pop_screen", _("tui_back")),
                Binding("j", "cursor_down", show=False), Binding("k", "cursor_up", show=False),
                Binding("r", "reply", _("reply")), Binding("f", "fav", _("fav")),
                Binding("b", "boost", _("boost")), Binding("m", "bookmark", _("bookmark")),
                Binding("o", "browser", _("open_browser"), show=False),
                Binding("p", "profile", _("tui_profile")),
                Binding("v", "pictures", _("tui_picture"), show=False),
                Binding("full_stop", "post_menu", "⋯"),
                Binding("w", "editor", _("tui_editor"), show=False),
                Binding("colon", "command", ":", show=False)]
    # the screen doesn't scroll as a whole, the list does (see ProfileScreen)
    CSS = """
    ThreadScreen { overflow: hidden hidden; layout: vertical; }
    ThreadScreen #posts { height: 1fr; }
    """

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

    async def fill(self, items_in):
        core = self.app.core
        lv = self.query_one("#posts", ListView)
        width = max(30, self.size.width - 6)
        posts = [n.post for n in items_in]
        short = core.short_ids(posts)
        unread = core.unread(posts)
        items, focus = [], 0
        for i, n in enumerate(items_in):
            pad = "  " * min(n.depth, 8)
            shown = show_post(core, n.post, short.get(n.post.id), n.post.id in unread,
                              n.number, width - len(pad))
            text = render(shown)
            if pad:
                text = Text("\n").join(Text(pad) + line for line in text.split())
            item = PostItem(n.post, text, key=n.post.id)
            item.depth = n.depth
            items.append(item)
            if n.post.id == self.status_id:
                focus = i
        root = posts[0] if posts else None
        self.query_one("#title", Static).update(
            _("tui_thread_title", who="@" + root.author.handle, n=len(posts) - 1)
            if root else "")
        await lv.clear()
        await lv.extend(items)
        lv.index = focus
        self.app.load_pictures(items)
        if core.cfg["read"]["mark_read"] != "manual":
            core.mark_read(posts)

    def action_command(self):
        self.query_one("#cmd", Input).focus()

    def status_changed(self, st):
        self.load()

    async def on_input_submitted(self, e: Input.Submitted):
        e.stop()
        await self.app.run_line(e.input, self)


class ProfileScreen(Screen, PostsMixin):
    """Someone's profile: who, the bio, follows you or not; F — follow / unfollow;
    their posts below (Enter — a thread).

    The header is a box of its own and the screen doesn't scroll as a whole: it used
    to, and highlighting the first post scrolled the header away — the profile
    flashed and what stayed looked just like a lane."""

    BINDINGS = [Binding("escape,q", "app.pop_screen", _("tui_back")),
                Binding("j", "cursor_down", show=False), Binding("k", "cursor_up", show=False),
                Binding("F", "follow", _("follow")),
                Binding("r", "reply", _("reply")), Binding("f", "fav", _("fav")),
                Binding("b", "boost", _("boost")), Binding("m", "bookmark", _("bookmark")),
                Binding("o", "browser", _("open_browser"), show=False),
                Binding("v", "pictures", _("tui_picture"), show=False),
                Binding("full_stop", "post_menu", "⋯", show=False),
                *[Binding(str(i), f"button({i})", show=False) for i in range(1, 10)],
                Binding("colon", "command", ":", show=False)]
    CSS = """
    ProfileScreen { overflow: hidden hidden; layout: vertical; }
    ProfileScreen #buttons { height: auto; padding: 0 1; }
    ProfileScreen #about { height: auto; max-height: 14; padding: 0 1 1 1;
                           border-bottom: solid $primary; overflow-y: auto; }
    ProfileScreen #posts-head { height: 1; padding: 0 1; color: $text-muted; }
    ProfileScreen #posts { height: 1fr; }
    """

    def __init__(self, acc_id):
        super().__init__()
        self.acc_id = acc_id
        self.acc, self.rel = None, None

    def compose(self) -> ComposeResult:
        yield Static(_("tui_profile") + " …", id="title")
        yield Static("…", id="about")
        yield Static("", id="buttons")
        yield Static(_("tui_profile_posts"), id="posts-head")
        yield ListView(id="posts")
        yield _cmd_line()
        yield Footer()

    def on_mount(self):
        core = self.app.core
        self.query_one("#posts", ListView).focus()
        self.later(core.account(self.acc_id), ok=self.got_account,
                   fail=lambda e: self.query_one("#about", Static).update(
                       Text(_("tui_profile_failed", err=e), style="red")))
        me = core.me
        if not me or self.acc_id != me.id:
            self.later(core.relationship(self.acc_id), ok=self.got_relation,
                       fail=lambda _e: None)
        self.later(core.account_posts(self.acc_id), ok=self.fill)

    def got_account(self, acc):
        self.acc = acc
        self.show_about()

    def got_relation(self, rel):
        self.rel = rel
        self.show_about()

    def own(self):
        me = self.app.core.me
        return bool(me and self.acc_id == me.id)

    def buttons(self):
        """The profile's buttons, the windows' (common/profile.py): keys 1…9."""
        from ..common import profile as prof
        if not self.acc:
            return []
        core = self.app.core
        return prof.actions(self.acc, self.rel, self.own(), core.cfg, core.supports,
                            lists=True)

    def action_button(self, n):
        from ..common import profile as prof
        acts = self.buttons()
        if not (0 < n <= len(acts)):
            return
        key = acts[n - 1].key

        def changed(rel):
            if rel is not None:
                self.got_relation(rel)
        prof.do(key, self.acc, self.rel, self.app.core, self.app.host, changed)

    def show_about(self):
        acc = self.acc
        if not acc:
            return
        head = Text(_("tui_profile_title", who=acc.handle) + "  ", style="bold")
        if acc.name and acc.name != acc.username:
            head.append(acc.name)
        self.query_one("#title", Static).update(head)
        t = Text()
        bits = [_("posts_n", n=acc.posts), _("followers_n", n=acc.followers),
                _("following_n", n=acc.following)]
        if self.rel and self.rel.followed_by:
            bits.append(_("acc_follows_you"))
        if self.rel and self.rel.following:
            bits.append("✓ " + _("tui_you_follow"))
        t.append(" · ".join(bits), style="dim")
        note = html_to_text(acc.note).strip()
        if note:
            t.append("\n" + note)
        for f in acc.fields:
            t.append("\n" + f.name + ": ", style="bold")
            t.append(html_to_text(f.value))
        from ..common import profile as prof
        line = prof.note_line(self.rel, self.own())
        if line:
            t.append("\n" + line, style="italic")
        self.query_one("#about", Static).update(t)
        from .screens import profile_line
        self.query_one("#buttons", Static).update(profile_line(self.buttons()))

    async def fill(self, page):
        core = self.app.core
        lv = self.query_one("#posts", ListView)
        width = max(30, self.size.width - 6)
        short = core.short_ids(page)
        parents = core.parents(page)
        items = [PostItem(e, render(show_post(core, e, short.get(real(e).id), width=width,
                                              parent=parents.get(e.id))), key=e.id)
                 for e in page]
        await lv.clear()
        await lv.extend(items)
        if items:
            lv.index = 0
            lv.scroll_home(animate=False)
        self.app.load_pictures(items)

    def action_follow(self):
        on = not (self.rel and self.rel.following)
        who = self.acc.handle if self.acc else "?"
        self.later(self.app.core.follow(self.acc_id, on),
                   ok=lambda rel: (self.app.notify(_("cmd_followed" if on else "cmd_unfollowed",
                                                     who=who)),
                                   self.got_relation(rel)))

    def action_command(self):
        self.query_one("#cmd", Input).focus()

    def status_changed(self, st):
        self.later(self.app.core.account_posts(self.acc_id), ok=self.fill)

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
                Binding("v", "pictures", _("tui_picture"), show=False),
                Binding("full_stop", "post_menu", "⋯"),
                Binding("g", "main_menu", "≡ " + _("menu")),
                Binding("slash", "search", _("search_title"), show=False),
                Binding("w", "editor", _("tui_editor"), show=False),
                Binding("ctrl+f", "find", _("find_next"), show=False),
                Binding("a", "request(True)", show=False),
                Binding("d", "request(False)", show=False),
                Binding("left_square_bracket", "lane_step(-1)", _("tui_lane_prev")),
                Binding("right_square_bracket", "lane_step(1)", _("tui_lane_next")),
                Binding("h", "to_lanes", _("tui_lanes_keys"), show=False),
                Binding("l", "to_posts", show=False),
                *[Binding(str(i), f"lane_number({i})", show=False) for i in range(1, 10)],
                # priority: the screen's own Tab (focus next) used to win, and the lanes
                # couldn't be reached without the mouse
                Binding("tab", "switch", _("tui_switch"), show=False, priority=True),
                Binding("colon", "command", ":", show=False),
                Binding("escape", "escape", show=False)]

    def __init__(self, core, instance=None):
        super().__init__()
        self.core = core if isinstance(core, View) else View(core)
        core = self.core
        from ..common.links import Links
        from .host import TuiHost
        self.host = TuiHost(self)  # what a link, a menu item, a profile button asks for
        self.links = Links(core, self.host)
        self._instance = instance
        self.cmds = Commands(core)
        self.delete_guard = DeleteGuard()
        self.lane = None
        self._ui_thread = None
        self._ui_loop = None
        tcfg = core.cfg.get("tui", {})
        self.lanes_width = int(tcfg.get("lanes_width", 26))
        self._theme_wanted = tcfg.get("theme", "")
        self._redraw_pending = False
        self._pictures = {}  # (address, cols, rows) -> the drawn picture
        self._picture_failed = False

    # ---- threads -------------------------------------------------------------------
    def in_ui(self, fn, *args):
        """Run fn(*args) in the interface's thread, from wherever — without waiting for
        it: Textual's call_from_thread waits for the answer, and a picture's or a poll's
        thread that came back while the app was closing waited forever (and with it the
        core's shutdown, which waits for its threads)."""
        if threading.get_ident() == self._ui_thread:
            self.call_next(fn, *args)
            return
        loop = self._ui_loop
        if loop is None or loop.is_closed() or not getattr(self, "is_running", True):
            return  # not started yet, or gone
        try:
            loop.call_soon_threadsafe(self._run_in_ui, fn, args)
        except RuntimeError:  # the loop closed just now
            pass

    def _run_in_ui(self, fn, args):
        if getattr(self, "is_running", True):
            self.call_next(fn, *args)

    def _main(self, selector, kind=None):
        """A widget of the main screen, whatever screen is on top now: core events come
        while a thread, a profile or the composer is open (App.query_one only looks at
        the screen on top, and the lanes aren't there)."""
        screen = self.screen_stack[0] if self.screen_stack else self.screen
        return screen.query_one(selector, kind) if kind else screen.query_one(selector)

    def _make_sounds(self):
        """tui.sound: the terminal's bell, the theme's sounds on this computer, or none."""
        how = self.core.cfg.get("tui", {}).get("sound", "bell")
        if how == "off":
            return None
        from ..common.sound import Sounds
        return Sounds(self.core.cfg, self.core.cfg["ui"].get("theme", "system"),
                      bell=self.bell, only_bell=(how == "bell"))

    def play_sound(self, event):
        # the terminal can't tell whether it is looked at: "when focused" is always so
        self.sounds.play(event, focused=False)

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
        self._ui_loop = asyncio.get_running_loop()
        self.title = "fedtail"
        self.query_one("#lanes").styles.width = self.lanes_width
        if self._theme_wanted:
            try:
                self.theme = self._theme_wanted
            except Exception as e:  # noqa: BLE001 — an unknown name: Textual's default
                log.warning("tui.theme %s: %s", self._theme_wanted, e)
        if self._instance is not None:
            self._instance.listen(lambda _m: None)
        self.core.on("lanes_updated", lambda _n, p: self.in_ui(self.lanes_updated, p))
        for event in ("activity_updated", "activity_seen", "requests_updated"):
            self.core.on(event, lambda n, _p: self.in_ui(self.other_updated, n))
        self.core.on("error", lambda _n, p: self.in_ui(self.show_error, p))
        self.sounds = self._make_sounds()
        if self.sounds is not None:
            self.core.on("sound", lambda _n, p: self.in_ui(self.play_sound, p))
        if not self.core.logged_in:
            self.push_screen(LoginScreen())
            return
        self.begin()

    def begin(self):
        self._main("#title", Static).update(_("tui_connecting"))
        self.later(self.core.connect(), ok=self.connected,
                   fail=lambda e: self.show_error(_("tui_connect_failed", err=e)))

    async def connected(self, _me):
        me = self.core.me
        self.sub_title = "@" + (me.handle if me else "")
        await self.fill_lanes()
        self.core.start_polling()
        first = start_lane(self.core, self._lane_names())
        if first:
            await self.select_lane(first)
        self._main("#posts", ListView).focus()

    async def fill_lanes(self):
        lv = self._main("#lanes", ListView)
        await lv.clear()
        items = []
        for _group, names in ordered_lanes(self.core):
            for name in names:
                title, n = lane_label(self.core, name, self.lanes_width - 2)
                items.append(LaneItem(name, title, n))
        await lv.extend(items)

    def update_lane_counts(self):
        for item in self._main("#lanes", ListView).children:
            if isinstance(item, LaneItem):
                item.update(*lane_label(self.core, item.lane, self.lanes_width - 2))

    async def select_lane(self, name):
        self._found = None
        self.lane = name
        self.core.set_active_lane(name)
        self.core.set_state("lane", name)
        lanes = self._main("#lanes", ListView)
        for i, item in enumerate(lanes.children):
            if isinstance(item, LaneItem) and item.lane == name:
                if lanes.index != i:
                    lanes.index = i
        await self.refresh_posts(first=True)

    async def refresh_posts(self, first=False):
        core, name = self.core, self.lane
        if name is None:
            return
        lv = self._main("#posts", ListView)
        if name in ("activity", "requests"):  # not posts: rows of their own
            await self._fill_other(lv, name, first)
            return
        entries = core.entries(name)
        if core.cfg["feed"]["order"] == "newest_first":
            entries = list(reversed(entries))
        keep = getattr(lv.highlighted_child, "key", None)
        unread = core.unread(entries)
        short = core.short_ids(entries)
        parents = core.parents(entries)
        width = max(30, lv.size.width - 4 if lv.size.width else 76)
        items = []
        for item_id, e in entries:
            shown = show_post(core, e, short.get(real(e).id), e.id in unread,
                              width=width, parent=parents.get(e.id))
            items.append(PostItem(e, render(shown), key=item_id))
        title = core.lane_title(name) or _("lane_" + name)
        self._main("#title", Static).update(
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
        self.load_pictures(items)

    # ---- pictures in the lane (tui.pictures = "inline") ------------------------------
    def load_pictures(self, items):
        """Draw each post's first picture under it, as the bytes come. Small and
        cached by address and size, so redrawing a lane costs nothing."""
        tcfg = self.core.cfg.get("tui", {})
        if tcfg.get("pictures", "inline") != "inline" or not pictures.available():
            return
        rows = max(2, int(tcfg.get("picture_rows", 8)))
        cols = rows * 4  # about a 2:1 box: room for a landscape photo
        cache = self._pictures
        for item in items:
            if not isinstance(item, PostItem):
                continue
            m = first_picture(item.entry)
            if m is None:
                continue
            url = m.preview or m.url
            key = (url, cols, rows)
            if key in cache:
                item.set_picture(cache[key])
                continue

            def done(f, item=item, key=key, url=url):
                try:
                    drawn = pictures.blocks(f.result(), cols, rows)
                except Exception as e:  # noqa: BLE001 — no picture, the text stays
                    # the first one said aloud: "no pictures in the terminal" was
                    # silent before (a refused address, a proxy, a timeout)
                    (log.debug if self._picture_failed else log.warning)(
                        "tui picture %s: %s", url, e)
                    self._picture_failed = True
                    return
                if drawn is None:
                    return
                if len(cache) > 400:
                    cache.clear()
                cache[key] = drawn
                self.in_ui(self._put_picture, item, drawn)
            self.core.media_bytes(url).add_done_callback(done)

    @staticmethod
    def _put_picture(item, drawn):
        if item.is_attached:
            item.set_picture(drawn)

    async def _fill_other(self, lv, name, first):
        core = self.core
        width = max(30, lv.size.width - 4 if lv.size.width else 76)
        keep = getattr(lv.highlighted_child, "key", None)
        if name == "activity":
            seen = core.activity_seen()
            rows = core.activity(300)  # newest first
            if core.cfg["feed"]["order"] == "oldest_first":
                rows = list(reversed(rows))
            items = [ActivityItem(a, render(show_activity(a, width, a.sort > seen)))
                     for a in rows]
            empty = _("activity_none")
        else:
            items = [RequestItem(acc, render(show_request(acc, width)))
                     for acc in core.follow_requests()]
            empty = _("no_requests")
        title = core.lane_title(name) or _("lane_" + name)
        self._main("#title", Static).update(Text(title, style="bold"))
        await lv.clear()
        if not items:
            await lv.append(ListItem(Static(Text(empty, style="dim"))))
            self.update_lane_counts()
            return
        await lv.extend(items)
        keys = [it.key for it in items]
        if keep in keys and not first:
            lv.index = keys.index(keep)
        else:
            newest = 0 if core.cfg["feed"]["order"] == "newest_first" else len(items) - 1
            lv.index = newest
        if name == "activity":
            core.mark_activity_seen()  # on screen: seen, as in the window
        self.update_lane_counts()

    def _start_index(self, entries, unread):
        """feed.start_at: the first unread (oldest first) or the newest."""
        newest = 0 if self.core.cfg["feed"]["order"] == "newest_first" else len(entries) - 1
        if self.core.cfg["feed"]["start_at"] == "newest" or not unread:
            return newest
        for i, (_item, e) in enumerate(entries):
            if e.id in unread:
                if self.core.cfg["feed"]["order"] == "newest_first":
                    continue  # the last unread in this order is the oldest one
                return i
        return max(i for i, (_x, e) in enumerate(entries) if e.id in unread)

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

    async def other_updated(self, event):
        """Activity or follow requests changed: the lane redrawn if it is on screen
        (not for "seen" — that is this very lane being looked at), the counts anyway."""
        lane = "requests" if event == "requests_updated" else "activity"
        if self.lane == lane and event != "activity_seen" and not self._redraw_pending:
            self._redraw_pending = True
            try:
                await self.refresh_posts()
            finally:
                self._redraw_pending = False
        else:
            self.update_lane_counts()

    def _lane_names(self):
        return [i.lane for i in self._main("#lanes", ListView).children
                if isinstance(i, LaneItem)]

    def refresh_lane(self):
        self.call_next(self.refresh_posts)

    # ---- events --------------------------------------------------------------------
    async def on_list_view_selected(self, e: ListView.Selected):
        e.stop()
        if e.list_view.id == "lanes" and isinstance(e.item, LaneItem):
            await self.select_lane(e.item.lane)
            self.query_one("#posts", ListView).focus()
        elif e.list_view.id == "posts" and isinstance(e.item, RequestItem):
            self.push_screen(ProfileScreen(e.item.account.id))
        elif e.list_view.id == "posts" and isinstance(e.item, ActivityItem):
            a = e.item.activity
            if a.post is not None:
                self.push_screen(ThreadScreen(a.post.id))
            elif a.who is not None:
                self.push_screen(ProfileScreen(a.who.id))
        elif e.list_view.id == "posts" and self.screen is self.screen_stack[0]:
            self.action_open()
        elif e.list_view.id == "posts" and isinstance(self.screen, ProfileScreen):
            self.screen.action_open()

    def on_list_view_highlighted(self, e: ListView.Highlighted):
        if e.list_view.id != "posts" or not isinstance(e.item, PostItem):
            return
        if self.core.cfg["read"]["mark_read"] == "on_scroll":
            entry = e.item.entry
            if entry.id in self.core.unread([entry]):
                self.core.mark_read([entry])
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
                self.push_screen(ProfileScreen(result[1].id))
            elif isinstance(result, tuple) and result[0] == "delete":
                st = result[1]
                if self.delete_guard.confirmed(st.id):
                    self.later(self.core.delete(st), ok=lambda _r: self.notify(_("deleted")))
                else:  # asked first: the line stays, Enter again deletes
                    field.value = line
                    self.notify(_("tui_delete_again", text=snippet(st, 120)),
                                severity="warning", timeout=15)
            elif isinstance(result, str):
                self.notify(result)
            elif result is not None:  # a post went out
                self.notify(message or _("sent"))
            where.query_one("#posts", ListView).focus()

        def fail(err):
            field.disabled = False
            self.show_error(_("send_failed_text", err=err))
        self.later(fut, ok=ok, fail=fail)

    # ---- what the host and the screens ask of the app -----------------------------------
    @staticmethod
    def date_words(when):
        return when.astimezone().strftime("%d.%m.%Y %H:%M") if when else ""

    def thread_screen(self, sid):
        return ThreadScreen(sid)

    def profile_screen(self, acc_id):
        return ProfileScreen(acc_id)

    def open_thing(self, o):
        """Where an action leads: {"thread"}, {"account"}, {"url"}, {"page", "arg", …}."""
        if not o:
            return
        if o.get("thread"):
            self.push_screen(ThreadScreen(o["thread"]))
        elif o.get("account"):
            self.push_screen(ProfileScreen(o["account"]))
        elif o.get("url"):
            self.host.open_url(o["url"])
        elif o.get("page"):
            from .screens import PlaceScreen
            self.push_screen(PlaceScreen(o["page"], o.get("arg", ""), o.get("tab", ""),
                                         o.get("cursor", ""), o.get("anchor", "")))

    def copy_text(self, text):
        """To the clipboard: the terminal's own (OSC 52), where it has one."""
        copy = getattr(self, "copy_to_clipboard", None)
        if copy is not None:
            try:
                copy(text)
            except Exception as e:  # noqa: BLE001 — a terminal without it: said below
                log.debug("clipboard: %s", e)
        self.notify(_("web_copied") + ": " + text)

    def put_in_command_line(self, text):
        cmd = self._main("#cmd", Input) if self.screen is self.screen_stack[0] else \
            self.screen.query_one("#cmd", Input)
        cmd.value = text
        cmd.cursor_position = len(text)
        cmd.focus()

    def read_up_to(self, sid):
        """This post and everything older in the lane: read (⋯ → read up to here)."""
        if not self.lane:
            return
        ids = [e.id for _i, e in self.core.entries(self.lane)]
        if sid in ids:
            self.core.mark_read(ids[:ids.index(sid) + 1])
            self.refresh_lane()

    def post_reply(self, st, _where=None):
        alias = self.core.short_ids([st]).get(real(st).id)
        self.put_in_command_line(f"#{alias} " if alias else "")

    def post_fav(self, st, where=None):
        self.later(self.core.like(st), ok=lambda _s: (where or self).status_changed(_s))

    def post_boost(self, st, where=None):
        if real(st).visibility in ("public", "unlisted"):
            self.later(self.core.share(st), ok=lambda _s: (where or self).status_changed(_s))

    def post_bookmark(self, st, where=None):
        self.later(self.core.bookmark(st), ok=lambda _s: (where or self).status_changed(_s))

    def menu_ctx(self, in_thread=False):
        from ..common import actions
        core = self.core
        me = core.me
        return actions.Ctx(cfg=core.cfg, me_id=me.id if me else None, supports=core.supports,
                           subscribed=core.subscribed, thread_quiet=core.thread_quiet,
                           lists=True, long_form=bool(core.cfg["feed"].get("long_form", True)),
                           translate=bool(getattr(core.caps, "translation", False)),
                           quote_reply=True, in_thread=in_thread)

    def post_menu_items(self, st, in_thread=False):
        """A post's ⋯ menu, the windows' own (common/actions.py): [(label, item)]."""
        from ..common import actions
        core = self.core
        short = core.short_ids([st]).get(real(st).id)
        unread = st.id in core.unread([st])
        out = []
        for it in actions.menu(st, self.menu_ctx(in_thread), short, unread):
            if it.kind == "separator":
                if out and out[-1] != "-":
                    out.append("-")
            elif it.kind != "act_as":  # one account a terminal
                out.append((it.label + (" …" if it.kind in ("lists", "long_form",
                                                             "translate") else ""), it))
        while out and out[-1] == "-":
            out.pop()
        return out

    def post_menu(self, st, where=None):
        from .screens import MenuScreen
        items = self.post_menu_items(st, isinstance(where, ThreadScreen))

        def chosen(it):
            if it is not None:
                self.do_menu_item(st, it)
        self.push_screen(MenuScreen("⋯ " + "@" + real(st).author.handle, items), chosen)

    def do_menu_item(self, st, it):
        """One item of a post's ⋯ menu, as the windows do it."""
        if it.kind == "link":
            self.links.open(it.url)
        elif it.kind == "open":
            self.host.open_url(it.url)
        elif it.kind == "copy":
            self.copy_text(it.text)
        elif it.kind == "lists":
            self.host.open_lists(it.data)
        elif it.kind in ("long_form", "translate"):
            self.open_thing({"page": it.kind, "arg": real(st).id})
        elif it.kind == "quote_reply":
            from ...model.text import quote_lines
            self.host.compose(reply_to=st, text=quote_lines(
                real(st).text, self.core.cfg["post"].get("quote_prefix", "> "),
                strip_mentions=True))

    def main_menu_items(self):
        """The ≡ menu: writing, the places (common/places.py), help, debug, quit."""
        from ..common.places import Places
        places = [(t + " …", ("place", n)) for n, t in Places(self.core).menu()
                  if n not in ("help", "news", "about", "federation")]
        return ([("✎ " + _("write"), ("do", "editor")),
                 (_("my_profile"), ("do", "my_profile")),
                 (_("refresh"), ("do", "refresh")),
                 (_("tui_all_read"), ("do", "all_read")), "-"]
                + places + ["-",
                            (_("help_title") + " …", ("place", "help")),
                            (_("help_news") + " …", ("place", "news")),
                            (_("about") + " …", ("place", "about")), "-",
                            (_("debug_federation"), ("place", "federation")),
                            (_("debug_report"), ("do", "bug_report")),
                            (_("debug_logs"), ("do", "logs")),
                            (_("debug_sound"), ("do", "test_sound")),
                            (_("debug_stacks"), ("do", "stacks")), "-",
                            (_("quit"), ("do", "quit"))])

    def action_main_menu(self):
        from .screens import MenuScreen

        def chosen(v):
            if v is None:
                return
            kind, what = v
            if kind == "place":
                self.open_thing({"page": what})
            else:
                self.call_next(self.menu_do, what)
        self.push_screen(MenuScreen("≡ fedtail", self.main_menu_items()), chosen)

    async def menu_do(self, what):
        from ... import diag
        if what == "editor":
            self.host.compose()
        elif what == "my_profile" and self.core.me:
            self.push_screen(ProfileScreen(self.core.me.id))
        elif what == "refresh":
            self.action_refresh()
        elif what == "all_read":
            self.action_all_read()
        elif what == "bug_report":
            try:
                diag.log_stats()
                out = diag.bug_report(self.core.paths, cfg=self.core.cfg)
                self.notify(_("debug_report_done", path=str(out)), timeout=20)
            except OSError as e:
                self.show_error(e)
        elif what == "logs":
            self.notify(str(diag.logs_dir(self.core.paths, self.core.cfg)), timeout=20)
        elif what == "test_sound" and self.sounds is not None:
            self.notify(self.sounds.test())
        elif what == "stacks":
            diag.dump_stacks("menu")
            self.notify(_("debug_stacks_done"))
        elif what == "quit":
            self.exit()

    def action_search(self):
        self.open_thing({"page": "search"})

    # ---- Ctrl+F: find in the lane (the windows' rule: every word, text, names, #id) -----
    def action_find(self):
        if getattr(self, "_found", None) and self._found["lane"] == self.lane:
            self._find_step()
            return
        from .screens import AskScreen

        def got(q):
            if q is not None:
                self.find(q)
        self.push_screen(AskScreen(_("find_next"), _("find_placeholder")), got)

    def find(self, query):
        from ...model.text import haystack, matches
        from ..common.find import count_text
        lv = self._main("#posts", ListView)
        items = [it for it in lv.children if isinstance(it, PostItem)]
        short = self.core.short_ids([it.entry for it in items])
        hits = [i for i, it in enumerate(lv.children) if isinstance(it, PostItem) and
                matches(query, haystack(it.entry, short.get(real(it.entry).id)))]
        self._found = {"lane": self.lane, "hits": hits, "at": -1, "query": query}
        if not hits:
            self._found = None
            self.notify(count_text(query, -1, 0)[0], severity="warning")
            return
        self._find_step()

    def _find_step(self):
        f = self._found
        f["at"] = (f["at"] + 1) % len(f["hits"])
        lv = self._main("#posts", ListView)
        lv.index = f["hits"][f["at"]]
        lv.focus()
        self.notify(_("find_count", i=f["at"] + 1, n=len(f["hits"])))

    # ---- actions -------------------------------------------------------------------
    def action_new(self):
        cmd = self.query_one("#cmd", Input)
        cmd.value = ""
        cmd.focus()

    def action_command(self):
        self.query_one("#cmd", Input).focus()

    def action_switch(self):
        if self.screen is not self.screen_stack[0]:  # a thread, a profile: Tab as usual
            self.screen.focus_next()
            return
        lanes, posts = self.query_one("#lanes", ListView), self.query_one("#posts", ListView)
        (posts if lanes.has_focus else lanes).focus()

    def _lanes_focused(self):
        try:
            return self._main("#lanes", ListView).has_focus
        except Exception:  # noqa: BLE001 — not built yet
            return False

    def action_cursor_down(self):  # j / k move whichever list has the focus
        if self._lanes_focused():
            self._main("#lanes", ListView).action_cursor_down()
        else:
            super().action_cursor_down()

    def action_cursor_up(self):
        if self._lanes_focused():
            self._main("#lanes", ListView).action_cursor_up()
        else:
            super().action_cursor_up()

    def action_to_lanes(self):
        self._main("#lanes", ListView).focus()

    def action_to_posts(self):
        lanes = self._main("#lanes", ListView)
        if lanes.has_focus and isinstance(lanes.highlighted_child, LaneItem) and \
                lanes.highlighted_child.lane != self.lane:
            self.call_next(self.select_lane, lanes.highlighted_child.lane)
        self._main("#posts", ListView).focus()

    async def action_lane_step(self, d):
        names = self._lane_names()
        if not names:
            return
        i = names.index(self.lane) if self.lane in names else -1
        await self.select_lane(names[(i + d) % len(names)])

    async def action_lane_number(self, n):
        names = self._lane_names()
        if 0 < n <= len(names):
            await self.select_lane(names[n - 1])

    def action_request(self, approve):
        item = self.current_item()
        if not isinstance(item, RequestItem):
            return
        who = item.account.handle
        self.later(self.core.answer_follow(item.account.id, approve),
                   ok=lambda _r: self.notify(("✔ " if approve else "✘ ") + "@" + who))

    def action_escape(self):
        cmd = self.query_one("#cmd", Input)
        if cmd.has_focus:
            self.query_one("#posts", ListView).focus()

    def action_refresh(self):
        self.core.poll_now()
        self.notify(_("refresh"))

    def action_all_read(self):
        if self.lane:
            self.core.mark_lane_read(self.lane)
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
