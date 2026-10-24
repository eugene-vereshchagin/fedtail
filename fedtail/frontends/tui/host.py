"""What common/links.py and common/profile.py ask of a window, the terminal's way: a
question is a ConfirmScreen, a line to type an AskScreen, the editor a ComposeScreen,
a place (history, report, who liked, quotes, whom someone follows, my profile, a
list's people) a PlaceScreen; a thread and a profile their screens; a link to the
outside the browser (the web only). So a ⋯ menu item, a profile's button or a link in
a post does in the terminal just what it does in the windows and on the web page."""

from __future__ import annotations

import logging
import webbrowser

from ...i18n import _
from ...model import Account, real
from ..richtext import openable

log = logging.getLogger(__name__)


class TuiHost:
    """The host for one FedtailApp (app: its screens, `later`, `notify`)."""

    def __init__(self, app):
        self.app = app

    @property
    def view(self):
        return self.app.core

    # ---- doing and telling -------------------------------------------------------------
    def call(self, fut, ok=None, fail=None):
        def done(result):
            if ok is not None:
                ok(result)
            self.app.refresh_lane()
        return self.app.later(fut, ok=done, fail=fail or self.error)

    def status(self, text):
        self.app.notify(str(text))

    def error(self, text):
        self.app.show_error(text)

    def confirm(self, title, text, then):
        from .screens import ConfirmScreen
        self.app.push_screen(ConfirmScreen(title, text), lambda yes: yes and then())

    def ask_text(self, title, question, then, text="", allow_empty=False):
        from .screens import AskScreen

        def got(answer):
            if answer is not None and (answer.strip() or allow_empty):
                then(answer)
        self.app.push_screen(AskScreen(title, question, text, allow_empty), got)

    def choose(self, title, text, options, done, check=None):
        """One of a few answers, and maybe a box to tick (common/timed.py)."""
        from .screens import ChooseScreen

        def got(answer):
            if answer is not None:
                done(*answer)
        self.app.push_screen(ChooseScreen(title, text, options, check), got)

    # ---- places --------------------------------------------------------------------------
    def open_url(self, url):
        if url and openable(url):  # the web only: never a file or a share from a post
            webbrowser.open(url)
        elif url:
            self.app.notify(_("link_refused"))

    def open_thread(self, sid):
        self.app.push_screen(self.app.thread_screen(sid))

    def open_account(self, acc_id):
        self.app.push_screen(self.app.profile_screen(acc_id))

    def _place(self, name, arg="", tab=""):
        from .screens import PlaceScreen
        self.app.push_screen(PlaceScreen(name, arg, tab))

    def open_tag(self, tag):
        self._place("tag", tag)

    def show_history(self, post):
        self._place("history", real(post).id)

    def report(self, post):
        self._place("report", post.id)

    def open_reactions(self, post, kind):
        self._place("reactions", post.id, kind)

    def open_quotes(self, post):
        self._place("quotes", post.id)

    def open_people(self, acc, which):
        self._place("people", acc.id, which)

    def edit_profile(self):
        self._place("profile_edit")

    def open_lists(self, acc):
        self._place("list_of", acc.id)

    def resolve_link(self, url):
        """A fediverse address: what my server finds there, else the browser."""
        def found(what):
            if isinstance(what, Account):
                self.open_account(what.id)
            elif what is not None:
                self.open_thread(what.id)
            else:
                self.status(_("resolve_browser"))
                self.open_url(url)
        self.status(_("resolving", url=url))
        self.app.later(self.view.resolve(url), ok=found, fail=lambda _e: self.open_url(url))

    def copy_handle(self, handle):
        self.app.copy_text("@" + handle.lstrip("@"))
        self.status(_("handle_copied", handle="@" + handle.lstrip("@")))

    def put_alias(self, alias):
        self.app.put_in_command_line(f"#{alias} ")

    def read_up_to(self, sid):
        """This post and everything older in the lane on screen: read."""
        self.app.read_up_to(sid)

    # ---- the editor ------------------------------------------------------------------
    def compose(self, reply_to=None, invite=False, edit=None, quote=None, text=None):
        from .screens import ComposeScreen
        if edit is not None:  # the text as typed, from the server
            def got(src):
                body, cw = src
                self.app.push_screen(ComposeScreen(edit=edit, text=body, warning=cw,
                                                   visibility=real(edit).visibility))
            self.app.later(self.view.source(edit), ok=got)
            return
        self.app.push_screen(ComposeScreen(reply_to=reply_to, invite=invite, quote=quote,
                                           text=text))

    def redrafted(self, d):
        from .screens import ComposeScreen
        parent = self.view.by_id(d.reply_to) if d.reply_to else None
        self.app.push_screen(ComposeScreen(reply_to=parent, text=d.text, warning=d.warning,
                                           visibility=d.visibility, language=d.language))
        if d.media:
            self.status(_("redraft_media", n=d.media))
