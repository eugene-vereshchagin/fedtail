"""The web page on the rest of the Mastodon API (0.20): a video's cover sent with it,
my post's pictures described anew in an edit, "who else shared this link" opening its
place."""

import json
import threading

from fedtail import i18n
from fedtail.frontends.common import places as places_mod
from fedtail.frontends.web import server as web

from . import test_cli, test_web
from .fakes import BOB, ME, status
from .test_core import TmpDir


class WebApiTest(TmpDir):
    make = test_cli.CliTest.make
    req = test_web.WebTest.req
    upload = test_web.WebTest.upload

    def setUp(self):
        super().setUp()
        i18n.setup("en")
        self.core, self.w = self.make()
        self.core.connect().result()
        self.core.poll_once()
        self.key = web.load_key(self.core.paths.data_dir)
        self.srv = web.make_server(self.core, "127.0.0.1", 0, self.key)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def test_cover_goes_with_the_video(self):
        code, got = self.upload(b"\x00\x00\x00\x18ftypmp42", "clip.mp4")
        self.assertEqual(code, 200, got)
        code, cover = self.upload(b"\xff\xd8\xff\xe0jpeg", "cover.jpg")
        self.assertEqual(code, 200, cover)
        body = {"text": "a clip", "visibility": "public", "alt_ok": True,
                "media": [{"token": got["token"], "alt": "a cat", "cover": cover["token"]}]}
        code, _h, r = self.req("/api/post", body)
        self.assertEqual(code, 200, r)
        path, alt, focus, thumb = self.w.uploads[-1]
        self.assertEqual((alt, focus), ("a cat", None))
        self.assertTrue(thumb.endswith(cover["token"]))

    def test_edit_describes_my_pictures(self):
        mine = self.w.add(status("400", ME, text="pic", vis="public"), home=True)
        mine["media_attachments"] = [{"id": "m9", "type": "image",
                                      "url": "https://example.test/m9.png",
                                      "preview_url": "https://example.test/m9s.png",
                                      "description": "old"}]
        self.core.poll_once()
        r = json.loads(self.req("/api/link", {"url": "fedtail:edit/400"})[2])
        media = r["compose"]["media"]
        self.assertEqual([(m["id"], m["alt"]) for m in media], [("m9", "old")])
        body = {"text": "pic", "edit": "400",
                "media_edit": [{"id": "m9", "alt": "new words", "focus": None},
                               {"id": "nope", "alt": "x"}]}
        code, _h, out = self.req("/api/post", body)
        self.assertEqual(code, 200, out)
        self.assertEqual(self.w.statuses["400"]["media_attachments"][0]["description"],
                         "new words")
        # unchanged: no media attributes sent (the post's words only)
        self.assertEqual(self.srv.web._media_changes(
            self.srv.web.core.by_id("400"), [{"id": "m9", "alt": "new words"}]), {})

    def test_link_posts_place(self):
        st = self.w.add(status("401", BOB, text="look", vis="public"), home=True)
        st["card"] = {"url": "https://news.example/a", "title": "A"}
        self.core.poll_once()
        r = json.loads(self.req("/api/link", {"url": "fedtail:linkposts/401"})[2])
        self.assertEqual(r["open"], {"page": "link", "arg": "https://news.example/a",
                                     "tab": ""})
        self.assertIn("link", places_mod.PLACES)
        page = json.loads(self.req("/api/page?name=link&arg=https%3A%2F%2Fnews.example%2Fa")[2])
        self.assertEqual([x["post"]["id"] for x in page["rows"] if x["kind"] == "post"],
                         ["401"])
