"""The formatting buttons over the GTK editor (post.format_bar) — Qt's (qt/markup.py):
a row of small buttons; what each does to the text is frontends/common/markup.py's. A
TextBuffer counts in characters, as Python does: no conversion here."""

from ...i18n import _
from ..common import markup
from .gi_setup import Gtk, tip

# Ctrl+<letter> → the format, for the editor's own key handler (compose._key)
KEYS = {f.keys.split("+")[-1].lower(): f.name for f in markup.FORMATS if f.keys}


def apply(view, name):
    """Format `name` on a TextView's selection — one step of undo."""
    buf = view.get_buffer()
    text = buf.get_text(buf.get_start_iter(), buf.get_end_iter(), True)
    got_sel = buf.get_selection_bounds()
    if got_sel:
        s, e = got_sel[0].get_offset(), got_sel[1].get_offset()
    else:
        s = e = buf.get_iter_at_mark(buf.get_insert()).get_offset()
    got = markup.apply(name, text, s, e)
    buf.begin_user_action()
    buf.set_text(got.text)
    buf.end_user_action()
    buf.select_range(buf.get_iter_at_offset(got.start), buf.get_iter_at_offset(got.end))
    view.grab_focus()


def bar(view, cfg, markdown):
    """The row of buttons for the TextView `view` — or None when post.format_bar says
    there are none here."""
    if not markup.shown(cfg, markdown):
        return None
    row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=2)
    row.add_css_class("ft-format-bar")
    row.buttons = {}
    styles = {"bold": "<b>{}</b>", "italic": "<i>{}</i>", "strike": "<s>{}</s>"}
    for f in markup.FORMATS:
        lab = Gtk.Label()
        face = f.face.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        lab.set_markup(styles.get(f.name, "{}").format(face))
        b = Gtk.Button(child=lab)
        b.add_css_class("flat")
        b.add_css_class("ft-tool")
        b.set_can_focus(False)  # the selection stays in the text
        b.set_focus_on_click(False)
        tip(b, markup.tip(f, _(f.tip)))
        b.connect("clicked", lambda _b, n=f.name: apply(view, n))
        row.append(b)
        row.buttons[f.name] = b
    return row
