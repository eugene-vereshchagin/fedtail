"""Writing a post in GTK: a new one, a reply, a quote, a call into a thread, or my post
corrected. The rules — which draft, what it starts with, the counter, completing
#tags and @names, when a draft is kept, a picture made to fit the server — are
common/compose.py's (the Qt editor asks there too); this is the window around them:
the text, the warning, who sees it, pictures with their descriptions or a poll.
"""

from __future__ import annotations

import logging

from ...i18n import _
from ...model import VISIBILITIES, Scheduled, real
from ...model.text import snippet
from ..common import compose as rules
from ..common.actions import vis_word
from .gi_setup import GLib, Gtk, Pango, tip

log = logging.getLogger(__name__)

AUTOSAVE_MS = 1500


class ComposeWindow(Gtk.Window):
    def __init__(self, win, reply_to=None, invite=False, edit=None, quote=None, text=""):
        super().__init__(transient_for=win, title=_("write"))
        self.win, self.view = win, win.view
        self.cfg = win.cfg
        self.reply_to = real(reply_to) if reply_to is not None else None
        self.quote = real(quote) if quote is not None else None
        self.edit = real(edit) if edit is not None else None
        self.invite = bool(invite and self.reply_to)
        self.key = rules.draft_key(self.view, self.reply_to, self.quote, self.edit,
                                   self.invite)
        self.sent = False
        self._kept = {}            # a draft's pictures and poll: kept as they were
        self._autosave = 0
        self.set_default_size(560, 360)
        self.add_css_class("fedtail")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(10)
        about = self._about()
        if about:
            lab = Gtk.Label(label=about, xalign=0, wrap=True)
            lab.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            lab.add_css_class("ft-ctx")
            box.append(lab)
        self.cw = Gtk.Entry(placeholder_text=_("cw_placeholder"))
        self.cw.set_visible(False)
        box.append(self.cw)
        self.text = Gtk.TextView()
        self.text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.text.set_vexpand(True)
        self.text.add_css_class("ft-body")
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.text)
        scroll.set_vexpand(True)
        box.append(scroll)
        self.media_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(self.media_box)  # a row per picture: name, description, ✕
        self.media = []             # [[path, description entry]]
        self.poll_box = self._build_poll()
        box.append(self.poll_box)
        self.suggest = Gtk.Label(xalign=0, wrap=True)  # what #tag or @name fits
        self.suggest.add_css_class("ft-muted")
        self.suggest.set_visible(False)
        box.append(self.suggest)

        bar = Gtk.Box(spacing=6)
        self.cw_btn = Gtk.ToggleButton(label="CW")
        tip(self.cw_btn, _("cw_placeholder"))
        self.cw_btn.connect("toggled", lambda b: self._toggle_cw(b.get_active()))
        bar.append(self.cw_btn)
        self.vis = Gtk.DropDown.new_from_strings([vis_word(v) for v in VISIBILITIES])
        bar.append(self.vis)
        self.attach_btn = Gtk.Button(label="📎 " + _("attach"))
        self.attach_btn.connect("clicked", lambda _b: self.attach())
        bar.append(self.attach_btn)
        self.poll_btn = Gtk.ToggleButton(label=_("poll_add"))
        tip(self.poll_btn, _("poll_add_tip"))
        self.poll_btn.connect("toggled", lambda b: self._toggle_poll(b.get_active()))
        bar.append(self.poll_btn)
        self.sensitive_btn = Gtk.ToggleButton(label="⚠")
        tip(self.sensitive_btn, _("sensitive_mark"))
        self.sensitive_btn.set_visible(False)
        bar.append(self.sensitive_btn)
        self.counter = Gtk.Label()
        self.counter.add_css_class("ft-muted")
        self.counter.set_hexpand(True)
        self.counter.set_xalign(1)
        bar.append(self.counter)
        self.send_btn = Gtk.Button(label=_("send"))
        self.send_btn.add_css_class("suggested-action")
        self.send_btn.add_css_class("ft-primary")
        self.send_btn.connect("clicked", lambda _b: self.send())
        bar.append(self.send_btn)
        box.append(bar)
        self.hint = Gtk.Label(xalign=0)
        self.hint.add_css_class("ft-status")
        box.append(self.hint)
        self.set_child(box)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        self.add_controller(keys)
        self.connect("close-request", self._closing)
        self.buffer = self.text.get_buffer()
        self._load(text)
        self.buffer.connect("changed", lambda _b: self._changed())
        self.cw.connect("changed", lambda _e: self._changed())
        self.vis.connect("notify::selected", lambda *_a: self._changed())
        self._count()
        self.text.grab_focus()
        GLib.idle_add(self._cursor_to_end)

    # ---- what it starts with -------------------------------------------------------------
    def _about(self):
        if self.edit:
            return _("edit") + ": " + snippet(self.edit, 80)
        if self.reply_to:
            return "↩ @" + self.reply_to.author.handle + ": " + snippet(self.reply_to, 80)
        if self.quote:
            return "❝ @" + self.quote.author.handle + ": " + snippet(self.quote, 80)
        return ""

    def _load(self, start_text):
        if self.edit:
            self._load_edit()
            return
        st = rules.start(self.view, self.key, self.reply_to, start_text, self.invite)
        self.buffer.set_text(st.text)
        self._set_cw(st.cw)
        self._set_vis(st.visibility)
        self._kept = {"language": st.language}
        from pathlib import Path
        for path, desc, *_focus in st.media:
            if Path(path).exists():
                self._add_media(path, desc)
        self.sensitive_btn.set_active(st.sensitive)
        if st.poll:
            self.poll_btn.set_active(True)
            for e, text in zip(self.poll_options, st.poll.get("options", []), strict=False):
                e.set_text(text)
            secs = [t for t, _k in rules.POLL_TIMES]
            if st.poll.get("expires_in") in secs:
                self.poll_time.set_selected(secs.index(st.poll["expires_in"]))
            self.poll_multiple.set_active(bool(st.poll.get("multiple")))
        if st.hint:
            self.hint.set_text(_(st.hint))
        self.initial = self._snapshot()

    def _load_edit(self):
        self._set_vis(self.edit.visibility)
        self.vis.set_sensitive(False)
        d = self.view.get_draft(self.key)
        if d:
            self.buffer.set_text(d.get("text", ""))
            self._set_cw(d.get("cw", ""))
            self.hint.set_text(_("draft_restored"))
            self.initial = self._snapshot()
            return
        self.text.set_sensitive(False)
        self.hint.set_text(_("loading"))
        self.initial = self._snapshot()

        def got(src):
            text, warning = src
            self.text.set_sensitive(True)
            self.buffer.set_text(text)
            self._set_cw(warning)
            self.hint.set_text(_("edit_hint"))
            self.initial = self._snapshot()
        self.win.call(self.view.source(self.edit), got,
                      lambda e: (self.text.set_sensitive(True),
                                 self.hint.set_text(_("load_failed", err=e))))

    def fill(self, text, warning="", visibility=None, language=None):
        """Put a redrafted post in."""
        self.buffer.set_text(text or "")
        self._set_cw(warning or "")
        if visibility:
            self._set_vis(visibility)
        if language:
            self._kept["language"] = language

    def _set_cw(self, text):
        self.cw.set_text(text or "")
        self.cw_btn.set_active(bool(text))
        self.cw.set_visible(bool(text))

    def _set_vis(self, vis):
        self.vis.set_selected(VISIBILITIES.index(vis) if vis in VISIBILITIES else 2)

    def _toggle_cw(self, on):
        self.cw.set_visible(on)
        if on:
            self.cw.grab_focus()

    def _cursor_to_end(self):
        self.buffer.place_cursor(self.buffer.get_end_iter())
        return GLib.SOURCE_REMOVE

    # ---- state -------------------------------------------------------------------------
    def _text(self):
        return self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(),
                                    False)

    def visibility(self):
        return VISIBILITIES[self.vis.get_selected()]

    def _media_list(self):
        return [[path, e.get_text().strip()] for path, e in self.media]

    def poll_data(self):
        secs = rules.POLL_TIMES[self.poll_time.get_selected()][0]
        return rules.poll_data(self.poll_btn.get_active(),
                               [e.get_text() for e in self.poll_options], secs,
                               self.poll_multiple.get_active())

    def _snapshot(self):
        return rules.snapshot(self._text(), self.cw.get_text(), self.visibility(),
                              self._media_list(), self._kept.get("language"),
                              self.sensitive_btn.get_active(), self.poll_data())

    # ---- pictures and a poll -------------------------------------------------------------
    def attach(self):
        """Pick files (Gtk.FileDialog: the desktop's own picker, portal or not)."""
        dlg = Gtk.FileDialog(title=_("media_files"))
        flt = Gtk.FileFilter()
        flt.set_name(_("media_files"))
        for ext in rules.MEDIA_EXT:
            flt.add_suffix(ext.lstrip("."))
        from gi.repository import Gio
        filters = Gio.ListStore.new(Gtk.FileFilter)
        filters.append(flt)
        dlg.set_filters(filters)

        def done(d, res):
            try:
                files = d.open_multiple_finish(res)
            except GLib.Error:
                return  # cancelled
            for i in range(files.get_n_items()):
                path = files.get_item(i).get_path()
                if path:
                    self._add_media(path)
        dlg.open_multiple(self, None, done)

    def _add_media(self, path, desc=""):
        from pathlib import Path
        limit = getattr(self.view.caps, "max_media", 4) or 4
        if len(self.media) >= limit:
            self.hint.set_text(_("media_limit", n=limit))
            return
        row = Gtk.Box(spacing=6)
        row.append(Gtk.Label(label="🖼 " + Path(path).name, xalign=0))
        alt = Gtk.Entry(placeholder_text=_("alt_prompt"))
        alt.set_text(desc or "")
        alt.set_hexpand(True)
        alt.connect("changed", lambda _e: self._changed())
        row.append(alt)
        rm = Gtk.Button(label="✕")
        rm.add_css_class("flat")
        tip(rm, _("detach"))
        item = [path, alt]
        rm.connect("clicked", lambda _b: self._remove_media(item, row))
        row.append(rm)
        self.media.append(item)
        self.media_box.append(row)
        self._media_or_poll()
        self._changed()

    def _remove_media(self, item, row):
        self.media.remove(item)
        self.media_box.remove(row)
        self._media_or_poll()
        self._changed()

    def _build_poll(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.set_visible(False)
        n = getattr(getattr(self.view, "caps", None), "max_poll_options", 4) or 4
        self.poll_options = []
        for i in range(max(2, min(n, 8))):
            e = Gtk.Entry(placeholder_text=_("poll_option", n=i + 1))
            e.connect("changed", lambda _e: self._changed())
            self.poll_options.append(e)
            box.append(e)
        row = Gtk.Box(spacing=6)
        self.poll_time = Gtk.DropDown.new_from_strings([_(k) for _t, k in rules.POLL_TIMES])
        self.poll_time.set_selected(4)  # a day
        row.append(self.poll_time)
        self.poll_multiple = Gtk.CheckButton(label=_("poll_several"))
        row.append(self.poll_multiple)
        box.append(row)
        return box

    def _toggle_poll(self, on):
        self.poll_box.set_visible(on)
        self._media_or_poll()
        self._changed()

    def _media_or_poll(self):
        """A server takes pictures or a poll, not both: one closes the other's door."""
        has_media = bool(self.media)
        self.poll_btn.set_sensitive(not has_media and not self.edit)
        self.attach_btn.set_sensitive(not self.poll_btn.get_active() and not self.edit)
        self.sensitive_btn.set_visible(has_media)

    def _changed(self):
        self._count()
        self._suggest()
        if self.cfg["post"]["drafts_autosave"]:
            if self._autosave:
                GLib.source_remove(self._autosave)
            self._autosave = GLib.timeout_add(AUTOSAVE_MS, self._autosave_now)

    def _autosave_now(self):
        self._autosave = 0
        self.save_draft()
        return GLib.SOURCE_REMOVE

    def save_draft(self):
        if self.sent:
            return
        snap = self._snapshot()
        what = rules.keep(snap, self.initial, bool(self.view.get_draft(self.key)))
        if what == "delete":
            self.view.delete_draft(self.key)
        elif what == "save":
            self.view.save_draft(self.key, snap)
            self.hint.set_text(_("draft_saved"))

    def _count(self):
        try:
            limit = self.view.caps.max_characters
        except Exception:  # noqa: BLE001
            limit = 500
        c = rules.count(self._text(), self.cw.get_text(), limit, self.cfg)
        text = (_("chain_count", n=c.parts) + " · " if c.parts > 1 else "") + f"{c.n} / {c.limit}"
        self.counter.set_text(text)
        (self.counter.add_css_class if c.over else self.counter.remove_css_class)("error")

    def _suggest(self):
        """What fits the #tag, @name or :emoji: before the cursor, as a line under the
        text (Tab puts the first one in)."""
        it = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        start = it.copy()
        start.set_line_offset(0)
        sigil, word = rules.token_at_end(self.buffer.get_text(start, it, False))
        items = rules.suggestions(self.view, sigil, word) if sigil else []
        self._offer = (sigil, word, items) if rules.worth_offering(items, word) else None
        self.suggest.set_visible(self._offer is not None)
        if self._offer:
            self.suggest.set_text("Tab: " + "  ".join(label for _i, label in items[:6]))

    def _complete(self):
        if not getattr(self, "_offer", None):
            return False
        _sigil, word, items = self._offer
        it = self.buffer.get_iter_at_mark(self.buffer.get_insert())
        start = it.copy()
        start.backward_chars(len(word) + 1)
        self.buffer.delete(start, it)
        self.buffer.insert_at_cursor(items[0][0] + " ")
        return True

    def _key(self, _ctl, keyval, _code, state):
        from gi.repository import Gdk
        ctrl = state & Gdk.ModifierType.CONTROL_MASK
        if keyval == Gdk.KEY_Return and ctrl:
            self.send()
            return True
        if keyval == Gdk.KEY_Tab and self._complete():
            return True
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    # ---- sending -------------------------------------------------------------------------
    def send(self):
        text = self._text().strip()
        media = [tuple(m) for m in self._media_list()]
        if self.cfg["post"].get("resize_images", True):
            media = [(rules.fit_for_server(m[0], self.view.caps, self.view.paths.cache_dir,
                                           _PixbufImages),) + tuple(m[1:]) for m in media]
        if not text and not media:
            return
        if any(not m[1] for m in media) and not getattr(self, "_alt_ok", False) and \
                not self.edit and self.cfg["post"].get("alt_reminder", True):
            self._ask_alt(sum(1 for m in media if not m[1]))
            return
        self.save_draft()  # whatever happens next, the text is safe
        log.info("send: %s, reply to %s, %s, %d chars", "edit" if self.edit else "post",
                 self.reply_to.id if self.reply_to else "-", self.visibility(), len(text))
        self.send_btn.set_sensitive(False)
        self.send_btn.set_label(_("sending"))
        cw = self.cw.get_text().strip() if self.cw.get_visible() else ""
        if self.edit:
            fut = self.view.edit(self.edit, text, cw, draft_key=self.key)
            self.win.call(fut, self._edited, self._failed)
            return
        fut = self.view.post(text, self.visibility(), self.reply_to, cw, media=media,
                             draft_key=self.key, language=self._kept.get("language"),
                             sensitive=self.sensitive_btn.get_active(), poll=self.poll_data(),
                             quote=self.quote)
        self.win.call(fut, self._sent, self._failed)

    def _ask_alt(self, n):
        """post.alt_reminder: a picture without a description — describe it, or send as is."""
        dlg = Gtk.AlertDialog()
        dlg.set_message(_("alt_missing_title"))
        dlg.set_detail(_("alt_missing", n=n))
        dlg.set_buttons([_("alt_describe"), _("alt_send_anyway")])
        dlg.set_cancel_button(0)
        dlg.set_default_button(0)

        def done(d, res):
            try:
                choice = d.choose_finish(res)
            except GLib.Error:
                choice = 0
            if choice == 1:
                self._alt_ok = True
                self.send()
            else:
                bare = next((e for _p, e in self.media if not e.get_text().strip()), None)
                if bare is not None:
                    bare.grab_focus()
        dlg.choose(self, None, done)
        self._asking = dlg

    def _sent(self, st):
        self.sent = True
        self.view.delete_draft(self.key)
        if isinstance(st, Scheduled):
            self.win.status(_("scheduled_msg", when=self.win.theme.date(st.at) if st.at else ""))
        else:
            self.win.status(_("sent"))
        self.close()

    def _edited(self, _st):
        self.sent = True
        self.view.delete_draft(self.key)
        self.win.status(_("edited_msg"))
        self.close()

    def _failed(self, err):
        self.send_btn.set_sensitive(True)
        self.send_btn.set_label(_("send"))
        self.hint.set_text(_("send_failed_text", err=err))

    def _closing(self, _w):
        if self._autosave:
            GLib.source_remove(self._autosave)
            self._autosave = 0
        self.save_draft()  # never lost: it waits as a draft
        return False


class _PixbufImages:
    """What common/compose.fit_for_server needs, with GdkPixbuf."""

    @staticmethod
    def size(path):
        from gi.repository import GdkPixbuf
        try:
            _fmt, w, h = GdkPixbuf.Pixbuf.get_file_info(path)
        except Exception:  # noqa: BLE001
            return None
        return (w, h) if w and h else None

    @staticmethod
    def load(path):
        from gi.repository import GdkPixbuf
        try:
            return GdkPixbuf.Pixbuf.new_from_file(path)
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def dims(img):
        return img.get_width(), img.get_height()

    @staticmethod
    def scaled(img, w, h):
        from gi.repository import GdkPixbuf
        return img.scale_simple(max(1, w), max(1, h), GdkPixbuf.InterpType.BILINEAR)

    @staticmethod
    def alpha(img):
        return img.get_has_alpha()

    @staticmethod
    def save(img, out, kind, quality):
        try:
            if kind == "jpeg":
                return img.savev(out, "jpeg", ["quality"], [str(quality)])
            return img.savev(out, "png", [], [])
        except Exception:  # noqa: BLE001
            return False
