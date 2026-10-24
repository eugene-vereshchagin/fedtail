"""People and posts from other servers in the core (core/app.py): outboxes that fail,
public APIs that page or refuse, collections of followers that break, follow dates in
notes, and the editor's suggestions and visibility — their server's trouble stays
theirs."""

import time
import unittest
from unittest import mock

from fedtail.protocols.mastodon.api import ApiError

from .fakes import BOB, status
from .test_cov_core_app_poll import CoreCase, boom

T = 10
FAR = dict(BOB, id="F", acct="far@far.test", username="far",
           url="https://far.test/@far", uri="https://far.test/users/far")


def page_of(n, start=0):
    return [{"id": str(start + i), "uri": f"https://far.test/s/{start + i}",
             "visibility": "public"} for i in range(n)]


class OriginTest(CoreCase):
    def test_outbox_failing_falls_back_to_the_api(self):
        c = self.connect()
        c._origin_json = lambda url: {"outbox": "https://far.test/outbox"} \
            if "users" in url else (_ for _ in ()).throw(OSError("outbox down"))
        served = []

        def get(url):
            if "lookup" in url:
                return {"id": "77"}
            served.append(url)
            return page_of(2) if len(served) % 2 else []  # a page, then nothing more
        with mock.patch.object(c, "_origin_get", get), \
                mock.patch.object(c, "_resolve_statuses", side_effect=lambda uris: uris):
            got = c.posts_from_origin(FAR).result(timeout=T)
            self.assertEqual(got, ["https://far.test/s/0", "https://far.test/s/1"])
            served.clear()
            uris, nxt = c.older_from_origin(FAR, resolve=False).result(timeout=T)
            self.assertEqual(len(uris), 2)
            self.assertIsNone(nxt)  # a page of 2 then nothing more: done
        self.assertEqual(c.older_from_origin(dict(FAR, acct="local")).result(timeout=T),
                         ([], None))

    def test_api_paging(self):
        c = self.connect()
        pages = iter([page_of(30), page_of(30, 30)])
        with mock.patch.object(c, "_origin_get", lambda url: next(pages, [])):
            uris, nxt = c._older_via_api(FAR, "api:77:500", set(), 40)
        self.assertEqual(len(uris), 60)
        self.assertEqual(nxt, "api:77:59")
        with mock.patch.object(c, "_origin_get", boom()):
            self.assertEqual(c._older_via_api(FAR, None, set(), 40), ([], None))
        self.assertEqual(c._older_via_api({"id": "x"}, None, set(), 40), ([], None))
        with mock.patch.object(c, "_origin_get", return_value={}):
            self.assertEqual(c._older_via_api(FAR, None, set(), 40), ([], None))
        with mock.patch.object(c, "_origin_get",
                               lambda url: [{"id": "", "uri": "u", "visibility": "public"}]):
            self.assertEqual(c._older_via_api(FAR, "api:1:2", set(), 40), (["u"], None))

    def test_outbox_of(self):
        c = self.connect()
        c._origin_json = boom()
        self.assertIsNone(c._outbox_of({"id": "x", "uri": None, "url": "https://f/x"}))

    def test_resolving(self):
        c = self.connect()
        c.api.search = lambda q, **k: (_ for _ in ()).throw(OSError("gone")) \
            if q.endswith("bad") else {"statuses": [dict(status("090", BOB), uri=q)]}
        got = c.resolve_statuses(["https://far.test/ok", "https://far.test/bad"]).result(
            timeout=T)
        self.assertEqual([s["uri"] for s in got], ["https://far.test/ok"])

    def test_people_from_origin(self):
        c = self.connect()
        c._origin_json = boom()
        res, _n = c.people_from_origin(FAR, "followers").result(timeout=T)
        self.assertEqual(res["accounts"], [])
        docs = {FAR["uri"]: {"followers": "https://far.test/f"},
                "https://far.test/f": {"totalItems": 3, "first": "https://far.test/f1"}}

        def get(url):
            if url == "https://far.test/f1":
                raise OSError("page down")
            return docs[url]
        c._origin_json = get
        res, _n = c.people_from_origin(FAR, "followers").result(timeout=T)
        self.assertEqual((res["accounts"], res["total"]), ([], 3))
        docs["https://far.test/f"] = {"items": ["https://far.test/a", "https://far.test/b"]}
        c.api.search = lambda q, **k: (_ for _ in ()).throw(ApiError(500, "x")) \
            if q.endswith("/a") else {"accounts": [dict(BOB, id="BB")]}
        res, _n = c.people_from_origin(FAR, "followers").result(timeout=T)
        self.assertEqual([a["id"] for a in res["accounts"]], ["BB"])


class NotesTest(CoreCase):
    def test_follow_date_notes(self):
        c = self.connect()
        c.api.relationship = boom(ApiError(404, "no notes here"))
        self.assertEqual(c._note_follow("B", {}, "2026-01-01T00:00:00Z"), {})
        rel = {"note": "друг\n\n[fedtail followed 2025-05-05]"}
        c.api.set_note = mock.Mock()
        self.assertIs(c._note_follow("B", rel, "2026-01-01T00:00:00Z"), rel)
        same = {"note": "друг"}
        self.assertIs(c._note_follow("B", same, None), same)
        c.api.set_note.assert_not_called()


class SuggestionsTest(CoreCase):
    def test_suggestions_and_visibility(self):
        c = self.connect()
        c.api.followed_tags = boom()
        c.api.custom_emojis = boom()
        c._followed_tag_names = None
        c.prepare_tags()
        c.prepare_emoji()
        c.prepare_emoji()  # once a run
        c.bg.submit(lambda: None).result(timeout=T)
        self.assertEqual(c.emoji_suggestions(""), [])
        self.assertEqual(c.mention_suggestions(""), [])
        c.api.followed_tags = lambda: [{"name": "fedi"}, {"name": ""}]
        c._followed_tag_names = None
        c.prepare_tags()
        c.bg.submit(lambda: None).result(timeout=T)
        for _ in range(100):
            if c._followed_tag_names:
                break
            time.sleep(0.01)
        self.assertEqual(c._followed_tag_names, {"fedi"})
        c._followed_tag_names = {"Georgia"}
        self.assertEqual(c.tag_suggestions("geo")[0], "Georgia")
        c.cfg["post"]["default_visibility"] = "server"
        c.server_prefs = {"posting:default:visibility": "weird"}
        self.assertEqual(c.default_visibility(), "public")
        c.cfg["post"]["reply_never_wider"] = False
        self.assertEqual(c.reply_visibility({"visibility": "direct"}), "public")
        c.api = None
        c._emoji = None
        c.prepare_emoji()  # not connected: nothing asked
        self.assertIsNone(c._emoji)


if __name__ == "__main__":
    unittest.main()
