"""The Point-style command line at the bottom of the GTK window (ui.command_line): what
Enter will do is said while you type, ↑ ↓ go through what was run before. The grammar,
the words and the doing are common/commands.py's, shared with Qt, the terminal and the
web page."""

from ...core.commands import parse
from ...i18n import _
from ..common import compose as rules
from ..common.commands import Commands, Failed, History, preview
from .gi_setup import Gtk, Pango, tip


class CommandLine(Gtk.Box):
    def __init__(self, win):
        super().__init__(spacing=8)
        self.win, self.view = win, win.view
        self.add_css_class("ft-cmdline")
        self.set_margin_start(8)
        self.set_margin_end(8)
        self.entry = Gtk.Entry(placeholder_text=_("cmd_placeholder"))
        tip(self.entry, _("cmd_tip"))
        self.entry.set_hexpand(True)
        self.entry.connect("changed", lambda e: self._hint(preview(self.view, e.get_text())))
        self.entry.connect("activate", lambda _e: self.run())
        self.append(self.entry)
        self.hint = Gtk.Label(xalign=0)
        self.hint.add_css_class("ft-muted")
        self.hint.set_ellipsize(Pango.EllipsizeMode.END)
        self.hint.set_max_width_chars(60)
        self.hint.set_visible(False)
        self.append(self.hint)
        self.history = History()
        self.cmds = Commands(self.view)
        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        self.entry.add_controller(keys)

    def _hint(self, text):
        self.hint.set_text(text or "")
        self.hint.set_visible(bool(text))

    def put_alias(self, alias):
        """A click on a post's #abc: at the start of the line, the cursor at its end."""
        self.entry.set_text(rules.put_alias(self.entry.get_text(), alias))
        self.entry.grab_focus()
        self.entry.set_position(-1)

    def run(self):
        line = self.entry.get_text()
        c = parse(line)
        if c.kind == "error":
            self._hint(_("cmd_unknown"))
            return
        self.history.add(line)
        if c.kind == "help":
            self._hint(_("cmd_help").replace("\n", "  "))
            return
        fut, msg = self.cmds.run(line, unknown_as_post=True)
        if fut is None:
            self._hint(msg or _("cmd_unknown"))
            return
        self.entry.set_sensitive(False)

        def ok(result):
            self.entry.set_sensitive(True)
            self.entry.grab_focus()
            if isinstance(result, Failed):
                self._hint(result)  # the line stays, to mend
                return
            self.entry.set_text("")
            if isinstance(result, tuple):
                what, x = result
                if what == "thread":
                    self.win.open_thread(x)
                elif what == "profile":
                    self.win.open_account(x.id)
                elif what == "delete":
                    self.win.on_link(f"fedtail:delete/{x.id}")
            else:
                self.win.status(result if isinstance(result, str) else (msg or _("sent")))

        def fail(e):
            self.entry.set_sensitive(True)
            self.win.status(_("send_failed_text", err=e))
        self.win.call(fut, ok, fail)

    def _key(self, _ctl, keyval, _code, _state):
        from gi.repository import Gdk
        if keyval in (Gdk.KEY_Up, Gdk.KEY_Down):
            line = self.history.up() if keyval == Gdk.KEY_Up else self.history.down()
            if line is not None:
                self.entry.set_text(line)
                self.entry.set_position(-1)
            return True
        return False
