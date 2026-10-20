"""Pictures drawn with half blocks for the terminal (frontends/tui/pictures.py).
Skipped without rich (comes with Textual) or Pillow."""

import io
import unittest

try:
    import rich  # noqa: F401
    from PIL import Image
    HAVE = True
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE, "rich or Pillow is not installed")
class HalfBlocksTest(unittest.TestCase):
    def png(self, w, h, colour):
        buf = io.BytesIO()
        Image.new("RGB", (w, h), colour).save(buf, "PNG")
        return buf.getvalue()

    def test_size_and_colour(self):
        from fedtail.frontends.tui import pictures
        text = pictures.blocks(self.png(200, 100, (255, 0, 0)), 20, 10)
        lines = text.plain.split("\n")
        self.assertEqual(len(lines[0]), 20)        # as wide as allowed
        self.assertEqual(len(lines), 5)            # 2:1 picture, two pixels a line
        self.assertTrue(set(text.plain) <= {"▀", "\n"})
        self.assertIn("#ff0000 on #ff0000", str(text.spans[0].style))

    def test_tall_picture_fits_the_height(self):
        from fedtail.frontends.tui import pictures
        text = pictures.blocks(self.png(50, 400, (0, 0, 255)), 40, 8)
        self.assertEqual(len(text.plain.split("\n")), 8)

    def test_not_a_picture(self):
        from fedtail.frontends.tui import pictures
        self.assertIsNone(pictures.blocks(b"<html>nope</html>", 20, 10))
        self.assertIsNone(pictures.blocks(b"", 20, 10))


if __name__ == "__main__":
    unittest.main()
