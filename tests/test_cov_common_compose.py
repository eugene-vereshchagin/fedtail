"""The rules of writing a post (frontends/common/compose.py) beyond tests/test_common.py:
draft names, what an editor starts with, "when to send", a chain's counter, what's
completed as it's typed, the command line's #alias, a picture made to fit the server,
and the languages' names."""

import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

from fedtail.frontends.common import compose


class View:
    def __init__(self, draft=None, me=None, **cfg):
        self.draft = draft
        self.me = me
        self.cfg = {"post": cfg}

    def get_draft(self, key):
        return self.draft

    def reply_visibility(self, _post):
        return "nonsense"  # not a visibility: the editor falls back on its default

    def draft_key(self, reply_id, quote_id):
        return f"core:{reply_id}:{quote_id}"

    def tag_suggestions(self, word):
        return [word + "ia"]

    def mention_suggestions(self, word):
        return [(word + "@x.test", "Name"), (word + "2@x.test", "")]

    def emoji_suggestions(self, word):
        return [(word + "_cat", None)]


class ComposeTest(unittest.TestCase):
    def test_draft_keys(self):
        v = View()
        post = types.SimpleNamespace(id="7", warning="")
        self.assertEqual(compose.draft_key(v, edit=post), "edit:7")
        self.assertEqual(compose.draft_key(v, reply_to=post, invite=True), "invite:7")
        self.assertEqual(compose.draft_key(v, quote=post), "core:None:7")

    def test_start_with_text_and_a_bad_visibility(self):
        s = compose.start(View(), "k", start_text="#a3f ")
        self.assertEqual(s.text, "#a3f ")
        self.assertEqual(s.visibility, compose.DEFAULT_VIS)
        d = compose.start(View(draft={"text": "x", "visibility": "private"}), "k")
        self.assertEqual(d.visibility, "followers")  # an old draft's word
        self.assertIsNone(d.language)

    def test_a_reply_s_warning_copied_or_not(self):
        """post.reply_warning: the post's CW carried into the reply ("copy", as
        Mastodon) or not ("none": a talk stayed under its first post's topic)."""
        post = types.SimpleNamespace(id="7", warning="fedtail", author=None, mentions=())
        with mock.patch.object(compose, "reply_mentions", lambda *_a: "@bob "):
            self.assertEqual(compose.start(View(), "k", reply_to=post).cw, "fedtail")
            self.assertEqual(compose.start(View(reply_warning="none"), "k",
                                           reply_to=post).cw, "")

    def test_when_utc(self):
        self.assertIsNone(compose.when_utc("  "))
        self.assertEqual(compose.when_utc("2030-01-01T12:00:00+04:00"),
                         "2030-01-01T08:00:00.000Z")
        self.assertTrue(compose.when_utc("2030-01-01 12:00").endswith(".000Z"))
        with self.assertRaisesRegex(ValueError, "tomorrow"):
            compose.when_utc("tomorrow")

    def test_a_chain_counts_its_longest_part(self):
        cfg = {"post": {"chain": True, "camelcase_hint": False}}
        text = "a" * 10 + "\n\n---\n\n" + "b" * 30
        c = compose.count(text, "cw", 20, cfg)
        if c.parts > 1:
            self.assertEqual(c.n, 32)
            self.assertTrue(c.over)
        self.assertEqual(compose.count("x", "", 5, cfg).parts, 1)

    def test_tokens_and_suggestions(self):
        self.assertEqual(compose.token_at_end("say :a"), (None, None))  # too short
        self.assertEqual(compose.token_at_end("say :ca"), (":", "ca"))
        v = View()
        self.assertEqual(compose.suggestions(v, "#", "georg"), [("#georgia", "#georgia")])
        self.assertEqual(compose.suggestions(v, "@", "bo")[0],
                         ("@bo@x.test", "@bo@x.test — Name"))
        self.assertEqual(compose.suggestions(v, ":", "ca"), [(":ca_cat:", ":ca_cat:")])
        off = View(complete_tags=False, complete_mentions=False, complete_emoji=False)
        for sigil in "#@:":
            self.assertEqual(compose.suggestions(off, sigil, "x"), [])
        self.assertFalse(compose.worth_offering([("#tag", "#tag")], "TAG"))
        self.assertTrue(compose.worth_offering([("#tags", "#tags")], "tag"))

    def test_polls_and_languages(self):
        self.assertIsNone(compose.poll_data(False, ["a", "b"], 60, False))
        self.assertIsNone(compose.poll_data(True, ["a", " "], 60, False))
        self.assertEqual(compose.poll_data(True, [" a ", "b"], 60, 1),
                         {"options": ["a", "b"], "expires_in": 60, "multiple": True})
        cfg = {"post": {"languages": ["ru", "en"], "language": "ka"}}
        self.assertEqual(compose.languages(cfg, ["eo", "ru"]), ["ru", "en", "ka", "eo"])
        self.assertEqual(compose.languages({"post": {}}), [])

    def test_put_alias(self):
        self.assertEqual(compose.put_alias("hello", "a3f"), "#a3f hello")
        self.assertEqual(compose.put_alias("#b12/3 hi", "a3f"), "#a3f hi")

    def test_language_label(self):
        self.assertEqual(compose.language_label("ka"), "ქართული (ka)")
        self.assertEqual(compose.language_label("xx"), "Xx (xx)")
        self.assertEqual(compose.language_label("ru", lambda c: "russe"), "Russe (ru)")


