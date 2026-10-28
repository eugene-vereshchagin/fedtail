"""Writing a post in GTK: a new one, a reply, a quote, a call into a thread, or my post
corrected. The rules — which draft, what it starts with, the counter, completing
#tags and @names, when a draft is kept, a picture made to fit the server, the
languages offered — are common/compose.py's (the Qt editor asks there too); this is
the panel around them, as Qt's: over the lanes inside the main window (ui.compose =
"inline", the default — a new window can come up with another keyboard layout), or a
window of its own. Its parts: the text, the warning, who sees it, the language,
pictures with their descriptions or a poll; Close (the draft stays), Discard, Later,
Preview, Send.
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
BIG_PCT = 90  # ⤡: this share of the main window


COVERED = ("mp4", "webm", "mov", "mp3", "ogg", "m4a", "flac")  # a cover goes with these


class ComposeWindow(Gtk.Box):
    """The editor. Inline, the window's overlay holds it; else a Gtk.Window does
    (self.host). close() closes either, keeping the draft."""

    def __init__(self, win, reply_to=None, invite=False, edit=None, quote=None, text=""):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.win, self.view = win, win.view
        self.cfg = win.cfg
        self.reply_to = real(reply_to) if reply_to is not None else None
        self.quote = real(quote) if quote is not None else None
        self.edit = real(edit) if edit is not None else None
        self.invite = bool(invite and self.reply_to)
        self.key = rules.draft_key(self.view, self.reply_to, self.quote, self.edit,
                                   self.invite)
        self.sent = False
        self.closed = False
        self._kept = {}            # a draft's pictures and poll: kept as they were
        self._autosave = 0
        self.inline = self.cfg["ui"].get("compose", "inline") == "inline"
        self.host = None
        self.add_css_class("fedtail")
        self.add_css_class("ft-compose")
        for m in ("top", "bottom", "start", "end"):
            getattr(self, f"set_margin_{m}")(0)
        title = _("compose_edit") if self.edit else _("compose_invite") if self.invite \
            else _("compose_reply") if self.reply_to else _("compose_quote") if self.quote \
            else _("compose_new")
        self.title = title
        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(inner, f"set_margin_{m}")(14)
        inner.set_vexpand(True)
        if self.inline:  # the title strip: ⤡ bigger / smaller, the title, ✕
            head = Gtk.Box(spacing=8)
            head.add_css_class("ft-compose-head")
            self.size_btn = Gtk.Button(label="⤡")
            self.size_btn.add_css_class("flat")
            tip(self.size_btn, _("compose_bigger_tip"))
            self.size_btn.connect("clicked", lambda _b: self._toggle_big())
            head.append(self.size_btn)
            t = Gtk.Label(label=title, xalign=0, hexpand=True)
            t.add_css_class("ft-lane-title")
            head.append(t)
            x = Gtk.Button(label="✕")
            x.add_css_class("flat")
            tip(x, _("close_tip") + " (Esc)")
            x.connect("clicked", lambda _b: self.close())
            head.append(x)
            inner.append(head)
        box = inner
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
        self.text.add_css_class("ft-compose-text")
        for m in ("top", "bottom", "left", "right"):
            getattr(self.text, f"set_{m}_margin")(8)
        scroll = Gtk.ScrolledWindow()
        scroll.set_child(self.text)
        scroll.set_vexpand(True)
        scroll.add_css_class("ft-compose-frame")
        # a TextView has no placeholder: a quiet line over it while it's empty
        over = Gtk.Overlay()
        over.set_child(scroll)
        self.placeholder = Gtk.Label(
            label=_("text_placeholder_md") if self._markdown() else _("text_placeholder"),
            xalign=0, yalign=0, halign=Gtk.Align.START, valign=Gtk.Align.START)
        self.placeholder.add_css_class("ft-muted")
        self.placeholder.set_can_target(False)
        self.placeholder.set_margin_start(10)
        self.placeholder.set_margin_top(8)
        over.add_overlay(self.placeholder)
        over.set_vexpand(True)
        from .markup import around
        from .markup import bar as format_bar
        # B I S code link quote list (post.format_bar): at the side, above or below
        self.format_bar = format_bar(self.text, self.cfg, self._markdown())
        box.append(around(over, self.format_bar))
        self.suggest = Gtk.Label(xalign=0, wrap=True)  # what #tag or @name fits
        self.suggest.add_css_class("ft-muted")
        self.suggest.set_visible(False)
        box.append(self.suggest)
        # ♿ #tags all small: screen readers spell them as one word (post.camelcase_hint)
        self.camel = Gtk.Label(xalign=0, wrap=True)
        self.camel.add_css_class("ft-muted")
        self.camel.set_visible(False)
        box.append(self.camel)
        # a private answer that brings someone new into the talk: said before it goes
        self.newcomer = Gtk.Label(xalign=0, wrap=True)
        self.newcomer.add_css_class("ft-newcomer")
        self.newcomer.set_visible(False)
        box.append(self.newcomer)
        self.media_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        box.append(self.media_box)  # a row per picture: name, description, ✕
        self.media = []             # [[path, description entry, focus [x, y] or None]]
        self.covers = {}            # path of a video or a sound -> its cover picture's path
        self._cover_labels = {}     # path -> the label saying which cover
        # edit: the post's attachments — [media id, description entry, focus, as they were]
        self.remote = []
        self.poll_box = self._build_poll()
        box.append(self.poll_box)

        # what the post is: who sees it, its language, pictures, warning, poll, the count
        bar = Gtk.Box(spacing=6)
        self.vis = Gtk.DropDown.new_from_strings(
            [vis_word(v) for v in VISIBILITIES])
        tip(self.vis, _("web_visibility"))
        # all accounts in one window: which one it goes from, its whole @name@server (as Qt)
        self.from_keys = []
        accounts, first = self.view.post_accounts(self.reply_to)
        if len(accounts) > 1 and not self.edit:
            self.from_keys = [k for k, _h in accounts]
            self.from_drop = Gtk.DropDown.new_from_strings(
                [_("post_from", acct=h) for _k, h in accounts])
            self.from_drop.set_selected(self.from_keys.index(first)
                                        if first in self.from_keys else 0)
            tip(self.from_drop, _("post_from_tip"))
            self._from_first = first

            def said(*_a):
                k = self.from_keys[self.from_drop.get_selected()]
                if self.reply_to is not None and k != self._from_first:
                    self.win.status(_("post_from_other", acct=accounts[
                        self.from_drop.get_selected()][1]))
            self.from_drop.connect("notify::selected", said)
            bar.append(self.from_drop)
        bar.append(self.vis)
        self._langs = [""]
        self.lang = Gtk.DropDown.new_from_strings([_("lang_default")])
        tip(self.lang, _("lang_tip"))
        self._fill_languages()
        bar.append(self.lang)
        self.attach_btn = Gtk.Button(label="📎 " + _("attach"))
        self.attach_btn.connect("clicked", lambda _b: self.attach())
        bar.append(self.attach_btn)
        self.cw_btn = Gtk.ToggleButton(label="⚠ " + _("cw_add"))
        tip(self.cw_btn, _("cw_add_tip"))
        self.cw_btn.connect("toggled", lambda b: self._toggle_cw(b.get_active()))
        bar.append(self.cw_btn)
        self.poll_btn = Gtk.ToggleButton(label="📊 " + _("poll_add"))
        tip(self.poll_btn, _("poll_add_tip"))
        self.poll_btn.connect("toggled", lambda b: self._toggle_poll(b.get_active()))
        self.poll_btn.set_visible(not self.edit)
        bar.append(self.poll_btn)
        self.sensitive_btn = Gtk.ToggleButton(label="🔞 " + _("sensitive_mark"))
        tip(self.sensitive_btn, _("sensitive_mark_tip"))
        self.sensitive_btn.set_visible(False)
        self.sensitive_btn.connect("toggled", lambda _b: self._changed())
        bar.append(self.sensitive_btn)
        # the count in the text field's own corner, bottom right (as Qt's)
        self.counter = Gtk.Label(halign=Gtk.Align.END, valign=Gtk.Align.END)
        self.counter.add_css_class("ft-muted")
        self.counter.set_can_target(False)
        self.counter.set_margin_end(14)
        self.counter.set_margin_bottom(6)
        over.add_overlay(self.counter)
        # a line of what happened (draft restored, saved…): there only when it says something
        self.hint = Gtk.Label(xalign=0, wrap=True)
        self.hint.add_css_class("ft-muted")
        self.hint.set_visible(False)
        self.hint.connect("notify::label", lambda lab, *_a: lab.set_visible(bool(lab.get_label())))
        box.append(self.hint)
        # what to do with it: on the right of the same row when there's room, a row of
        # its own in a narrow window — each half keeping to its side (as Qt's)
        row = Gtk.Box(spacing=6)
        close = Gtk.Button(label=_("close"))
        tip(close, _("close_tip"))
        close.connect("clicked", lambda _b: self.close())
        row.append(close)
        self.discard_btn = Gtk.Button(label=_("discard"))
        self.discard_btn.connect("clicked", lambda _b: self.discard())
        row.append(self.discard_btn)
        self.later_btn = Gtk.Button(label="⏰ " + _("schedule"))
        tip(self.later_btn, _("schedule_tip"))
        self.later_btn.connect("clicked", lambda _b: self.ask_schedule())
        self.later_btn.set_visible(not self.edit and self.cfg["post"].get("schedule", True))
        row.append(self.later_btn)
        if self.cfg["post"].get("preview", True):
            pv = Gtk.Button(label="👁 " + _("preview"))
            tip(pv, _("preview_tip"))
            pv.connect("clicked", lambda _b: self.preview())
            row.append(pv)
        self.send_btn = Gtk.Button(label=_("send"))
        self.send_btn.add_css_class("suggested-action")
        self.send_btn.add_css_class("ft-primary")
        self.send_btn.connect("clicked", lambda _b: self.send())
        row.append(self.send_btn)
        bottom = Gtk.FlowBox(selection_mode=Gtk.SelectionMode.NONE, homogeneous=False,
                             min_children_per_line=1, max_children_per_line=2,
                             column_spacing=8, row_spacing=6)
        bottom.add_css_class("ft-compose-bar")
        bar.set_halign(Gtk.Align.START)
        row.set_halign(Gtk.Align.END)
        row.set_hexpand(True)
        bottom.append(bar)
        bottom.append(row)
        for child in (bottom.get_child_at_index(0), bottom.get_child_at_index(1)):
            child.set_can_focus(False)  # the buttons inside take the focus, not the halves
        bottom.get_child_at_index(1).set_hexpand(True)
        box.append(bottom)
        self.append(inner)

        keys = Gtk.EventControllerKey()
        keys.connect("key-pressed", self._key)
        self.add_controller(keys)
        # pictures and files: dropped on the editor or pasted (Ctrl+V) — attachments;
        # the paste is looked at before the text field takes it as text
        from . import dropin
        dropin.add_drop(self, self._data_dir, self.add_paths)
        paste = Gtk.EventControllerKey()
        paste.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        paste.connect("key-pressed", self._paste_key)
        self.add_controller(paste)
        self.buffer = self.text.get_buffer()
        self._load(text)
        self.buffer.connect("changed", lambda _b: self._changed())
        self.cw.connect("changed", lambda _e: self._changed())
        self.vis.connect("notify::selected", lambda *_a: self._changed())
        self.lang.connect("notify::selected", lambda *_a: self._lang_picked())
        # spelling (core/spell.py): checked in the post's language, picked anew with it
        from .spellcheck import Spell
        self.spell = Spell(self, self.text)
        self.lang.connect("notify::selected", self.spell.repick)
        self._count()
        self._placeholder()
        if self.edit:
            self.attach_btn.set_sensitive(False)
            tip(self.attach_btn, _("edit_media_kept"))

    # ---- where it lives ---------------------------------------------------------------------
    def open(self):
        """Into the main window over the lanes (one editor at a time: an open one closes,
        its text kept as a draft), or into a window of its own."""
        win = self.win
        if self.inline:
            old = getattr(win, "composer", None)
            if old is not None and not old.closed:
                old.close()
            win.composer = self
            self.add_css_class("ft-compose-panel")
            self.set_halign(Gtk.Align.FILL)
            self.set_valign(Gtk.Align.FILL)
            win.overlay.add_overlay(self)
            self._ticking = self.add_tick_callback(lambda *_a: self._place())
            self._place()
        else:
            self.host = Gtk.Window(transient_for=win, title=self.title)
            self.host.set_default_size(620, 420)
            self.host.add_css_class("fedtail")
            self.host.set_child(self)
            self.host.connect("close-request", lambda _w: (self._closing(), False)[1])
            self.host.present()
        self.text.grab_focus()
        GLib.idle_add(self._cursor_to_end)
        return self

    def _big(self):
        big = self.view.get_state("compose_big")
        if big:
            return BIG_PCT
        if big is False:
            return 0
        return min(100, int(self.cfg["ui"].get("compose_size", 0) or 0))

    def _toggle_big(self):
        self.view.set_state("compose_big", not self._big())
        self._place()

    def _place(self):
        """In the middle of the window: ui.compose_size per cent of it (⤡: 90), or at
        most 820 × 540 — following the window as it's resized."""
        parent = self.win.overlay
        w, h = parent.get_width(), parent.get_height()
        if w <= 0 or h <= 0:
            return GLib.SOURCE_CONTINUE
        pct = self._big()
        if pct:
            pw, ph = max(420, int(w * pct / 100) - 20), max(320, int(h * pct / 100) - 20)
        else:
            pw, ph = min(820, max(420, w - 80)), min(540, max(320, h - 120))
        pw, ph = min(pw, w), min(ph, h)
        mx, my = max(0, (w - pw) // 2), max(0, (h - ph) // 2)
        if (self.get_margin_start(), self.get_margin_top()) != (mx, my) or \
                self.get_margin_end() != w - pw - mx or self.get_margin_bottom() != h - ph - my:
            self.set_margin_start(mx)
            self.set_margin_end(w - pw - mx)
            self.set_margin_top(my)
            self.set_margin_bottom(h - ph - my)
        return GLib.SOURCE_CONTINUE

    def close(self):
        """Close; whatever was typed waits as a draft."""
        if self.closed:
            return
        self._closing()
        self.closed = True
        if self.inline:
            if getattr(self, "_ticking", 0):
                self.remove_tick_callback(self._ticking)
                self._ticking = 0
            parent = self.get_parent()
            if parent is not None:
                self.win.overlay.remove_overlay(self)
            if getattr(self.win, "composer", None) is self:
                self.win.composer = None
        elif self.host is not None:
            host, self.host = self.host, None
            host.destroy()

    def _away(self, away):
        """Out of sight while the post goes in the background (or back: it failed)."""
        (self.host or self).set_visible(not away)

    def _markdown(self):
        try:
            return bool(self.view.markdown)
        except Exception:  # noqa: BLE001 — not connected yet
            return False

    def _placeholder(self):
        self.placeholder.set_visible(not self._text())

    # ---- the language ------------------------------------------------------------------
    def _fill_languages(self):
        """"As in settings" first, then post.languages and post.language, then any added
        by hand; "Another language…" at the bottom."""
        added = list(self.view.get_state("languages_added", []) or [])
        self._langs = [""] + rules.languages(self.cfg, added) + [rules.OTHER_LANG]
        labels = [_("lang_default")] + [rules.language_label(c) for c in self._langs[1:-1]] \
            + [_("lang_other")]
        self.lang.set_model(Gtk.StringList.new(labels))
        self._set_language(self.cfg["post"].get("language") or "")

    def _set_language(self, code):
        code = code or ""
        if code not in self._langs:
            self._langs.insert(len(self._langs) - 1, code)
            model = self.lang.get_model()
            model.splice(len(self._langs) - 2, 0, [rules.language_label(code)])
        self._lang_before = self._langs.index(code)
        self.lang.set_selected(self._lang_before)

    def language(self):
        i = self.lang.get_selected()
        code = self._langs[i] if 0 <= i < len(self._langs) else ""
        return "" if code == rules.OTHER_LANG else code

    def _lang_picked(self):
        i = self.lang.get_selected()
        if i >= len(self._langs) or self._langs[i] != rules.OTHER_LANG:
            self._lang_before = i
            self._changed()
            return
        from . import dialogs

        def got(code):
            code = code.strip().lower()
            if not rules.LANG_CODE.fullmatch(code):
                self.lang.set_selected(self._lang_before)
                return
            added = list(self.view.get_state("languages_added", []) or [])
            if code not in added:
                self.view.set_state("languages_added", added + [code])
                log.info("compose: language %s added to the list", code)
            self._set_language(code)
            self._changed()
        self.lang.set_selected(self._lang_before)
        dialogs.ask_text(self.get_root(), _("lang_other_title"), _("lang_other_ask"), got)

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
        self._kept = {}
        if st.language:
            self._set_language(st.language)
        from pathlib import Path
        for path, desc, *rest in st.media:
            if Path(path).exists():
                self._add_media(path, desc, rest[0] if rest else None)
                if len(rest) > 1 and rest[1] and Path(rest[1]).exists():
                    self.pick_cover(path, rest[1])
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
        for m in self.edit.media:  # their words and focus can change; they stay
            self._add_remote(m)
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
            self._set_language(language)

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
        out = []
        for path, e, f in self.media:
            entry = [path, e.get_text().strip()]
            cover = self.covers.get(path)
            if f or cover:
                entry.append(list(f) if f else None)
            if cover:
                entry.append(cover)
            out.append(entry)
        return out

    def media_changes(self):
        """Edit: {media id: (description, focus)} of the post's attachments whose words or
        focus point were changed here."""
        out = {}
        for item in self.remote:
            mid, e, focus, was = item
            now = (e.get_text().strip(), tuple(round(float(x), 2) for x in focus)
                   if focus else None)
            if now != was:
                out[mid] = now
        return out

    def _add_remote(self, m):
        """An attachment of the post being edited: its description (and a picture's focus
        point, its preview being at hand) can be changed; it can't go or be replaced."""
        row = Gtk.Box(spacing=6)
        row.append(Gtk.Label(label=("🖼 " if m.kind == "image" else "🎞 ") + _("alt_title"),
                             xalign=0))
        alt = Gtk.Entry(placeholder_text=_("alt_prompt"))
        alt.set_text(m.alt or "")
        alt.set_hexpand(True)
        alt.connect("changed", lambda _e: self._changed())
        row.append(alt)
        focus = list(m.focus) if m.focus else None
        item = [m.ref.id, alt, focus,
                ((m.alt or "").strip(), tuple(round(float(x), 2) for x in focus)
                 if focus else None)]
        images = getattr(self.win, "images", None)
        local = images.local(m.preview or m.url) if images is not None and \
            m.kind == "image" else None
        if local:
            aim = Gtk.Button(label="◎")
            aim.add_css_class("flat")
            tip(aim, _("focus_tip"))
            aim.connect("clicked", lambda _b: self._focus_remote(item, local))
            row.append(aim)
        self.remote.append(item)
        self.media_box.append(row)

    def _focus_remote(self, item, local):
        from .focus import FocusDialog

        def done(desc, focus):
            item[1].set_text(desc)
            item[2] = focus
            self._changed()
        return FocusDialog(self.get_root(), local, item[1].get_text(), item[2], done)

    def pick_cover(self, path, file=None):
        """A cover picture for the video or the sound at path: file, or asked."""
        if file:
            self.covers[path] = file
            self._cover_labels[path].set_text(_("media_cover_set",
                                                name=file.rsplit("/", 1)[-1]))
            self._changed()
            return
        dlg = Gtk.FileDialog(title=_("media_cover"))
        flt = Gtk.FileFilter()
        flt.set_name(_("media_cover"))
        for ext in ("jpg", "jpeg", "png", "webp", "gif"):
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
                self.pick_cover(path, f.get_path())
        dlg.open(self.get_root(), None, done)

    def poll_data(self):
        secs = rules.POLL_TIMES[self.poll_time.get_selected()][0]
        return rules.poll_data(self.poll_btn.get_active(),
                               [e.get_text() for e in self.poll_options], secs,
                               self.poll_multiple.get_active())

    def _snapshot(self):
        return rules.snapshot(self._text(), self.cw.get_text(), self.visibility(),
                              self._media_list(), self.language() or None,
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
        dlg.open_multiple(self.get_root(), None, done)

    def _data_dir(self):
        return self.view.paths.data_dir

    def add_paths(self, paths):
        """Files in as attachments (a drop, a paste, a drop on the window), each once."""
        known = {m[0] for m in self.media}
        for path in paths:
            if path not in known:
                known.add(path)
                self._add_media(path)

    def _paste_key(self, _ctl, keyval, _code, state):
        from gi.repository import Gdk

        from . import dropin
        if not state & Gdk.ModifierType.CONTROL_MASK or keyval not in (Gdk.KEY_v, Gdk.KEY_V):
            return False
        if state & Gdk.ModifierType.SHIFT_MASK:
            return False  # Ctrl+Shift+V: always as text
        return dropin.paste(self, self._data_dir, self.add_paths,
                            as_text=self.buffer.insert_at_cursor)

    def _add_media(self, path, desc="", focus=None):
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
        item = [path, alt, list(focus) if focus else None]
        if path.lower().rsplit(".", 1)[-1] in ("png", "jpg", "jpeg", "gif", "webp"):
            aim = Gtk.Button(label="◎")  # where on the picture the main thing is (Qt's)
            aim.add_css_class("flat")
            tip(aim, _("focus_tip"))
            aim.connect("clicked", lambda _b: self._focus_dialog(item))
            row.append(aim)
        if path.lower().rsplit(".", 1)[-1] in COVERED:  # a video or a sound: a cover
            cover = Gtk.Button(label=_("media_cover"))
            cover.add_css_class("flat")
            tip(cover, _("media_cover_tip"))
            cover.connect("clicked", lambda _b: self.pick_cover(path))
            row.append(cover)
            label = Gtk.Label(label="", xalign=0)
            label.add_css_class("ft-muted")
            self._cover_labels[path] = label
            row.append(label)
        rm = Gtk.Button(label="✕")
        rm.add_css_class("flat")
        tip(rm, _("detach"))
        rm.connect("clicked", lambda _b: self._remove_media(item, row))
        row.append(rm)
        self.media.append(item)
        self.media_box.append(row)
        self._media_or_poll()
        self._changed()

    def insert_quote(self, text, whole=False, at_end=False):
        """`text` in as a quote (post.quote_prefix) where the cursor is (at_end: after
        what's there), the cursor after it, ready for the answer — as Qt's."""
        from ...model.text import join_quote, quote_lines
        q = quote_lines(text, self.cfg["post"].get("quote_prefix", "> ") or "> ",
                        strip_mentions=whole)
        if not q:
            return
        buf = self.buffer
        it = buf.get_end_iter() if at_end else buf.get_iter_at_mark(buf.get_insert())
        before = buf.get_text(buf.get_start_iter(), it, False)
        buf.insert(it, join_quote(before, q) + q)
        buf.place_cursor(it)
        self.text.grab_focus()

    def _focus_dialog(self, item):
        from .focus import FocusDialog

        def done(desc, focus):
            item[1].set_text(desc)
            item[2] = focus
            self._changed()
        return FocusDialog(self.get_root(), item[0], item[1].get_text(), item[2], done)

    def _remove_media(self, item, row):
        self.media.remove(item)
        self.covers.pop(item[0], None)
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
        self._placeholder()
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
        c = rules.count(self._text(), self.cw.get_text(), limit, self.cfg,
                        reply_to=self.reply_to, visibility=self.visibility(),
                        me=self.view.me)
        self.newcomer.set_visible(bool(c.newcomers))
        if c.newcomers:
            self.newcomer.set_text(_("dm_newcomer_typed", who=", ".join(c.newcomers)))
        text = (_("chain_count", n=c.parts) + " · " if c.parts > 1 else "") + f"{c.n} / {c.limit}"
        self.counter.set_text(text)
        (self.counter.add_css_class if c.over else self.counter.remove_css_class)("error")
        flat = c.flat_tags if self.cfg["post"].get("camelcase_hint", True) else []
        self.camel.set_visible(bool(flat))
        if flat:
            self.camel.set_text(_("camel_hint", tags=", ".join("#" + t for t in flat[:3])))

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
        if ctrl and self.format_bar is not None and self.text.has_focus():
            from .markup import KEYS, apply
            name = KEYS.get((Gdk.keyval_name(Gdk.keyval_to_lower(keyval)) or "").lower())
            if name:  # Ctrl+B / Ctrl+I / Ctrl+K: the formatting buttons' keys
                apply(self.text, name)
                return True
        if keyval == Gdk.KEY_Escape:
            self.close()
            return True
        return False

    # ---- sending -------------------------------------------------------------------------
    def send(self, scheduled_at=None):
        text = self._text().strip()
        media = [tuple(m) for m in self._media_list()]
        if self.cfg["post"].get("resize_images", True):
            media = [(rules.fit_for_server(m[0], self.view.caps, self.view.paths.cache_dir,
                                           _PixbufImages),) + tuple(m[1:]) for m in media]
        if not text and not media and not (self.edit and self.media_changes()):
            return
        if any(not m[1] for m in media) and not getattr(self, "_alt_ok", False) and \
                not self.edit and self.cfg["post"].get("alt_reminder", True):
            self._ask_alt(sum(1 for m in media if not m[1]), scheduled_at)
            return
        said = None if getattr(self, "_lang_ok", False) or self.edit else \
            rules.lang_mismatch(self.cfg, text, self.language())
        if said:  # post.lang_check: the text reads as another language
            self._ask_lang(said, scheduled_at)
            return
        self.save_draft()  # whatever happens next, the text is safe
        log.info("send: %s, reply to %s, %s, %d chars", "edit" if self.edit else "post",
                 self.reply_to.id if self.reply_to else "-", self.visibility(), len(text))
        self.send_btn.set_sensitive(False)
        self.send_btn.set_label(_("sending"))
        cw = self.cw.get_text().strip() if self.cw.get_visible() else ""
        if self.edit:
            changed = self.media_changes()
            fut = self.view.edit(self.edit, text, cw, draft_key=self.key,
                                 **({"media": changed} if changed else {}))
            self.win.call(fut, self._edited, self._failed)
            return
        fut = self.view.post(text, self.visibility(), self.reply_to, cw, media=media,
                             draft_key=self.key, language=self.language() or None,
                             sensitive=self.sensitive_btn.get_active(), poll=self.poll_data(),
                             quote=self.quote, scheduled_at=scheduled_at,
                             **({"account": self.from_keys[self.from_drop.get_selected()]}
                                if self.from_keys else {}))
        self.win.call(fut, self._sent, self._failed)
        if self.cfg["post"].get("send_in_background"):  # out of the way at once
            self._away(True)
            self.win.status(_("sent_background"))

    def _ask_lang(self, said, scheduled_at=None):
        """post.lang_check: the text reads as `said` — mark it so, send as is, or back."""
        title, text, switch_w, anyway_w = rules.lang_question(
            said, self.language() or self.cfg["post"].get("language"))
        dlg = Gtk.AlertDialog()
        dlg.set_message(title)
        dlg.set_detail(text)
        dlg.set_buttons([_("cancel"), anyway_w, switch_w])
        dlg.set_cancel_button(0)
        dlg.set_default_button(2)

        def done(d, res):
            try:
                choice = d.choose_finish(res)
            except GLib.Error:
                choice = 0
            if choice == 2:
                self._set_language(said)
            if choice in (1, 2):
                self._lang_ok = True
                self.send(scheduled_at)
                self._lang_ok = False
        dlg.choose(self.get_root(), None, done)

    def _ask_alt(self, n, scheduled_at=None):
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
                self.send(scheduled_at)
            else:
                bare = next((e for _p, e, _f in self.media if not e.get_text().strip()),
                            None)
                if bare is not None:
                    bare.grab_focus()
        dlg.choose(self.get_root(), None, done)
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
        away = not (self.host or self).get_visible()
        self._away(False)  # sent in the background (post.send_in_background): back
        maybe = getattr(err, "maybe_sent", False)  # no answer: the post may be out
        self.hint.set_text((_("send_maybe") + ". " if maybe else "")
                           + _("sent_background_failed" if away else "send_failed_text",
                               err=err))

    def _closing(self, *_a):
        if getattr(self, "spell", None) is not None:
            self.spell.stop()
        if self._autosave:
            GLib.source_remove(self._autosave)
            self._autosave = 0
        self.save_draft()  # never lost: it waits as a draft
        return False

    # ---- discard, later, preview ---------------------------------------------------------
    def discard(self):
        """Throw the text away for good (asked first)."""
        def go():
            self.view.delete_draft(self.key)
            self.sent = True  # nothing to keep
            self.close()
        if not self._text().strip() and not self.media:
            go()
            return
        self.win.confirm(_("discard_q_title"), _("discard_q"), go)

    def ask_schedule(self):
        """When to send it: the server keeps the post and sends it then (at least five
        minutes on; an hour on to start with)."""
        from datetime import UTC, datetime, timedelta
        start = datetime.now().astimezone() + timedelta(hours=1)
        dlg = Gtk.Window(title=_("schedule"), transient_for=self.get_root(), modal=True)
        dlg.add_css_class("fedtail")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(12)
        box.append(Gtk.Label(label=_("schedule_when"), xalign=0))
        cal = Gtk.Calendar()
        cal.select_day(GLib.DateTime.new_local(start.year, start.month, start.day, 0, 0, 0))
        box.append(cal)
        row = Gtk.Box(spacing=4, halign=Gtk.Align.CENTER)
        hour = Gtk.SpinButton.new_with_range(0, 23, 1)
        hour.set_value(start.hour)
        minute = Gtk.SpinButton.new_with_range(0, 59, 1)
        minute.set_value(start.minute)
        row.append(hour)
        row.append(Gtk.Label(label=":"))
        row.append(minute)
        box.append(row)
        note = Gtk.Label(xalign=0)
        note.add_css_class("ft-muted")
        box.append(note)
        cancel = Gtk.Button(label=_("cancel"))
        ok = Gtk.Button(label=_("schedule_ok"))
        ok.add_css_class("suggested-action")
        buttons = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        buttons.append(cancel)
        buttons.append(ok)
        box.append(buttons)
        dlg.set_child(box)

        def when():
            d = cal.get_date()
            local = datetime(d.get_year(), d.get_month(), d.get_day_of_month(),
                             int(hour.get_value()), int(minute.get_value()))
            return local.astimezone()

        def go(_b):
            at = when()
            if at < datetime.now().astimezone() + timedelta(minutes=5):
                note.set_text(_("schedule_too_soon"))
                return
            dlg.close()
            utc = at.astimezone(UTC)
            self.send(scheduled_at=utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"))
        cancel.connect("clicked", lambda _b: dlg.close())
        ok.connect("clicked", go)
        self.schedule_dialog = dlg
        dlg.present()
        return dlg

    def preview(self):
        """How it will look: Markdown made into text the way a Markdown server does (when
        this one is), the warning, who sees it, each post of a chain, the pictures; Send
        or back to editing from here."""
        from ...model.text import chain_parts
        from .. import pango
        text = self._text().strip()
        parts = (chain_parts(text) if self.cfg["post"].get("chain", True) else [text]) or [text]
        md = self._markdown()
        head = " · ".join(x for x in (
            vis_word(self.visibility()),
            rules.language_label(self.language()) if self.language() else "",
            _("chain_count", n=len(parts)) if len(parts) > 1 else "",
            _("preview_media", n=len(self.media)) if self.media else "",
            _("preview_md") if md else _("preview_plain")) if x)
        dlg = Gtk.Window(title=_("preview"), transient_for=self.get_root(), modal=True)
        dlg.set_default_size(640, 520)
        dlg.add_css_class("fedtail")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        for m in ("top", "bottom", "start", "end"):
            getattr(box, f"set_margin_{m}")(12)
        info = Gtk.Label(label=head, xalign=0, wrap=True)
        info.add_css_class("ft-muted")
        box.append(info)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        cw = self.cw.get_text().strip() if self.cw.get_visible() else ""
        for i, part in enumerate(parts):
            if cw:
                body.append(Gtk.Label(label="⚠ " + cw, xalign=0, wrap=True))
            lab = Gtk.Label(xalign=0, yalign=0, wrap=True)
            lab.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            lab.add_css_class("ft-card")
            if md:
                lab.set_markup(pango.markdown(part))
            else:
                lab.set_text(part)
            body.append(lab)
            if i < len(parts) - 1:
                body.append(Gtk.Label(label="↳", xalign=0))
        sc = Gtk.ScrolledWindow(vexpand=True)
        sc.set_child(body)
        box.append(sc)
        back = Gtk.Button(label=_("preview_back"))
        send = Gtk.Button(label=_("send"))
        send.add_css_class("suggested-action")
        back.connect("clicked", lambda _b: dlg.close())
        send.connect("clicked", lambda _b: (dlg.close(), self.send()))
        row = Gtk.Box(spacing=6, halign=Gtk.Align.END)
        row.append(send)
        row.append(back)
        box.append(row)
        dlg.set_child(box)
        dlg.present()
        self.preview_dialog = dlg
        return dlg


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
