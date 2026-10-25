"""The REST client's last untested calls: collections (Mastodon 4.6), a cover sent with a
video (v2, and v1 on an old server), a cover set anew, my emoji reactions both ways."""

import tempfile
import unittest
from pathlib import Path

from .test_api import Resp, make


class CollectionsCallsTest(unittest.TestCase):
    def test_every_call(self):
        a, s = make(Resp(body={"collections": [{"id": "C1"}]}), Resp(body=[{"id": "C2"}]),
                    Resp(body={"collections": []}), Resp(body={"collection": {}}))
        self.assertEqual(a.collections_of("7"), [{"id": "C1"}])
        self.assertEqual(s.last[1], "/api/v1/accounts/7/collections")
        self.assertEqual(s.last[2]["params"], {"limit": 40, "offset": 0})
        self.assertEqual(a.collections_of("7", 5, 10), [{"id": "C2"}])  # a bare list too
        self.assertEqual(a.in_collections("7"), [])
        self.assertEqual(s.last[1], "/api/v1/accounts/7/in_collections")
        a.collection("C1")
        self.assertEqual(s.last[:2], ("GET", "/api/v1/collections/C1"))
        a.create_collection("Друзья", "мои", discoverable=False, sensitive=True,
                            account_ids=["1", "2"])
        method, path, kw = s.last
        self.assertEqual((method, path), ("POST", "/api/v1/collections"))
        self.assertEqual(kw["data"], {"name": "Друзья", "description": "мои",
                                      "discoverable": "false", "sensitive": "true",
                                      "account_ids[]": ["1", "2"]})
        a.create_collection("x")
        self.assertNotIn("account_ids[]", s.last[2]["data"])
        self.assertEqual(s.last[2]["data"]["discoverable"], "true")
        a.update_collection("C1", "y", "z", discoverable=True, sensitive=False)
        self.assertEqual(s.last[:2], ("PATCH", "/api/v1/collections/C1"))
        self.assertEqual(s.last[2]["data"]["sensitive"], "false")
        a.delete_collection("C1")
        self.assertEqual(s.last[:2], ("DELETE", "/api/v1/collections/C1"))
        a.collection_add("C1", "9")
        self.assertEqual(s.last[:2], ("POST", "/api/v1/collections/C1/items"))
        self.assertEqual(s.last[2]["data"], {"account_id": "9"})
        a.collection_remove("C1", "I3")
        self.assertEqual(s.last[:2], ("DELETE", "/api/v1/collections/C1/items/I3"))
        a.collection_revoke("C1", "I3")
        self.assertEqual(s.last[:2], ("POST", "/api/v1/collections/C1/items/I3/revoke"))


class CoverTest(unittest.TestCase):
    def files(self, d):
        video, cover = Path(d) / "v.mp4", Path(d) / "c.png"
        video.write_bytes(b"mp4")
        cover.write_bytes(b"png")
        return str(video), str(cover)

    def test_a_video_with_its_cover(self):
        with tempfile.TemporaryDirectory() as d:
            video, cover = self.files(d)
            a, s = make(Resp(body={"id": "M", "url": "https://x/v.mp4"}))
            a.upload_media(video, thumbnail=cover)
            files = s.calls[0][2]["files"]
            self.assertEqual(files["thumbnail"][0], "c.png")
            self.assertEqual(files["thumbnail"][2], "image/png")
            self.assertTrue(files["thumbnail"][1].closed)  # closed after

    def test_an_old_server_gets_it_again_from_the_start(self):
        with tempfile.TemporaryDirectory() as d:
            video, cover = self.files(d)
            a, s = make(Resp(404, {"error": "no"}), Resp(body={"id": "M", "url": "u"}))
            self.assertEqual(a.upload_media(video, thumbnail=cover)["url"], "u")
            self.assertTrue(s.calls[1][1].endswith("/api/v1/media"))
            self.assertIn("thumbnail", s.calls[1][2]["files"])

    def test_a_cover_set_anew(self):
        with tempfile.TemporaryDirectory() as d:
            _video, cover = self.files(d)
            a, s = make(Resp(body={"id": "M"}))
            a.update_media("M", description="кот", focus=(0, 0.5), thumbnail=cover)
            method, path, kw = s.last
            self.assertEqual((method, path), ("PUT", "/api/v1/media/M"))
            self.assertEqual(kw["data"], {"description": "кот", "focus": "0.00,0.50"})
            self.assertEqual(kw["files"]["thumbnail"][0], "c.png")


class ReactTest(unittest.TestCase):
    def test_both_ways(self):
        a, s = make()
        a.react_status("5", "👍")
        self.assertEqual(s.last[:2], ("PUT", "/api/v1/pleroma/statuses/5/reactions/%F0%9F%91%8D"))
        a.react_status("5", "blobcat", on=False)
        self.assertEqual(s.last[:2], ("DELETE", "/api/v1/pleroma/statuses/5/reactions/blobcat"))
        a.react_status("5", "🔥", style="fedibird")
        self.assertEqual(s.last[:2], ("POST", "/api/v1/statuses/5/react/%F0%9F%94%A5"))
        a.react_status("5", "🔥", on=False, style="fedibird")
        self.assertEqual(s.last[:2], ("POST", "/api/v1/statuses/5/unreact/%F0%9F%94%A5"))


if __name__ == "__main__":
    unittest.main()
