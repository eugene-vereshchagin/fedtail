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


@unittest.skipUnless(HAVE, "rich or Pillow is not installed")
class ChafaTest(unittest.TestCase):
    """chafa, when installed, draws the app's own pictures too (it was only the v
    viewer's: installing it changed nothing in the lane, 29.10); our blocks without it."""

    def png(self):
        buf = io.BytesIO()
        Image.new("RGB", (120, 60), (20, 200, 40)).save(buf, "PNG")
        return buf.getvalue()

    def test_blocks_without_chafa(self):
        from unittest import mock

        from fedtail.frontends.tui import pictures
        with mock.patch.object(pictures, "_chafa", lambda: None):
            got = pictures.text(self.png(), 20, 6)
        self.assertEqual(got.plain, pictures.blocks(self.png(), 20, 6).plain)
        self.assertIsNone(pictures.text(b"not a picture", 20, 6))

    def test_chafa_when_there(self):
        import shutil

        from fedtail.frontends.tui import pictures
        if not shutil.which("chafa"):
            self.skipTest("no chafa here")
        got = pictures.text(self.png(), 20, 6)
        lines = got.plain.split("\n")
        self.assertLessEqual(len(lines), 6)
        self.assertLessEqual(max(len(x) for x in lines), 20)
        self.assertTrue(got.spans)  # coloured
        self.assertIsNone(pictures.text(b"not a picture", 20, 6))

    def test_how_they_are_drawn_is_said(self):
        """The log at start and tools/tui_check.py say which way the lane's pictures
        go; chafa failing is a warning once, the half blocks drawn instead."""
        from unittest import mock

        from fedtail.frontends.tui import pictures
        with mock.patch.object(pictures, "_chafa", lambda: "/usr/bin/chafa"), \
                mock.patch.dict(pictures._graphics, {"kind": None}):
            self.assertIn("chafa", pictures.how("auto"))
            self.assertIn("v shows", pictures.how("key"))
        with mock.patch.object(pictures, "_chafa", lambda: None), \
                mock.patch.dict(pictures._graphics, {"kind": "sixel"}):
            self.assertIn("sixel", pictures.how("auto"))
            self.assertIn("half blocks", pictures.how("blocks"))
        with mock.patch.object(pictures, "Image", None):
            self.assertIn("Pillow", pictures.how("auto"))
        pictures._chafa_said["failed"] = False
        with mock.patch.object(pictures, "_chafa", lambda: "/nonexistent/chafa"), \
                self.assertLogs(pictures.log, "WARNING") as said:
            got = pictures.text(self.png(), 20, 6)
        self.assertIn("▀", got.plain)  # ours instead
        self.assertIn("half blocks instead", said.output[0])
        with mock.patch.object(pictures, "_chafa", lambda: "/bin/false"), \
                self.assertLogs(pictures.log, "DEBUG") as said:
            pictures.text(self.png(), 20, 6)
        self.assertTrue(all("DEBUG" in x for x in said.output))  # once loud is enough
