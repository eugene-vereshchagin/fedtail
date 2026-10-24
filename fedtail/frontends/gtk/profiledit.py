"""My profile, edited in the GTK window as in Qt's: the face and the banner (new
pictures picked from disk), the name, the bio, the fields, who may follow and how I'm
listed. Only what changed goes to the server (common/server.py profile_changes)."""

from __future__ import annotations

import logging

from ...i18n import _
from ..common import server
from .dialogs import _box, _buttons, _window
from .gi_setup import GLib, Gtk, tip

log = logging.getLogger(__name__)

FIELDS_SHOWN = 4  # Mastodon allows 4; more are kept if the server already has them
IMAGE_EXT = ("png", "jpg", "jpeg", "gif", "webp")


class ProfileEditor:
    def __init__(self, win):
        self.win = win
        self.loaded = None
        self.avatar_path = self.header_path = None
        self.dlg = dlg = _window(win, _("profile_title"), 600, 680)
        outer = _box()
        scroll = Gtk.ScrolledWindow(vexpand=True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        box = _box(0)
        scroll.set_child(box)
        outer.append(scroll)
        # the banner and the face as they are now (as Qt's): "no banner" until one
        self.header_pic = Gtk.Overlay()
        self.header_pic.set_size_request(-1, 120)
        self.header_pic.add_css_class("ft-thumb")
        self.header_none = Gtk.Label(label=_("no_header"))
        self.header_none.add_css_class("ft-muted")
        self.header_pic.set_child(self.header_none)
        box.append(self.header_pic)
        self.face = Gtk.Box()
        pics = Gtk.Box(spacing=8)
        pics.append(self.face)
        self.avatar_note = Gtk.Label(xalign=0)
        self.header_note = Gtk.Label(xalign=0)
        for label, fn, note in ((_("change_avatar"), self._pick_avatar, self.avatar_note),
                                (_("change_header"), self._pick_header, self.header_note)):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, f=fn: f())
            pics.append(b)
            note.add_css_class("ft-muted")
            pics.append(note)
        box.append(pics)
        box.append(Gtk.Label(label=_("profile_name"), xalign=0))
        self.name = Gtk.Entry()
        box.append(self.name)
        box.append(Gtk.Label(label=_("profile_bio"), xalign=0))
        self.bio = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.bio.set_size_request(-1, 110)
        self.bio.add_css_class("ft-compose-text")
        frame = Gtk.Frame(child=self.bio)
        frame.add_css_class("ft-compose-frame")
        box.append(frame)
        box.append(Gtk.Label(label=_("profile_fields"), xalign=0))
        self.grid = Gtk.Grid(row_spacing=6, column_spacing=6)
        box.append(self.grid)
        self.field_edits = []
        self.locked = Gtk.CheckButton(label=_("profile_locked"))
        self.bot = Gtk.CheckButton(label=_("profile_bot"))
        self.discoverable = Gtk.CheckButton(label=_("profile_discoverable"))
        self.hide_collections = Gtk.CheckButton(label=_("profile_hide_collections"))
        self.indexable = Gtk.CheckButton(label=_("profile_indexable"))
        for c in (self.locked, self.bot, self.discoverable, self.hide_collections,
                  self.indexable):
            box.append(c)
        box.append(Gtk.Label(label=_("profile_attribution"), xalign=0))
        self.attribution = Gtk.Entry(placeholder_text="blog.example, news.example")
        tip(self.attribution, _("profile_attribution_tip"))
        box.append(self.attribution)
        # the tags I write about most, not yet on my profile: one click puts one there
        self.suggest = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE)
        self.suggest_label = Gtk.Label(label=_("featured_suggest"), xalign=0)
        self.suggest_label.set_visible(False)
        box.append(self.suggest_label)
        box.append(self.suggest)
        self.suggest_buttons = []
        self.hint = Gtk.Label(label=_("loading"), xalign=0)
        self.hint.add_css_class("ft-muted")
        outer.append(self.hint)
        cancel = Gtk.Button(label=_("cancel"))
        cancel.connect("clicked", lambda _b: dlg.close())
        self.save_btn = Gtk.Button(label=_("save"))
        self.save_btn.add_css_class("suggested-action")
        self.save_btn.set_sensitive(False)
        self.save_btn.connect("clicked", lambda _b: self.save())
        outer.append(_buttons(cancel, self.save_btn))
        dlg.set_child(outer)
        win.call(win.view.my_profile(), self._loaded,
                 lambda e: self.hint.set_text(_("load_failed", err=e)))
        dlg.present()

    def _loaded(self, prof):
        self.loaded = prof
        me = prof.account
        self.name.set_text(me.name or "")
        self.bio.get_buffer().set_text(prof.bio or "")
        fields = list(prof.fields)
        for i in range(max(FIELDS_SHOWN, len(fields))):
            n, v = fields[i] if i < len(fields) else ("", "")
            name = Gtk.Entry(text=n, placeholder_text=_("field_name"))
            value = Gtk.Entry(text=v, placeholder_text=_("field_value"), hexpand=True)
            self.grid.attach(name, 0, i, 1, 1)
            self.grid.attach(value, 1, i, 1, 1)
            self.field_edits.append((name, value))
        self.locked.set_active(me.locked)
        self.bot.set_active(me.bot)
        self.discoverable.set_active(bool(me.discoverable))
        self.hide_collections.set_active(bool(prof.hide_collections))
        self.indexable.set_active(bool(prof.indexable))
        self.attribution.set_text(", ".join(prof.attribution_domains))
        if self.win.view.supports("featured_tags"):
            self.win.call(self.win.view.featured_tag_suggestions(), self._suggest,
                          lambda _e: None)
        self.hint.set_text("")
        self.save_btn.set_sensitive(True)
        from .card import Avatar
        self.face.append(Avatar(self.win.ctx, me, 72))  # (the picture comes by itself)
        url = me.header_static or me.header
        if url and "missing" not in url and self.win.images is not None:
            def show(paintable):
                pic = Gtk.Picture.new_for_paintable(paintable)
                pic.set_can_shrink(True)
                pic.set_content_fit(Gtk.ContentFit.COVER)
                self.header_pic.set_child(pic)
            self.win.images.get(url, show)

    def _suggest(self, tags):
        """featured_tag_suggestions: a button per tag; a click features it."""
        for t in tags or ():
            name = getattr(t, "name", "")
            if not name:
                continue
            b = Gtk.Button(label="#" + name)
            b.add_css_class("flat")
            b.connect("clicked", lambda btn, n=name: self._feature(n, btn))
            self.suggest.append(b)
            self.suggest_buttons.append(b)
        self.suggest_label.set_visible(bool(self.suggest_buttons))

    def _feature(self, name, button):
        button.set_sensitive(False)
        self.win.call(self.win.view.feature_tag(name, True),
                      lambda _r: button.set_label("✓ #" + name),
                      lambda e: (button.set_sensitive(True), self.win.status(str(e))))

    def _pick(self, title, then):
        dlg = Gtk.FileDialog(title=title)
        flt = Gtk.FileFilter()
        flt.set_name(_("media_files"))
        for ext in IMAGE_EXT:
            flt.add_suffix(ext)
        from gi.repository import Gio
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(flt)
        dlg.set_filters(filters)

        def done(d, res):
            try:
                f = d.open_finish(res)
            except GLib.Error:
                return  # cancelled
            if f is not None and f.get_path():
                then(f.get_path())
        dlg.open(self.dlg, None, done)

    def _pick_avatar(self):
        def got(path):
            self.avatar_path = path
            self.avatar_note.set_text(path.rsplit("/", 1)[-1])
        self._pick(_("change_avatar"), got)

    def _pick_header(self):
        def got(path):
            self.header_path = path
            self.header_note.set_text(path.rsplit("/", 1)[-1])
            try:  # the new one shown at once
                from .gi_setup import Gdk
                pic = Gtk.Picture.new_for_paintable(Gdk.Texture.new_from_filename(path))
                pic.set_can_shrink(True)
                pic.set_content_fit(Gtk.ContentFit.COVER)
                self.header_pic.set_child(pic)
            except GLib.Error:
                pass
        self._pick(_("change_header"), got)

    def changes(self):
        buf = self.bio.get_buffer()
        out = server.profile_changes(
            self.loaded, self.name.get_text(),
            buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False),
            [(n.get_text(), v.get_text()) for n, v in self.field_edits],
            {"locked": self.locked.get_active(), "bot": self.bot.get_active(),
             "discoverable": self.discoverable.get_active()},
            self.avatar_path, self.header_path)
        out.update(server.flag_changes(self.loaded, self.hide_collections.get_active(),
                                self.indexable.get_active(), self.attribution.get_text()))
        return out

    def save(self):
        if self.loaded is None:
            return
        changes = self.changes()
        if not changes:
            self.dlg.close()
            return
        self.save_btn.set_sensitive(False)
        self.hint.set_text(_("saving"))

        def failed(e):
            self.hint.set_text(_("error", err=e))
            self.save_btn.set_sensitive(True)

        def done(_me):
            self.win.status(_("profile_saved"))
            self.dlg.close()
        self.win.call(self.win.view.update_profile(**changes), done, failed)
