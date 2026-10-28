"""The terminal's screens beyond the lanes, the thread and the profile: a question
("sure?"), a line to type, a menu to choose from (a post's ⋯, the ≡ menu), a place
(frontends/common/places.py — the same silence, lists, search, help… the web page
shows), and the editor for a whole post. Keys: Enter — choose, Esc — back; in a place,
1…9 press the buttons of the row under the cursor, [ / ] — its tabs; in the editor,
Ctrl+S — send."""

from __future__ import annotations

import asyncio
import logging

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (
    Button,
    Checkbox,
    Footer,
    Input,
    Label,
    ListItem,
    ListView,
    Markdown,
    Select,
    Static,
    TextArea,
)

from ...i18n import _
from ...model import real
from ..common import places as places_mod

log = logging.getLogger(__name__)


# ---- a question, a line, a choice ------------------------------------------------------

class ConfirmScreen(ModalScreen):
    """"Sure?": y or Enter — yes, n or Esc — no. Dismissed with True or False."""

    BINDINGS = [Binding("y,enter", "answer(True)", _("yes_short")),
                Binding("n,escape", "answer(False)", _("no_short"))]
    CSS = """
    ConfirmScreen { align: center middle; }
    ConfirmScreen > Vertical { width: 70; height: auto; max-height: 80%;
                               border: thick $warning; background: $surface; padding: 1 2; }
    ConfirmScreen #q-title { text-style: bold; }
    """

    def __init__(self, title, text):
        super().__init__()
        self.q_title, self.text = str(title or ""), str(text or "")

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self.q_title, id="q-title")
            yield Static(self.text, id="q-text")
            yield Static(Text(_("tui_yes_no"), style="dim"))

    def action_answer(self, yes):
        self.dismiss(bool(yes))


class AskScreen(ModalScreen):
    """A line to type: Enter — done (dismissed with the text), Esc — never mind (None)."""

    BINDINGS = [Binding("escape", "cancel", _("cancel"))]
    CSS = """
    AskScreen { align: center middle; }
    AskScreen > Vertical { width: 76; height: auto; border: thick $primary;
                           background: $surface; padding: 1 2; }
    """

    def __init__(self, title, question, text="", allow_empty=False):
        super().__init__()
        self.q_title, self.question = str(title or ""), str(question or "")
        self.text, self.allow_empty = str(text or ""), allow_empty

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(Text(self.q_title, style="bold"))
            yield Static(self.question)
            yield Input(value=self.text, id="ask")

    def on_mount(self):
        self.query_one("#ask", Input).focus()

    def on_input_submitted(self, e: Input.Submitted):
        e.stop()
        if e.value.strip() or self.allow_empty:
            self.dismiss(e.value)

    def action_cancel(self):
        self.dismiss(None)


class ChoiceItem(ListItem):
    def __init__(self, label, value, enabled=True):
        super().__init__(Label(Text(label, style="" if enabled else "dim")))
        self.value = value
        self.enabled = enabled


class MenuScreen(ModalScreen):
    """A menu: [(label, value)] or [(label, value, hint)], "-" a line between. Enter —
    dismissed with the value, Esc — with None. A post's ⋯ menu and the ≡ menu are these.
    An item's hint (the windows' tooltip) shows under the menu while it is chosen."""

    BINDINGS = [Binding("escape,q", "cancel", _("tui_back")),
                Binding("j", "down", show=False), Binding("k", "up", show=False)]
    CSS = """
    MenuScreen { align: center middle; }
    MenuScreen > Vertical { width: 64; height: auto; max-height: 90%;
                            border: thick $primary; background: $surface; }
    MenuScreen #menu-title { padding: 0 1; background: $primary-background;
                             text-style: bold; }
    MenuScreen ListView { height: auto; max-height: 40; }
    MenuScreen #menu-hint { padding: 0 1; color: $text-muted; height: auto; }
    """

    def __init__(self, title, items):
        super().__init__()
        self.m_title = str(title or "")
        self.items = list(items)

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self.m_title, id="menu-title")
            yield ListView(*[ChoiceItem("─" * 20, None, False) if it == "-" else
                             ChoiceItem(it[0], it[1]) for it in self.items], id="menu")
            yield Static("", id="menu-hint")

    def on_mount(self):
        lv = self.query_one("#menu", ListView)
        lv.focus()
        for i, it in enumerate(lv.children):
            if isinstance(it, ChoiceItem) and it.enabled:
                lv.index = i
                break

    def labels(self):
        """What the menu offers, in order (the walks and the scenario read this)."""
        return [it[0] for it in self.items if it != "-"]

    def hint_of(self, index):
        """The hint of the item at index of the list (lines included), or ""."""
        it = self.items[index] if 0 <= index < len(self.items) else "-"
        return it[2] if it != "-" and len(it) > 2 else ""

    def on_list_view_highlighted(self, e: ListView.Highlighted):
        e.stop()
        lv = self.query_one("#menu", ListView)
        hint = self.hint_of(lv.index if lv.index is not None else -1)
        box = self.query_one("#menu-hint", Static)
        box.update(Text(hint, style="dim"))
        box.display = bool(hint)

    def on_list_view_selected(self, e: ListView.Selected):
        e.stop()
        if isinstance(e.item, ChoiceItem) and e.item.enabled:
            self.dismiss(e.item.value)

    def action_down(self):
        self.query_one("#menu", ListView).action_cursor_down()

    def action_up(self):
        self.query_one("#menu", ListView).action_cursor_up()

    def action_cancel(self):
        self.dismiss(None)


