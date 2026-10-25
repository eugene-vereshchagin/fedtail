"""Spell checking in the post editor (core/spell.py), as in Qt: words with mistakes
underlined (Pango's error wave), and on a right click over one — what to put instead
and "Add to dictionary" at the top of the text's own menu (its extra_menu). The
checker follows the post's language picked in the editor."""

from __future__ import annotations

import logging

from ...core import spell
from ...i18n import _, current_language
from .gi_setup import Gio, GLib, Gtk, Pango, tip

log = logging.getLogger(__name__)
SUGGESTIONS = 8
DELAY_MS = 300  # typing on: marked once it pauses, not at every key


def config_dir(view):
    """Where my own dictionary lives: next to the config (spelling.txt)."""
    try:
        from ..common import settings
        return settings.config_file(view).parent
    except Exception:  # noqa: BLE001 — a view without paths (tests): no own words file
        return None


class Spell:
    def __init__(self, compose, textview):
        self.compose, self.textview = compose, textview
        self.view = compose.view
        self.buffer = textview.get_buffer()
        self.on = bool((self.view.cfg.get("post") or {}).get("spellcheck", True))
        self.checker = None
        self._timer = 0
        self._word = None  # (start offset, end offset, word) under the last right click
        self.said_unavailable = False
        self.tag = self.buffer.create_tag("ft-spell", underline=Pango.Underline.ERROR)
        if not self.on:
            return
        self.buffer.connect("changed", lambda _b: self.later())
        group = Gio.SimpleActionGroup()
        for name, fn in (("replace", self._replace), ("add", self._add)):
            act = Gio.SimpleAction.new(name, GLib.VariantType.new("s"))
            act.connect("activate", fn)
            group.add_action(act)
        textview.insert_action_group("spell", group)
        click = Gtk.GestureClick()
        click.set_button(3)  # the right button: before the text's own menu opens
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self._pressed)
        textview.add_controller(click)
        self.repick()

    # ---- the checker and the marks ----------------------------------------------------
    def repick(self, *_a):
        """The checker for the language picked now (the editor's language list)."""
        if not self.on:
            return
        lang = ""
        try:
            lang = self.compose.language() or ""
        except Exception:  # noqa: BLE001 — called before the list is filled
            pass
        self.checker = spell.for_post(self.view.cfg, config_dir(self.view), lang,
                                      current_language())
        if self.checker is None and not spell.available() and not self.said_unavailable:
            self.said_unavailable = True
            tip(self.textview, _("spell_unavailable"))
        self.mark()

    def later(self):
        if self._timer:
            GLib.source_remove(self._timer)
        self._timer = GLib.timeout_add(DELAY_MS, self._due)

    def _due(self):
        self._timer = 0
        self.mark()
        return GLib.SOURCE_REMOVE

    def stop(self):
        """The editor closes: no mark due after it."""
        if self._timer:
            GLib.source_remove(self._timer)
            self._timer = 0

    def text(self):
        return self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(),
                                    True)

    def wrong(self):
        if self.checker is None:
            return []
        try:
            return self.checker.wrong(self.text())
        except Exception as e:  # noqa: BLE001 — a dictionary failing: no marks
            log.debug("spell: %s", e)
            return []

    def mark(self):
        """The marks anew over the whole text (a post is short)."""
        b = self.buffer
        b.remove_tag(self.tag, b.get_start_iter(), b.get_end_iter())
        for start, end, _w in self.wrong():
            b.apply_tag(self.tag, b.get_iter_at_offset(start), b.get_iter_at_offset(end))

    def marked(self):
        """[(start, end)] of the marks on now (for the tests)."""
        out, it = [], self.buffer.get_start_iter()
        while True:
            if it.starts_tag(self.tag):
                end = it.copy()
                end.forward_to_tag_toggle(self.tag)
                out.append((it.get_offset(), end.get_offset()))
            if not it.forward_to_tag_toggle(self.tag):
                break
        return out

    # ---- the right click ---------------------------------------------------------------
    def word_at_offset(self, offset):
        for start, end, word in spell.words(self.text()):
            if start <= offset <= end:
                return start, end, word
        return None

    def menu_for(self, offset):
        """The extra menu for the word at offset (None — a good word, or none)."""
        got = self.word_at_offset(offset) if self.checker is not None else None
        if got is None or self.checker.ok(got[2]):
            self._word = None
            return None
        self._word = got
        menu = Gio.Menu()
        fixes = Gio.Menu()
        for s in self.checker.suggest(got[2], SUGGESTIONS):
            fixes.append(s, "spell.replace(" + GLib.Variant.new_string(s).print_(False) + ")")
        if fixes.get_n_items() == 0:
            fixes.append(_("spell_none"), "spell.none")  # no such action: shown greyed
        menu.append_section(None, fixes)
        add = Gio.Menu()
        add.append(_("spell_add"), "spell.add(" + GLib.Variant.new_string(got[2]).print_(
            False) + ")")
        menu.append_section(None, add)
        return menu

    def _pressed(self, _gesture, _n, x, y):
        bx, by = self.textview.window_to_buffer_coords(Gtk.TextWindowType.WIDGET,
                                                       int(x), int(y))
        found = self.textview.get_iter_at_location(bx, by)
        it = found[1] if isinstance(found, tuple) else found
        menu = self.menu_for(it.get_offset()) if it is not None else None
        self.textview.set_extra_menu(menu)

    def replace(self, word):
        if self._word is None:
            return
        start, end, _old = self._word
        b = self.buffer
        b.begin_user_action()
        s, e = b.get_iter_at_offset(start), b.get_iter_at_offset(end)
        b.delete(s, e)
        b.insert(b.get_iter_at_offset(start), word)
        b.end_user_action()
        self._word = None
        self.mark()

    def add(self, word):
        if self.checker is not None:
            self.checker.add(word)
        self._word = None
        self.mark()

    def _replace(self, _act, param):
        self.replace(param.get_string())

    def _add(self, _act, param):
        self.add(param.get_string())


__all__ = ["Spell", "config_dir"]
