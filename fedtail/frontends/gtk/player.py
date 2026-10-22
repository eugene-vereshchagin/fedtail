"""Video, gifv and audio over the GTK window, as Qt's player (qt/player.py): GTK's own
Gtk.Video (the GStreamer media backend: libgtk-4-media-gstreamer). Space: pause / play;
← →: 5 s back / forward; M: sound; PgUp / PgDn: the post's previous / next one; S: save;
O: the browser; Esc: close. A gifv loops, muted. The copy on disk is played when there
is one (fetched ahead, or played before) — else the server's, and it's kept for next
time. No media backend (or ui.video_player = "browser"): the browser, as before."""

from __future__ import annotations

import logging

from ...i18n import _
from .gi_setup import Gio, Gtk, tip

log = logging.getLogger(__name__)

SEEK_US = 5_000_000
MARGIN = 24


def media_url(m):
    return m.url or m.remote_url


def available():
    """Is there a media backend (GStreamer) to play with?"""
    try:
        return type(Gtk.MediaFile.new()).__name__ != "GtkNoMediaFile"
    except Exception:  # noqa: BLE001
        return False


class VideoPlayer(Gtk.Box):
    def __init__(self, win, media, index=0):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.win, self.media, self.i = win, list(media), index
        self.add_css_class("ft-viewer")
        self.set_focusable(True)
        bar = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        for m in ("top", "end"):
            getattr(bar, "set_margin_" + m)(MARGIN)
        self.prev_btn = self._button("◀", _("player_prev_tip"), lambda: self.go(-1))
        self.next_btn = self._button("▶", _("player_next_tip"), lambda: self.go(1))
        bar.append(self.prev_btn)
        bar.append(self.next_btn)
        self.mute_btn = self._button("🔇", _("player_mute_tip"), self.toggle_mute)
        bar.append(self.mute_btn)
        bar.append(self._button("⤓  " + _("save_media"), _("save_media") + " (S)", self.save))
        bar.append(self._button("↗", _("open_browser") + " (O)", self.open_outside))
        bar.append(self._button("✕", _("close") + " (Esc)", self.close))
        self.append(bar)
        self.video = Gtk.Video(vexpand=True, hexpand=True, autoplay=True)
        for m in ("start", "end"):
            getattr(self.video, "set_margin_" + m)(MARGIN)
        self.append(self.video)
        self.caption = Gtk.Label(wrap=True, justify=Gtk.Justification.CENTER)
        self.caption.add_css_class("ft-viewer-text")
        self.append(self.caption)
        keys = Gtk.Label(label=_("player_keys"))
        keys.add_css_class("ft-viewer-keys")
        keys.set_margin_bottom(MARGIN // 2)
        self.append(keys)
        key = Gtk.EventControllerKey()
        key.connect("key-pressed", self._key)
        self.add_controller(key)
        self.closed = False
        self.stream = None
        win.player = self
        win.overlay.add_overlay(self)
        self.grab_focus()
        self.load()

    def _button(self, text, tip_text, fn):
        b = Gtk.Button(label=text)
        b.add_css_class("ft-viewer-button")
        b.set_focusable(False)  # the keys stay with the player
        tip(b, tip_text)
        b.connect("clicked", lambda _b: fn())
        return b

    # ---- what's played ------------------------------------------------------------------
    def load(self):
        m = self.media[self.i]
        url = media_url(m)
        images = self.win.images
        local = images.video_local(url) if images is not None and url else None
        if local:
            log.info("video: from disk (%s)", m.kind)
            f = Gio.File.new_for_path(local)
        else:
            if images is not None and url:
                images.prefetch_video([url])  # kept on disk for next time
            f = Gio.File.new_for_uri(url or "")
        self.stream = Gtk.MediaFile.new_for_file(f)
        loop = m.kind == "gifv"
        self.stream.connect("notify::error", lambda s, _p: self._failed(s.get_error()))
        # (the video applies its own loop to a stream it's given: set after)
        self.video.set_loop(loop)
        self.video.set_media_stream(self.stream)
        self.stream.set_loop(loop)
        self.stream.set_muted(loop)  # a gifv is silent
        self.stream.play()
        many = len(self.media) > 1
        self.prev_btn.set_visible(many)
        self.next_btn.set_visible(many)
        self._caption()

    def _failed(self, err):
        if err is None:
            return
        log.info("video: %s", err.message)
        self.caption.set_text(_("player_failed", err=err.message))

    def _caption(self):
        m = self.media[self.i]
        parts = [f"{self.i + 1} / {len(self.media)}"] if len(self.media) > 1 else []
        if m.alt:
            parts.append(m.alt.replace("\n", " "))
        self.caption.set_text("    ".join(parts))
        self.mute_btn.set_label("🔇" if self.stream and self.stream.get_muted() else "🔊")

    # ---- doing ------------------------------------------------------------------------
    def go(self, step):
        if len(self.media) > 1:
            self.i = (self.i + step) % len(self.media)
            self.load()

    def toggle_pause(self):
        if self.stream is not None:
            (self.stream.pause if self.stream.get_playing() else self.stream.play)()

    def seek(self, us):
        if self.stream is not None and self.stream.is_seekable():
            dur = self.stream.get_duration() or 0
            at = max(0, self.stream.get_timestamp() + us)
            self.stream.seek(min(at, dur) if dur else at)

    def toggle_mute(self):
        if self.stream is not None:
            self.stream.set_muted(not self.stream.get_muted())
            self._caption()

    def save(self):
        self.win.save_media(self.media[self.i])

    def open_outside(self):
        self.win.open_url(media_url(self.media[self.i]))

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.stream is not None:
            self.stream.pause()
            self.video.set_media_stream(None)
            self.stream = None
        if self.get_parent() is not None:
            self.win.overlay.remove_overlay(self)
        if getattr(self.win, "player", None) is self:
            self.win.player = None

    def _key(self, _c, keyval, _code, _state):
        from .gi_setup import Gdk
        k = Gdk.keyval_name(keyval) or ""
        if k == "Escape":
            self.close()
        elif k == "space":
            self.toggle_pause()
        elif k == "Right":
            self.seek(SEEK_US)
        elif k == "Left":
            self.seek(-SEEK_US)
        elif k == "Page_Down":
            self.go(1)
        elif k == "Page_Up":
            self.go(-1)
        elif k.lower() == "m":
            self.toggle_mute()
        elif k.lower() == "o":
            self.open_outside()
        elif k.lower() == "s":
            self.save()
        else:
            return False
        return True


def show(win, media, index=0):
    """ui.video_player = "internal" (and a media backend there): over the window; else
    the browser."""
    if not media:
        return None
    m = media[index]
    if win.cfg["ui"].get("video_player", "internal") != "internal" or not available():
        win.open_url(media_url(m))
        return None
    for old in (getattr(win, "player", None), getattr(win, "viewer", None)):
        if old is not None:
            old.close()
    return VideoPlayer(win, media, index)