class ChooseScreen(ModalScreen):
    """One of a few answers (how long a mute lasts…), and maybe a box to tick: Enter on
    an answer — dismissed with (key, ticked), space or t — the box, Esc — None. The
    host's choose() (common/timed.py) is this."""

    BINDINGS = [Binding("escape,q", "cancel", _("tui_back")),
                Binding("space,t", "tick", "☑"),
                Binding("j", "down", show=False), Binding("k", "up", show=False)]
    CSS = """
    ChooseScreen { align: center middle; }
    ChooseScreen > Vertical { width: 64; height: auto; max-height: 90%;
                              border: thick $primary; background: $surface; }
    ChooseScreen #choose-title { padding: 0 1; background: $primary-background;
                                 text-style: bold; }
    ChooseScreen #choose-text { padding: 0 1; }
    ChooseScreen ListView { height: auto; max-height: 20; }
    ChooseScreen #choose-check { padding: 0 1; }
    """

    def __init__(self, title, text, options, check=None):
        super().__init__()
        self.c_title, self.text = str(title or ""), str(text or "")
        self.options = list(options)
        self.check = str(check) if check else ""
        self.ticked = False

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(self.c_title, id="choose-title")
            if self.text:
                yield Static(self.text, id="choose-text")
            yield ListView(*[ChoiceItem(label, key) for key, label in self.options],
                           id="choose")
            if self.check:
                yield Static(self.check_line(), id="choose-check")

    def check_line(self):
        return Text(("☑ " if self.ticked else "☐ ") + self.check + "  (t)")

    def on_mount(self):
        lv = self.query_one("#choose", ListView)
        lv.focus()
        lv.index = 0

    def labels(self):
        return [label for _k, label in self.options]

    def action_tick(self):
        if self.check:
            self.ticked = not self.ticked
            self.query_one("#choose-check", Static).update(self.check_line())

    def on_list_view_selected(self, e: ListView.Selected):
        e.stop()
        if isinstance(e.item, ChoiceItem):
            self.dismiss((e.item.value, self.ticked))

    def action_down(self):
        self.query_one("#choose", ListView).action_cursor_down()

    def action_up(self):
        self.query_one("#choose", ListView).action_cursor_up()

    def action_cancel(self):
        self.dismiss(None)


# ---- a place: common/places.py drawn in the terminal -------------------------------------

def _md_parser():
    """CommonMark with tables, no linkify: Textual's own default wants linkify-it, which
    a system may not have (and the help needs none: its links are written out)."""
    from markdown_it import MarkdownIt
    return MarkdownIt("commonmark").enable("table")


class RowItem(ListItem):
    """A row of a place that isn't a post: words, and its buttons numbered."""

    def __init__(self, row, body):
        super().__init__(Static(body, classes="post"))
        self.row = row
        self.key = row.key


def row_text(row):
    t = Text(row.title or "", style="bold" if row.kind in ("account", "tag", "item")
             else ("bold underline" if row.kind == "heading" else ""))
    if row.line:
        t.append("\n" + row.line, style="dim")
    if row.buttons:
        t.append("\n")
        for i, b in enumerate(row.buttons, 1):
            if i > 1:
                t.append("  ")
            t.append(f"{i}", style="bold cyan")
            t.append(" " + b.label, style="cyan" if b.primary else "")
    return t


