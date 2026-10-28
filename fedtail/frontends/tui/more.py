"""Screens the windows have and the terminal had not: a poll to vote in, and the
editor's preview. Keys are on each screen's footer.

PollScreen — j / k the options, Space ticks one (several, if the poll lets), Enter
votes, r shows the results before voting, u asks the server for fresh counts, Esc back.
PreviewScreen — the post as it will go: its text (Markdown drawn when the server takes
it), how many posts the chain will be, the pictures; Esc or Enter — back to editing."""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Label, ListItem, ListView, Markdown, Static

from ...i18n import _
from ...model import real
from .model import poll_line, when


class OptionItem(ListItem):
    def __init__(self, i, text):
        self.label = Label(text)
        super().__init__(self.label)
        self.i = i


class PollScreen(ModalScreen):
    BINDINGS = [Binding("escape,q", "app.pop_screen", _("tui_back")),
                Binding("j", "down", show=False), Binding("k", "up", show=False),
                Binding("space", "tick", "☑"),
                Binding("enter", "vote", _("poll_vote")),
                Binding("r", "results", _("poll_results")),
                Binding("u", "refresh", _("poll_refresh"))]
    CSS = """
    PollScreen { align: center middle; }
    PollScreen > Vertical { width: 76; height: auto; max-height: 90%;
                            border: thick $primary; background: $surface; }
    PollScreen #poll-title { padding: 0 1; background: $primary-background;
                             text-style: bold; }
    PollScreen #poll-line { padding: 0 1; color: $text-muted; }
    PollScreen ListView { height: auto; max-height: 30; }
    """

    def __init__(self, post, where=None):
        super().__init__()
        self.post = real(post)
        self.where = where      # the screen to tell when the post changed
        self.picked = set()
        self.peek = False       # r: the results before voting
        self.sending = False

    @property
    def poll(self):
        return self.post.poll

    def open_ended(self):
        """Votes may still go: not closed, not voted, not my own post."""
        me = self.app.core.me
        return not (self.poll.expired or self.poll.voted or
                    (me is not None and self.post.author.id == me.id))

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static("📊 @" + self.post.author.handle, id="poll-title")
            yield ListView(id="options")
            yield Static("", id="poll-line")
        yield Footer()

    async def on_mount(self):
        await self.draw()
        self.query_one("#options", ListView).focus()

    def lines(self):
        """Each option as the windows show it: the tick (or my vote), the title, and
        the count with its share when the results are to be seen."""
        poll = self.poll
        show = self.peek or not self.open_ended()
        total = max(1, poll.total)
        out = []
        for i, o in enumerate(poll.options):
            title = o.title or _("poll_option", n=i + 1)
            if show:
                mark = "✔" if i in poll.my_votes else " "
                n = o.votes
                tail = "" if n is None else f"  {n} ({round(100 * n / total)}%)"
                out.append(Text(f"{mark} {title}") + Text(tail, style="dim"))
            else:
                box = ("☑" if i in self.picked else "☐") if poll.multiple else \
                    ("●" if i in self.picked else "○")
                out.append(Text(f"{box} {title}"))
        return out

    async def draw(self):
        lv = self.query_one("#options", ListView)
        at = lv.index or 0
        await lv.clear()
        await lv.extend(OptionItem(i, t) for i, t in enumerate(self.lines()))
        lv.index = min(at, len(self.poll.options) - 1)
        self.query_one("#poll-line", Static).update(poll_line(self.poll, when))

    async def on_list_view_selected(self, e: ListView.Selected):
        e.stop()  # Enter on the list: the list takes the key first
        await self.action_vote()

    def action_down(self):
        self.query_one("#options", ListView).action_cursor_down()

    def action_up(self):
        self.query_one("#options", ListView).action_cursor_up()

    async def action_tick(self):
        if not self.open_ended():
            return
        i = self.query_one("#options", ListView).index or 0
        if self.poll.multiple:
            self.picked.symmetric_difference_update({i})
        else:
            self.picked = {i}
        await self.draw()

    async def action_vote(self):
        if not self.open_ended() or self.sending:
            return
        if not self.picked:  # Enter on an option, nothing ticked: that one
            await self.action_tick()
        self.sending = True
        self.app.notify(_("poll_sending"))
        self.app.later(self.app.core.vote(self.post, sorted(self.picked)), ok=self.voted,
                       fail=self.failed)

    async def voted(self, post):
        self.sending = False
        self.app.notify(_("poll_voted"))
        await self.changed(post)

    def failed(self, err):
        self.sending = False
        self.app.show_error(err)

    async def changed(self, post):
        if post is not None and real(post).poll is not None:
            self.post = real(post)
        self.picked = set()
        if self.is_attached:
            await self.draw()
        if self.where is not None:
            self.where.status_changed(post)

    async def action_results(self):
        self.peek = not self.peek
        await self.draw()

    def action_refresh(self):
        self.app.later(self.app.core.refresh_poll(self.post), ok=self.changed)


class PreviewScreen(ModalScreen):
    BINDINGS = [Binding("escape,enter,q", "app.pop_screen", _("preview_back"))]
    CSS = """
    PreviewScreen { align: center middle; }
    PreviewScreen > Vertical { width: 90%; height: 90%; border: thick $primary;
                               background: $surface; }
    PreviewScreen #pv-title { padding: 0 1; background: $primary-background;
                              text-style: bold; }
    PreviewScreen #pv-line { padding: 0 1; color: $text-muted; }
    """

    def __init__(self, text, cw="", markdown=False, parts=1, media=0):
        super().__init__()
        self.text, self.cw, self.markdown = text, cw, markdown
        self.parts, self.media = parts, media

    def compose(self) -> ComposeResult:
        bits = [_("preview_md") if self.markdown else _("preview_plain")]
        if self.parts > 1:
            bits.append(_("chain_count", n=self.parts))
        if self.media:
            bits.append(_("preview_media", n=self.media))
        with Vertical():
            yield Static(_("preview") + " · " + " · ".join(bits), id="pv-title")
            if self.cw:
                yield Static(Text("⚠ " + self.cw, style="yellow"))
            with VerticalScroll():
                if self.markdown:
                    from .screens import _md_parser
                    yield Markdown(self.text, parser_factory=_md_parser)
                else:
                    yield Static(self.text)
            yield Static(_("preview_tip"), id="pv-line")
        yield Footer()


__all__ = ["PollScreen", "PreviewScreen"]
