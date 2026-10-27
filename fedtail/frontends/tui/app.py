"""The Textual application: lanes on the left, posts on the right, the command
line at the bottom. Keys as in the window: j / k, Enter — the thread, r — reply,
f — like, b — boost, m — bookmark, . — the post's ⋯ menu, n — a line to post, w — the
editor, x — the lane read, g — the ≡ menu (every place: search, lists, silence, help…),
/ — search, Ctrl+F — find in the lane, Esc — back; [ / ] or 1…9 — another lane,
h / l — to the lanes / the posts, Tab — between them; v — the post's pictures full
screen (sixel or kitty graphics where the terminal can, half blocks elsewhere — see
pictures.py; with chafa, timg or kitty's icat the picture is shown by them, the app
suspended) and its video in mpv (termcaps.py). What a menu item, a profile's button
or a link does is the windows' (common/links.py, common/profile.py) through TuiHost
(host.py); the places are common/places.py's (screens.py)."""

import asyncio
import contextlib
import inspect
import logging
import os
import subprocess
import tempfile
import threading
import webbrowser

from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import Footer, Input, Label, ListItem, ListView, Static

from ... import sysenv
from ...core.view import View
from ...i18n import _
from ...model import real
from ...model.text import html_to_text, snippet
from ...version import NAME
from ..common import timed
from ..richtext import openable
from . import pictures, termcaps
from .model import (
    Commands,
    DeleteGuard,
    lane_groups,
    lane_label,
    show_activity,
    show_post,
    show_request,
    start_lane,
)

log = logging.getLogger(__name__)

STYLE = {"num": "bold magenta", "alias": "cyan", "who": "bold", "name": "dim",
         "time": "dim", "boost": "green", "direct": "yellow", "muted": "dim",
         "unread": "bold green", "quote": "italic", "myreply": "dim cyan",
         "conv": "cyan", "divider": "bold green", "newcomer": "bold red"}


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
    for kind, line in getattr(shown, "above", ()):
        t.append(line + "\n", style=STYLE.get(kind, ""))
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
    for kind, line in getattr(shown, "below", ()):
        t.append("\n" + line, style=STYLE.get(kind, ""))
    return t


class PostItem(ListItem):
    def __init__(self, entry, text, key=None):
        self.body = Static(text, classes="post")  # kept: a picture comes in later
        super().__init__(self.body)
        self.entry = entry  # a Post or a Share
        self.key = key
        self.text = text
        self.has_picture = False
        self.graphic = None

    def set_picture(self, pic):
        """The post's first picture under its text, in half blocks."""
        self.has_picture = pic is not None
        self.body.update(self.text + Text("\n") + pic if pic is not None else self.text)

    def set_graphic(self, widget):
        """The post's first picture under its text for real (sixel, kitty): a widget of
        its own under the text, the one before it gone."""
        if self.graphic is not None:
            self.graphic.remove()
        self.graphic = widget
        self.has_picture = widget is not None
        if widget is not None:
            self.mount(widget)


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


PLAYABLE = ("video", "gifv")


def first_picture(entry):
    """The first picture of a post (Post or Share) worth drawing, or None."""
    for m in real(entry).media:
        if m.kind in ("image", "gifv", "video") and (m.preview or m.url):
            return m
    return None


