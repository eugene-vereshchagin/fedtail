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
    """A menu: [(label, value)], "-" a line between. Enter — dismissed with the value,
    Esc — with None. A post's ⋯ menu and the ≡ menu are these."""

    BINDINGS = [Binding("escape,q", "cancel", _("tui_back")),
                Binding("j", "down", show=False), Binding("k", "up", show=False)]
    CSS = """
    MenuScreen { align: center middle; }
    MenuScreen > Vertical { width: 64; height: auto; max-height: 90%;
                            border: thick $primary; background: $surface; }
    MenuScreen #menu-title { padding: 0 1; background: $primary-background;
                             text-style: bold; }
    MenuScreen ListView { height: auto; max-height: 40; }
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
                Binding("full_stop", "post_menu", "⋯", show=False)]
    CSS = """
    PlaceScreen { overflow: hidden hidden; layout: vertical; }
    PlaceScreen #title { height: 1; padding: 0 1; background: $primary-background; }
    PlaceScreen #hint { height: auto; max-height: 4; padding: 0 1; color: $text-muted; }
    PlaceScreen #tabs { height: auto; padding: 0 1; }
    PlaceScreen #form { height: auto; max-height: 60%; padding: 0 1;
                        border-bottom: solid $primary-background; }
    PlaceScreen #form Input, PlaceScreen #form Select { width: 1fr; }
    PlaceScreen #form TextArea { height: 6; }
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
                widgets.append(Horizontal(*[b for _v, b in boxes], classes="checks"))
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
                w = Input(value=str(f.value or ""), placeholder=f.label)
                widgets.append(w)
            self.form_widgets[f.name] = w
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
            self.app.push_screen(self.app.thread_screen(real(item.entry).id))
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
                Binding("escape", "leave", _("web_cancel"))]
    CSS = """
    ComposeScreen { layout: vertical; padding: 0 1; }
    ComposeScreen #c-extras { height: auto; color: $accent; }
    ComposeScreen #c-title { height: 1; background: $primary-background; padding: 0 1; }
    ComposeScreen #c-context { height: auto; max-height: 8; color: $text-muted; }
    ComposeScreen #c-hint { height: auto; color: $text-muted; }
    ComposeScreen #c-text { height: 1fr; }
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
        self.poll = None       # {"options", "expires_in", "multiple"}
        self.sensitive = False
        self.when = ""         # "2026-10-23 09:30": later, else now

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
            yield Static(_("edit_hint"), id="c-hint")
        elif st.hint:
            yield Static(_(st.hint), id="c-hint")
        vis = "followers" if st.visibility == "private" else st.visibility
        # all accounts in one window: whom it goes from, whole @name@server (as the windows)
        rid = None if self.reply_to is None else getattr(real(self.reply_to), "id",
                                                         self.reply_to)
        pick = getattr(core, "post_accounts", None)
        accounts, first = pick(rid) if pick is not None else ([], "")
        self.accounts = accounts if len(accounts) > 1 and self.edit is None else []
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
        yield TextArea("", id="c-text")
        yield Static("", id="c-extras")
        yield Footer()

    def on_mount(self):
        if self.accounts:
            self.query_one("#c-from", Select).tooltip = _("post_from_tip")
        ta = self.query_one("#c-text", TextArea)
        ta.text = self.start.text or ""
        self.media = [tuple(m)[:2] for m in self.start.media or ()]
        self.sensitive = bool(self.start.sensitive)
        self.poll = self.start.poll or None
        self.show_extras()
        ta.focus()
        ta.move_cursor(ta.document.end)
        self.initial = self._snapshot()

    def _snapshot(self):
        from ..common import compose as cc
        text, cw, vis, lang = self._fields()
        return cc.snapshot(text, cw, vis, [list(m) for m in self.media], lang or None,
                           self.sensitive, self.poll)

    # ---- pictures, a poll, later (Ctrl+O) -------------------------------------------------
    def show_extras(self):
        from ..common import compose as cc
        bits = []
        for path, alt in self.media:
            from pathlib import Path
            bits.append("📎 " + Path(path).name + (f" — {alt}" if alt else
                                                    " — " + _("no_alt")))
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
        for i, (path, _alt) in enumerate(self.media):
            from pathlib import Path
            items.append(("✕ " + _("detach") + " " + Path(path).name, ("detach", i)))
        if self.media:
            items.append((("☑ " if self.sensitive else "☐ ") + _("sensitive_mark"),
                          "sensitive"))
        if not self.media:
            items.append(((_("detach") + " " if self.poll else "") + _("poll_add"), "poll"))
        items.append(((_("detach") + " " if self.when else "") + _("schedule"), "when"))

        def chosen(v):
            if v == "attach":
                self.app.push_screen(AskScreen(_("attach"), _("tui_attach_path")),
                                     self._attached)
            elif isinstance(v, tuple):
                del self.media[v[1]]
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
        self.sending = True
        from ..common import compose as cc
        if self.edit is not None:
            fut = core.edit(self.edit, text, cw)
        else:
            fut = core.post(text, vis, self.reply_to, cw, language=lang or None,
                            quote=self.quote, draft_key=self.key, media=list(self.media),
                            sensitive=self.sensitive and bool(self.media),
                            poll=None if self.media else self.poll,
                            scheduled_at=cc.when_utc(self.when),
                            **({"account": self.query_one("#c-from", Select).value}
                               if self.accounts else {}))

        def ok(_p):
            self.sending = False
            core.delete_draft(self.key)
            self.app.notify(_("edited_msg") if self.edit is not None else _("sent"))
            self.dismiss(True)
            self.app.refresh_lane()

        def fail(err):
            self.sending = False
            self.app.show_error(_("send_failed_text", err=err))
        self.app.later(fut, ok=ok, fail=fail)

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
