"""Writing a post or a reply. Drafts are saved as you type."""

import logging
import re
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, QStringListModel, Qt, QTimer
from PySide6.QtGui import QGuiApplication, QIcon, QImage, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QCompleter,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ...core.hashtags import flat_tags
from ...core.model import VISIBILITIES, real, reply_mentions, snippet
from ...i18n import _
from .text import display_name, esc

MEDIA_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".heic",
             ".mp4", ".webm", ".mov", ".mp3", ".ogg", ".m4a", ".flac")
MEDIA_FILTER = " ".join("*" + e for e in MEDIA_EXT)

log = logging.getLogger(__name__)



def fit_for_server(path, caps, folder):
    """A picture bigger than the server takes (caps.image_bytes, caps.image_pixels) as a
    smaller copy, so it isn't refused after the upload: scaled down to the pixel limit,
    saved as JPEG (PNG when it has transparency) until it's under the size. Anything
    else — a video, a picture that fits, a server that doesn't say — goes as it is."""
    import os

    from PySide6.QtGui import QImage, QImageReader
    max_b, max_px = int(caps.image_bytes or 0), int(caps.image_pixels or 0)
    if not max_b and not max_px or str(path).lower().endswith((".gif", ".webp")):
        return path  # nothing said; or it may move: never flatten an animation
    reader = QImageReader(str(path))
    if not reader.canRead():
        return path
    size = reader.size()
    big_px = max_px and size.isValid() and size.width() * size.height() > max_px
    big_b = max_b and os.path.getsize(path) > max_b
    if not big_px and not big_b:
        return path
    img = QImage(str(path))
    if img.isNull():
        return path
    if big_px:
        k = (max_px / float(img.width() * img.height())) ** 0.5 * 0.98
        img = img.scaled(int(img.width() * k), int(img.height() * k),
                         Qt.AspectRatioMode.KeepAspectRatio,
                         Qt.TransformationMode.SmoothTransformation)
    alpha = img.hasAlphaChannel()
    out = Path(folder) / ("upload-" + Path(path).stem + (".png" if alpha else ".jpg"))
    quality = 90
    while True:
        img.save(str(out), "PNG" if alpha else "JPG", -1 if alpha else quality)
        if not max_b or out.stat().st_size <= max_b or quality <= 40:
            break
        if alpha:  # a PNG can't get lighter by quality: smaller instead
            img = img.scaled(int(img.width() * 0.8), int(img.height() * 0.8),
                             Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        else:
            quality -= 15
    log.info("compose: %s made to fit the server: %dx%d, %d KB → %dx%d, %d KB", Path(path).name,
             size.width(), size.height(), os.path.getsize(path) // 1024, img.width(),
             img.height(), out.stat().st_size // 1024)
    return str(out)

def media_paths(mime):
    """Local media files in a drag or the clipboard (Dolphin, browser, file dialog)."""
    out = []
    if mime.hasUrls():
        for url in mime.urls():
            if url.isLocalFile() and url.toLocalFile().lower().endswith(MEDIA_EXT):
                out.append(str(Path(url.toLocalFile())))  # C:\\… on Windows, not C:/…
    return out


def save_image(core, image):
    """A picture without a file (a screenshot, an image from a web page): keep it
    as PNG next to the profile's data, so the draft can refer to it."""
    folder = core.paths.data_dir / "attachments"
    folder.mkdir(exist_ok=True)
    path = folder / f"pasted-{datetime.now():%Y%m%d-%H%M%S-%f}.png"
    return str(path) if image.save(str(path), "PNG") else None



OTHER_LANG = "\x00other"
BIG_PCT = 90  # the ⤢ button: this share of the main window
# languages Qt has no name of their own for
LANG_NAMES = {"tok": "toki pona", "jbo": "la .lojban.", "eo": "Esperanto",
              "ia": "Interlingua", "vo": "Volapük", "ie": "Interlingue"}


def _lang_label(code, qlocale):
    name = LANG_NAMES.get(code) or qlocale(code).nativeLanguageName()
    if not name or (qlocale(code).language() == qlocale.Language.C and code != "c"):
        name = LANG_NAMES.get(code, code)
    return f"{name[:1].upper()}{name[1:]} ({code})"

class Compose(QDialog):
    def __init__(self, win, reply_to=None, attach=(), text="", edit=None, quote=None,
                 invite=False):
        """invite: "Call into the thread" — a reply to reply_to that is only "@" at first,
        the people list open: the one named gets a notification and the thread with it."""
        super().__init__(win)
        self.win, self.core = win, win.core
        self.edit = real(edit) if edit else None  # my post being corrected
        self.reply_to = real(reply_to) if reply_to else None
        self.quote = real(quote) if quote else None  # the post this one quotes
        self.invite = bool(invite and self.reply_to)
        if self.edit:
            self.key = f"edit:{self.edit['id']}"
        elif self.invite:  # not the reply's draft: a call has its own
            self.key = f"invite:{self.reply_to['id']}"
        else:
            self.key = self.core.draft_key(self.reply_to["id"] if self.reply_to else None,
                                           self.quote["id"] if self.quote else None)
        self.start_text = text  # "@someone " from a profile's Mention button
        self.sent = False
        title = _("compose_edit") if edit else _("compose_invite") if self.invite else \
            _("compose_reply") if reply_to else _("compose_quote") if quote else _("compose_new")
        self.setWindowTitle(title)
        # ui.compose = "inline": a panel inside the main window, not a window of its own.
        # A new window can come up with another keyboard layout (KDE keeps one per
        # window): typing on in Russian you'd get Latin letters. Inside, it stays.
        self.inline = win.cfg["ui"]["compose"] == "inline"
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 12)
        lay.setSpacing(10)
        if self.inline:
            old = getattr(win, "inline_compose", None)
            try:
                if old is not None and old.isVisible():
                    old.reject()  # one panel at a time; its text stays a draft
            except RuntimeError:  # already gone
                pass
            win.inline_compose = self
            self.setWindowFlags(Qt.WindowType.Widget)
            self.setObjectName("composePanel")
            self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            # the title strip (shape.header_stripes: point.im's hatched band)
            head_box = QWidget(self)
            head_box.setObjectName("composeHead")
            head_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            top = QHBoxLayout(head_box)
            top.setContentsMargins(10, 6, 6, 6)
            # bigger / smaller (⤡) at the top left, as ✕ is at the top right
            self.size_btn = QPushButton("⤡")
            self.size_btn.setObjectName("tool")
            self.size_btn.setToolTip(_("compose_bigger_tip"))
            self.size_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.size_btn.clicked.connect(self._toggle_big)
            top.addWidget(self.size_btn)
            head = QLabel(title)
            head.setObjectName("laneTitle")
            top.addWidget(head, 1)
            close = QPushButton("✕")
            close.setObjectName("tool")
            close.setToolTip(_("close_tip") + " (Esc)")
            close.setCursor(Qt.CursorShape.PointingHandCursor)
            close.clicked.connect(self.reject)
            top.addWidget(close)
            lay.addWidget(head_box)
            win.installEventFilter(self)

        if self.reply_to:
            q = QLabel(f"↑ <b>{display_name(self.reply_to['account'])}</b>: "
                       f"{esc(snippet(self.reply_to, 400))}")
            q.setWordWrap(True)
            q.setObjectName("ctx")
            lay.addWidget(q)
        if self.quote:
            q = QLabel(f"❝ <b>{display_name(self.quote['account'])}</b>: "
                       f"{esc(snippet(self.quote, 400))}")
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
        # "#ge" offers the tags already in use: #georgia, #GeorgiaNews…
        self._tag_model = QStringListModel(self)
        self.tag_completer = QCompleter(self._tag_model, self)
        self.tag_completer.setWidget(self.text)
        self.tag_completer.setCompletionMode(QCompleter.CompletionMode.UnfilteredPopupCompletion)
        self.tag_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.tag_completer.activated.connect(self._put_tag)
        self.text.textChanged.connect(self._suggest_tags)
        self._people_query = ""
        self._people_timer = QTimer(self, singleShot=True, interval=350)
        self._people_timer.timeout.connect(self._ask_server_people)
        self.core.prepare_tags()
        self.core.prepare_people()
        if self.core.cfg["post"].get("complete_emoji", True):
            self.core.prepare_emoji()
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
        self._build_poll(lay)

        row = QHBoxLayout()
        self.vis = QComboBox()
        self.vis.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        for v in VISIBILITIES:
            self.vis.addItem(_("vis_" + v), v)
        row.addWidget(self.vis)
        self.lang = QComboBox()
        self.lang.setToolTip(_("lang_tip"))
        self.lang.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self._fill_languages()
        row.addWidget(self.lang)
        add = QPushButton(QIcon.fromTheme("mail-attachment"), _("attach"))
        self.attach_btn = add
        add.setObjectName("tool")
        add.clicked.connect(self.attach)
        row.addWidget(add)
        if self.edit:  # an edit changes words; pictures and who sees it stay as they were
            add.setEnabled(False)
            add.setToolTip(_("edit_media_kept"))
            self.setAcceptDrops(False)
        self.cw_btn = QPushButton("⚠ " + _("cw_add"))
        self.cw_btn.setObjectName("tool")
        self.cw_btn.setCheckable(True)
        self.cw_btn.setToolTip(_("cw_add_tip"))
        self.cw_btn.toggled.connect(self._toggle_cw)
        row.addWidget(self.cw_btn)
        self.poll_btn = QPushButton("📊 " + _("poll_add"))
        self.poll_btn.setObjectName("tool")
        self.poll_btn.setCheckable(True)
        self.poll_btn.setToolTip(_("poll_add_tip"))
        self.poll_btn.toggled.connect(self._toggle_poll)
        self.poll_btn.setVisible(not self.edit)
        row.addWidget(self.poll_btn)
        self.sensitive_btn = QPushButton("🔞 " + _("sensitive_mark"))
        self.sensitive_btn.setObjectName("tool")
        self.sensitive_btn.setCheckable(True)
        self.sensitive_btn.setToolTip(_("sensitive_mark_tip"))
        self.sensitive_btn.setVisible(False)
        self.sensitive_btn.toggled.connect(lambda _on: self._changed())
        row.addWidget(self.sensitive_btn)
        rm = QPushButton(_("detach"))
        rm.setObjectName("tool")
        self.detach_btn = rm
        rm.clicked.connect(self.detach)
        row.addWidget(rm)
        row.addStretch(1)
        self.counter = QLabel()
        self.counter.setObjectName("counter")
        row.addWidget(self.counter)
        lay.addLayout(row)
        # what the post is (above) and what to do with it (below): two rows, so nothing
        # gets squeezed into "ontent war" in a narrow window
        row = QHBoxLayout()
        self.hint = QLabel()
        self.hint.setObjectName("muted")
        self.hint.setWordWrap(True)
        row.addWidget(self.hint, 1)
        close_btn = QPushButton(_("close"))
        close_btn.setObjectName("tool")
        close_btn.setToolTip(_("close_tip"))
        close_btn.clicked.connect(self.reject)
        row.addWidget(close_btn)
        self.discard_btn = QPushButton(_("discard"))
        self.discard_btn.setObjectName("tool")
        self.discard_btn.clicked.connect(self.discard)
        row.addWidget(self.discard_btn)
        self.later_btn = QPushButton("⏰ " + _("schedule"))
        self.later_btn.setObjectName("tool")
        self.later_btn.setToolTip(_("schedule_tip"))
        self.later_btn.clicked.connect(self.ask_schedule)
        self.later_btn.setVisible(not self.edit and self.core.cfg["post"].get("schedule", True))
        row.addWidget(self.later_btn)
        if self.core.cfg["post"].get("preview", True):
            pv = QPushButton("👁 " + _("preview"))
            pv.setObjectName("tool")
            pv.setToolTip(_("preview_tip"))
            pv.clicked.connect(self.preview)
            row.addWidget(pv)
        self.send_btn = QPushButton(_("send"))
        self.send_btn.setObjectName("primary")
        self.send_btn.setDefault(True)
        self.send_btn.clicked.connect(self.send)
        row.addWidget(self.send_btn)
        lay.addLayout(row)

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
        pct = self._size_pct()
        if pct and not self.inline:  # a window of its own: the same share of the main one
            self.resize(int(win.width() * pct / 100), int(win.height() * pct / 100))
        else:
            self.resize(720, 500)
        if self.inline:
            self._place()
        self.text.setFocus()
        cur = self.text.textCursor()
        cur.movePosition(cur.MoveOperation.End)
        self.text.setTextCursor(cur)
        if self.invite and self.text.toPlainText() == "@":  # who to call: the list at once
            QTimer.singleShot(0, self._suggest_tags)

    def _fill_languages(self):
        """"As in settings" first, then post.languages, then post.language if it's
        not among them — each by its own name (Русский, ქართული…)."""
        from PySide6.QtCore import QLocale
        cfg = self.core.cfg["post"]
        added = list(self.core.get_state("languages_added", []) or [])
        codes = list(dict.fromkeys(cfg["languages"] + ([cfg["language"]] if cfg["language"]
                                                       else []) + added))
        self.lang.addItem(_("lang_default"), "")
        for code in codes:
            self.lang.addItem(_lang_label(code, QLocale), code)
        # one more at the bottom: any language by its code, kept for the next posts
        self.lang.addItem(_("lang_other"), OTHER_LANG)
        self.set_language(cfg["language"])
        self._lang_before = self.lang.currentIndex()
        self.lang.activated.connect(self._lang_picked)

    def _language(self):
        code = self.lang.currentData()
        return "" if code == OTHER_LANG else code

    def _lang_picked(self, i):
        if self.lang.itemData(i) != OTHER_LANG:
            self._lang_before = i
            return
        from PySide6.QtCore import QLocale
        from PySide6.QtWidgets import QInputDialog
        code, ok = QInputDialog.getText(self, _("lang_other_title"), _("lang_other_ask"))
        code = (code or "").strip().lower()
        if not ok or not re.fullmatch(r"[a-z]{2,3}(-[a-z0-9]{2,8})?", code):
            self.lang.setCurrentIndex(self._lang_before)
            return
        if self.lang.findData(code) < 0:
            self.lang.insertItem(self.lang.count() - 1, _lang_label(code, QLocale), code)
            added = list(self.core.get_state("languages_added", []) or [])
            if code not in added:
                self.core.set_state("languages_added", added + [code])
                log.info("compose: language %s added to the list", code)
        self.set_language(code)
        self._lang_before = self.lang.currentIndex()

    def set_language(self, code):
        i = self.lang.findData(code or "")
        if i < 0 and code:
            self.lang.addItem(code, code)
            i = self.lang.count() - 1
        self.lang.setCurrentIndex(max(i, 0))

    # ---- drafts -------------------------------------------------------------------
    def _load(self):
        if self.edit:
            self._load_edit()
            return
        d = self.core.get_draft(self.key)
        vis = self.core.reply_visibility(self.reply_to)
        if d:
            self.text.setPlainText(d.get("text", ""))
            self.cw.setText(d.get("cw", ""))
            vis = d.get("visibility", vis)
            if "language" in d:
                self.set_language(d["language"])
            for path, desc, *focus in d.get("media", []):
                if Path(path).exists():
                    self._add_media(path, desc, focus[0] if focus else None)
            self.sensitive_btn.setChecked(bool(d.get("sensitive")))
            poll = d.get("poll")
            if poll:
                self.poll_btn.setChecked(True)
                for e, text in zip(self.poll_options, poll.get("options", []), strict=False):
                    e.setText(text)
                i = self.poll_time.findData(poll.get("expires_in"))
                if i >= 0:
                    self.poll_time.setCurrentIndex(i)
                self.poll_multiple.setChecked(bool(poll.get("multiple")))
            self.hint.setText(_("draft_restored"))
        else:
            if self.start_text:
                self.text.setPlainText(self.start_text)
            if self.invite:  # only the one called: the thread's people aren't bothered
                self.text.setPlainText("@")
                self.hint.setText(_("invite_hint"))
                if self.reply_to.get("spoiler_text"):
                    self.cw.setText(self.reply_to["spoiler_text"])
            elif self.reply_to:
                self.text.setPlainText(reply_mentions(self.reply_to, self.core.me["acct"]))
                if self.reply_to.get("spoiler_text"):
                    self.cw.setText(self.reply_to["spoiler_text"])
        self.vis.setCurrentIndex(VISIBILITIES.index(vis) if vis in VISIBILITIES else 2)
        self.initial = self._snapshot()

    def _load_edit(self):
        v = self.edit.get("visibility", "private")
        self.vis.setCurrentIndex(VISIBILITIES.index(v) if v in VISIBILITIES else 2)
        self.set_language(self.edit.get("language") or "")
        self.lang.setEnabled(False)
        self.vis.setEnabled(False)
        self.vis.setToolTip(_("edit_media_kept"))
        d = self.core.get_draft(self.key)
        if d:
            self.text.setPlainText(d.get("text", ""))
            self.cw.setText(d.get("cw", ""))
            self.hint.setText(_("draft_restored"))
            self.initial = self._snapshot()
            return
        self.text.setEnabled(False)
        self.hint.setText(_("loading"))

        def got(src):
            self.text.setEnabled(True)
            self.text.setPlainText(src.get("text", ""))
            self.cw.setText(src.get("spoiler_text", ""))
            if self.cw.text():
                self.cw_btn.setChecked(True)
            self.hint.setText(_("edit_hint"))
            self.initial = self._snapshot()
            self.text.setFocus()
        self.initial = self._snapshot()
        self.win.bridge.call(self.core.source(self.edit), ok=got,
                             fail=lambda e: (self.text.setEnabled(True),
                                             self.hint.setText(_("load_failed", err=e))))

    def _snapshot(self):
        return {"text": self.text.toPlainText(), "cw": self.cw.text(),
                "visibility": self.vis.currentData(), "media": self._media_list(),
                "language": self._language(),
                "sensitive": self.sensitive_btn.isChecked(), "poll": self.poll_data()}

    # ---- a poll -------------------------------------------------------------------
    POLL_TIMES = [(300, "poll_5m"), (1800, "poll_30m"), (3600, "poll_1h"), (21600, "poll_6h"),
                  (86400, "poll_1d"), (259200, "poll_3d"), (604800, "poll_7d")]

    def _build_poll(self, lay):
        self.poll_box = QWidget()
        self.poll_box.setObjectName("pollEditor")
        v = QVBoxLayout(self.poll_box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self.poll_options = []
        for i in range(max(2, self.core.caps.max_poll_options)):
            e = QLineEdit()
            e.setPlaceholderText(_("poll_option", n=i + 1))
            e.textChanged.connect(lambda _t: self._changed())
            v.addWidget(e)
            self.poll_options.append(e)
        h = QHBoxLayout()
        self.poll_time = QComboBox()
        for secs, key in self.POLL_TIMES:
            self.poll_time.addItem(_(key), secs)
        self.poll_time.setCurrentIndex(4)  # a day
        self.poll_time.currentIndexChanged.connect(lambda _i: self._changed())
        h.addWidget(self.poll_time)
        self.poll_multiple = QCheckBox(_("poll_several"))
        self.poll_multiple.toggled.connect(lambda _on: self._changed())
        h.addWidget(self.poll_multiple)
        h.addStretch(1)
        v.addLayout(h)
        self.poll_box.setVisible(False)
        lay.addWidget(self.poll_box)

    def _toggle_poll(self, on):
        self.poll_box.setVisible(on)
        if on:
            self.poll_options[0].setFocus()
        self._media_or_poll()
        self._changed()

    def _media_or_poll(self):
        """A server takes pictures or a poll, not both: one closes the other's door."""
        if not hasattr(self, "sensitive_btn"):
            return  # still being built
        has_media = bool(self._media_list())
        self.poll_btn.setEnabled(not has_media and not self.edit)
        self.sensitive_btn.setVisible(has_media)
        if getattr(self, "attach_btn", None) is not None:
            self.attach_btn.setEnabled(not self.poll_btn.isChecked() and not self.edit)

    def poll_data(self):
        if not getattr(self, "poll_btn", None) or not self.poll_btn.isChecked():
            return None
        options = [e.text().strip() for e in self.poll_options if e.text().strip()]
        if len(options) < 2:
            return None
        return {"options": options, "expires_in": self.poll_time.currentData(),
                "multiple": self.poll_multiple.isChecked()}

    def _changed(self):
        self._count()
        self._media_or_poll()
        self._autosave.start()

    # ---- completing #tags and @people -----------------------------------------------
    _TOKEN_AT_END = re.compile(r"(?:^|[\s(«\"'])([#@:])(\w[\w.@-]*)$")

    def _token_at_cursor(self):
        """("#" or "@", the word typed right before the cursor) — or (None, None)."""
        cur = self.text.textCursor()
        before = cur.block().text()[:cur.positionInBlock()]
        m = self._TOKEN_AT_END.search(before)
        if not m or (m.group(1) in "#:" and not re.fullmatch(r"\w+", m.group(2))):
            return None, None
        if m.group(1) == ":" and len(m.group(2)) < 2:
            return None, None
        return m.group(1), m.group(2)

    # (kept for the name the tests know it by)
    def _tag_at_cursor(self):
        sigil, word = self._token_at_cursor()
        return word if sigil == "#" else None

    def _suggest_tags(self):
        """Offer what fits the #tag or @name being typed (post.complete_tags,
        post.complete_mentions); for a name, the server is asked too, a moment later."""
        sigil, word = self._token_at_cursor()
        post = self.core.cfg["post"]
        items = []
        if sigil == "#" and post.get("complete_tags", True):
            items = [("#" + n, "#" + n) for n in self.core.tag_suggestions(word)]
        elif sigil == "@" and post.get("complete_mentions", True):
            items = self._people_items(self.core.mention_suggestions(word))
            if len(word) >= 2:
                self._people_query = word
                self._people_timer.start()
        elif sigil == ":" and post.get("complete_emoji", True):
            items = [(f":{code}:", f":{code}:") for code, _e in self.core.emoji_suggestions(word)]
        self._offer(items, sigil, word)

    def _people_items(self, people):
        return [("@" + acct, f"@{acct}" + (f" — {name}" if name else "")) for acct, name in people]

    def _ask_server_people(self):
        word = self._people_query

        def got(found):
            sigil, now = self._token_at_cursor()
            if sigil != "@" or now != word:
                return  # typed on meanwhile
            local = self.core.mention_suggestions(word)
            seen = {a.casefold() for a, _n in local}
            more = [(a, n) for a, n in found if a.casefold() not in seen]
            self._offer(self._people_items(local + more)[:10], "@", word)
        self.win.bridge.call(self.core.search_people(word), ok=got, fail=lambda _e: None)

    def _offer(self, items, sigil, word):
        popup = self.tag_completer.popup()
        if not items or (len(items) == 1 and items[0][0][1:].casefold() == (word or "").casefold()):
            popup.hide()
            return
        self._inserts = {label: insert for insert, label in items}
        self._tag_model.setStringList([label for _i, label in items])
        rect = self.text.cursorRect()
        rect.setWidth(popup.sizeHintForColumn(0) + popup.verticalScrollBar().sizeHint().width()
                      + 16)
        self.tag_completer.complete(rect)
        popup.setCurrentIndex(self._tag_model.index(0))

    def _put_tag(self, label):
        sigil, word = self._token_at_cursor()
        if word is None:
            return
        cur = self.text.textCursor()
        cur.movePosition(cur.MoveOperation.Left, cur.MoveMode.KeepAnchor, len(word) + 1)
        cur.insertText(getattr(self, "_inserts", {}).get(label, label) + " ")
        self.text.setTextCursor(cur)
        self.tag_completer.popup().hide()

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
        if self.inline and obj is self.win and t == QEvent.Type.Resize:
            self._place()  # the panel follows the window
            return False
        if t in (QEvent.Type.DragEnter, QEvent.Type.DragMove) and self._accepts(e.mimeData()):
            e.acceptProposedAction()
            return True
        if t == QEvent.Type.Drop and self._accepts(e.mimeData()):
            e.acceptProposedAction()
            self._take(e.mimeData())
            return True
        if t == QEvent.Type.KeyPress and obj is self.text and \
                self.tag_completer.popup().isVisible() and e.key() in (
                    Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Tab, Qt.Key.Key_Escape,
                    Qt.Key.Key_Backtab):
            return True  # the list of tags takes these
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
            entry = [it.data(Qt.ItemDataRole.UserRole), it.data(Qt.ItemDataRole.UserRole + 1)]
            focus = it.data(Qt.ItemDataRole.UserRole + 2)
            if focus:
                entry.append(list(focus))
            out.append(entry)
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

    def _add_media(self, path, desc="", focus=None):
        it = QListWidgetItem(QIcon(path), "")
        it.setData(Qt.ItemDataRole.UserRole, path)
        it.setData(Qt.ItemDataRole.UserRole + 1, desc)
        it.setData(Qt.ItemDataRole.UserRole + 2, list(focus) if focus else None)
        self._label_item(it)
        self.media.addItem(it)
        self._media_or_poll()

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
        """The picture's description and (post.focus_point) its focus point: a click on
        the picture puts the cross where the main thing is."""
        from .focus import FocusDialog
        dlg = FocusDialog(self, it.data(Qt.ItemDataRole.UserRole),
                          it.data(Qt.ItemDataRole.UserRole + 1) or "",
                          it.data(Qt.ItemDataRole.UserRole + 2),
                          with_focus=self.core.cfg["post"].get("focus_point", True))

        def done():
            it.setData(Qt.ItemDataRole.UserRole + 1, dlg.description())
            it.setData(Qt.ItemDataRole.UserRole + 2, dlg.focus)
            self._label_item(it)
            self._changed()
        dlg.accepted.connect(done)
        self.focus_dialog = dlg
        dlg.open()
        return dlg

    # ---- preview ----------------------------------------------------------------------
    def preview(self):
        """How it will look: Markdown made into text the way a Markdown server does (when
        this one is), the CW, who sees it, each post of a chain, the pictures; Send or
        back to editing from here."""
        from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser

        from ...core.model import chain_parts
        text = self.text.toPlainText().strip()
        parts = chain_parts(text) if self.core.cfg["post"].get("chain", True) else [text]
        parts = parts or [text]
        dlg = QDialog(self)
        dlg.setWindowTitle(_("preview"))
        dlg.resize(min(720, self.win.width() - 80), min(600, self.win.height() - 80))
        lay = QVBoxLayout(dlg)
        head = " · ".join(x for x in (
            self.vis.currentText(), self.lang.currentText() if self._language() else "",
            _("chain_count", n=len(parts)) if len(parts) > 1 else "",
            _("preview_media", n=self.media.count()) if self.media.count() else "",
            _("preview_md") if self.core.markdown else _("preview_plain")) if x)
        info = QLabel(head)
        info.setObjectName("meta")
        info.setWordWrap(True)
        lay.addWidget(info)
        for i, part in enumerate(parts):
            if self.cw.text().strip():
                cw = QLabel("⚠ " + esc(self.cw.text().strip()))
                cw.setWordWrap(True)
                lay.addWidget(cw)
            view = QTextBrowser()
            view.setOpenExternalLinks(False)
            if self.core.markdown:
                view.setMarkdown(part)
            else:
                view.setPlainText(part)
            lay.addWidget(view, 1)
            if i < len(parts) - 1:
                lay.addWidget(QLabel("↳"))
        box = QDialogButtonBox()
        send = box.addButton(_("send"), QDialogButtonBox.ButtonRole.AcceptRole)
        box.addButton(_("preview_back"), QDialogButtonBox.ButtonRole.RejectRole)
        box.rejected.connect(dlg.reject)
        send.clicked.connect(lambda: (dlg.accept(), self.send()))
        lay.addWidget(box)
        dlg.open()
        return dlg

    # ---- sending --------------------------------------------------------------------
    def _count(self):
        from ...core.model import chain_parts
        lim = self.core.caps.max_characters
        parts = chain_parts(self.text.toPlainText()) \
            if self.core.cfg["post"].get("chain", True) else []
        if len(parts) > 1:  # a chain: each part counts on its own
            n = max(len(x) for x in parts) + len(self.cw.text())
            self.counter.setText(_("chain_count", n=len(parts)) + f" · {n} / {lim}")
        else:
            n = len(self.text.toPlainText()) + len(self.cw.text())
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

    def ask_schedule(self):
        """When to send it: the server keeps the post and sends it then."""
        from PySide6.QtCore import QDateTime
        from PySide6.QtWidgets import QDateTimeEdit, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle(_("schedule"))
        v = QVBoxLayout(dlg)
        when = QDateTimeEdit(QDateTime.currentDateTime().addSecs(3600))
        when.setCalendarPopup(True)
        when.setMinimumDateTime(QDateTime.currentDateTime().addSecs(300))
        when.setDisplayFormat("dd.MM.yyyy HH:mm")
        v.addWidget(QLabel(_("schedule_when")))
        v.addWidget(when)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        ok = buttons.addButton(_("schedule_ok"), QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setObjectName("primary")
        buttons.rejected.connect(dlg.reject)
        ok.clicked.connect(dlg.accept)
        v.addWidget(buttons)
        self.schedule_dialog = dlg
        dlg.accepted.connect(lambda: self.send(
            scheduled_at=when.dateTime().toUTC().toString("yyyy-MM-ddTHH:mm:ss.zzzZ")))
        dlg.open()
        return dlg

    def send(self, scheduled_at=None, alt_checked=False):
        text = self.text.toPlainText().strip()
        media = [tuple(m) for m in self._media_list()]
        if self.core.cfg["post"].get("resize_images", True):
            media = [(fit_for_server(m[0], self.core.caps, self.core.paths.cache_dir),) +
                     tuple(m[1:]) for m in media]
        if not text and not media:
            return
        bare = [i for i in range(self.media.count())
                if not self.media.item(i).data(Qt.ItemDataRole.UserRole + 1)]
        if bare and not alt_checked and not self.edit and \
                self.core.cfg["post"].get("alt_reminder", True):
            self._ask_alt(bare, scheduled_at)
            return
        self.save_draft()  # whatever happens next, the text is safe
        log.info("send: %s, reply to %s, %s, language %s, %d chars, %d pictures",
                 "edit" if self.edit else "post", self.reply_to["id"] if self.reply_to else "-",
                 self.vis.currentData(), self._language() or "-", len(text), len(media))
        self.send_btn.setEnabled(False)
        self.send_btn.setText(_("sending"))
        if self.edit:
            fut = self.core.edit(self.edit, text, self.cw.text().strip(), draft_key=self.key)
            self.win.bridge.call(fut, ok=self._edited, fail=self._failed)
            return
        fut = self.core.post(text, self.vis.currentData(),
                             self.reply_to["id"] if self.reply_to else None,
                             self.cw.text().strip(), media, draft_key=self.key,
                             language=self._language(),
                             sensitive=self.sensitive_btn.isChecked(), poll=self.poll_data(),
                             quote=self.quote["id"] if self.quote else None,
                             scheduled_at=scheduled_at)
        self.win.bridge.call(fut, ok=self._sent, fail=self._failed)

    def _ask_alt(self, bare, scheduled_at):
        """post.alt_reminder: a picture without a description — describe it, or send as is."""
        box = QMessageBox(QMessageBox.Icon.Question, _("alt_missing_title"),
                          _("alt_missing", n=len(bare)), parent=self)
        describe = box.addButton(_("alt_describe"), QMessageBox.ButtonRole.AcceptRole)
        anyway = box.addButton(_("alt_send_anyway"), QMessageBox.ButtonRole.DestructiveRole)
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.setDefaultButton(describe)

        def done(button):
            if button is describe:
                self.edit_description(self.media.item(bare[0]))
            elif button is anyway:
                self.send(scheduled_at, alt_checked=True)
        box.buttonClicked.connect(done)
        self.alt_box = box
        box.open()
        return box

    def _sent(self, st):
        self.sent = True
        try:
            self.core.delete_draft(self.key)
            if st.get("scheduled"):
                self.win.statusBar().showMessage(
                    _("scheduled_msg", when=self.win.theme.date(st.get("scheduled_at", ""))),
                    8000)
                return
            self.win.after_post(st, self.reply_to)
        finally:
            self._leave()

    def _edited(self, st):
        self.sent = True
        self.core.delete_draft(self.key)
        self.win.statusBar().showMessage(_("edited_msg"), 4000)
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

    # ---- the inline panel: over the lanes, in the middle, following the window ------
    def _size_pct(self):
        """How big, in % of the main window: the ⤢ choice if made, else ui.compose_size
        (0: as before — at most 820 × 540)."""
        big = self.core.get_state("compose_big")
        if big:
            return BIG_PCT
        if big is False:
            return 0
        return min(100, int(self.win.cfg["ui"].get("compose_size", 0) or 0))

    def _toggle_big(self):
        self.core.set_state("compose_big", not self._size_pct())
        self._place()

    def _place(self):
        win = self.win
        pct = self._size_pct()
        if pct:
            w = max(420, int(win.width() * pct / 100) - 20)
            h = max(320, int(win.height() * pct / 100) - 20)
        else:
            w = min(820, max(420, win.width() - 80))
            h = min(540, max(320, win.height() - 120))
        x = max(10, (win.width() - w) // 2)
        y = max(10, (win.height() - h) // 2)
        self.setGeometry(x, y, w, h)
        self.raise_()

    def showEvent(self, e):
        super().showEvent(e)
        if self.inline:
            self._place()
            self.text.setFocus()

    def _leave(self):
        self._autosave.stop()
        if self.inline:
            self.win.removeEventFilter(self)
        super().reject()  # hides the dialog
        self.deleteLater()
