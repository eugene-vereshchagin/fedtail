"""The terminal on the rest of the Mastodon API (0.20): a cover for a video or a sound
in the editor, my post's pictures described anew in an edit, "who else shared this link"
opening its place. Skipped without Textual."""

import unittest
from types import SimpleNamespace as NS

from fedtail import i18n

from .test_cov_tui_host import HAVE_TEXTUAL


@unittest.skipUnless(HAVE_TEXTUAL, "Textual is not installed")
class TuiApiTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_cover_and_edit_words(self):
        from fedtail.frontends.tui.screens import ComposeScreen
        cs = ComposeScreen()
        cs.media = [("/tmp/clip.mp4", "a cat"), ("/tmp/pic.png", "")]
        self.assertTrue(cs._playable("/tmp/clip.mp4"))
        self.assertFalse(cs._playable("/tmp/pic.png"))
        cs.covers["/tmp/clip.mp4"] = "/tmp/cover.jpg"
        self.assertEqual(cs._media_out(), [("/tmp/clip.mp4", "a cat", None, "/tmp/cover.jpg"),
                                           ("/tmp/pic.png", "")])
        self.assertEqual(cs._edit_media(), [])  # not an edit
        pic = NS(ref=NS(id="m9"), alt="old", focus=(0.5, 0.5), kind="image")
        post = NS(media=(pic,), boosted=None)
        cs = ComposeScreen(edit=post)
        import fedtail.model as model
        model_real = model.real
        model.real = lambda p: p  # the stand-in post is its own
        try:
            self.assertEqual([m.ref.id for m in cs._edit_media()], ["m9"])
            self.assertEqual(cs._media_changes(), {})
            cs.edit_alts["m9"] = "old"
            self.assertEqual(cs._media_changes(), {})  # the same words: nothing
            cs.edit_alts["m9"] = "new words"
            self.assertEqual(cs._media_changes(), {"m9": ("new words", (0.5, 0.5))})
        finally:
            model.real = model_real

    def test_link_posts_opens_its_place(self):
        from fedtail.frontends.tui.host import TuiHost
        pushed = []
        host = TuiHost.__new__(TuiHost)
        host.app = NS(push_screen=pushed.append)
        host.open_link_posts("https://news.example/a")
        self.assertEqual((pushed[0].name_, pushed[0].arg), ("link", "https://news.example/a"))


if __name__ == "__main__":
    unittest.main()