class PictureScreen(Screen):
    """A post's pictures over everything: ← / → through them, Enter — play a video,
    o — the original in the browser, Esc — back. As big as the terminal allows: sixel
    or kitty graphics where it can, half blocks elsewhere."""

    BINDINGS = [Binding("escape,q,v", "app.pop_screen", _("tui_back")),
                Binding("left,h,k", "step(-1)", "←"), Binding("right,l,j", "step(1)", "→"),
                Binding("enter,p,space", "play", _("tui_play")),
                Binding("s", "save", _("viewer_save")),
                Binding("r", "again", show=False),
                Binding("d", "description", _("alt_title")),
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

    def action_description(self):
        """d: a long description whole (most of the screen), and back to four lines."""
        alt = self.query_one("#pic-alt", Static)
        alt.styles.max_height = 4 if alt.styles.max_height and \
            alt.styles.max_height.value != 4 else "70%"

    def on_resize(self, _event):
        self.show()

    def show(self):
        m = self.media[self.at]
        n = len(self.media)
        title = _("tui_picture_of", i=self.at + 1, n=n) if n > 1 else _("tui_picture")
        if m.kind in PLAYABLE:  # its still frame below: Enter plays it
            title += " · ▶ " + _("tui_play_hint")
        title += " · s — " + (_("save_media") if m.kind in PLAYABLE else _("save_image"))
        head = self.query_one("#pic-title", Static)
        head.update(title)
        head.tooltip = _("viewer_save_tip")
        self.query_one("#pic-alt", Static).update(Text(m.alt or "", style="dim"))
        pic = self.query_one("#pic", Static)
        self._drop_graphic()
        pic.display = True
        if not pictures.available():
            pic.update(_("tui_no_pil"))
            return
        pic.update("▶ " + _("tui_play_hint") if m.kind in PLAYABLE else _("image_loading"))
        cols = max(10, self.size.width - 2)
        rows = max(4, self.size.height - 4 - (2 if m.alt else 0))
        # a picture whole; a video's still frame (never the video fetched as a picture)
        url = (m.url or m.preview) if m.kind == "image" else m.preview
        if not url:
            pic.update("▶ " + _("media_" + m.kind) + " — " + _("tui_play_hint"))
            return
        at = self.at
        real_ones = pictures.graphics() is not None
        app = self.app  # kept now: the answer may come after the app has ended

        def done(f):
            try:
                data = f.result()
            except Exception as e:  # noqa: BLE001 — said on the screen: r again, o browser
                app.in_ui(self._put, at, _("viewer_unreachable", err=e))
                return
            if real_ones:
                app.in_ui(self._put_graphic, at, data, cols, rows)
                return
            drawn = pictures.blocks(data, cols, rows)
            app.in_ui(self._put, at, drawn if drawn is not None else
                      _("tui_picture_failed", err="?"))
        app.core.media_bytes(url).add_done_callback(done)

    def _put(self, at, what):
        if at == self.at and self.is_attached:
            self.query_one("#pic", Static).update(what)

    def _put_graphic(self, at, data, cols, rows):
        if at != self.at or not self.is_attached:
            return
        w = pictures.graphic(data, rows, classes="pic-img")
        if w is None:
            self._put(at, _("tui_picture_failed", err="?"))
            return
        w.styles.max_width = cols
        self._drop_graphic()
        self.query_one("#pic", Static).display = False
        self.mount(w, before=self.query_one("#pic-alt"))

    def _drop_graphic(self):
        for old in self.query(".pic-img"):
            old.remove()

    def action_play(self):
        m = self.media[self.at]
        if m.kind in PLAYABLE:
            self.app.play(m)

    def action_step(self, d):
        if len(self.media) > 1:
            self.at = (self.at + d) % len(self.media)
            self.show()

    def action_again(self):
        """r: once more, after the original didn't load (viewer_unreachable)."""
        self.show()

    def action_original(self):
        m = self.media[self.at]
        url = m.remote_url or m.url
        if url and openable(url):
            webbrowser.open(url)

    def action_save(self):
        """s: the original into ui.save_dir, as the windows' "Save picture"."""
        self.app.save_media(self.media[self.at])


class GroupItem(ListItem):
    """A section's heading in the lanes (ui.sidebar_groups): Enter folds it away and
    back (kept in the profile's state, the windows fold the same)."""

    def __init__(self, key, title, folded, n=0):
        self.label = Label(self._text(title, folded, n))
        super().__init__(self.label)
        self.group, self.title, self.folded = key, title, folded
        self.tooltip = _("group_fold_tip")

    @staticmethod
    def _text(title, folded, n):
        t = Text(("▸ " if folded else "▾ ") + title.upper(), style="bold dim")
        if folded and n:
            t.append(f" {n}", style="bold green")
        return t


class LaneItem(ListItem):
    def __init__(self, name, title, n, fresh=0):
        # kept by reference: a count can come before the item is mounted, when a query
        # for its Label finds nothing yet (and that error took the whole app down)
        self.label = Label(self._text(title, n, fresh))
        super().__init__(self.label)
        self.lane = name

    @staticmethod
    def _text(title, n, fresh=0):
        t = Text(title, style="bold" if n else "")
        if n:
            t.append(f" {n}", style="bold green")
            if fresh:  # of them, what the last update brought
                t.append(f" +{fresh}", style="dim green")
        return t

    def update(self, title, n, fresh=0):
        self.label.update(self._text(title, n, fresh))


class Ui:
    """What both screens need: run a core future, hear back in the UI thread."""

    def later(self, fut, ok=None, fail=None):
        """fut's answer to ok (or its error to fail) in the interface's thread — unless
        this screen was closed meanwhile: a thread that loaded after Esc took it away
        found no "#posts" and brought the whole terminal down (the night of 23.10)."""
        app = self.app
        me = self

        async def guarded(fn, arg):
            if me is not app and not getattr(me, "is_attached", True):
                return
            if me is app and (not getattr(app, "is_running", True) or not app.screen_stack):
                return  # the app is closing (Esc while it connected): nothing to draw on
            got = fn(arg)
            if inspect.isawaitable(got):
                await got

        def done(f):
            if f.cancelled():
                return
            exc = f.exception()
            if exc is not None:
                if fail is None:
                    app.in_ui(app.show_error, str(exc))
                else:
                    app.in_ui(guarded, fail, str(exc))
            elif ok:
                app.in_ui(guarded, ok, f.result())
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
        """v: the post's pictures — shown by chafa/timg/icat with the app suspended
        when one is there (tui.viewer = "auto"), else in the app; a post of videos
        only — the first one plays (tui.video)."""
        st = self.current()
        media = [m for m in real(st).media if m.kind in ("image", "gifv", "video")
                 and (m.preview or m.url)] if st else []
        if not media:
            if st:
                self.app.notify(_("tui_no_pictures"))
            return
        if all(m.kind in PLAYABLE for m in media):
            self.app.play(media[0])
            return
        images = [m for m in media if m.kind == "image"]
        if images and self.app.show_outside(images):
            return
        self.app.push_screen(PictureScreen(media))

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

    def action_poll(self):
        """u: the post's poll — vote, the results, fresh counts (more.py)."""
        st = self.current()
        if st is not None and real(st).poll is not None:
            from .more import PollScreen
            self.app.push_screen(PollScreen(st, self))


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
                Binding("u", "poll", "📊 " + _("poll_vote"), show=False),
                Binding("c", "all_cw", _("cw_all_show"), show=False),
                Binding("s", "follow_thread", _("sub_tip"), show=False),
                Binding("colon", "command", ":", show=False)]
    # the screen doesn't scroll as a whole, the list does (see ProfileScreen)
    CSS = """
    ThreadScreen { overflow: hidden hidden; layout: vertical; }
    ThreadScreen #posts { height: 1fr; }
    """

    def __init__(self, status_id):
        super().__init__()
        self.status_id = status_id
        self.cw_open = False
        self.root = None
        self.nodes = []

    def compose(self) -> ComposeResult:
        yield Static(_("thread_loading"), id="title")
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
        self.nodes = list(items_in)
        lv = self.query_one("#posts", ListView)
        keep = getattr(lv.highlighted_child, "key", None)
        width = max(30, self.size.width - 6)
        posts = [n.post for n in items_in]
        short = core.short_ids(posts)
        unread = core.unread(posts)
        items, focus = [], 0
        for i, n in enumerate(items_in):
            pad = "  " * min(n.depth, 8)
            shown = show_post(core, n.post, short.get(n.post.id), n.post.id in unread,
                              n.number, width - len(pad), open_cw=self.cw_open)
            if n.post.id == self.status_id and i:  # where the reader came from
                shown.above.insert(0, ("conv", "↘ " + _("came_from")))
            text = render(shown)
            if pad:
                text = Text("\n").join(Text(pad) + line for line in text.split())
            item = PostItem(n.post, text, key=n.post.id)
            item.depth = n.depth
            items.append(item)
            if n.post.id == self.status_id:
                focus = i
        root = posts[0] if posts else None
        self.root = root
        self.info = ""
        if root is not None:
            self.info = "@" + root.author.handle + " · " + _("thread_info", n=len(posts) - 1) \
                + (f" · #{short[root.id]}" if short.get(root.id) else "") \
                + (" · ✓ " + _("subscribed") if core.subscribed(root) else "")
            if any(p.warning for p in posts):
                self.info += " · c — " + (_("cw_all_hide") if self.cw_open else
                                          _("cw_all_show"))
        self.query_one("#title", Static).update(self.info)
        if root is not None and not core.subscribed(root):
            self.later(core.followed_among([p.author for p in posts]), ok=self.via_home,
                       fail=lambda _e: None)
        await lv.clear()
        await lv.extend(items)
        keys = [it.key for it in items]
        lv.index = keys.index(keep) if keep in keys else focus
        self.app.load_pictures(items)
        if core.cfg["read"]["mark_read"] != "manual":
            core.mark_read(posts)

    def via_home(self, followed):
        """Not followed, yet the replies come: the server puts replies between people I
        follow into Home — said in the title, as the windows' thread header."""
        if not followed or self.root is None or self.app.core.subscribed(self.root):
            return
        names = ", ".join("@" + a.handle.split("@")[0] for a in followed[:3])
        if len(followed) > 3:
            names += " " + _("and_more", n=len(followed) - 3)
        self.query_one("#title", Static).update(
            Text(self.info + " · " + _("thread_via_home", names=names)))
        self.tooltip = _("thread_via_home_tip")

    async def action_all_cw(self):
        """c: every text behind a warning in the thread, open or closed (cw_all_tip)."""
        self.cw_open = not self.cw_open
        await self.fill(self.nodes)
        self.app.notify(_("cw_all_tip"), timeout=3)

    def action_follow_thread(self):
        """s: follow the thread (its new comments to the Subscriptions lane) or stop."""
        if self.root is None:
            return
        core = self.app.core
        if core.subscribed(self.root):
            self.later(core.unsubscribe(self.root),
                       ok=lambda _r: (self.app.notify(_("unsubbed")), self.load()))
        else:
            self.later(core.subscribe(self.root),
                       ok=lambda _r: (self.app.notify(_("subscribed")), self.load()))

    def action_command(self):
        self.query_one("#cmd", Input).focus()

    def status_changed(self, st):
        self.load()

    async def on_input_submitted(self, e: Input.Submitted):
        e.stop()
        await self.app.run_line(e.input, self)


