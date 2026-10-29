"""Video, gifv and audio inside the window (QtMultimedia), instead of the browser.

* a video opens over the main window, like the image viewer: Space pause,
  ←/→ 5 s back / forward, M mute, O the browser, Esc close;
* a gifv (Mastodon's short silent "gif") loops in its card, muted, only while the
  card is on screen, at most a few at once;
* audio gets a small bar in its card: ▶/⏸ and a slider.

QtMultimedia is optional (Debian: python3-pyside6.qtmultimedia and
python3-pyside6.qtmultimediawidgets): without it — or with ui.video_player =
"browser" — everything opens in the browser as before.
"""

import functools
import logging
import os
import time

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSlider,
    QStyle,
    QStyleOptionSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...i18n import _
from ..richtext import plain_tip

log = logging.getLogger(__name__)

INFINITE = -1  # QMediaPlayer.Loops.Infinite as the int setLoops takes
MAX_LOOPS = 3      # gifvs playing at once (the ones on screen; the rest show a still)
VISIBLE_CHECK_MS = 600
FRAME_FPS = 12     # a gifv in a card: at most this many frames a second drawn
SEEK_MS = 5000


class SeekSlider(QSlider):
    """A time slider: a click anywhere goes there at once (a plain QSlider only steps a
    page towards the click), and the handle can be dragged on from there. seek(ms)."""
    seek = Signal(int)

    def __init__(self):
        super().__init__(Qt.Orientation.Horizontal)
        self.sliderMoved.connect(self.seek.emit)

    def value_at(self, x):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        groove = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt,
                                             QStyle.SubControl.SC_SliderGroove, self)
        handle = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt,
                                             QStyle.SubControl.SC_SliderHandle, self)
        span = max(1, groove.width() - handle.width())
        pos = int(x) - groove.x() - handle.width() // 2
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(),
                                              max(0, min(pos, span)), span,
                                              opt.upsideDown)

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled() and \
                self.maximum() > self.minimum():
            v = self.value_at(e.position().x())
            self.setValue(v)
            self.seek.emit(v)
        super().mousePressEvent(e)  # the handle is under the mouse now: drag on


HW_ENV = "QT_FFMPEG_DECODING_HW_DEVICE_TYPES"


def choose_decoding(how):
    """ui.video_decode, before the first player is made. "software": Qt's ffmpeg gets
    no hardware decoders at all — on some cards (NVIDIA: "cuvidCreateDecoder …
    CUDA_ERROR_INVALID_VALUE", "more than 32 decode surfaces") it tries one, fails and
    the video stutters, stalls or stays black; fediverse videos are small, the
    processor plays them easily. "hardware": as Qt likes. A variable already set
    in the environment by hand wins over both."""
    if how == "software" and HW_ENV not in os.environ:
        os.environ[HW_ENV] = "none"  # a name no decoder has: the list ends up empty
        log.info("video: software decoding (ui.video_decode)")


AV_LOG_FATAL = 8  # libavutil's log levels: what FFmpeg says goes to stderr from here up —
# not its errors either: a decoder trying the hardware first says "[h264] Failed setup for
# format vdpau…" at every video though it plays; a video that won't play is Qt's error
# (errorOccurred), in the log


@functools.cache
def _avutils():
    """The libavutil this process may use: Qt's own (the PySide wheel's), the system's."""
    import ctypes
    import ctypes.util
    import glob
    names = []
    try:
        import PySide6
        names += sorted(glob.glob(os.path.join(os.path.dirname(PySide6.__file__),
                                               "Qt", "lib", "libavutil.so*")))
    except ImportError:
        pass
    found = ctypes.util.find_library("avutil")
    if found:
        names.append(found)
    libs = []
    for name in names:
        try:
            libs.append(ctypes.CDLL(name).av_log_set_level)
        except (OSError, AttributeError) as e:
            log.debug("libavutil %s: %s", name, e)
    return tuple(libs)


def new_player(parent):
    """A QMediaPlayer, FFmpeg quieted once it is loaded (quiet_ffmpeg): every player of
    fedtail is made here."""
    from PySide6.QtMultimedia import QMediaPlayer
    player = QMediaPlayer(parent)
    quiet_ffmpeg()
    return player


