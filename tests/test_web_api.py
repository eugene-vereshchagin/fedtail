"""The web page on the rest of the Mastodon API (0.20): a video's cover sent with it,
my post's pictures described anew in an edit, "who else shared this link" opening its
place."""

import json
import threading
import time

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


class WebProfileTest(TmpDir):
    """A profile as the windows have it: the pinned posts on top (once), what the person
    puts forward, and page after page further back."""
    make = test_cli.CliTest.make

    def setUp(self):
        super().setUp()
        i18n.setup("en")
        self.core, self.w = self.make()
        self.core.connect().result()
        self.core.poll_once()
        self.web = web.Web(self.core, None)

    def test_pinned_featured_and_further_back(self):
        from tests import fakes
        b_posts = [f"{i:03d}" for i in range(201, 209)]  # more than a page (page_size 3)
        for m, i in enumerate(b_posts):
            self.w.add(fakes.status(i, fakes.BOB, minute=m, vis="public", text=f"b{i}"))
        pin = b_posts[0]  # the oldest, pinned: on top all the same
        self.w.statuses[pin]["pinned"] = True
        self.w.featured["B"] = {"tags": [{"name": "fediverse", "statuses_count": "12"}],
                                "people": [fakes.NEWS]}
        got = self.web.account("B", "all")
        ids = [p["sid"] for p in got["posts"]]
        self.assertEqual(ids[0], pin)
        self.assertTrue(got["posts"][0]["pinned"])
        self.assertEqual(ids.count(pin), 1)  # not twice
        self.assertEqual([f["title"] for f in got["featured"]],
                         ["Often writes about:", "Recommends:"][:len(got["featured"])])
        self.assertIn("#fediverse (12)", got["featured"][0]["text"])
        self.assertEqual(got["featured"][1]["people"][0]["id"], "N")
        seen = set(ids)
        more = got["older"]
        for _round in range(10):  # page by page until my server has nothing older
            if not more or more["cursor"]:
                break
            nxt = self.web.account_more("B", "all", got["max_id"], more["cursor"])
            seen |= {p["sid"] for p in nxt["posts"]}
            got, more = nxt, nxt["older"]
        self.assertEqual(seen, set(b_posts))

    def test_origin_step_by_step(self):
        """Their own server: the addresses first, then the posts a few at a time."""
        from unittest import mock

        from tests import fakes
        st = fakes.status("401", fakes.BOB, minute=1, vis="public", text="old one")
        self.w.add(st, home=True)
        self.core.poll_once()
        acc = object()  # who they are: only what the patched calls below are given
        uris = ["https://far.example/s/1", "http://plain.example/s/2"]
        with mock.patch.object(self.core, "account", return_value=_done(acc)), \
                mock.patch.object(self.core, "older_from_origin",
                                  return_value=_done((uris, None))) as older, \
                mock.patch.object(self.web, "_remote_host", return_value="far.example"):
            got = self.web.origin_list("B", "origin")
        self.assertEqual(got["uris"], uris)
        self.assertIsNone(older.call_args[0][1])  # from their newest
        self.assertFalse(older.call_args.kwargs["resolve"])  # addresses only, fast
        self.assertIn("{n}", got["words"]["fetching"])
        self.assertIsNone(got["older"])  # nothing further back: no button
        with mock.patch.object(self.core, "resolve_statuses",
                               return_value=_done([self.core.store.get_status("401")])) as res:
            got = self.web.origin_fetch("B", uris, "all")
        self.assertEqual(res.call_args[0][0], uris[:1])  # https only
        self.assertEqual([p["sid"] for p in got["posts"]], ["401"])
        with mock.patch.object(self.web, "_remote_host", return_value=""):
            self.assertEqual(self.web.origin_list("B")["uris"], [])
        self.assertEqual(self.web.origin_fetch("B", [])["posts"], [])

    def test_the_token_refused(self):
        """The server no longer takes the token: the page hears it with the news."""
        self.assertNotIn("auth_failed", self.web.wait_answer(-99, -1))
        self.core.emit("auth_failed", "HTTP 401")
        got = self.web.wait_answer(-99, -1)
        self.assertEqual(got["auth_failed"]["title"], i18n._("auth_failed_title"))

    def test_completion_of_names_tags_emoji(self):
        """The editor's #tag, @name, :emoji: — the windows' completion, on the page."""
        from tests import fakes
        st = fakes.status("301", fakes.BOB, minute=1, vis="public", text="про #fediverse")
        st["tags"] = [{"name": "fediverse"}]
        self.w.add(st, home=True)
        self.core.poll_once()
        self.web.complete("")  # the first call warms what completion reads
        time.sleep(0.3)
        got = self.web.complete("привет @bo")
        self.assertEqual(got["word"], "@bo")
        self.assertTrue(any(i["insert"].startswith("@bob") for i in got["items"]), got)
        got = self.web.complete("и #fed")
        self.assertIn("#fediverse", [i["insert"] for i in got["items"]])
        self.assertEqual(self.web.complete("просто слово")["items"], [])


def _done(value):
    from concurrent.futures import Future
    f = Future()
    f.set_result(value)
    return f
