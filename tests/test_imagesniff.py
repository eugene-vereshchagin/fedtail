"""Pictures sniffed before any decoder sees them (core/imagesniff.py): the format by
its first bytes, a file cut short by a flaky connection told apart — so that no plugin
of the toolkit goes guessing on bytes that aren't its own (the crash of 28.10)."""

import io
import struct
import unittest

from fedtail.core import imagesniff as s


def _picture(fmt):
    """An 8×8 red picture in fmt: by Pillow, else by Qt (the CI's Windows and Debian
    jobs have one of them only); neither — the test is skipped."""
    try:
        from PIL import Image
        out = io.BytesIO()
        Image.new("RGB", (8, 8), "red").save(out, fmt.upper())
        return out.getvalue()
    except ImportError:
        pass
    try:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice
        from PySide6.QtGui import QColor, QImage
    except ImportError:
        raise unittest.SkipTest("needs Pillow or PySide6") from None
    img = QImage(8, 8, QImage.Format.Format_RGB32)
    img.fill(QColor("red"))
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, fmt.upper())
    buf.close()
    return bytes(data)


def png():
    return _picture("png")


def jpeg():
    return _picture("jpeg")


class SniffTest(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(s.sniff(png()), "png")
        self.assertEqual(s.sniff(jpeg()), "jpeg")
        self.assertEqual(s.sniff(b"GIF89a" + bytes(20)), "gif")
        self.assertEqual(s.sniff(b"RIFF\x10\x00\x00\x00WEBPVP8 "), "webp")
        self.assertEqual(s.sniff(b"\x00\x00\x00\x1cftypavif" + bytes(16)), "avif")
        self.assertEqual(s.sniff(b"\x00\x00\x00\x1cftypisom" + bytes(16)), None)  # a video
        self.assertEqual(s.sniff(b"<html><body>404</body></html>"), None)
        self.assertEqual(s.sniff(b""), None)

    def test_cut_short(self):
        for data in (png(), jpeg()):
            self.assertEqual(s.readable(data)[0], s.sniff(data))
            self.assertEqual(s.readable(data[:len(data) // 2]), (None, "cut short"))
        webp = b"RIFF" + struct.pack("<I", 100) + b"WEBPVP8 " + bytes(40)
        self.assertFalse(s.whole(webp, "webp"))
        self.assertTrue(s.whole(webp + bytes(60), "webp"))
        box = struct.pack(">I", 24) + b"ftypavif" + bytes(12)
        self.assertTrue(s.whole(box, "avif"))
        self.assertFalse(s.whole(box + struct.pack(">I", 4000) + b"mdat" + bytes(10), "avif"))
        self.assertEqual(s.readable(b"junk"), (None, "not a picture"))


class QtDecodeTest(unittest.TestCase):
    def test_only_the_named_format(self):
        try:
            from PySide6.QtWidgets import QApplication
        except ImportError:
            self.skipTest("no Qt")
        QApplication.instance() or QApplication([])
        from fedtail.frontends.qt import images
        img = images.decode(png(), 400)
        self.assertEqual((img.width(), img.height()), (8, 8))
        self.assertTrue(images.decode(png()[:40], 400).isNull())  # cut short: not read
        self.assertTrue(images.decode(b"\x00\x01" * 500, 400).isNull())  # nobody's
        self.assertEqual(images.decode(jpeg(), 400, "jpeg").width(), 8)


if __name__ == "__main__":
    unittest.main()