def quiet_ffmpeg():
    """FFmpeg (Qt Multimedia's backend) says only what is fatal. By default it prints its
    warnings to stderr — for a looping gif with an old pixel format "[swscaler @ …]
    deprecated pixel format used" at every frame, the terminal flooded (29.10). Set in
    the libavutil this process loads (Qt's own, or the system's); FEDTAIL_FFMPEG_LOG=1
    lets it say everything. Qt sets FFmpeg's level as its plugin loads, with the first
    player: so again after each one is made (new_player). True if it took."""
    if os.environ.get("FEDTAIL_FFMPEG_LOG"):  # asked for by hand: FFmpeg says it all
        return False
    for set_level in _avutils():
        set_level(AV_LOG_FATAL)
    return bool(_avutils())


@functools.cache
def available():
    """Can this Qt play media at all (the modules are there)?"""
    try:
        from PySide6 import QtMultimedia, QtMultimediaWidgets  # noqa: F401
        return True
    except ImportError as e:
        log.info("no QtMultimedia (%s): video and audio open in the browser", e)
        return False


def install_hint():
    """The command that brings QtMultimedia here (deps.install_line), or its package."""
    from ... import deps
    need = [n for n in deps.NEEDS if n.key == "PySide6 QtMultimedia"]
    return deps.install_line(need) or "PySide6-Addons"


def inline_loop(label, m, fit):
    """A gifv looping in its card (InlineLoop) — or its still frame alone where this Qt
    has no QtMultimedia: asked here, at the first gifv, not at the window's start."""
    return InlineLoop(label, m, fit) if available() else None


def audio_bar(m):
    """An audio attachment's player in its card (AudioBar), or None where this Qt has no
    QtMultimedia (the card links the file then, as any other attachment)."""
    return AudioBar(m) if available() else None


def media_url(m):
    """A media attachment's file (fedtail.model Media)."""
    return m.url or m.remote_url


_cache = None  # the window's Images: videos kept on disk (ui.video_disk_mb)


def set_cache(images):
    global _cache
    _cache = images


def source(m):
    """What the player plays: the copy on disk if there is one (fetched ahead, or
    played before), else the server's — and then it's fetched to disk for next time."""
    from PySide6.QtCore import QUrl
    url = media_url(m)
    if _cache is not None and url:
        local = _cache.video_local(url)
        if local:
            log.info("video: from disk (%s)", m.kind)
            return QUrl.fromLocalFile(local)
        _cache.prefetch_video([url])
    return QUrl(url)