class Pictures:
    """The toolkit's pictures for fit_for_server: a picture is (w, h, alpha); its file
    as big as w * h * quality / 1000 bytes."""

    def __init__(self, size=(4000, 3000), alpha=False, loads=True, saves=True):
        self._size, self._alpha, self.loads, self.saves = size, alpha, loads, saves
        self.saved = []

    def size(self, path):
        return self._size

    def load(self, path):
        return (*self._size, self._alpha) if self.loads else None

    def dims(self, img):
        return img[0], img[1]

    def scaled(self, img, w, h):
        return (w, h, img[2])

    def alpha(self, img):
        return img[2]

    def save(self, img, out, kind, quality):
        self.saved.append((kind, quality, img[0], img[1]))
        if not self.saves:
            return False
        Path(out).write_bytes(b"x" * (img[0] * img[1] * quality // 1000))
        return True


class FitTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.pic = self.dir / "photo.jpg"
        self.pic.write_bytes(b"x" * 200_000)

    def caps(self, b=0, px=0):
        return types.SimpleNamespace(image_bytes=b, image_pixels=px)

    def fit(self, caps, imgs, path=None):
        return compose.fit_for_server(str(path or self.pic), caps, self.dir, imgs)

    def test_left_as_it_is(self):
        self.assertEqual(self.fit(self.caps(), Pictures()), str(self.pic))  # says nothing
        gif = self.dir / "a.GIF"
        gif.write_bytes(b"g")
        self.assertEqual(self.fit(self.caps(1, 1), Pictures(), gif), str(gif))
        self.assertEqual(self.fit(self.caps(10**9, 10**9), Pictures()), str(self.pic))
        no_size = Pictures()
        no_size.size = lambda p: None
        self.assertEqual(self.fit(self.caps(1, 1), no_size), str(self.pic))
        self.assertEqual(self.fit(self.caps(1), Pictures(loads=False)), str(self.pic))
        self.assertEqual(self.fit(self.caps(1), Pictures(saves=False)), str(self.pic))

    def test_too_many_pixels(self):
        imgs = Pictures()
        out = self.fit(self.caps(px=1_000_000), imgs)
        self.assertTrue(out.endswith("upload-photo.jpg"))
        _k, _q, w, h = imgs.saved[0]
        self.assertLessEqual(w * h, 1_000_000)

    def test_too_heavy_jpeg_loses_quality(self):
        imgs = Pictures(size=(1000, 1000))
        self.fit(self.caps(b=70_000), imgs)
        self.assertEqual([q for _k, q, _w, _h in imgs.saved], [90, 75, 60])
        imgs = Pictures(size=(1000, 1000))
        self.fit(self.caps(b=1), imgs)  # never fits: stops at the lowest quality
        self.assertEqual([q for _k, q, _w, _h in imgs.saved], [90, 75, 60, 45, 30])

    def test_too_heavy_png_gets_smaller(self):
        imgs = Pictures(size=(1000, 1000), alpha=True)
        out = self.fit(self.caps(b=50_000), imgs)
        self.assertTrue(out.endswith(".png"))
        self.assertTrue(all(k == "png" for k, *_r in imgs.saved))
        self.assertLess(imgs.saved[-1][2], 1000)


if __name__ == "__main__":
    unittest.main()
