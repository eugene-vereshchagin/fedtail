"""The picture viewer over the main window, as the Qt one (qt/viewer.py): the picture
fits the window (a small one grows up to ui.image_upscale times), the feed's copy at
once while the original comes. ← → Space: flip; Z or a double click: 100 % and back
(scrolled then); O: in the browser; S: save (ui.save_dir); R: the original again;
Esc or a click: close."""

from __future__ import annotations

import logging

from ...i18n import _
from .gi_setup import GLib, Gtk, tip

log = logging.getLogger(__name__)

FULL_SIDE = 8192
MARGIN = 24
ALT_MAX_H = 180  # px a picture's description takes at most: the rest scrolls


class ImageViewer(Gtk.Box):
    def __init__(self, win, media, index=0):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.win, self.media, self.i = win, list(media), index
        self.actual = False
        self.preview = False
        self.problem = ""
        self.add_css_class("ft-viewer")
        self.set_focusable(True)
        self.set_halign(Gtk.Align.FILL)
        self.set_valign(Gtk.Align.FILL)
        for m in ("top", "bottom", "start", "end"):
            getattr(self, "set_margin_" + m)(0)

        bar = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        for m in ("top", "end"):
            getattr(bar, "set_margin_" + m)(MARGIN)
        save = self._button("⤓  " + _("viewer_save"), _("viewer_save_tip") + " (S)", self.save)
        bar.append(save)
        bar.append(self._button("↗", _("open_browser") + " (O)", self.open_outside))
        bar.append(self._button("✕", _("close") + " (Esc)", self.close))
        self.append(bar)

        self.picture = Gtk.Picture()
        self.picture.set_can_shrink(True)
        upscale = float(win.cfg["ui"].get("image_upscale", 2) or 1)
        self.fit = Gtk.ContentFit.CONTAIN if upscale > 1 else Gtk.ContentFit.SCALE_DOWN
        self.picture.set_content_fit(self.fit)
        self.scroll = Gtk.ScrolledWindow(vexpand=True, hexpand=True)
        self.scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
        self.scroll.set_child(self.picture)
        for m in ("start", "end"):
            getattr(self.scroll, "set_margin_" + m)(MARGIN)
        self.append(self.scroll)

        self.caption = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.caption.add_css_class("ft-viewer-text")
        self.caption.set_selectable(False)
        # a long description scrolls past ALT_MAX_H instead of pushing the picture away
        alt = Gtk.ScrolledWindow(propagate_natural_height=True, max_content_height=ALT_MAX_H)
        alt.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        alt.set_child(self.caption)
        for m in ("start", "end"):
            getattr(alt, "set_margin_" + m)(MARGIN)
        self.append(alt)
        keys = Gtk.Label(label=_("viewer_keys"))
        keys.add_css_class("ft-viewer-keys")
        keys.set_margin_bottom(MARGIN // 2)
        self.append(keys)

        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._key)
        self.add_controller(key)
        click = Gtk.GestureClick()
        click.connect("released", self._clicked)
        self.add_controller(click)
        self._click_timer = 0
        self.closed = False
        win.viewer = self
        win.overlay.add_overlay(self)
        self.grab_focus()
        # (not focusable until it's on screen: the card clicked kept the keys — again
        # once it's mapped, so ← → Z S O work without a click first)
        self.connect("map", lambda *_a: GLib.idle_add(
            lambda: (self.grab_focus(), GLib.SOURCE_REMOVE)[1]))
        self.load()

    def _button(self, text, tip_text, fn):
        b = Gtk.Button(label=text)
        b.add_css_class("ft-viewer-button")
        b.set_focusable(False)  # the keys stay with the viewer
        tip(b, tip_text)
        b.connect("clicked", lambda _b: fn())
        return b

    # ---- what's shown ------------------------------------------------------------------
    def url(self):
        m = self.media[self.i]
        return m.url or m.remote_url or m.preview

    def load(self, retry=False):
        self.preview, self.problem = True, ""
        self.picture.set_paintable(None)
        self._set_actual(False)
        want = self.i
        m = self.media[self.i]
        images = self.win.images
        if m.preview and m.preview != self.url():
            images.get(m.preview, lambda tex, w=want: self._small(w, tex))
        images.get(self.url(), lambda tex, w=want: self._loaded(w, tex), FULL_SIDE,
                   failed=lambda w=want: self._failed(w), retry=retry, big=True)
        self._caption()

    def _small(self, index, tex):
        if index == self.i and self.picture.get_paintable() is None:
            self.picture.set_paintable(tex)
            self._caption()

    def _loaded(self, index, tex):
        if index == self.i:
            self.preview, self.problem = False, ""
            self.picture.set_paintable(tex)
            self._caption()

    def _failed(self, index):
        if index != self.i:
            return
        kind, detail = self.win.images.why.get(self.url(), ("network", ""))
        self.problem = _("viewer_format", kind=detail) if kind == "format" else \
            _("viewer_unreachable", err=detail or "?")
        self._caption()

    def _caption(self):
        m = self.media[self.i]
        parts = []
        if len(self.media) > 1:
            parts.append(f"{self.i + 1} / {len(self.media)}")
        if self.problem:
            parts.append(self.problem)
        elif self.picture.get_paintable() is None:
            parts.append(_("loading"))
        elif self.preview:
            parts.append(_("viewer_original_coming"))
        if m.alt:
            parts.append(m.alt.replace("\n", " "))
        self.caption.set_text("    ".join(parts))

    def go(self, step):
        if len(self.media) > 1:
            self.i = (self.i + step) % len(self.media)
            self.load()

    def _set_actual(self, on):
        """100 %: the picture at its own size, scrolled; else fitted to the window."""
        self.actual = on
        self.picture.set_can_shrink(not on)
        self.picture.set_content_fit(Gtk.ContentFit.FILL if on else self.fit)
        pol = Gtk.PolicyType.AUTOMATIC if on else Gtk.PolicyType.NEVER
        self.scroll.set_policy(pol, pol)

    # ---- doing ----------------------------------------------------------------------
    def save(self):
        from ...core import saving
        win = self.win
        url = self.url()
        if url:
            win.call(win.images.save(url, saving.save_dir(win.cfg)),
                     lambda p: win.status(_("saved_to", path=str(p))),
                     lambda e: win.error(_("save_failed", err=e)))

    def open_outside(self):
        self.win.open_url(self.url())

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self._click_timer:
            GLib.source_remove(self._click_timer)
            self._click_timer = 0
        if self.get_parent() is not None:
            self.win.overlay.remove_overlay(self)
        if getattr(self.win, "viewer", None) is self:
            self.win.viewer = None

    def _key(self, _c, keyval, _code, _state):
        from .gi_setup import Gdk
        k = Gdk.keyval_name(keyval) or ""
        if k == "Escape":
            self.close()
        elif k in ("Right", "space", "Page_Down"):
            self.go(1)
        elif k in ("Left", "BackSpace", "Page_Up"):
            self.go(-1)
        elif k.lower() == "z":
            self._set_actual(not self.actual)
        elif k.lower() == "r":
            self.load(retry=True)
        elif k.lower() == "o":
            self.open_outside()
        elif k.lower() == "s":
            self.save()
        else:
            return False
        return True

    def _clicked(self, gesture, n, _x, _y):
        """One click closes — unless it turns out to be the first of two (100 %)."""
        if n >= 2:
            if self._click_timer:
                GLib.source_remove(self._click_timer)
                self._click_timer = 0
            self._set_actual(not self.actual)
            return
        if self._click_timer:
            return

        def later():
            self._click_timer = 0
            self.close()
            return GLib.SOURCE_REMOVE
        self._click_timer = GLib.timeout_add(260, later)


def show(win, media, index=0):
    """ui.image_viewer = "internal": over the window; "browser": the file outside."""
    if not media:
        return None
    if win.cfg["ui"].get("image_viewer", "internal") != "internal":
        m = media[index]
        win.open_url(m.url or m.remote_url or m.preview)
        return None
    old = getattr(win, "viewer", None)
    if old is not None:
        old.close()
    return ImageViewer(win, media, index)