class PlaceScreen(Screen):
    """A place (common/places.py) as the terminal draws it: the hint, the tabs ([ / ]),
    the rows (Enter — a post's thread, a person's profile, else the row's first button;
    1…9 — its buttons), a form (Ctrl+S — its button) and "more" at the end."""

    BINDINGS = [Binding("escape,q", "back", _("tui_back")),
                Binding("j", "cursor_down", show=False), Binding("k", "cursor_up", show=False),
                Binding("left_square_bracket", "tab(-1)", _("tui_tab_prev")),
                Binding("right_square_bracket", "tab(1)", _("tui_tab_next")),
                Binding("ctrl+s", "submit", _("tui_submit")),
                *[Binding(str(i), f"press({i})", show=False) for i in range(1, 10)],
                Binding("r", "reply", _("reply"), show=False),
                Binding("f", "fav", _("fav"), show=False),
                Binding("b", "boost", _("boost"), show=False),
                Binding("m", "bookmark", _("bookmark"), show=False),
                Binding("p", "profile", _("tui_profile"), show=False),
                Binding("full_stop", "post_menu", "⋯", show=False),
                # the help's pages, as the windows' ← and →
                Binding("alt+left", "help_back", _("help_back")),
                Binding("alt+right", "help_forward", _("help_forward"))]
    CSS = """
    PlaceScreen { overflow: hidden hidden; layout: vertical; }
    PlaceScreen #title { height: 1; padding: 0 1; background: $primary-background; }
    PlaceScreen #hint { height: auto; max-height: 4; padding: 0 1; color: $text-muted; }
    PlaceScreen #tabs { height: auto; padding: 0 1; }
    PlaceScreen #form { height: auto; max-height: 60%; padding: 0 1;
                        border-bottom: solid $primary-background; }
    PlaceScreen #form Input, PlaceScreen #form Select { width: 1fr; }
    PlaceScreen #form TextArea { height: 6; }
    PlaceScreen #form .checks { height: auto; }
    PlaceScreen #form .tip { height: auto; margin-bottom: 1; }
    PlaceScreen #posts { height: 1fr; }
    PlaceScreen #posts > ListItem { padding: 0 1 1 1; }
    """

    def __init__(self, name, arg="", tab="", cursor="", anchor=""):
        super().__init__()
        self.name_, self.arg, self.tab, self.cursor = name, str(arg or ""), tab, cursor
        self.anchor = anchor
        self.page = None
        self.form_widgets = {}

    @property
    def places(self):
        return places_mod.Places(self.app.core, self.app.date_words)

    def compose(self) -> ComposeResult:
        yield Static(_("loading"), id="title")
        yield Static("", id="hint")
        yield Static("", id="tabs")
        yield VerticalScroll(id="form")
        yield ListView(id="posts")
        yield Footer()

    async def on_mount(self):
        self.query_one("#posts", ListView).focus()
        await self.load()

    async def load(self):
        try:
            page = await asyncio.to_thread(self.places.page, self.name_, self.arg, self.tab,
                                           self.cursor)
        except Exception as e:  # noqa: BLE001 — said on the screen
            log.info("place %s: %s", self.name_, e.__class__.__name__)
            self.query_one("#title", Static).update(Text(_("load_failed", err=e), style="red"))
            return
        if not self.is_attached:
            return
        await self.show(page)

    async def show(self, page):
        self.page = page
        self.tab = page.tab
        self.query_one("#title", Static).update(Text(page.title, style="bold"))
        self.query_one("#hint", Static).update(page.hint or "")
        self.query_one("#hint", Static).display = bool(page.hint)
        tabs = Text()
        for i, (key, words) in enumerate(page.tabs):
            if i:
                tabs.append("  ")
            tabs.append(f" {words} ", style="reverse bold" if key == page.tab else "")
        self.query_one("#tabs", Static).update(tabs)
        self.query_one("#tabs", Static).display = bool(page.tabs)
        await self.show_form(page)
        lv = self.query_one("#posts", ListView)
        await lv.clear()
        await lv.extend(self.items(page))
        if len(lv.children):
            lv.index = 0
        self.app.load_pictures([x for x in lv.children if hasattr(x, "entry")])

    def items(self, page):
        from .app import PostItem, render
        from .model import show_post
        core = self.app.core
        width = max(30, (self.size.width or 80) - 6)
        posts = [r.data for r in page.rows if r.kind == "post"]
        short = core.short_ids(posts) if posts else {}
        unread = core.unread(posts) if posts else set()
        out = []
        for r in page.rows:
            if r.kind == "post":
                e = r.data
                out.append(PostItem(e, render(show_post(core, e, short.get(real(e).id),
                                                        e.id in unread, width=width)),
                                    key=e.id))
            elif r.kind == "html":
                md = r.data if isinstance(r.data, str) else None
                if md is not None:
                    item = ListItem(Markdown(md, classes="help", parser_factory=_md_parser))
                    item.key = r.key
                    out.append(item)
                else:
                    from ...model.text import html_to_text
                    out.append(RowItem(r, Text(html_to_text(r.title))))
            else:
                out.append(RowItem(r, row_text(r)))
        if not page.rows and page.empty:
            out.append(ListItem(Static(Text(page.empty, style="dim"))))
        if page.more is not None:
            more = places_mod.Row("item", "▼ " + page.more.label, buttons=(page.more,))
            out.append(RowItem(more, Text("▼ " + page.more.label, style="cyan")))
        return out

    async def show_form(self, page):
        box = self.query_one("#form", VerticalScroll)
        await box.remove_children()
        self.form_widgets = {}
        box.display = bool(page.form or page.submit)
        # a place that is all form (the settings): the form takes the screen
        box.styles.max_height = "75%" if page.name == "settings" else "60%"
        if not box.display:
            return
        widgets = []
        for f in page.form:
            if f.kind == "check":
                w = Checkbox(f.label, bool(f.value))
                widgets.append(w)
            elif f.kind == "checks":
                if f.label:
                    widgets.append(Label(f.label))
                boxes = [(v, Checkbox(words, v in (f.value or ()))) for v, words in f.choices]
                row = Horizontal if len(boxes) <= 4 else Vertical  # many: one under another
                widgets.append(row(*[b for _v, b in boxes], classes="checks"))
                w = boxes
            elif f.kind == "choice":
                widgets.append(Label(f.label))
                w = Select([(words, v) for v, words in f.choices], value=f.value,
                           allow_blank=False)
                widgets.append(w)
            elif f.kind == "text":
                widgets.append(Label(f.label))
                w = TextArea(str(f.value or ""))
                widgets.append(w)
            else:
                widgets.append(Label(f.label))
                w = Input(value=str(f.value or ""), placeholder=f.label,
                          password=f.kind == "secret")
                widgets.append(w)
            self.form_widgets[f.name] = w
            if f.tip:
                widgets.append(Static(Text(f.tip, style="dim"), classes="tip"))
        if page.submit is not None:
            widgets.append(Button(page.submit.label + "  (Ctrl+S)", id="submit",
                                  variant="primary" if page.submit.primary else "default"))
        await box.mount(*widgets)
        first = next((w for w in widgets if isinstance(w, (Input, TextArea))), None)
        if first is not None and page.name in ("search",) and not page.arg:
            first.focus()

    def values(self):
        out = {}
        for name, w in self.form_widgets.items():
            if isinstance(w, list):
                out[name] = [v for v, b in w if b.value]
            elif isinstance(w, TextArea):
                out[name] = w.text
            elif isinstance(w, (Checkbox, Input, Select)):
                out[name] = w.value
        return out

    # ---- doing ----------------------------------------------------------------------
    async def act(self, btn, values=None, confirmed=False, answer=None):
        out = await asyncio.to_thread(self.places.act, *btn.act, values=values,
                                      confirmed=confirmed, answer=answer)
        if out.confirm:
            def then(yes):
                if yes:
                    self.app.call_next(self.act, btn, values, True, answer)
            self.app.push_screen(ConfirmScreen(btn.label, out.confirm), then)
            return
        if out.ask:
            def got(text):
                if text is not None:
                    self.app.call_next(self.act, btn, values, confirmed, text)
            self.app.push_screen(AskScreen(*out.ask), got)
            return
        if out.error:
            self.app.show_error(out.error)
            return
        if out.copy:  # the terminal's clipboard (OSC 52), where it has one
            copy = getattr(self.app, "copy_to_clipboard", None)
            try:
                copy(out.copy)
            except Exception:  # noqa: BLE001 — none: the message says it all the same
                pass
        if out.message:
            self.app.notify(out.message)
        if out.compose:
            self.app.host.compose(**out.compose)
        if out.open:
            if out.open.get("back"):
                self.app.pop_screen()
                return
            if out.open.get("page") == self.name_ and not out.open.get("back"):
                self.arg = out.open.get("arg", self.arg)
                self.tab = out.open.get("tab", "") or self.tab
                self.cursor = out.open.get("cursor", "")
                await self.load()
                return
            self.app.open_thing(out.open)
            return
        if out.refresh:
            self.cursor = ""
            await self.load()

    def current_item(self):
        return self.query_one("#posts", ListView).highlighted_child

    def current(self):
        item = self.current_item()
        return getattr(item, "entry", None)

    async def action_press(self, n):
        item = self.current_item()
        row = getattr(item, "row", None)
        if row is not None and 0 < n <= len(row.buttons):
            await self.act(row.buttons[n - 1])

    async def on_list_view_selected(self, e: ListView.Selected):
        e.stop()
        item = e.item
        if hasattr(item, "entry"):
            at = getattr(item, "open_at", None) or self.app.core.open_at()
            self.app.push_screen(self.app.thread_screen(real(item.entry).id, at))
            return
        row = getattr(item, "row", None)
        if row is None:
            return
        if row.kind == "account" and row.data is not None and not row.buttons:
            self.app.push_screen(self.app.profile_screen(row.data.id))
        elif row.buttons:
            await self.act(row.buttons[0])

    async def action_submit(self):
        if self.page is not None and self.page.submit is not None:
            await self.act(self.page.submit, self.values())

    async def on_button_pressed(self, e: Button.Pressed):
        if e.button.id == "submit":
            e.stop()
            await self.action_submit()

    async def on_input_submitted(self, e: Input.Submitted):
        e.stop()
        if self.page is not None and self.page.submit is not None and len(self.form_widgets) == 1:
            await self.action_submit()  # one line (search, a list's name): Enter sends

    async def action_tab(self, d):
        if self.page is None or not self.page.tabs:
            return
        keys = [k for k, _w in self.page.tabs]
        i = keys.index(self.tab) if self.tab in keys else 0
        self.tab = keys[(i + d) % len(keys)]
        self.cursor = ""
        await self.load()

    def action_back(self):
        self.app.pop_screen()

    def _help_fwd(self):
        """Pages left by ← (alt+left), for →; the app keeps them, the screens come and go."""
        if not hasattr(self.app, "help_forward_pages"):
            self.app.help_forward_pages = []
        return self.app.help_forward_pages

    def check_action(self, action, parameters):
        if action in ("help_back", "help_forward"):
            if self.name_ != "help":
                return False
            if action == "help_back":
                stack = self.app.screen_stack
                return len(stack) > 1 and getattr(stack[-2], "name_", "") == "help" or None
            return bool(self._help_fwd()) or None
        return True

    def action_help_back(self):
        """← in the help: the page before this one (the one under it on the stack)."""
        stack = self.app.screen_stack
        if self.name_ == "help" and len(stack) > 1 and getattr(stack[-2], "name_", "") == "help":
            self._help_fwd().append((self.arg, self.anchor))
            self.app.pop_screen()

    def action_help_forward(self):
        """→ in the help: the page ← left."""
        fwd = self._help_fwd()
        if self.name_ == "help" and fwd:
            page, anchor = fwd.pop()
            self.app.push_screen(PlaceScreen("help", page, anchor=anchor))

    def action_cursor_down(self):
        self.query_one("#posts", ListView).action_cursor_down()

    def action_cursor_up(self):
        self.query_one("#posts", ListView).action_cursor_up()

    # a post in a place: the lane's keys
    def _post_key(self, name):
        st = self.current()
        if st is not None:
            getattr(self.app, "post_" + name)(st, self)

    def action_reply(self):
        self._post_key("reply")

    def action_fav(self):
        self._post_key("fav")

    def action_boost(self):
        self._post_key("boost")

    def action_bookmark(self):
        self._post_key("bookmark")

    def action_profile(self):
        st = self.current()
        if st is not None:
            self.app.push_screen(self.app.profile_screen(real(st).author.id))

    def action_post_menu(self):
        st = self.current()
        if st is not None:
            self.app.post_menu(st)

    def status_changed(self, _st):
        self.app.call_next(self.load)

    async def on_markdown_link_clicked(self, e):
        """A link in the help: another page of it, or the web."""
        e.stop()
        href = getattr(e, "href", "") or ""
        if href.startswith("fedtail:help/"):
            page, _s, anchor = href[len("fedtail:help/"):].partition("#")
            self._help_fwd().clear()  # a new way: what ← left is gone, as in a browser
            self.app.push_screen(PlaceScreen("help", page, anchor=anchor))
        else:
            self.app.open_thing(self.places.help_target(href, self.arg or "index").open or {})


