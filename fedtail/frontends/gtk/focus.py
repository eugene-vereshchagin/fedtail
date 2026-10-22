"""A picture's description and focus point before it is sent, as Qt's: a click on the
picture puts a cross there (Mastodon's focus: what a cropped preview keeps), "Centre"
takes it away; the description below. done(description, focus or None) on OK."""

from __future__ import annotations

import math

from ...i18n import _
from ..common.focus import from_focus, to_focus
from .dialogs import _box, _buttons, _window
from .gi_setup import Gdk, GLib, Gtk

SIDE = 360


class FocusDialog:
    def __init__(self, parent, path, description, focus, done):
        self.focus = list(focus) if focus else None
        self.done = done
        self.dlg = dlg = _window(parent, _("alt_title"), 460, 560)
        dlg.set_modal(True)
        box = _box()
        self.size = (0, 0)
        try:
            tex = Gdk.Texture.new_from_filename(path)
            w, h = tex.get_width(), tex.get_height()
            k = min(SIDE / w, SIDE / h, 1.0)
            self.size = (max(1, int(w * k)), max(1, int(h * k)))
        except GLib.Error:
            tex = None
        if tex is not None:
            pic = Gtk.Picture.new_for_paintable(tex)
            pic.set_can_shrink(True)
            pic.set_size_request(*self.size)
            self.cross = Gtk.DrawingArea()
            self.cross.set_draw_func(self._draw)
            over = Gtk.Overlay(halign=Gtk.Align.CENTER)
            over.set_child(pic)
            over.add_overlay(self.cross)
            over.set_size_request(*self.size)
            over.set_cursor(Gdk.Cursor.new_from_name("crosshair", None))
            from .gi_setup import tip
            tip(over, _("focus_tip"))
            click = Gtk.GestureClick()
            click.connect("pressed", lambda _g, _n, x, y: self._clicked(x, y))
            over.add_controller(click)
            box.append(over)
            row = Gtk.Box(spacing=6)
            self.where = Gtk.Label(xalign=0, hexpand=True)
            self.where.add_css_class("ft-muted")
            row.append(self.where)
            centre = Gtk.Button(label=_("focus_centre"))
            centre.connect("clicked", lambda _b: self._centre())
            row.append(centre)
            box.append(row)
        box.append(Gtk.Label(label=_("alt_prompt"), xalign=0, wrap=True))
        self.text = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR)
        self.text.get_buffer().set_text(description or "")
        self.text.set_size_request(-1, 90)
        frame = Gtk.Frame(child=self.text)
        box.append(frame)
        cancel = Gtk.Button(label=_("cancel"))
        cancel.connect("clicked", lambda _b: dlg.close())
        ok = Gtk.Button(label=_("save"))
        ok.add_css_class("suggested-action")
        ok.connect("clicked", lambda _b: self._ok())
        box.append(_buttons(cancel, ok))
        dlg.set_child(box)
        self._show_where()
        dlg.present()
        self.text.grab_focus()

    def description(self):
        buf = self.text.get_buffer()
        return buf.get_text(buf.get_start_iter(), buf.get_end_iter(), False).strip()

    def _ok(self):
        self.done(self.description(), self.focus)
        self.dlg.close()

    def _clicked(self, x, y):
        w, h = self.size
        if w and h:
            self.focus = list(to_focus(x, y, w, h))
            self._show_where()

    def _centre(self):
        self.focus = None
        self._show_where()

    def _show_where(self):
        if not hasattr(self, "where"):
            return
        self.where.set_text(_("focus_at", x=f"{self.focus[0]:+.2f}", y=f"{self.focus[1]:+.2f}")
                            if self.focus else _("focus_none"))
        self.cross.queue_draw()

    def _draw(self, _area, cr, w, h):
        if not self.focus:
            return
        x, y = from_focus(self.focus, w, h)
        for (r, g, b, a), width in (((0, 0, 0, 0.67), 4), ((1, 1, 1, 1), 2)):
            cr.set_source_rgba(r, g, b, a)
            cr.set_line_width(width)
            cr.arc(x, y, 12, 0, 2 * math.pi)
            cr.stroke()
            cr.move_to(x - 20, y)
            cr.line_to(x + 20, y)
            cr.move_to(x, y - 20)
            cr.line_to(x, y + 20)
            cr.stroke()
