"""Writing a post or a reply. Drafts are saved as you type."""

from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
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

from ...core.model import VISIBILITIES, real, reply_mentions, snippet
from ...i18n import _
from .text import display_name, esc

MEDIA_FILTER = "*.jpg *.jpeg *.png *.gif *.webp *.avif *.mp4 *.webm *.mov *.mp3 *.ogg"


class Compose(QDialog):
    def __init__(self, win, reply_to=None):
        super().__init__(win)
        self.win, self.core = win, win.core
        self.reply_to = real(reply_to) if reply_to else None
        self.key = self.core.draft_key(self.reply_to["id"] if self.reply_to else None)
        self.sent = False
        self.setWindowTitle(_("compose_reply") if reply_to else _("compose_new"))
        lay = QVBoxLayout(self)

        if self.reply_to:
            q = QLabel(f"↪ <b>{display_name(self.reply_to['account'])}</b>: "
                       f"{esc(snippet(self.reply_to, 400))}")
            q.setWordWrap(True)
            q.setObjectName("ctx")
            lay.addWidget(q)

        self.cw = QLineEdit()
        self.cw.setPlaceholderText(_("cw_placeholder"))
        lay.addWidget(self.cw)

        self.text = QPlainTextEdit()
        self.text.setPlaceholderText(_("text_placeholder_md") if self.core.markdown
                                     else _("text_placeholder"))
        lay.addWidget(self.text, 1)

        self.media = QListWidget()
        self.media.setMaximumHeight(90)
        self.media.setToolTip(_("media_tip"))
        self.media.itemDoubleClicked.connect(self.edit_description)
        lay.addWidget(self.media)

        row = QHBoxLayout()
        self.vis = QComboBox()
        for v in VISIBILITIES:
            self.vis.addItem(_("vis_" + v), v)
        row.addWidget(self.vis)
        add = QPushButton(QIcon.fromTheme("mail-attachment"), _("attach"))
        add.clicked.connect(self.attach)
        row.addWidget(add)
        rm = QPushButton(_("detach"))
        rm.clicked.connect(self.detach)
        row.addWidget(rm)
        row.addStretch(1)
        self.counter = QLabel()
        row.addWidget(self.counter)
        close_btn = QPushButton(_("close"))
        close_btn.setToolTip(_("close_tip"))
        close_btn.clicked.connect(self.reject)
        row.addWidget(close_btn)
        self.discard_btn = QPushButton(_("discard"))
        self.discard_btn.clicked.connect(self.discard)
        row.addWidget(self.discard_btn)
        self.send_btn = QPushButton(_("send"))
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

    # ---- media --------------------------------------------------------------------
    def _media_list(self):
        out = []
        for i in range(self.media.count()):
            it = self.media.item(i)
            out.append([it.data(Qt.ItemDataRole.UserRole), it.data(Qt.ItemDataRole.UserRole + 1)])
        return out

    def _add_media(self, path, desc=""):
        it = QListWidgetItem()
        it.setData(Qt.ItemDataRole.UserRole, path)
        it.setData(Qt.ItemDataRole.UserRole + 1, desc)
        self._label_item(it)
        self.media.addItem(it)

    def _label_item(self, it):
        name = Path(it.data(Qt.ItemDataRole.UserRole)).name
        desc = it.data(Qt.ItemDataRole.UserRole + 1)
        it.setText(f"{name} — {desc}" if desc else f"{name} — {_('no_alt')}")

    def attach(self):
        left = self.core.caps.max_media - self.media.count()
        if left <= 0:
            self.hint.setText(_("media_limit", n=self.core.caps.max_media))
            return
        last = self.core.get_state("last_media_dir", str(Path.home()))
        paths, _f = QFileDialog.getOpenFileNames(self, _("attach"), last,
                                                 f"{_('media_files')} ({MEDIA_FILTER});;* (*)")
        for p in paths[:left]:
            self._add_media(p)
        if paths:
            self.core.set_state("last_media_dir", str(Path(paths[0]).parent))
            self._changed()

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
        self.counter.setStyleSheet("color: #d33" if n > lim else "")

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
