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

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ...i18n import _

log = logging.getLogger(__name__)

INFINITE = -1  # QMediaPlayer.Loops.Infinite as the int setLoops takes
MAX_LOOPS = 3      # gifvs playing at once (the ones on screen; the rest show a still)
VISIBLE_CHECK_MS = 600
SEEK_MS = 5000


@functools.cache
def available():
    """Can this Qt play media at all (the modules are there)?"""
    try:
        from PySide6 import QtMultimedia, QtMultimediaWidgets  # noqa: F401
        return True
    except ImportError as e:
        log.info("no QtMultimedia (%s): video and audio open in the browser", e)
        return False


def media_url(m):
    return m.get("url") or m.get("remote_url") or ""


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

    def __init__(self, window, ctx, m, loop=False):
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        from PySide6.QtMultimediaWidgets import QVideoWidget
        super().__init__(window)
        self.win, self.ctx, self.m = window, ctx, m
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setStyleSheet(BUTTONS_CSS)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 16)
        lay.setSpacing(10)
        top = QHBoxLayout()
        top.addStretch(1)
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
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(lambda v: self.player.setPosition(v))
        bar.addWidget(self.slider, 1)
        self.time = QLabel("0:00")
        bar.addWidget(self.time)
        self.mute = self._button("🔊", _("player_mute_tip"), self.toggle_mute)
        bar.addWidget(self.mute)
        lay.addLayout(bar)
        desc = (m.get("description") or "").replace("\n", " ")
        if desc:
            cap = QLabel(desc)
            cap.setWordWrap(True)
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(cap)
        keys = QLabel(_("player_keys"))
        keys.setAlignment(Qt.AlignmentFlag.AlignCenter)
        keys.setStyleSheet("color: #888;")
        lay.addWidget(keys)

        self.player = QMediaPlayer(self)
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
            keys.setText(_("gif_keys"))
        self.player.durationChanged.connect(lambda d: self.slider.setRange(0, int(d)))
        self.player.positionChanged.connect(self._position)
        self.player.errorOccurred.connect(self._error)
        self.player.playbackStateChanged.connect(self._state)
        window.installEventFilter(self)
        self.setGeometry(window.rect())
        self.show()
        self.raise_()
        self.setFocus()
        log.info("video: playing in the window (%s)", m.get("type"))
        self.player.setSource(QUrl(media_url(m)))
        self.player.play()

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
        else:
            super().keyPressEvent(e)


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
        if self._on_screen():
            self.play()
        elif self.player is not None:
            self.pause()

    def play(self):
        if self.player is None:
            self.player = self._QMediaPlayer(self)
            self.sink = self._QVideoSink(self)
            self.player.setVideoSink(self.sink)
            self.player.setLoops(INFINITE)
            self.sink.videoFrameChanged.connect(self._frame)
            self.player.errorOccurred.connect(
                lambda _e, t="": (log.info("gifv: %s", t or self.player.errorString()),
                                  self.timer.stop()))
            self.player.setSource(QUrl(media_url(self.m)))
        if self.player.playbackState() != self._QMediaPlayer.PlaybackState.PlayingState:
            _Loops.start(self)
            self.player.play()

    def pause(self):
        _Loops.stop(self)
        if self.player is not None:
            self.player.pause()

    def _frame(self, frame):
        img = frame.toImage()
        if img.isNull():
            return
        try:
            self.label.setPixmap(self.fit(QPixmap.fromImage(img)))
        except RuntimeError:
            self._gone()

    def _gone(self, *_a):
        _Loops.stop(self)
        self.timer.stop()
        if self.player is not None:
            try:
                self.player.stop()
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
        self.btn.setToolTip(_("media_audio") + (": " + m["description"]
                                                if m.get("description") else ""))
        self.btn.clicked.connect(self.toggle)
        h.addWidget(self.btn)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setEnabled(False)
        h.addWidget(self.slider, 1)
        self.time = QLabel("🎵 " + _("media_audio"))
        self.time.setObjectName("muted")
        h.addWidget(self.time)

    def toggle(self):
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
        if self.player is None:
            self.player = QMediaPlayer(self)
            self.out = QAudioOutput(self)
            self.player.setAudioOutput(self.out)
            self.player.durationChanged.connect(lambda d: self.slider.setRange(0, int(d)))
            self.player.positionChanged.connect(self._position)
            self.player.errorOccurred.connect(
                lambda _e, t="": self.time.setText(_("player_failed",
                                                     err=t or self.player.errorString())))
            self.slider.sliderMoved.connect(lambda v: self.player.setPosition(v))
            self.slider.setEnabled(True)
            self.player.setSource(QUrl(media_url(self.m)))
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
