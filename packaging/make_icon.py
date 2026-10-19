"""fedtail.png (or an .svg) → fedtail.ico (16…256 px) for the Windows build. Needs
PySide6."""

import sys
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

SIZES = (16, 24, 32, 48, 64, 128, 256)


def png(renderer, side):
    if isinstance(renderer, QImage):  # a picture: scaled down smoothly
        img = renderer.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio,
                              Qt.TransformationMode.SmoothTransformation)
    else:
        img = QImage(QSize(side, side), QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        renderer.render(p)
        p.end()
    buf = QByteArray()
    io = QBuffer(buf)
    io.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(io, "PNG")
    return bytes(buf)


def ico(images):
    """An .ico of PNG images (Windows Vista and later read those)."""
    head = (0).to_bytes(2, "little") + (1).to_bytes(2, "little") + len(images).to_bytes(2, "little")
    entries, data, offset = b"", b"", 6 + 16 * len(images)
    for side, blob in images:
        s = 0 if side >= 256 else side
        entries += bytes([s, s, 0, 0]) + (1).to_bytes(2, "little") + (32).to_bytes(2, "little") \
            + len(blob).to_bytes(4, "little") + offset.to_bytes(4, "little")
        data += blob
        offset += len(blob)
    return head + entries + data


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    QGuiApplication.instance() or QGuiApplication([])
    r = QSvgRenderer(str(src)) if src.suffix == ".svg" else QImage(str(src))
    out.write_bytes(ico([(s, png(r, s)) for s in SIZES]))
    print("icon", out, out.stat().st_size, "bytes")


if __name__ == "__main__":
    main()