# ---- the editor ------------------------------------------------------------------------

VISIBILITIES = ("public", "unlisted", "followers", "direct")
VIS_WORD = {"public": "vis_public", "unlisted": "vis_unlisted", "followers": "vis_private",
            "direct": "vis_direct"}


class ComposeScreen(Screen):
    """A whole post: the text (several lines), the warning, who sees it, the language.
    What it starts with and how drafts are kept are the windows' (common/compose.py).
    Ctrl+S — send; Esc — away (the draft is kept, as in the windows)."""

    BINDINGS = [Binding("ctrl+s", "send", _("tui_send")),
                Binding("ctrl+o", "extras", "📎 " + _("tui_extras")),
                # Ctrl+R: Textual keeps Ctrl+P for its command palette, above any screen
                Binding("ctrl+r", "preview", _("preview")),
                # priority: Textual's TextArea takes F7 for "select all" otherwise
                Binding("f7", "spell", _("spell_check"), priority=True),
                Binding("escape", "leave", _("web_cancel"))]
    CSS = """
    ComposeScreen { layout: vertical; padding: 0 1; }
    ComposeScreen #c-extras { height: auto; color: $accent; }
    ComposeScreen #c-title { height: 1; background: $primary-background; padding: 0 1; }
    ComposeScreen #c-context { height: auto; max-height: 8; color: $text-muted; }
    ComposeScreen #c-hint { height: auto; color: $text-muted; }
    ComposeScreen #c-count { height: auto; color: $text-muted; }
    ComposeScreen #c-text { height: 1fr; }
    ComposeScreen #c-format { height: 1; }
    ComposeScreen #c-format Button { height: 1; min-width: 5; border: none; margin: 0 1 0 0; }
    ComposeScreen #c-row { height: auto; }
    ComposeScreen #c-row Select { width: 30; }
    ComposeScreen #c-row Input { width: 1fr; }
    """

    def __init__(self, reply_to=None, invite=False, edit=None, quote=None, text=None,
                 warning="", visibility=None, language=""):
        super().__init__()
        self.reply_to, self.invite, self.edit, self.quote = reply_to, invite, edit, quote
        self.text0, self.warning0 = text, warning
        self.visibility0, self.language0 = visibility, language
        self.sending = False
        self.key = None
        self.start = None
        self.initial = None
        self.media = []        # [(path, description)]
        self.covers = {}       # a video's or a sound's path -> its cover picture's path
        self.edit_alts = {}    # editing my post: its picture's id -> the new description
        self.poll = None       # {"options", "expires_in", "multiple"}
        self.sensitive = False
        self.when = ""         # "2026-10-23 09:30": later, else now
        self.alt_ok = False    # "send as is" said once: pictures without a description go

    def compose(self) -> ComposeResult:
        from ..common import compose as cc
        core = self.app.core
        self.key = cc.draft_key(core, self.reply_to, self.quote, self.edit, self.invite)
        st = cc.start(core, self.key, self.reply_to, self.text0 or "", self.invite)
        if self.text0 and not st.restored and self.edit is None and self.reply_to is not None \
                and not self.invite:  # a reply with a quote: the mentions, then the quote
            mentions = st.text if st.text.strip() != self.text0.strip() else ""
            st.text = (mentions.rstrip() + "\n" if mentions.strip() else "") + self.text0
        if self.edit is not None and not st.restored:
            st.text = self.text0 or ""
            st.cw = self.warning0 or ""
            st.visibility = self.visibility0 or st.visibility
        if self.visibility0 and not st.restored:
            st.visibility = self.visibility0
        if self.warning0 and not st.restored:
            st.cw = self.warning0
        if self.language0 and not st.restored:
            st.language = self.language0
        self.start = st
        if self.edit is not None:
            title = _("compose_edit")
        elif self.quote is not None:
            title = _("compose_quote")
        elif self.invite:
            title = _("compose_invite")
        elif self.reply_to is not None:
            title = _("compose_reply")
        else:
            title = _("compose_new")
        yield Static(Text(title + "  ·  Ctrl+S — " + _("send").split(" (")[0], style="bold"),
                     id="c-title")
        ctx = self.reply_to or self.quote
        if ctx is not None:
            from ...model.text import snippet
            p = real(ctx)
            yield Static(Text(("❝ " if self.quote is not None else "↳ ") + "@" + p.author.handle
                              + ": " + snippet(p, 400)), id="c-context")
        if self.edit is not None:
            yield Static(_("edit_hint") + " " + _("edit_media_kept"), id="c-hint")
        elif st.hint:
            yield Static(_(st.hint), id="c-hint")
        vis = "followers" if st.visibility == "private" else st.visibility
        # all accounts in one window: whom it goes from, whole @name@server (as the windows)
        rid = None if self.reply_to is None else getattr(real(self.reply_to), "id",
                                                         self.reply_to)
        pick = getattr(core, "post_accounts", None)
        accounts, first = pick(rid) if pick is not None else ([], "")
        self.accounts = accounts if len(accounts) > 1 and self.edit is None else []
        self.from_first = first or ""  # the account that got the post replied to
        with Horizontal(id="c-row"):
            if self.accounts:
                yield Select([(_("post_from", acct=h), k) for k, h in self.accounts],
                             value=first if first in [k for k, _h in self.accounts] else "",
                             allow_blank=False, id="c-from")
            yield Select([(_(VIS_WORD[v]), v) for v in VISIBILITIES],
                         value=vis if vis in VISIBILITIES else "followers", allow_blank=False,
                         id="c-vis")
            yield Input(value=st.cw or "", placeholder=_("cw_placeholder"), id="c-cw")
            yield Input(value=st.language or "", placeholder=_("lang_label"), id="c-lang")
        from ..common import markup
        if markup.shown(core.cfg, getattr(core, "markdown", False)):
            # the formatting buttons (post.format_bar), clicked with the mouse: the
            # terminal's Ctrl+B/I/K belong to the text field (Ctrl+I is Tab there)
            with Horizontal(id="c-format"):
                for f in markup.FORMATS:
                    b = Button(f.face, id="fmt-" + f.name, tooltip=_(f.tip))
                    b.can_focus = False  # the selection stays in the text
                    yield b
        yield TextArea("", id="c-text")
        yield Static("", id="c-count")
        yield Static("", id="c-extras")
        yield Footer()

    def on_button_pressed(self, e: Button.Pressed):
        """A formatting button (common/markup.py): Markdown around the selection."""
        bid = e.button.id or ""
        if not bid.startswith("fmt-"):
            return
        e.stop()
        self.format_text(bid[4:])

    def format_text(self, name):
        from ..common import markup
        ta = self.query_one("#c-text", TextArea)
        text = ta.text
        lines = text.split("\n")

        def index(loc):
            row, col = loc
            return sum(len(x) + 1 for x in lines[:row]) + col

        def location(i, t):
            before = t[:i]
            return before.count("\n"), i - (before.rfind("\n") + 1)
        sel = ta.selection
        got = markup.apply(name, text, index(sel.start), index(sel.end))
        ta.text = got.text
        from textual.widgets.text_area import Selection
        ta.selection = Selection(location(got.start, got.text), location(got.end, got.text))
        ta.focus()

    def on_mount(self):
        if self.accounts:
            self.query_one("#c-from", Select).tooltip = _("post_from_tip")
        ta = self.query_one("#c-text", TextArea)
        ta.text = self.start.text or ""
        self.media = [tuple(m)[:2] for m in self.start.media or ()]
        self.sensitive = bool(self.start.sensitive)
        self.poll = self.start.poll or None
        self.show_extras()
        self.show_count()
        ta.focus()
        ta.move_cursor(ta.document.end)
        self.initial = self._snapshot()

    # ---- the count, a chain, #CamelCase; whom it goes from --------------------------------
    def show_count(self):
        """n / limit, "a chain of N posts" when it will be split, and the accessibility
        hint for #lowercasetags (post.camelcase_hint) — as the windows' counter."""
        from ..common import compose as cc
        core = self.app.core
        text = self.query_one("#c-text", TextArea).text
        cw = self.query_one("#c-cw", Input).value
        try:
            vis = self.query_one("#c-vis", Select).value
        except Exception:  # noqa: BLE001 — not composed yet
            vis = ""
        c = cc.count(text, cw, int(getattr(core.caps, "max_characters", 500) or 500),
                     core.cfg, reply_to=self.reply_to, visibility=vis if isinstance(vis, str)
                     else "", me=getattr(core, "me", None))
        line = Text(f"{c.n} / {c.limit}", style="bold red" if c.over else "")
        if c.newcomers:  # a private answer that brings someone new in
            line = Text(_("dm_newcomer_typed", who=", ".join(c.newcomers)) + "\n",
                        style="bold red") + line
        if c.parts > 1:
            line = Text(_("chain_count", n=c.parts) + " · ") + line
        if c.flat_tags:
            line.append("\n" + _("camel_hint", tags=", ".join("#" + t for t in
                                                               c.flat_tags[:3])), style="dim")
        self.query_one("#c-count", Static).update(line)
        return c

    def on_text_area_changed(self, _e):
        self.show_count()

    def on_select_changed(self, e):
        """All accounts in one window: a reply from another account than the one that
        got the post is looked up on its server — said under the fields."""
        if getattr(e.select, "id", "") == "c-vis":  # made private: whom it adds
            self.show_count()
            return
        if getattr(e.select, "id", "") != "c-from" or self.reply_to is None:
            return
        chosen = e.value or ""
        acct = dict(self.accounts).get(chosen, "")
        hint = _("post_from_other", acct=acct) if chosen != self.from_first else ""
        self.query_one("#c-count", Static).update(Text(hint, style="yellow") if hint else
                                                  "")

    def action_preview(self):
        """Ctrl+R: the post as it will go (Esc — back to the text)."""
        from .more import PreviewScreen
        text, cw, _vis, _lang = self._fields()
        c = self.show_count()
        self.app.push_screen(PreviewScreen(text, cw, bool(getattr(self.app.core, "markdown",
                                                                  False)),
                                           c.parts, len(self.media)))

    def _snapshot(self):
        from ..common import compose as cc
        text, cw, vis, lang = self._fields()
        return cc.snapshot(text, cw, vis, [list(m) for m in self.media], lang or None,
                           self.sensitive, self.poll)

    # ---- pictures, a poll, later (Ctrl+O) -------------------------------------------------
    def show_extras(self):
        from ..common import compose as cc
        bits = []
        from pathlib import Path
        for path, alt in self.media:
            bits.append("📎 " + Path(path).name + (f" — {alt}" if alt else
                                                    " — " + _("no_alt")) +
                        (" · " + _("media_cover_set", name=Path(self.covers[path]).name)
                         if path in self.covers else ""))
        for m in self._edit_media():
            alt = self.edit_alts.get(m.ref.id, m.alt)
            bits.append("📎 " + m.kind + (f" — {alt}" if alt else " — " + _("no_alt")))
        if self.media and self.sensitive:
            bits.append("⚠ " + _("sensitive_mark"))
        if self.poll:
            words = dict((s, _(k)) for s, k in cc.POLL_TIMES)
            bits.append("📊 " + " / ".join(self.poll["options"]) + " · " +
                        words.get(self.poll["expires_in"], "") +
                        (" · " + _("poll_several") if self.poll.get("multiple") else ""))
        if self.when:
            bits.append("🕒 " + _("schedule_when") + " " + self.when)
        box = self.query_one("#c-extras", Static)
        box.update("\n".join(bits))
        box.display = bool(bits)

    def action_extras(self):
        caps = self.app.core.caps
        items = []
        if not self.poll and len(self.media) < getattr(caps, "max_media", 4):
            items.append((_("attach"), "attach"))
        from pathlib import Path
        for i, (path, _alt) in enumerate(self.media):
            items.append(("✕ " + _("detach") + " " + Path(path).name, ("detach", i)))
            if self._playable(path):  # a cover for a video or a sound
                items.append(("🖼 " + _("media_cover") + " " + Path(path).name,
                              ("cover", path)))
        for m in self._edit_media():  # my post's pictures stay; their words can change
            items.append(("✎ " + _("alt_title") + ": " + m.kind + " " +
                          (self.edit_alts.get(m.ref.id, m.alt) or "")[:30], ("alt", m.ref.id)))
        if self.media:
            items.append((("☑ " if self.sensitive else "☐ ") + _("sensitive_mark"),
                          "sensitive"))
        if not self.media:
            items.append(((_("detach") + " " if self.poll else "") + _("poll_add"), "poll"))
        items.append(((_("detach") + " " if self.when else "") + _("schedule"), "when"))
        if self.edit is None:
            items.append((_("lang_other"), "lang"))
        if self.app.core.cfg["post"].get("spellcheck", True):
            items.append(("abc " + _("spell_check") + " (F7)", "spell"))
        items += ["-", ("🗑 " + _("discard"), "discard")]

        def chosen(v):
            if v == "attach":
                self.app.push_screen(AskScreen(_("attach"), _("tui_attach_path")),
                                     self._attached)
            elif isinstance(v, tuple) and v[0] == "cover":
                self.app.push_screen(AskScreen(_("media_cover"), _("media_cover_tip")),
                                     lambda got, path=v[1]: self._covered(path, got))
                return
            elif isinstance(v, tuple) and v[0] == "alt":
                m = next((x for x in self._edit_media() if x.ref.id == v[1]), None)
                if m is not None:
                    self.app.push_screen(
                        AskScreen(_("alt_title"), _("alt_prompt"),
                                  self.edit_alts.get(m.ref.id, m.alt), allow_empty=True),
                        lambda alt, mid=m.ref.id: self._redescribed(mid, alt))
                return
            elif isinstance(v, tuple):
                path = self.media[v[1]][0]
                del self.media[v[1]]
                self.covers.pop(path, None)
            elif v == "sensitive":
                self.sensitive = not self.sensitive
            elif v == "poll":
                if self.poll:
                    self.poll = None
                else:
                    self.app.push_screen(AskScreen(_("poll_add"), _("tui_poll_options")),
                                         self._polled)
                    return
            elif v == "when":
                if self.when:
                    self.when = ""
                else:
                    self.app.push_screen(AskScreen(_("schedule"), _("tui_when")),
                                         self._scheduled)
                    return
            elif v == "lang":
                self.app.push_screen(AskScreen(_("lang_other_title"), _("lang_other_ask")),
                                     self._language)
                return
            elif v == "discard":
                self.app.push_screen(ConfirmScreen(_("discard_q_title"), _("discard_q")),
                                     self._discard)
                return
            elif v == "spell":
                self.action_spell()
                return
            self.show_extras()
        self.app.push_screen(MenuScreen("📎 " + _("tui_extras"), items), chosen)

    def _attached(self, path):
        from pathlib import Path
        if not path:
            return
        p = Path(path.strip().strip("'\"")).expanduser()
        if not p.is_file():
            self.app.show_error(_("save_failed", err=str(p)))
            return

        def described(alt):
            self.media.append((str(p), (alt or "").strip()))
            self.show_extras()
        self.app.push_screen(AskScreen(_("alt_title"), _("alt_prompt"), allow_empty=True),
                             described)

    @staticmethod
    def _playable(path):
        import mimetypes
        kind = mimetypes.guess_type(str(path))[0] or ""
        return kind.startswith(("video/", "audio/"))

    def _edit_media(self):
        """My post's own attachments, when this edits it ([] otherwise)."""
        if self.edit is None:
            return []
        from ...model import real
        return list(real(self.edit).media or ())

    def _covered(self, path, got):
        from pathlib import Path
        if not got:
            return
        p = Path(got.strip().strip("'\"")).expanduser()
        if not p.is_file():
            self.app.show_error(_("save_failed", err=str(p)))
            return
        self.covers[path] = str(p)
        self.show_extras()

    def _redescribed(self, media_id, alt):
        if alt is None:
            return
        self.edit_alts[media_id] = alt.strip()
        self.show_extras()

    def _media_out(self):
        """The pictures to send: (path, description[, None, cover])."""
        return [(path, alt, None, self.covers[path]) if path in self.covers else (path, alt)
                for path, alt in self.media]

    def _media_changes(self):
        """{id: (description, focus)} of my post's pictures whose words changed."""
        return {m.ref.id: (self.edit_alts[m.ref.id], m.focus) for m in self._edit_media()
                if m.ref.id in self.edit_alts and self.edit_alts[m.ref.id] != m.alt}

    def _polled(self, text):
        from ..common import compose as cc
        if not text:
            return
        options = [o.strip() for o in text.replace(";", "|").split("|") if o.strip()]
        poll = cc.poll_data(True, options[:getattr(self.app.core.caps, "max_poll_options", 4)],
                            86400, False)
        if poll is None:
            self.app.show_error(_("tui_poll_options"))
            return
        self.poll = poll
        self.show_extras()

    # ---- spell checking (core/spell.py): a list of what looks wrong, F7 ------------------
    def _speller(self):
        """The checker for this post's language (or the interface's), or None."""
        from ...core import spell
        from ...i18n import current_language
        lang = self.query_one("#c-lang", Input).value.strip()
        core = self.app.core
        return spell.for_post(core.cfg, core.paths.config_file.parent, lang,
                              current_language())

    def action_spell(self):
        """F7: the words that look wrong, each to put right — a suggestion in its
        place, or into my own dictionary."""
        if not self.app.core.cfg["post"].get("spellcheck", True):
            return
        checker = self._speller()
        if checker is None:
            self.app.notify(_("spell_unavailable"), timeout=10)
            return
        text = self.query_one("#c-text", TextArea).text
        wrong = checker.wrong(text)
        if not wrong:
            self.app.notify(_("spell_all_ok"))
            return
        items = [(f"{w}  ({text[max(0, s - 12):s].split(chr(10))[-1]}…)", (s, e, w))
                 for s, e, w in wrong]

        def chosen(v):
            if v is not None:
                self._spell_word(checker, *v)
        self.app.push_screen(MenuScreen("abc " + _("spell_wrong_n", n=len(wrong)), items),
                             chosen)

    def _spell_word(self, checker, start, end, word):
        options = [(s, ("put", s)) for s in checker.suggest(word)] or \
            [("(" + _("spell_none") + ")", None)]
        options += ["-", ("＋ " + _("spell_add"), ("add", word))]

        def chosen(v):
            if not v:
                return
            if v[0] == "add":
                checker.add(v[1])
            else:
                self._spell_put(start, end, word, v[1])
            self.action_spell()  # on to the next one
        self.app.push_screen(MenuScreen(word, options), chosen)

    def _spell_put(self, start, end, word, instead):
        """The word at start…end (still there, still that word) becomes instead."""
        ta = self.query_one("#c-text", TextArea)
        text = ta.text
        if text[start:end] != word:  # the text changed meanwhile: its first such word
            start = text.find(word)
            if start < 0:
                return
            end = start + len(word)
        ta.load_text(text[:start] + instead + text[end:])

    def _language(self, code):
        """Another language: an ISO 639 code typed (eo, tok…) — into the field."""
        code = (code or "").strip().lower()
        if code and code.replace("-", "").isalpha() and len(code) <= 8:
            self.query_one("#c-lang", Input).value = code

    def _discard(self, yes):
        """Discard (asked first): the text and its draft gone, the editor closed."""
        if yes:
            self.app.core.delete_draft(self.key)
            self.dismiss(False)

    def _scheduled(self, text):
        from ..common import compose as cc
        if not text:
            return
        try:
            cc.when_utc(text)
        except ValueError:
            self.app.show_error(_("tui_when"))
            return
        self.when = text.strip()
        self.show_extras()

    def _fields(self):
        return (self.query_one("#c-text", TextArea).text,
                self.query_one("#c-cw", Input).value.strip(),
                self.query_one("#c-vis", Select).value,
                self.query_one("#c-lang", Input).value.strip())

    def action_send(self):
        if self.sending:
            return
        text, cw, vis, lang = self._fields()
        text = text.strip()
        if not text:
            return
        core = self.app.core
        bare = [i for i, (_p, alt) in enumerate(self.media) if not alt]
        if bare and not self.alt_ok and self.edit is None and \
                core.cfg["post"].get("alt_reminder", True):
            self._ask_alt(bare)
            return
        from ..common import compose as cc
        said = None if getattr(self, "lang_ok", False) or self.edit is not None else \
            cc.lang_mismatch(core.cfg, text, lang)
        if said:  # post.lang_check: the text reads as another language
            self._ask_lang(said, lang or core.cfg["post"].get("language"))
            return
        self.sending = True
        if self.edit is not None:
            changed = self._media_changes()
            fut = core.edit(self.edit, text, cw, media=changed) if changed else \
                core.edit(self.edit, text, cw)
        else:
            fut = core.post(text, vis, self.reply_to, cw, language=lang or None,
                            quote=self.quote, draft_key=self.key, media=self._media_out(),
                            sensitive=self.sensitive and bool(self.media),
                            poll=None if self.media else self.poll,
                            scheduled_at=cc.when_utc(self.when),
                            **({"account": self.query_one("#c-from", Select).value}
                               if self.accounts else {}))

        away = self.edit is None and core.cfg["post"].get("send_in_background")
        app = self.app

        def ok(_p):
            self.sending = False
            core.delete_draft(self.key)
            app.notify(_("edited_msg") if self.edit is not None else _("sent"))
            if not away:
                self.dismiss(True)
            app.refresh_lane()

        def fail(err):
            self.sending = False
            if away:  # the editor is gone: what was typed waits as a draft
                app.show_error(_("sent_background_failed", err=err))
                return
            app.show_error(_("send_failed_text", err=err))
        if away:  # post.send_in_background: out of the way at once, the draft kept
            core.save_draft(self.key, self._snapshot())
            app.notify(_("sent_background"))
            self.dismiss(True)
        app.later(fut, ok=ok, fail=fail)

    def _ask_lang(self, said, chosen):
        """post.lang_check: the text reads as `said` — mark it so, or send as is."""
        from ..common import compose as cc
        title, text, switch_w, anyway_w = cc.lang_question(said, chosen)

        def chosen_(v):
            if v == "switch":
                self.query_one("#c-lang", Input).value = said
            if v in ("switch", "send"):
                self.lang_ok = True
                self.action_send()
                self.lang_ok = False
        self.app.push_screen(MenuScreen(title + ": " + text, [(switch_w, "switch"),
                                                              (anyway_w, "send")]), chosen_)

    def _ask_alt(self, bare):
        """post.alt_reminder: pictures without a description — describe them, or send
        as they are (as the windows ask)."""
        title = _("alt_missing_title") + ": " + _("alt_missing", n=len(bare))

        def chosen(v):
            if v == "send":
                self.alt_ok = True
                self.action_send()
            elif v == "describe":
                i = bare[0]

                def described(alt):
                    if alt and alt.strip():
                        self.media[i] = (self.media[i][0], alt.strip())
                        self.show_extras()
                self.app.push_screen(AskScreen(_("alt_title"), _("alt_prompt")), described)
        self.app.push_screen(MenuScreen(title, [(_("alt_describe"), "describe"),
                                                (_("alt_send_anyway"), "send")]), chosen)

    def action_leave(self):
        from ..common import compose as cc
        snap = self._snapshot()
        what = cc.keep(snap, self.initial, bool(self.start and self.start.restored))
        core = self.app.core
        if what == "save":
            core.save_draft(self.key, snap)
            self.app.notify(_("draft_saved"))
        elif what == "delete":
            core.delete_draft(self.key)
        self.dismiss(False)


# ---- a profile's buttons -----------------------------------------------------------------

def profile_line(acts):
    """The profile's buttons (common/profile.py) as a line: 1 Follow  2 Mention …"""
    t = Text()
    for i, a in enumerate(acts[:9], 1):
        if i > 1:
            t.append("  ")
        t.append(str(i), style="bold cyan")
        t.append(" " + a.label, style="bold" if a.primary else "")
    return t
