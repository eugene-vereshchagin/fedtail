""""Report a bug on GitHub…" drawn by GTK — Qt's (qt/issue.py): the scrubbed text to
read and edit, "Open GitHub" opens the tracker's new-issue page with it."""

from __future__ import annotations

from ...i18n import _
from .gi_setup import Gtk


class IssueWindow(Gtk.Window):
    def __init__(self, win):
        super().__init__(transient_for=win, modal=True, title=_("issue_title"))
        from ... import issue
        from ..common.places import Places
        self.win = win
        self.mine = Places(win.view)._mine()
        self.set_default_size(720, 560)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(12)
        note = Gtk.Label(label=_("issue_check"), xalign=0, wrap=True)
        box.append(note)
        d = issue.draft(win.view.paths, win.cfg, known=self.mine)
        self.text = Gtk.TextView(monospace=True, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.text.get_buffer().set_text(d.body)
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_child(self.text)
        box.append(scroll)
        row = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        go = Gtk.Button(label=_("issue_open"))
        go.add_css_class("suggested-action")
        go.connect("clicked", lambda _b: self.go())
        row.append(go)
        cancel = Gtk.Button(label=_("cancel"))
        cancel.connect("clicked", lambda _b: self.close())
        row.append(cancel)
        box.append(row)
        self.set_child(box)

    def body(self):
        buf = self.text.get_buffer()
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False)

    def url(self):
        from ... import issue
        return issue.issue_url(self.win.cfg, "", issue.scrub(self.body(), self.mine))

    def go(self):
        """The whole text on the clipboard (the address holds only its start), the page
        in the browser."""
        from ... import issue
        self.win.get_clipboard().set(issue.scrub(self.body(), self.mine))
        self.win.open_url(self.url())
        self.win.status(_("issue_opened"), seconds=12)
        self.close()


__all__ = ["IssueWindow"]