class ProfileScreen(Screen, PostsMixin):
    """Someone's profile: who, the bio, follows you or not; F — follow / unfollow;
    their posts below (Enter — a thread); s — which of them: posts, posts and replies,
    media (common/timed.py, feed.profile_show first).

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
                Binding("u", "poll", "📊 " + _("poll_vote"), show=False),
                Binding("s", "show_next", _("profile_show_posts") + " / " +
                        _("profile_show_media")),
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
        self.show = None  # which of their posts: common/timed.py PROFILE_SHOWS

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
        self.show = timed.profile_show(core.cfg)
        self.load_posts()

    def posts_head(self):
        """"Posts: Posts · Posts and replies · Media (s)" — the one shown in brackets."""
        bits = [f"[{label}]" if key == self.show else label
                for key, label in timed.profile_shows()]
        return _("tui_profile_posts") + ": " + " · ".join(bits) + "  (s)"

    def load_posts(self):
        head = self.query_one("#posts-head", Static)
        head.update(Text(self.posts_head()))
        head.tooltip = _("profile_show_tip")
        self.later(self.app.core.account_posts(self.acc_id, show=self.show), ok=self.fill)

    def action_show_next(self):
        """Posts → posts and replies → media → posts, from the top each time."""
        keys = [k for k, _label in timed.PROFILE_SHOWS]
        at = keys.index(self.show) if self.show in keys else -1
        self.show = keys[(at + 1) % len(keys)]
        self.load_posts()

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
                            lists=True, details=True, collections=True)

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
        self.later(self.app.core.account_posts(self.acc_id, show=self.show), ok=self.fill)

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
                Binding("N", "find_prev", _("find_prev"), show=False),
                Binding("D", "find_deeper", _("find_deeper"), show=False),
                Binding("E", "find_everywhere", _("find_everywhere"), show=False),
                Binding("J", "to_new", _("to_new"), show=False),
                Binding("u", "poll", "📊 " + _("poll_vote"), show=False),
                Binding("s", "lane_choices", _("media_filter"), show=False),
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
                Binding("escape", "escape", _("find_close"), show=False)]

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
        self.title = NAME
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
        # a round began or ended: "⟳ updating the lanes…" / "updated at 14:32" on top
        self.core.on("poll_state", lambda _n, _p: self.in_ui(self._slow_title))
        # the server no longer takes the token: said as the windows say it, and Accounts
        # opened — "log in again" is there
        self.core.on("auth_failed", lambda _n, _p: self.in_ui(self.auth_lost))
        self.sounds = self._make_sounds()
        if self.sounds is not None:
            self.core.on("sound", lambda _n, p: self.in_ui(self.play_sound, p))
        from .notify import Notifier
        self.notifier = Notifier(self)  # notify-send, or the terminal's own (notify.py)
        self.core.on("notify", lambda _n, p: self.in_ui(self.notifier.notify, p))
        if not self.core.logged_in:
            self.push_screen(LoginScreen())
            return
        self.begin()

    def auth_lost(self):
        if getattr(self, "_auth_said", False):
            return
        self._auth_said = True
        self.show_error(f"{_('auth_failed_title')}: {_('auth_failed')}")
        try:
            from .screens import PlaceScreen
            self.push_screen(PlaceScreen("accounts"))
        except Exception:  # noqa: BLE001 — the words are said in any case
            log.debug("auth lost: accounts not opened", exc_info=True)

    def begin(self):
        self._main("#title", Static).update(_("tui_connecting"))
        self.later(self.core.connect(), ok=self.connected,
                   fail=lambda e: self.show_error(_("tui_connect_failed", err=e)))

    async def connected(self, _me):
        self._slow_title()
        self.set_interval(30, self._slow_title)  # slow mode: when the next batch comes
        await self.fill_lanes()
        self.core.start_polling()
        first = start_lane(self.core, self._lane_names())
        if first:
            await self.select_lane(first)
        self._main("#posts", ListView).focus()

    async def fill_lanes(self):
        """The lanes in the windows' sections (ui.sidebar_groups): a heading each, Enter
        on it folds the section (its unread stays as a number on the heading)."""
        from ..common import sidebar
        lv = self._main("#lanes", ListView)
        at = getattr(lv.highlighted_child, "lane", None) or \
            getattr(lv.highlighted_child, "group", None)
        await lv.clear()
        items = []
        folded = sidebar.folded(self.core)
        for key, title, names in lane_groups(self.core):
            if title is not None:
                n = sum(lane_label(self.core, x)[1] for x in names) if key in folded else 0
                items.append(GroupItem(key, title, key in folded, n))
                if key in folded:
                    continue
            for name in names:
                title_, n = lane_label(self.core, name, self.lanes_width - 2)
                items.append(LaneItem(name, title_, n, sidebar.fresh(self.core, name) if n else 0))
        await lv.extend(items)
        for i, it in enumerate(items):
            if at is not None and at in (getattr(it, "lane", None), getattr(it, "group", None)):
                lv.index = i
                break

    async def fold_group(self, item):
        from ..common import sidebar
        sidebar.fold(self.core, item.group)
        await self.fill_lanes()

    def _slow_title(self):
        """The subtitle: "@me", how fresh the lanes are ("⟳ updating the lanes…",
        "updated at 14:32"), and in slow mode when the next batch comes."""
        from ..common import sidebar
        me = self.core.me
        slow = sidebar.status_words(self.core)
        self.sub_title = "@" + (me.handle if me else "") + (f" · {slow}" if slow else "")

    def update_lane_counts(self):
        from ..common import sidebar
        self._slow_title()
        for item in self._main("#lanes", ListView).children:
            if isinstance(item, LaneItem):
                title, n = lane_label(self.core, item.lane, self.lanes_width - 2)
                item.update(title, n, sidebar.fresh(self.core, item.lane) if n else 0)

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
        try:
            lv = self._main("#posts", ListView)
        except NoMatches:  # a redraw queued (a post sent) while the app was closing
            return
        if name in ("activity", "requests"):  # not posts: rows of their own
            await self._fill_other(lv, name, first)
            return
        from ..common.lane import SEPARATOR
        m = self.lane_model(name)
        if first:  # opened anew: "new below" stands where reading stands now
            m.separator = None
            m.left()
        built = m.build(not first)
        keep = getattr(lv.highlighted_child, "key", None)
        width = max(30, lv.size.width - 4 if lv.size.width else 76)
        items, entries, unread = [], [], set()
        for sp in built.specs:
            if sp.key == SEPARATOR:  # "new below", fixed where reading stood
                div = ListItem(Static(Text("── " + sp.extra.get("separator", "") + " ──",
                                           style=STYLE["divider"])))
                div.key = SEPARATOR
                div.disabled = True  # j / k step over it, as over the windows' divider
                items.append(div)
                continue
            if sp.extra.get("event"):  # a like, a follow… a lane of rules shows: one line
                from ..common.activity import event_bit
                from .model import when as tui_when
                ev = ListItem(Static(Text("  " + event_bit(sp.extra["event"], tui_when).text,
                                          style=STYLE["muted"])))
                ev.key = sp.key
                ev.disabled = True  # not a post: j / k step over it
                items.append(ev)
                continue
            e = sp.entry
            entries.append((sp.key, e))
            if sp.unread:
                unread.add(e.id)
            shown = show_post(core, e, sp.extra.get("short_id"), sp.unread, width=width,
                              parent=sp.parent, spec=sp)
            items.append(PostItem(e, render(shown), key=sp.key))
        title = core.lane_title(name) or _("lane_" + name)
        line = Text(title, style="bold") + Text(f"  {_('tui_unread', n=len(unread))}"
                                                if unread else "", style="dim")
        if built.info:
            line += Text("  · " + built.info, style="yellow")
        elif m.current_filter() != "all" or m.conversations():
            line += Text("  · " + self.lane_choice_words(m), style="dim")
        self._main("#title", Static).update(line)
        await lv.clear()
        await lv.extend(items)
        if not items:
            return
        keys = [it.key for it in items]
        if keep in keys and not first:
            lv.index = keys.index(keep)
        else:
            start = m.start_key(built.specs)
            if start == SEPARATOR and keys.index(start) + 1 < len(keys):
                start = keys[keys.index(start) + 1]  # the first new one, under the divider
            lv.index = keys.index(start) if start in keys else self._start_index(entries,
                                                                                  unread)
        self.update_lane_counts()
        self.load_pictures(items)

    # ---- pictures in the lane (tui.pictures = "inline") ------------------------------
    def load_pictures(self, items):
        """Draw each post's first picture under it, as the bytes come. Small and
        cached by address and size, so redrawing a lane costs nothing."""
        tcfg = self.core.cfg.get("tui", {})
        how = pictures.mode(self.core.cfg)
        if how not in ("auto", "blocks") or not pictures.available():
            return
        real_ones = how == "auto" and pictures.graphics() is not None
        rows = max(2, int(tcfg.get("picture_rows", 8)))
        cols = rows * 4  # about a 2:1 box: room for a landscape photo
        cache = self._pictures
        for item in items:
            if not isinstance(item, PostItem):
                continue
            m = first_picture(item.entry)
            if m is None:
                continue
            url = m.preview or (m.url if m.kind == "image" else "")
            if not url:
                continue
            key = (url, cols, rows) if not real_ones else ("bytes", url)
            if key in cache:
                if real_ones:
                    self._put_graphic(item, cache[key], rows)
                else:
                    item.set_picture(cache[key])
                continue

            def done(f, item=item, key=key, url=url):
                try:
                    drawn = f.result() if real_ones else pictures.blocks(f.result(), cols,
                                                                         rows)
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
                if real_ones:
                    self.in_ui(self._put_graphic, item, drawn, rows)
                else:
                    self.in_ui(self._put_picture, item, drawn)
            self.core.media_bytes(url).add_done_callback(done)

    @staticmethod
    def _put_picture(item, drawn):
        if item.is_attached:
            item.set_picture(drawn)

    @staticmethod
    def _put_graphic(item, data, rows):
        if item.is_attached:
            w = pictures.graphic(data, rows, classes="inline-pic")
            if w is not None:
                item.set_graphic(w)

    # ---- outside the app: a picture viewer, a video player ----------------------------
    def caps(self):
        return termcaps.detect()

    def run_outside(self, argv, wait=False):
        """argv in this terminal, the app suspended until it ends (and, with wait,
        until Enter). False when the app can't be suspended (a test, Textual Web)."""
        if self.is_headless:
            return False
        try:
            with self.suspend():
                subprocess.run(argv, env=sysenv.child_env(), check=False)
                if wait:
                    with contextlib.suppress(EOFError, KeyboardInterrupt):
                        input("\n" + _("tui_enter_back"))
        except Exception as e:  # noqa: BLE001 — SuspendNotSupported, a failed program
            log.info("outside the app: %s: %s", argv[0], e)
            return False
        return True

    def show_outside(self, media):
        """The pictures by chafa / timg / kitty's icat, the app suspended: their real
        size and colours in any terminal those know. True when it went that way."""
        if self.core.cfg.get("tui", {}).get("viewer", "auto") != "auto" or self.is_headless:
            return False
        tool = termcaps.viewer(self.caps())
        if tool is None:
            return False
        futs = [self.core.media_bytes(m.url or m.preview) for m in media[:8]]
        size = self.size

        def go(results):
            files = []
            try:
                for data in results:
                    fd, path = tempfile.mkstemp(prefix="fedtail-", suffix=".img")
                    with os.fdopen(fd, "wb") as f:
                        f.write(data)
                    files.append(path)
                with self.suspend():
                    for path in files:
                        subprocess.run(tool.argv(path, size.width, size.height - 2),
                                       env=sysenv.child_env(), check=False)
                    with contextlib.suppress(EOFError, KeyboardInterrupt):
                        input(_("tui_enter_back"))
            except Exception as e:  # noqa: BLE001 — shown in the app instead
                log.info("picture viewer %s: %s", tool.name, e)
                self.push_screen(PictureScreen(media))
            finally:
                for path in files:
                    with contextlib.suppress(OSError):
                        os.unlink(path)

        def gathered():
            got = []
            for f in futs:
                try:
                    got.append(f.result(timeout=60))
                except Exception as e:  # noqa: BLE001 — a picture that didn't come
                    log.info("picture viewer: %s", e)
            if got:
                self.in_ui(go, got)
            else:
                self.in_ui(self.notify, _("tui_picture_failed", err="?"))
        threading.Thread(target=gathered, name="tui-viewer", daemon=True).start()
        return True

    def play(self, m):
        """A video or gifv by mpv: in a window of its own on a desktop, drawn into the
        terminal otherwise (tui.video); no mpv — the browser, and it says so."""
        url = m.url or m.remote_url
        if not url or not openable(url):
            self.notify(_("tui_no_video"))
            return
        how, argv = termcaps.video(self.caps(), self.core.cfg.get("tui", {}).get(
            "video", "auto"), loop=m.kind == "gifv")
        if how == "window":
            subprocess.Popen(argv + [url], env=sysenv.child_env(), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             start_new_session=True)
            self.notify(_("tui_playing"))
            return
        if how == "terminal" and self.run_outside(argv + [url]):
            return
        webbrowser.open(m.remote_url or url)
        self.notify(_("tui_video_browser") if argv is None else _("open_browser"))

    async def _fill_other(self, lv, name, first):
        core = self.core
        width = max(30, lv.size.width - 4 if lv.size.width else 76)
        keep = getattr(lv.highlighted_child, "key", None)
        if name == "activity":
            seen = core.activity_seen()
            rows = core.activity(300)  # newest first
            if core.cfg["feed"]["order"] == "oldest_first":
                rows = list(reversed(rows))
            # a follow request among them (activity.requests): its row answers to a / d
            items = [RequestItem(a.who, render(show_request(a.who, width)))
                     if a.kind == "request" and a.asks == "follow" and a.who is not None
                     else ActivityItem(a, render(show_activity(a, width, a.sort > seen)))
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

    # ---- a lane's choices (common/lane.py LaneModel: the windows' own) ---------------
    def lane_model(self, name):
        from ..common.lane import LaneModel
        models = self.__dict__.setdefault("_models", {})
        if name not in models:
            models[name] = LaneModel(self.core, name)
        return models[name]

    def lane_choice_words(self, m):
        bits = [m.filter_words(m.current_filter())[0]]
        if m.conversations():
            bits.append(_("conv_mode"))
        return " · ".join(bits)

    def action_lane_choices(self):
        """s: what the lane shows — All | Posts only | New, Feed | Conversations, and the
        media funnel (as the windows' lane header)."""
        from ..common.lane import MEDIA_KINDS
        from .screens import MenuScreen
        if self.lane == "activity":  # its quick filters (as the windows' header)
            from ..common import activity as act
            now = act.chosen(self.core)

            def picked(v):
                if v is not None:
                    self.core.set_activity_filter(v)
                    self.call_next(self.refresh_posts, True)
            self.push_screen(MenuScreen(_("actf_tip"), [
                (("● " if k == now else "○ ") + act.filter_words(k)[0], k,
                 act.filter_words(k)[1]) for k in act.offered(self.core)]), picked)
            return
        if not self.lane or self.lane == "requests":
            return
        m = self.lane_model(self.lane)
        items = []
        if len(m.filters) > 1:
            now = m.current_filter()
            items += [(("● " if f == now else "○ ") + m.filter_words(f)[0], ("filter", f),
                       m.filter_words(f)[1]) for f in m.filters] + ["-"]
        if m.conversations_offered():
            on = m.conversations()
            items += [(("● " if not on else "○ ") + _("view_feed"), ("conv", False),
                       _("view_feed_tip")),
                      (("● " if on else "○ ") + _("conv_mode"), ("conv", True),
                       _("conv_mode_tip")), "-"]
        items.append(("⇣ " + _("to_new"), ("new", None), _("to_new_tip")))
        items += [(("☑ " if k in m.media.wanted else "☐ ") + _("filter_" + k), ("media", k))
                  for k in MEDIA_KINDS]
        items += [(("☑ " if m.media.boosts else "☐ ") + _("filter_boosts"), ("media", "boosts")),
                  (_("filter_all"), ("media", "reset"))]

        def chosen(v):
            if v is None:
                return
            what, arg = v
            if what == "new":
                self.action_to_new()
                return
            if what == "filter":
                m.set_filter(arg)
            elif what == "conv":
                m.set_conversations(arg)
            elif arg == "reset":
                m.media.reset()
            elif arg == "boosts":
                m.media.boosts = not m.media.boosts
            else:
                m.media.toggle(arg, arg not in m.media.wanted)
            self.call_next(self.refresh_posts, True)
        self.push_screen(MenuScreen(_("media_filter"), items), chosen)

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
        if e.list_view.id == "lanes" and isinstance(e.item, GroupItem):
            await self.fold_group(e.item)
        elif e.list_view.id == "lanes" and isinstance(e.item, LaneItem):
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
        if e.list_view.id != "posts" or not isinstance(e.item, PostItem) or \
                not self.screen_stack:  # no screens: it came in as the app was closing
            return
        if self.core.cfg["read"]["mark_read"] == "on_scroll":
            entry = e.item.entry
            ids = [entry.id]
            if self.lane and self.screen is self.screen_stack[0]:  # a conversation: all of it
                ids = self.lane_model(self.lane).read(ids) or ids
            if entry.id in self.core.unread([entry]) or len(ids) > 1:
                self.core.mark_read(ids)
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
            # a screen opened takes the focus itself: its list isn't there yet to be
            # focused from here (Textual 2 raised NoMatches and closed the terminal)
            if isinstance(result, tuple) and result[0] == "thread":
                self.push_screen(ThreadScreen(result[1]))
                return
            if isinstance(result, tuple) and result[0] == "profile":
                self.push_screen(ProfileScreen(result[1].id))
                return
            if isinstance(result, tuple) and result[0] == "delete":
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

    relaunch = None  # a profile to start anew with when the app ends (tui/__init__.run)

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
        elif o.get("profile"):  # another account: fedtail again, in this terminal (run())
            from ...core import paths
            from ...core.instance import SingleInstance
            name = str(o["profile"])
            # open in its own window already: brought up there, this terminal stays
            if SingleInstance(paths.resolve(name).socket_file).poke_existing():
                self.notify(_("profile_busy", profile=name), timeout=10)
                return
            self.relaunch = name
            self.exit()
        elif o.get("file"):  # the config: in $EDITOR, or its path copied
            self.open_file(o["file"])
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
                           translates=getattr(core, "translation_languages", None),
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
        if real(st).poll is not None:  # the windows vote on the card; here: its screen
            from types import SimpleNamespace
            out.insert(0, ("📊 " + _("poll_vote") + " …  (u)", SimpleNamespace(kind="poll")))
        return out

    def post_menu(self, st, where=None):
        from .screens import MenuScreen
        items = self.post_menu_items(st, isinstance(where, ThreadScreen))
        via = self.core.via(st) if hasattr(self.core, "via") else ""
        title = "⋯ " + "@" + real(st).author.handle
        if via:  # every account in one window: which one acts on it
            items = [(it[0], it[1], _("via_tip", acct=via)) if it != "-" else it
                     for it in items]

        def chosen(it):
            if it is not None:
                if getattr(it, "kind", "") == "poll":
                    from .more import PollScreen
                    self.push_screen(PollScreen(st, where or self))
                    return
                self.do_menu_item(st, it)
        self.push_screen(MenuScreen(title, items), chosen)

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
            from ...model.text import quote_lines, without_quote_fallback
            # the words, as the windows quote them: not the post's HTML
            self.host.compose(reply_to=st, text=quote_lines(
                html_to_text(without_quote_fallback(real(st).text)),
                self.core.cfg["post"].get("quote_prefix", "> "), strip_mentions=True))

    def send_report(self, out):
        """Into debug.report_repo too, if one is set (fedtail/reportsend.py)."""
        from ... import reportsend
        repo = self.core.cfg["debug"].get("report_repo", "")
        if not repo:
            return
        self.notify(_("bugreport_sending", repo=repo))
        self.later(self.core.submit(reportsend.send_report, out, self.core.cfg,
                                    self.core.paths.data_dir),
                   ok=lambda where: self.notify(_("bugreport_sent", where=where), timeout=20),
                   fail=lambda err: self.notify(_("bugreport_send_failed", repo=repo, err=err),
                                                severity="error", timeout=30))

    def main_menu_items(self):
        """The ≡ menu: writing, the places (common/places.py), help, debug, quit."""
        from ..common.places import Places
        places = [(t + " …", ("place", n)) for n, t in Places(self.core).menu()
                  if n not in ("help", "news", "about", "issue", "federation")]
        return ([("✎ " + _("write"), ("do", "editor")),
                 (_("my_profile"), ("do", "my_profile")),
                 (_("refresh"), ("do", "refresh")),
                 (_("tui_all_read"), ("do", "all_read")), "-"]
                + places + ["-",
                            (_("help_title") + " …", ("place", "help")),
                            (_("help_news") + " …", ("place", "news")),
                            (_("about") + " …", ("place", "about")),
                            (_("issue_menu"), ("place", "issue")), "-",
                            (_("debug_menu") + " …", ("do", "debug")),
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
                self.send_report(out)
            except OSError as e:
                self.show_error(e)
        elif what == "logs":
            self.notify(str(diag.logs_dir(self.core.paths, self.core.cfg)), timeout=20)
        elif what == "test_sound" and self.sounds is not None:
            self.notify(self.sounds.test())
        elif what == "stacks":
            diag.dump_stacks("menu")
            self.notify(_("debug_stacks_done"))
        elif what == "debug":
            self.debug_menu()
        elif what == "quit":
            self.exit()

    # ---- ≡ → Debugging: the windows' debug menu, memory and all ----------------------------
    def corner_words(self):
        """How the terminal draws it: the windows' debug corner (common/corner.py)."""
        from textual import __version__ as textual_version

        from ..common import corner
        return corner.text(self.theme or "textual", f"Textual {textual_version}", "",
                           "", termcaps.detect().name, 0)

    def debug_menu(self):
        from ... import leaks
        from .screens import MenuScreen
        tracing = leaks.tracing()
        items = [(self.corner_words(), ("corner", None), _("debug_corner_tip")), "-",
                 (_("debug_notify"), ("notify", None)),
                 (_("debug_census"), ("census", None)),
                 (_("debug_trim"), ("trim", None)),
                 (("☑ " if tracing else "☐ ") + _("debug_tracing"), ("tracing", None),
                  _("debug_tracing_tip")),
                 (_("debug_snapshot"), ("snapshot", None)), "-",
                 (_("open_config"), ("config", None)),
                 (_("open_data"), ("data", None)),
                 (("☑ " if self.merged() else "☐ ") + _("accounts_merge"), ("merge", None),
                  _("accounts_merge_tip"))]

        def chosen(v):
            if v is not None:
                self.call_next(self.debug_do, v[0])
        self.push_screen(MenuScreen(_("debug_menu"), items), chosen)

    def merged(self):
        primary = getattr(self.core, "primary", self.core)
        return bool(self.core.cfg["ui"].get("merge") or primary.get_state("merge"))

    async def debug_do(self, what):
        from ... import diag, leaks
        if what == "notify":
            self.notify(self.notifier.test())
        elif what == "census":
            got = diag.check_now(int(self.core.cfg["debug"].get("rss_warn_mb", 1500)),
                                 objects=True)
            self.notify(_("debug_census_done", rss=got["rss_mb"], objects=got["py_objects"]))
        elif what == "trim":
            freed = diag.trim_memory()
            self.notify(_("debug_trim_none") if freed is None else
                        _("debug_trim_done", mb=freed))
        elif what == "tracing":
            (leaks.stop_tracing if leaks.tracing() else leaks.start_tracing)()
            self.notify(("☑ " if leaks.tracing() else "☐ ") + _("debug_tracing"))
        elif what == "snapshot":
            try:
                out = leaks.snapshot(diag.logs_dir(self.core.paths, self.core.cfg))
            except (OSError, RuntimeError) as e:
                self.show_error(e)
                return
            self.notify(_("debug_snapshot_done", path=str(out)), timeout=15)
        elif what == "config":
            self.open_file(self.core.paths.config_file)
        elif what == "data":
            self.copy_text(str(self.core.paths.data_dir))
        elif what == "merge":
            primary = getattr(self.core, "primary", self.core)
            primary.set_state("merge", [] if self.merged() else ["all"])
            self.notify(("☑ " if self.merged() else "☐ ") + _("accounts_merge") + " — " +
                        _("settings_restart_tip"), timeout=10)
        else:  # the corner: copied, for a bug report
            self.copy_text(self.corner_words())

    def open_file(self, path):
        """The config in $VISUAL / $EDITOR, the terminal handed over and back; without
        one — its path, copied."""
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if editor and self.run_outside(editor.split() + [str(path)]):
            return
        self.copy_text(str(path))

    def save_media(self, m):
        """A picture's (or a video's) original into ui.save_dir, as the windows' "Save"."""
        from ...core import saving
        url = m.url or m.remote_url or m.preview
        if not url:
            return
        self.notify(_("saving"))

        def write(data):
            folder = saving.save_dir(self.core.cfg)
            folder.mkdir(parents=True, exist_ok=True)
            path = saving.free_path(folder, saving.file_name(url, ""))
            path.write_bytes(data)
            return path

        def done(f):
            try:
                path = write(f.result())
            except Exception as e:  # noqa: BLE001 — said, nothing left half written
                self.in_ui(self.show_error, _("save_failed", err=e))
                return
            self.in_ui(self.notify, _("saved_to", path=str(path)))
        self.core.media_bytes(url).add_done_callback(done)

    def action_search(self):
        self.open_thing({"page": "search"})

    # ---- Ctrl+F: find in the lane (the windows' rule: every word, text, names, #id) -----
    def action_find(self):
        f = getattr(self, "_found", None)
        if f and f["hits"] and f["lane"] == self.lane:
            self._find_step()
            return
        from .screens import AskScreen

        def got(q):
            if q is not None:
                self.find(q)
        keys = "\n".join([f"Ctrl+F — {_('find_next')}", f"N — {_('find_prev')}",
                          f"D — {_('find_deeper')}: {_('find_deeper_tip')}",
                          f"E — {_('find_everywhere')}: {_('find_everywhere_tip')}",
                          f"Esc — {_('find_close')}"])
        self.push_screen(AskScreen(_("find_next"), _("find_placeholder") + "\n\n" + keys),
                         got)

    def find(self, query):
        from ...model.text import haystack, matches
        from ..common.find import count_text
        lv = self._main("#posts", ListView)
        items = [it for it in lv.children if isinstance(it, PostItem)]
        short = self.core.short_ids([it.entry for it in items])
        hits = [i for i, it in enumerate(lv.children) if isinstance(it, PostItem) and
                matches(query, haystack(it.entry, short.get(real(it.entry).id)))]
        self._found = {"lane": self.lane, "hits": hits, "at": -1, "query": query}
        if not hits:  # the query kept: D looks further back, E everywhere
            self.notify(count_text(query, -1, 0)[0] + f" · D — {_('find_deeper')}, "
                        f"E — {_('find_everywhere')}", severity="warning")
            return
        self._find_step()

    def action_find_prev(self):
        """N: the match before (find_prev)."""
        f = getattr(self, "_found", None)
        if f and f["hits"] and f["lane"] == self.lane:
            self._find_step(-1)

    def action_find_deeper(self):
        """D: past what the lane shows — everything stored for it; the lane grows down to
        an older match (find_deeper_tip)."""
        f = getattr(self, "_found", None)
        if not f or not self.lane:
            return
        query = f["query"]
        self.notify(_("find_searching"))

        def done(res):
            if not res.get("more"):
                self.notify(_("find_archive_none") if not res.get("total") else
                            _("find_count", i=f["at"] + 1, n=len(f["hits"])))
                return
            self.call_next(self._refound, query)
        self.later(self.core.deep_find(self.lane, query), ok=done)

    async def _refound(self, query):
        await self.refresh_posts()
        self.find(query)

    def action_find_everywhere(self):
        """E: everything stored, in every lane at once (find_everywhere_tip): a menu of
        the matches; the one chosen opens in its lane."""
        f = getattr(self, "_found", None)
        query = f["query"] if f else ""
        if not query:
            self.action_find()
            return
        self.notify(_("find_searching"))
        self.later(self.core.find_everywhere(query), ok=lambda hits: self._everywhere(
            query, hits))

    def _everywhere(self, query, hits):
        from ..common.find import count_text
        from .screens import MenuScreen
        names = set(self._lane_names())
        hits = [h for h in hits or () if h["lane"] in names]
        if not hits:
            self.notify(count_text(query, -1, 0, everywhere=True)[0], severity="warning")
            return
        items = []
        for h in hits[:60]:
            st = self.core.by_id(h["status_id"])
            words = snippet(st, 50) if st is not None else h["status_id"]
            items.append((f"{self.core.lane_title(h['lane']) or _('lane_' + h['lane'])}: "
                          + words, h))

        def chosen(h):
            if h is not None:
                self.call_next(self._go_hit, h)
        self.push_screen(MenuScreen(_("find_everywhere") + f" · {len(hits)}", items), chosen)

    async def _go_hit(self, h):
        self.core.reveal_in_lane(h["lane"], h["index"])
        await self.select_lane(h["lane"])
        lv = self._main("#posts", ListView)
        for i, it in enumerate(lv.children):
            e = getattr(it, "entry", None)
            if e is not None and h["status_id"] in (e.id, real(e).id):
                lv.index = i
                break
        lv.focus()

    def _find_step(self, step=1):
        f = self._found
        f["at"] = (f["at"] + step) % len(f["hits"])
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
            return
        lv = self.query_one("#posts", ListView)
        oldest_first = self.core.cfg["feed"]["order"] == "oldest_first"
        if not oldest_first and lv.children and lv.index == len(lv.children) - 1 and \
                self.screen is self.screen_stack[0]:
            self.call_next(self.action_older)  # newest first: older ones are below
            return
        super().action_cursor_down()

    def action_cursor_up(self):
        if self._lanes_focused():
            self._main("#lanes", ListView).action_cursor_up()
            return
        lv = self.query_one("#posts", ListView)
        if self.core.cfg["feed"]["order"] == "oldest_first" and lv.children and \
                lv.index == 0 and self.screen is self.screen_stack[0]:
            self.call_next(self.action_older)  # oldest first: older ones are above
            return
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
        elif getattr(self, "_found", None):  # Esc closes the find (find_close)
            self._found = None
            self.notify(_("find_close"), timeout=2)

    def action_to_new(self):
        """J: to the first unread of the lane (to_new_tip)."""
        lv = self._main("#posts", ListView)
        entries = [it.entry for it in lv.children if isinstance(it, PostItem)]
        unread = self.core.unread(entries) if entries else set()
        order = list(enumerate(lv.children))
        if self.core.cfg["feed"]["order"] == "newest_first":
            order.reverse()  # the first new one is the oldest unread: the lowest
        for i, it in order:
            if isinstance(it, PostItem) and it.entry.id in unread:
                lv.index = i
                lv.focus()
                return
        self.notify(_("to_new_tip") + ": —")

    async def action_older(self):
        """j past the last post: older ones from the server, or "nothing older"."""
        if not self.lane or self.lane in ("activity", "requests"):
            return
        n = await asyncio.wrap_future(self.core.load_older(self.lane))
        if not n:
            self.notify(_("no_older"))
        else:
            await self.refresh_posts()

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