def _clock(ms):
    s = max(0, int(ms // 1000))
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else \
        f"{s // 60}:{s % 60:02d}"


BUTTONS_CSS = """
QToolButton { background: rgba(0, 0, 0, 120); color: rgba(255, 255, 255, 210);
    border: 1px solid rgba(255, 255, 255, 60); border-radius: 8px; padding: 7px 14px; }
QToolButton:hover { background: rgba(255, 255, 255, 45); color: white; }
QLabel { color: rgba(255, 255, 255, 210); }
"""


class VideoOverlay(QWidget):
    """A video over the main window, with sound and the usual keys."""

    def __init__(self, window, ctx, m, loop=False, items=None):
        from PySide6.QtMultimedia import QAudioOutput
        from PySide6.QtMultimediaWidgets import QVideoWidget
        super().__init__(window)
        self.win, self.ctx, self.m = window, ctx, m
        self.items = [x for x in (items or [m])]
        self.i = next((n for n, x in enumerate(self.items) if x is m or x == m), 0)
        if not self.items or self.items[self.i] != m:
            self.items, self.i = [m], 0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(BUTTONS_CSS)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 16)
        lay.setSpacing(10)
        top = QHBoxLayout()
        self.counter = QLabel()
        top.addStretch(1)
        if len(self.items) > 1:  # several in the post: go between them right here
            top.addWidget(self.counter)
            top.addWidget(self._button("‹", _("player_prev_tip"), lambda: self.go(-1)))
            top.addWidget(self._button("›", _("player_next_tip"), lambda: self.go(1)))
        if ctx.save_image:
            top.addWidget(self._button("⤓", _("save_media") + " (S)", self.save))
        top.addWidget(self._button("↗", _("open_browser") + " (O)", self.to_browser))
        top.addWidget(self._button("✕", _("close") + " (Esc)", self.close_player))
        lay.addLayout(top)
        self.video = QVideoWidget()
        self.video.setStyleSheet("background: black;")
        lay.addWidget(self.video, 1)
        self.problem = QLabel()
        self.problem.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.problem.hide()
        lay.addWidget(self.problem)
        bar = QHBoxLayout()
        self.btn = self._button("⏸", _("player_pause_tip"), self.toggle)
        bar.addWidget(self.btn)
        self.slider = SeekSlider()
        self.slider.seek.connect(lambda v: self.player.setPosition(v))
        bar.addWidget(self.slider, 1)
        self.time = QLabel("0:00")
        bar.addWidget(self.time)
        self.mute = self._button("🔊", _("player_mute_tip"), self.toggle_mute)
        bar.addWidget(self.mute)
        lay.addLayout(bar)
        desc = m.alt.replace("\n", " ")
        cap = QLabel(desc)  # the alt text; changes as I go between the post's videos
        cap.setTextFormat(Qt.TextFormat.PlainText)  # someone else's words, never HTML
        cap.setWordWrap(True)
        cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cap.setVisible(bool(desc))
        lay.addWidget(cap)
        self.desc_label = cap
        keys = QLabel(_("player_keys"))
        keys.setAlignment(Qt.AlignmentFlag.AlignCenter)
        keys.setStyleSheet("color: rgba(255, 255, 255, 110);")  # as faint as the viewer's
        lay.addWidget(keys)
        self.keys = keys

        self.player = new_player(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        self.gif = loop
        if loop:
            # a gif: just the picture, big and looping — no player bar, no sound;
            # a click anywhere or Esc closes it, as in the image viewer
            self.player.setLoops(INFINITE)
            self.audio.setMuted(True)
            for w in (self.btn, self.slider, self.time, self.mute):
                w.hide()
        self._hint()
        self.player.durationChanged.connect(lambda d: self.slider.setRange(0, int(d)))
        self.player.positionChanged.connect(self._position)
        self.player.errorOccurred.connect(self._error)
        self.player.playbackStateChanged.connect(self._state)
        window.installEventFilter(self)
        self.setGeometry(window.rect())
        self.show()
        self.raise_()
        self.setFocus()
        self._start()

    def _hint(self):
        many = len(self.items) > 1
        key = ("gif_keys" if self.gif else "player_keys") + ("_many" if many else "")
        self.keys.setText(_(key))
        self.counter.setText(f"{self.i + 1} / {len(self.items)}" if many else "")

    def _start(self):
        m = self.m
        log.info("video: playing in the window (%s, %d of %d)", m.kind, self.i + 1,
                 len(self.items))
        self.problem.hide()
        self.player.setSource(source(m))
        self.player.play()

    def go(self, step):
        """The next (or previous) video or gif of the post, in this same overlay."""
        if len(self.items) < 2:
            return
        self.i = (self.i + step) % len(self.items)
        self.m = self.items[self.i]
        self.gif = self.m.kind == "gifv"
        self.player.stop()
        self.player.setLoops(INFINITE if self.gif else 1)
        self.audio.setMuted(self.gif)
        self.mute.setText("🔇" if self.gif else "🔊")
        for w in (self.btn, self.slider, self.time, self.mute):
            w.setVisible(not self.gif)
        desc = self.m.alt.replace("\n", " ")
        self.desc_label.setText(desc)
        self.desc_label.setVisible(bool(desc))
        self._hint()
        self._start()

    def wheelEvent(self, e):
        if self.gif and len(self.items) > 1:  # as in the picture viewer: wheel goes on
            self.go(1 if e.angleDelta().y() < 0 else -1)
            e.accept()
        else:
            super().wheelEvent(e)

    def _button(self, text, tip, fn):
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.clicked.connect(fn)
        return b

    def paintEvent(self, _e):
        QPainter(self).fillRect(self.rect(), QColor(0, 0, 0, 225))

    def eventFilter(self, obj, e):
        if obj is self.win and e.type() == QEvent.Type.Resize:
            self.setGeometry(self.win.rect())
        return False

    def _position(self, pos):
        if not self.slider.isSliderDown():
            self.slider.setValue(int(pos))
        self.time.setText(f"{_clock(pos)} / {_clock(self.player.duration())}")

    def _state(self, _s):
        from PySide6.QtMultimedia import QMediaPlayer
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        self.btn.setText("⏸" if playing else "▶")

    def _error(self, _err, text=""):
        log.warning("video: %s", text or self.player.errorString())
        self.problem.setText(_("player_failed", err=text or self.player.errorString()))
        self.problem.show()

    def toggle(self):
        from PySide6.QtMultimedia import QMediaPlayer
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def toggle_mute(self):
        self.audio.setMuted(not self.audio.isMuted())
        self.mute.setText("🔇" if self.audio.isMuted() else "🔊")

    def to_browser(self):
        self.player.pause()
        self.ctx.open_url(media_url(self.m))

    def close_player(self):
        self.player.stop()
        self.player.setSource(QUrl())
        self.win.removeEventFilter(self)
        self.hide()
        self.deleteLater()

    def mousePressEvent(self, e):
        if self.gif:
            self.close_player()
        else:
            super().mousePressEvent(e)

    def keyPressEvent(self, e):
        k = e.key()
        if k == Qt.Key.Key_Escape:
            self.close_player()
        elif k in (Qt.Key.Key_PageDown, Qt.Key.Key_N) or \
                (self.gif and k in (Qt.Key.Key_Right, Qt.Key.Key_Space)):
            self.go(1)
        elif k in (Qt.Key.Key_PageUp, Qt.Key.Key_P, Qt.Key.Key_Backspace) or \
                (self.gif and k == Qt.Key.Key_Left):
            self.go(-1)
        elif k in (Qt.Key.Key_Space, Qt.Key.Key_K):
            self.toggle()
        elif k == Qt.Key.Key_Left:
            self.player.setPosition(max(0, self.player.position() - SEEK_MS))
        elif k == Qt.Key.Key_Right:
            self.player.setPosition(self.player.position() + SEEK_MS)
        elif k == Qt.Key.Key_M:
            self.toggle_mute()
        elif k == Qt.Key.Key_O:
            self.to_browser()
        elif k == Qt.Key.Key_S:
            self.save()
        else:
            super().keyPressEvent(e)

    def save(self):
        if self.ctx.save_image:
            self.win.statusBar().showMessage(_("saving"), 30000)
            self.ctx.save_image(self.m)


class _Loops:
    """The gifvs playing now, oldest first: no more than MAX_LOOPS at once."""
    playing = []

    @classmethod
    def start(cls, loop):
        if loop in cls.playing:
            return
        while len(cls.playing) >= MAX_LOOPS:
            cls.playing[0].pause()
        cls.playing.append(loop)

    @classmethod
    def stop(cls, loop):
        if loop in cls.playing:
            cls.playing.remove(loop)


class InlineLoop(QObject):
    """A gifv looping in its card, muted, drawn into the card's picture label — only
    while the label is on screen (checked twice a second), the still frame otherwise."""

    def __init__(self, label, m, fit):
        """fit(QPixmap) -> the pixmap as the card shows pictures (size, corners)."""
        from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
        super().__init__(label)
        self.label, self.m, self.fit = label, m, fit
        self._last_frame, self._slow, self.too_slow = 0.0, 0, False
        self.player = None
        self.sink = None
        self._QMediaPlayer, self._QVideoSink = QMediaPlayer, QVideoSink
        self.timer = QTimer(self)
        self.timer.setInterval(VISIBLE_CHECK_MS)
        self.timer.timeout.connect(self._check)
        self.timer.start()
        label.destroyed.connect(self._gone)

    def _on_screen(self):
        try:
            return self.label.isVisible() and not self.label.visibleRegion().isEmpty() and \
                self.label.window().isVisible() and not self.label.window().isMinimized()
        except RuntimeError:  # the card is gone
            return False

    def _check(self):
        if self._on_screen() and not self.too_slow:
            self.play()
        elif self.player is not None:
            self.pause()

    def play(self):
        if self.player is None:
            self.player = new_player(self)
            self.sink = self._QVideoSink(self)
            self.player.setVideoSink(self.sink)
            self.player.setLoops(INFINITE)
            self.sink.videoFrameChanged.connect(self._frame)
            self.player.errorOccurred.connect(
                lambda _e, t="": (log.info("gifv: %s", t or self.player.errorString()),
                                  self.timer.stop()))
            self.player.setSource(source(self.m))
        if self.player.playbackState() != self._QMediaPlayer.PlaybackState.PlayingState:
            _Loops.start(self)
            self.player.play()

    def pause(self):
        _Loops.stop(self)
        if self.player is not None:
            self.player.pause()

    def _frame(self, frame):
        # every frame came to the GUI thread whole: converted, scaled, rounded — 0.6–1.7 s
        # stalls a frame on the night of 22.10 (software decoding). A card's loop is a
        # preview: at most FRAME_FPS, and made small before anything else is done to it
        now = time.monotonic()
        if now - self._last_frame < 1.0 / FRAME_FPS:
            return
        self._last_frame = now
        img = frame.toImage()
        if img.isNull():
            return
        try:
            ratio = self.label.devicePixelRatioF() or 1.0
            w, h = int(self.label.width() * ratio), int(self.label.height() * ratio)
            if w > 0 and h > 0 and (img.width() > 2 * w or img.height() > 2 * h):
                img = img.scaled(2 * w, 2 * h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                 Qt.TransformationMode.FastTransformation)
            self.label.setPixmap(self.fit(QPixmap.fromImage(img)))
        except RuntimeError:
            self._gone()
        took = time.monotonic() - now
        if took > 0.1:  # still dear here: fewer frames for this one
            self._slow += 1
            if self._slow >= 3:
                log.info("gifv: a frame takes %.0f ms — this one stays still", took * 1000)
                self.too_slow = True  # a click still opens it in the player
                self.pause()
        else:
            self._slow = 0

    def _gone(self, *_a):
        _Loops.stop(self)
        self.timer.stop()
        if self.player is not None:
            try:
                self.player.stop()
            except RuntimeError:
                pass


def stop_all(window):
    """Every video and looping gif of the window stopped, before the window is restyled
    and its cards let go: a theme tried with a gif still decoding in a card (its player
    deleted with the card mid-frame) took the whole program down (23.10, juick-classic)."""
    for loop in list(_Loops.playing):
        loop._gone()
    for loop in window.findChildren(InlineLoop):
        loop._gone()
        if loop.player is not None:
            try:
                loop.player.setSource(QUrl())
            except RuntimeError:
                pass
    for overlay in window.findChildren(VideoOverlay):
        try:
            overlay.close_player()
        except RuntimeError:
            pass


class AudioBar(QWidget):
    """▶/⏸, a slider and the time: an audio attachment played in its card."""

    def __init__(self, m):
        super().__init__()
        self.m = m
        self.player = None
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        self.btn = QToolButton()
        self.btn.setText("▶")
        self.btn.setAutoRaise(True)
        self.btn.setToolTip(plain_tip(_("media_audio") + (": " + m.alt if m.alt else "")))
        self.btn.clicked.connect(self.toggle)
        h.addWidget(self.btn)
        self.slider = SeekSlider()
        self.slider.setEnabled(False)
        h.addWidget(self.slider, 1)
        self.time = QLabel("🎵 " + _("media_audio"))
        self.time.setObjectName("muted")
        h.addWidget(self.time)

    def toggle(self):
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        if self.player is None:
            self.player = new_player(self)
            self.out = QAudioOutput(self)
            self.player.setAudioOutput(self.out)
            self.player.durationChanged.connect(lambda d: self.slider.setRange(0, int(d)))
            self.player.positionChanged.connect(self._position)
            self.player.errorOccurred.connect(
                lambda _e, t="": self.time.setText(_("player_failed",
                                                     err=t or self.player.errorString())))
            self.slider.seek.connect(lambda v: self.player.setPosition(v))
            self.slider.setEnabled(True)
            self.player.setSource(source(self.m))
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
            self.btn.setText("▶")
        else:
            self.player.play()
            self.btn.setText("⏸")

    def _position(self, pos):
        if not self.slider.isSliderDown():
            self.slider.setValue(int(pos))
        self.time.setText(f"{_clock(pos)} / {_clock(self.player.duration())}")

    def hideEvent(self, e):
        # out of sight (another lane, a closed tab): no sound from nowhere
        if self.player is not None and not self.window().isMinimized():
            self.player.pause()
            self.btn.setText("▶")
        super().hideEvent(e)
