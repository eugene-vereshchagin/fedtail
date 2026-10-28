"""common/qr.py: the QR code of the sync key. Known answers (checked once against
python-qrcode and read back by OpenCV's decoder), the same checks again where those
libraries are installed, and the pictures every interface draws from the matrix."""

import hashlib
import unittest

from fedtail.frontends.common import qr


def _hash(m):
    return hashlib.sha256("".join(qr.rows(m)).encode()).hexdigest()[:16]


class QrTest(unittest.TestCase):
    def test_known_answers(self):
        self.assertEqual(_hash(qr.matrix("fedtail", mask=3)), "c5aa3088211df040")
        m = qr.matrix("k" * 120, mask=5)  # version 7: the version's own bits too
        self.assertEqual(len(m), 45)
        self.assertEqual(_hash(m), "c02fce2ce8b4388d")

    def test_sizes_and_limits(self):
        self.assertEqual(len(qr.matrix("")), 21)
        self.assertEqual(len(qr.matrix("x" * 14)), 21)  # 14 bytes: version 1 at level M
        self.assertEqual(len(qr.matrix("x" * 15)), 25)
        self.assertEqual(len(qr.matrix("x" * 213)), 57)  # version 10
        with self.assertRaises(qr.TooLong):
            qr.matrix("x" * 214)

    def test_the_pictures(self):
        m = qr.matrix("fedtail")
        rows = qr.rows(m)
        self.assertEqual(len(rows), 21 + 2 * qr.QUIET)
        self.assertEqual(rows[0], "0" * len(rows))  # the quiet zone
        self.assertTrue(rows[qr.QUIET].startswith("0000" + "1111111"))  # a finder
        self.assertTrue(qr.svg(rows).startswith("<svg"))
        lines = qr.blocks(rows)
        self.assertEqual(len(lines), (len(rows) + 1) // 2)
        self.assertEqual({len(x) for x in lines}, {len(rows)})

    def test_as_python_qrcode_makes_it(self):
        try:
            import qrcode
        except ImportError:
            self.skipTest("python-qrcode isn't installed")
        for text in ("hello world 123", "x" * 40, "fedtail-sync:" + "A" * 60, "y" * 150,
                     "z" * 200, "ключ"):
            m = qr.matrix(text)
            version = (len(m) - 17) // 4
            for mask in range(8):
                q = qrcode.QRCode(version=version, border=0, mask_pattern=mask,
                                  error_correction=qrcode.constants.ERROR_CORRECT_M)
                q.add_data(text.encode(), optimize=0)
                q.make(fit=False)
                self.assertEqual(q.get_matrix(), qr.matrix(text, mask=mask), (text, mask))

    def test_a_decoder_reads_it(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV isn't installed")
        det = cv2.QRCodeDetector()
        for text in ("fedtail-sync:1:abcdefghijklmnopqrstuvwxyz0123456789", "q" * 180):
            a = np.array([[0 if c == "1" else 255 for c in row]
                          for row in qr.rows(qr.matrix(text))], dtype=np.uint8)
            got, _pts, _s = det.detectAndDecode(np.kron(a, np.ones((8, 8), dtype=np.uint8)))
            self.assertEqual(got, text)


    def test_every_interface_draws_it(self):
        from fedtail.frontends.common.places import Row
        rows = qr.rows(qr.matrix("fedtail-sync:test"))
        row = Row("qr", line="the key", data=rows)
        try:
            from fedtail.frontends.tui.screens import qr_text
        except ImportError:
            pass
        else:
            text = qr_text(row).plain.split("\n")
            self.assertEqual(text[:-1], qr.blocks(rows))
            self.assertEqual(text[-1], "the key")
        try:
            import os
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PySide6.QtWidgets import QApplication

            from fedtail.frontends.qt.place import _qr_label
        except ImportError:
            pass
        else:
            QApplication.instance() or QApplication([])
            pix = _qr_label(rows, module=3).pixmap()
            self.assertEqual(pix.width(), len(rows) * 3)
            img = pix.toImage()
            self.assertEqual(img.pixelColor(0, 0).lightness(), 255)  # the quiet zone
            self.assertEqual(img.pixelColor(qr.QUIET * 3, qr.QUIET * 3).lightness(), 0)
        self.assertIn("<svg", qr.svg(rows))

    def test_gtk_draws_it(self):
        try:
            import gi
            gi.require_version("Gtk", "4.0")
            from fedtail.frontends.gtk.place import _qr_picture
        except (ImportError, ValueError):
            self.skipTest("no GTK 4")
        rows = qr.rows(qr.matrix("fedtail-sync:test"))
        self.assertEqual(_qr_picture(rows, module=2).get_paintable().get_width(),
                         len(rows) * 2)


if __name__ == "__main__":
    unittest.main()
