"""Pictures made lighter before the upload (common/compose.fit_media, 25.11), with each
toolkit's own pictures on real files: a phone's photo, held upright (EXIF orientation 6)
with the place it was taken (GPS) — the copy comes WebP (or JPEG where it can't be),
no longer than post.photo_max_side, standing as it was held, without its EXIF."""

import os
import tempfile
import types
import unittest
from pathlib import Path

try:
    from PIL import Image
    HAVE_PIL = True
except ImportError:
    HAVE_PIL = False

from fedtail.frontends.common import compose

CFG = {"post": {"resize_images": True, "photo_format": "webp", "photo_quality": 80,
                "photo_max_side": 2560, "png_format": "webp", "png_quality": 80,
                "png_max_side": 2560}}
CAPS = types.SimpleNamespace(image_bytes=16 * 1024 * 1024, image_pixels=33_177_600,
                             media_types=["image/jpeg", "image/png", "image/webp"])


def phone_photo(path):
    """4000×3000 as the sensor has it, the EXIF saying "turn right" and where it was."""
    im = Image.new("RGB", (4000, 3000), (200, 30, 30))
    for x in range(0, 4000, 50):  # something to compress
        im.paste((x % 255, 90, 200), (x, 0, x + 20, 3000))
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation: rotate 90° clockwise to stand
    exif[0x010F] = "PhoneMaker"
    gps = {1: "N", 2: (41.0, 43.0, 0.0), 3: "E", 4: (44.0, 47.0, 0.0)}
    exif[0x8825] = gps
    im.save(path, "JPEG", quality=95, exif=exif.tobytes())


@unittest.skipUnless(HAVE_PIL, "Pillow is not installed")
class UploadPicturesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.photo = self.dir / "IMG_0001.jpg"
        phone_photo(self.photo)

    def check(self, out, ext):
        self.assertNotEqual(out, str(self.photo))
        self.assertTrue(out.endswith(ext), out)
        self.assertLess(os.path.getsize(out), os.path.getsize(self.photo))
        with Image.open(out) as im:
            self.assertEqual(im.size, (1920, 2560))  # upright, the longest side 2560
            raw = im.info.get("exif") or b""
            self.assertNotIn(b"PhoneMaker", raw)
            self.assertFalse(im.getexif().get_ifd(0x8825))  # no place
        self.assertNotIn(b"PhoneMaker", Path(out).read_bytes())
        self.assertEqual(Image.open(self.photo).size, (4000, 3000))  # mine untouched

    def fit(self, images, caps=CAPS):
        return compose.fit_media([(str(self.photo), "")], CFG, caps, self.dir, images)[0][0]

    def test_pillow(self):  # the page, the phone, the terminal
        from PIL import features
        out = self.fit(compose.PilImages)
        self.check(out, ".webp" if features.check("webp") else ".jpg")

    def test_pillow_to_a_server_without_webp(self):
        caps = types.SimpleNamespace(**{**vars(CAPS), "media_types": ["image/jpeg"]})
        self.check(self.fit(compose.PilImages, caps), ".jpg")

    def test_a_screenshot_with_transparency(self):
        shot = self.dir / "shot.png"
        im = Image.new("RGBA", (3000, 1000), (0, 0, 0, 0))
        im.paste((10, 200, 10, 255), (100, 100, 2900, 900))
        im.save(shot)
        out = compose.fit_media([(str(shot), "")], CFG, CAPS, self.dir,
                                compose.PilImages)[0][0]
        with Image.open(out) as got:
            self.assertEqual(got.size, (2560, 853))
            self.assertEqual(got.convert("RGBA").getpixel((5, 5))[3], 0)  # still see-through

    def test_qt(self):
        try:
            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            from PySide6.QtGui import QGuiApplication

            from fedtail.frontends.qt.compose import _QtImages
        except ImportError:
            self.skipTest("PySide6 is not installed")
        _app = QGuiApplication.instance() or QGuiApplication([])
        out = self.fit(_QtImages)
        self.check(out, ".webp" if _QtImages.can("webp") else ".jpg")

    def test_gtk(self):
        try:
            import gi
            gi.require_version("GdkPixbuf", "2.0")
            from gi.repository import GdkPixbuf  # noqa: F401

            from fedtail.frontends.gtk.compose import _PixbufImages
        except (ImportError, ValueError):
            self.skipTest("GdkPixbuf is not installed")
        out = self.fit(_PixbufImages)
        self.check(out, ".webp" if _PixbufImages.can("webp") else ".jpg")



if __name__ == "__main__":
    unittest.main()
