"""Avatars and thumbnails for the Qt window: common/images.py's cache, with Qt's
pictures — decoded to a QImage in the workers (QImage is fine outside the GUI thread),
a QPixmap for the widgets."""

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QTimer
from PySide6.QtGui import QImage, QImageReader, QPixmap

from ..common import images as common
from ..common.images import (  # noqa: F401  (Qt's names for them)
    FEED_SIDE,
    MEDIA_SCHEMES,
    MEM_MB,
    ORIGINAL_MAX,
    PICTURE_MAX,
    SAVE_MAX,
    VIDEO_MAX,
    _short,
    _where,
)


def decode(data, max_side, fmt=None):
    """The picture in data, already no bigger than max_side: the decoder makes it small
    (a JPEG is read at a fraction of its size) instead of decoding all of a 4000-px
    photo and shrinking it after — less time, less memory, the GUI thread waits less.
    fmt: read as that format only — Qt doesn't go asking every plugin installed
    (core/imagesniff.py says why)."""
    if fmt is None:
        from ...core import imagesniff
        fmt, _why = imagesniff.readable(data)
        if fmt is None:
            return QImage()
    name = fmt.encode()
    if name not in {bytes(f) for f in QImageReader.supportedImageFormats()}:
        return QImage()  # no plugin for it here (qt6-image-formats-plugins)
    buf = QBuffer()
    buf.setData(QByteArray(data))
    buf.open(QIODevice.OpenModeFlag.ReadOnly)
    reader = QImageReader(buf, name)
    reader.setDecideFormatFromContent(False)
    reader.setAutoDetectImageFormat(False)
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > max_side:
        reader.setScaledSize(size.scaled(max_side, max_side,
                                         Qt.AspectRatioMode.KeepAspectRatio))
    img = reader.read()
    if img.isNull():  # some plugins can't read scaled: the plain way, the same format
        img = QImage.fromData(data, fmt)
    return img


class Images(common.Cache):
    FORMAT_HINT = "Qt can't show this format (qt6-image-formats-plugins?)"

    def decode(self, data, max_side, fmt=None):
        img = decode(data, max_side, fmt)
        if img.isNull():
            return None
        if max(img.width(), img.height()) > max_side:  # read the plain way: big
            img = img.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        return img

    def size(self, picture):
        return picture.width(), picture.height()

    def to_screen(self, picture):
        return QPixmap.fromImage(picture)

    def later(self, ms, fn):
        QTimer.singleShot(int(ms), fn)

    def _ready(self, key, img):
        if img is not None and img.isNull():  # (a null QImage handed in: none)
            img = None
        super()._ready(key, img)
