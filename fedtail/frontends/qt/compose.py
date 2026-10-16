"""Writing a post or a reply. Drafts are saved as you type."""

from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

from ...core.hashtags import flat_tags
from ...core.model import VISIBILITIES, real, reply_mentions, snippet
from ...i18n import _
from .text import display_name, esc

MEDIA_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".heic",
             ".mp4", ".webm", ".mov", ".mp3", ".ogg", ".m4a", ".flac")
MEDIA_FILTER = " ".join("*" + e for e in MEDIA_EXT)


def media_paths(mime):
    """Local media files in a drag or the clipboard (Dolphin, browser, file dialog)."""
    out = []
    if mime.hasUrls():
        for url in mime.urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(MEDIA_EXT):
                out.append(url.toLocalFile())
    return out


def save_image(core, image):
    """A picture without a file (a screenshot, an image from a web page): keep it
    as PNG next to the profile's data, so the draft can refer to it."""
    folder = core.paths.data_dir / "attachments"
    folder.mkdir(exist_ok=True)
    path = folder / f"pasted-{datetime.now():%Y%m%d-%H%M%S-%f}.png"
    return str(path) if image.save(str(path), "PNG") else None


class Compose(QDialog):
    def __init__(self, win, reply_to=None, attach=(), text=""):
        super().__init__(win)
        self.win, self.core = win, win.core
        self.reply_to = real(reply_to) if reply_to else None
        self.key = self.core.draft_key(self.reply_to["id"] if self.reply_to else None)
        self.start_text = text  # "@someone " from a profile's Mention button
        self.sent = False
        self.setWindowTitle(_("compose_reply") if reply_to else _("compose_new"))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)

        if self.reply_to:
            q = QLabel(f"↑ <b>{display_name(self.reply_to['account'])}</b>: "
                       f"{esc(snippet(self.reply_to, 400))}")
            q.setWordWrap(True)
            q.setObjectName("ctx")
            lay.addWidget(q)

        self.cw = QLineEdit()
        self.cw.setPlaceholderText(_("cw_placeholder"))
        self.cw.setVisible(False)
        lay.addWidget(self.cw)

        self.text = QPlainTextEdit()
        # pictures dropped or pasted into the text become attachments
        self.text.installEventFilter(self)
        self.text.viewport().installEventFilter(self)
        self.setAcceptDrops(True)
        self.text.setPlaceholderText(_("text_placeholder_md") if self.core.markdown
                                     else _("text_placeholder"))
        lay.addWidget(self.text, 1)
        self.camel = QLabel()
        self.camel.setObjectName("counter")
        self.camel.setWordWrap(True)
        self.camel.hide()
        lay.addWidget(self.camel)

        self.media = QListWidget()
        self.media.setObjectName("mediaList")
        self.media.setViewMode(QListWidget.ViewMode.IconMode)
        self.media.setIconSize(QSize(72, 72))
        self.media.setMovement(QListWidget.Movement.Static)
        self.media.setWrapping(False)
        self.media.setFixedHeight(112)
        self.media.setVisible(False)
        self.media.setToolTip(_("media_tip"))
        self.media.itemDoubleClicked.connect(self.edit_description)
        lay.addWidget(self.media)

        row = QHBoxLayout()
        self.vis = QComboBox()
        self.vis.setMinimumWidth(230)
        for v in VISIBILITIES:
            self.vis.addItem(_("vis_" + v), v)
        row.addWidget(self.vis)
        add = QPushButton(QIcon.fromTheme("mail-attachment"), _("attach"))
        add.setObjectName("tool")
        add.clicked.connect(self.attach)
        row.addWidget(add)
        self.cw_btn = QPushButton("⚠ " + _("cw_add"))
        self.cw_btn.setObjectName("tool")
        self.cw_btn.setCheckable(True)
        self.cw_btn.setToolTip(_("cw_add_tip"))
        self.cw_btn.toggled.connect(self._toggle_cw)
        row.addWidget(self.cw_btn)
        rm = QPushButton(_("detach"))
        rm.setObjectName("tool")
        self.detach_btn = rm
        rm.clicked.connect(self.detach)
        row.addWidget(rm)
        row.addStretch(1)
        self.counter = QLabel()
        self.counter.setObjectName("counter")
        row.addWidget(self.counter)
        close_btn = QPushButton(_("close"))
        close_btn.setObjectName("tool")
        close_btn.setToolTip(_("close_tip"))
        close_btn.clicked.connect(self.reject)
        row.addWidget(close_btn)
        self.discard_btn = QPushButton(_("discard"))
        self.discard_btn.setObjectName("tool")
        self.discard_btn.clicked.connect(self.discard)
        row.addWidget(self.discard_btn)
        self.send_btn = QPushButton(_("send"))
        self.send_btn.setObjectName("primary")
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self.send)
        row.addWidget(self.send_btn)
        lay.addLayout(row)

        self.hint = QLabel()
        self.hint.setObjectName("muted")
        lay.addWidget(self.hint)

        for seq in ("Ctrl+Return", "Ctrl+Enter"):
            QShortcut(QKeySequence(seq), self).activated.connect(self.send)

        self._autosave = QTimer(self, singleShot=True, interval=700)
        self._autosave.timeout.connect(self.save_draft)
        self._load()
        if self.cw.text() or self.core.cfg["post"]["cw_field"]:
            self.cw_btn.setChecked(True)
        if attach:
            self.add_paths(attach)
        self.text.textChanged.connect(self._changed)
        self.cw.textChanged.connect(self._changed)
        self.vis.currentIndexChanged.connect(self._changed)
        self._count()
        self.resize(720, 500)
        self.text.setFocus()
        cur = self.text.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        self.text.setTextCursor(cur)

    # ---- drafts -------------------------------------------------------------------
    def _load(self):
        d = self.core.get_draft(self.key)
        vis = self.core.reply_visibility(self.reply_to)
        if d:
            self.text.setPlainText(d.get("text", ""))
            self.cw.setText(d.get("cw", ""))
            vis = d.get("visibility", vis)
            for path, desc in d.get("media", []):
                if Path(path).exists():
                    self._add_media(path, desc)
            self.hint.setText(_("draft_restored"))
        else:
            if self.start_text:
                self.text.setPlainText(self.start_text)
            if self.reply_to:
                self.text.setPlainText(reply_mentions(self.reply_to, self.core.me["acct"]))
                if self.reply_to.get("spoiler_text"):
                    self.cw.setText(self.reply_to["spoiler_text"])
        self.vis.setCurrentIndex(VISIBILITIES.index(vis) if vis in VISIBILITIES else 2)
        self.initial = self._snapshot()

    def _snapshot(self):
        return {"text": self.text.toPlainText(), "cw": self.cw.text(),
                "visibility": self.vis.currentData(), "media": self._media_list()}

    def _changed(self):
        self._count()
        self._autosave.start()

    def save_draft(self):
        if self.sent:
            return
        snap = self._snapshot()
        if snap == self.initial and not self.core.get_draft(self.key):
            return
        if not snap["text"].strip() and not snap["media"] and not snap["cw"]:
            self.core.delete_draft(self.key)
            return
        self.core.save_draft(self.key, snap)
        if self.core.cfg["post"]["drafts_autosave"]:
            self.hint.setText(_("draft_saved"))

    def discard(self):
        if QMessageBox.question(self, _("discard_q_title"), _("discard_q")) \
                == QMessageBox.StandardButton.Yes:
            self.core.delete_draft(self.key)
            self.sent = True  # nothing to keep
            self._leave()

    def _toggle_cw(self, on):
        self.cw.setVisible(on)
        if on:
            self.cw.setFocus()
        elif self.cw.text():
            self.cw.clear()  # hiding the field drops the warning
            self.text.setFocus()

    # ---- drag & drop, paste -----------------------------------------------------------
    def _accepts(self, mime):
        return bool(media_paths(mime)) or mime.hasImage()

    def _take(self, mime):
        paths = media_paths(mime)
        if not paths and mime.hasImage():
            img = QImage(mime.imageData())
            saved = save_image(self.core, img) if not img.isNull() else None
            paths = [saved] if saved else []
        if paths:
            self.add_paths(paths)
        return bool(paths)

    def eventFilter(self, obj, e):
        t = e.type()
        if t in (QEvent.Type.DragEnter, QEvent.Type.DragMove) and self._accepts(e.mimeData()):
            e.acceptProposedAction()
            return True
        if t == QEvent.Type.Drop and self._accepts(e.mimeData()):
            e.acceptProposedAction()
            self._take(e.mimeData())
            return True
        if t == QEvent.Type.KeyPress and e.matches(QKeySequence.StandardKey.Paste):
            mime = QGuiApplication.clipboard().mimeData()
            if (media_paths(mime) or (mime.hasImage() and not mime.hasText())) and \
                    self._take(mime):
                return True
        return super().eventFilter(obj, e)

    def dragEnterEvent(self, e):
        if self._accepts(e.mimeData()):
            e.acceptProposedAction()

    def dropEvent(self, e):
        if self._take(e.mimeData()):
            e.acceptProposedAction()

    # ---- media --------------------------------------------------------------------
    def _media_list(self):
        out = []
        for i in range(self.media.count()):
            it = self.media.item(i)
            out.append([it.data(Qt.ItemDataRole.UserRole), it.data(Qt.ItemDataRole.UserRole + 1)])
        return out

    def add_paths(self, paths):
        known = {m[0] for m in self._media_list()}
        paths = [p for p in paths if p not in known]
        left = self.core.caps.max_media - self.media.count()
        if len(paths) > left:
            self.hint.setText(_("media_limit", n=self.core.caps.max_media))
        for p in paths[:max(left, 0)]:
            self._add_media(p)
        if paths:
            self._changed()

    def _add_media(self, path, desc=""):
        it = QListWidgetItem(QIcon(path), "")
        it.setData(Qt.ItemDataRole.UserRole, path)
        it.setData(Qt.ItemDataRole.UserRole + 1, desc)
        self._label_item(it)
        self.media.addItem(it)

    def _label_item(self, it):
        name = Path(it.data(Qt.ItemDataRole.UserRole)).name
        desc = it.data(Qt.ItemDataRole.UserRole + 1)
        it.setText(_("alt_set") if desc else _("no_alt"))
        it.setToolTip(f"{name}\n{desc}" if desc else f"{name}\n{_('media_tip')}")

    def attach(self):
        left = self.core.caps.max_media - self.media.count()
        if left <= 0:
            self.hint.setText(_("media_limit", n=self.core.caps.max_media))
            return
        last = self.core.get_state("last_media_dir", str(Path.home()))
        paths, _f = QFileDialog.getOpenFileNames(self, _("attach"), last,
                                                 f"{_('media_files')} ({MEDIA_FILTER});;* (*)")
        if paths:
            self.core.set_state("last_media_dir", str(Path(paths[0]).parent))
            self.add_paths(paths)

    def detach(self):
        for it in self.media.selectedItems():
            self.media.takeItem(self.media.row(it))
        self._changed()

    def edit_description(self, it):
        desc, ok = QInputDialog.getMultiLineText(
            self, _("alt_title"), _("alt_prompt"), it.data(Qt.ItemDataRole.UserRole + 1) or "")
        if ok:
            it.setData(Qt.ItemDataRole.UserRole + 1, desc.strip())
            self._label_item(it)
            self._changed()

    # ---- sending --------------------------------------------------------------------
    def _count(self):
        n = len(self.text.toPlainText()) + len(self.cw.text())
        lim = self.core.caps.max_characters
        self.counter.setText(f"{n} / {lim}")
        over = "true" if n > lim else "false"
        if self.counter.property("over") != over:
            self.counter.setProperty("over", over)
            self.counter.style().unpolish(self.counter)
            self.counter.style().polish(self.counter)
        if self.core.cfg["post"]["camelcase_hint"]:
            flat = flat_tags(self.text.toPlainText())
            self.camel.setVisible(bool(flat))
            if flat:
                self.camel.setText(_("camel_hint", tags=", ".join("#" + t for t in flat[:3])))
        has_media = self.media.count() > 0
        self.media.setVisible(has_media)
        self.detach_btn.setVisible(has_media)

    def send(self):
        text = self.text.toPlainText().strip()
        media = [tuple(m) for m in self._media_list()]
        if not text and not media:
            return
        self.save_draft()  # whatever happens next, the text is safe
        self.send_btn.setEnabled(False)
        self.send_btn.setText(_("sending"))
        fut = self.core.post(text, self.vis.currentData(),
                             self.reply_to["id"] if self.reply_to else None,
                             self.cw.text().strip(), media, draft_key=self.key)
        self.win.bridge.call(fut, ok=self._sent, fail=self._failed)

    def _sent(self, st):
        self.sent = True
        try:
            self.core.delete_draft(self.key)
            self.win.after_post(st, self.reply_to)
        finally:
            self._leave()

    def _failed(self, err):
        self.send_btn.setEnabled(True)
        self.send_btn.setText(_("send"))
        QMessageBox.warning(self, _("send_failed"), _("send_failed_text", err=err))

    # Every way out (Esc, the window's X, Close, after sending) goes through
    # reject(): QDialog.closeEvent itself calls reject(), so reject() must
    # never call close() again — that loop is what kept the window stuck.
    def reject(self):
        if not self.sent and self.send_btn.isEnabled():
            if self.core.cfg["post"]["drafts_autosave"]:
                self.save_draft()
            elif self._snapshot() != self.initial and self.text.toPlainText().strip():
                if QMessageBox.question(self, _("discard_q_title"), _("discard_q")) \
                        != QMessageBox.StandardButton.Yes:
                    return
        # still sending? fine: the core drops the draft once the post is out
        self._leave()

    def _leave(self):
        self._autosave.stop()
        super().reject()  # hides the dialog
        self.deleteLater()
