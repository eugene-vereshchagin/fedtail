"""The Mastodon REST client (protocols/mastodon/api.py) against a recording HTTP session:
every call makes the request the Mastodon API expects — method, path, query, body —
and every answer (an error, 429, a proxy's HTML page, an empty body, Link paging) comes
out the way the core counts on. Nothing goes to the network."""

import json
import tempfile
import time
import unittest
from pathlib import Path

import requests

from fedtail.protocols.base import Budget
from fedtail.protocols.mastodon import api as api_mod
from fedtail.protocols.mastodon.api import Api, ApiError, RateLimited


class Resp:
    def __init__(self, status=200, body=None, headers=None, text=None, links=None,
                 reason=""):
        self.status_code = status
        self.headers = headers or {}
        self.links = links or {}
        self.reason = reason
        if text is not None:
            self.text = text
            self.content = text.encode()
        elif body is None:
            self.text, self.content = "", b""
        else:
            self.text = json.dumps(body)
            self.content = self.text.encode()
        self._body = body

    def json(self):
        if self._body is None:
            return json.loads(self.text)
        return self._body


class Session:
    """Records each request; answers with the next of `answers` (or {} when none)."""

    def __init__(self, *answers):
        self.headers = {}
        self.calls = []
        self.answers = list(answers)

    def _next(self):
        a = self.answers.pop(0) if self.answers else Resp(body={})
        if isinstance(a, Exception):
            raise a
        return a

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        return self._next()

    def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return self._next()

    @property
    def last(self):
        method, url, kw = self.calls[-1]
        return method, url.removeprefix("https://example.test"), kw


def make(*answers, token="tok"):
    s = Session(*answers)
    return Api("example.test", token, session=s), s


class PlumbingTest(unittest.TestCase):
    def test_server_and_headers(self):
        a, s = make()
        self.assertEqual(a.base, "https://example.test")
        self.assertEqual(a.host, "example.test")
        self.assertEqual(s.headers["Authorization"], "Bearer tok")
        self.assertIn("fedtail", s.headers["User-Agent"])
        b = Api("http://local.lan/", session=Session())
        self.assertEqual(b.base, "http://local.lan")
        self.assertNotIn("Authorization", b.s.headers)

    def test_answers(self):
        a, s = make(Resp(body={"x": 1}), Resp(body=None))
        self.assertEqual(a.get("/p"), {"x": 1})
        self.assertIsNone(a.get("/p"))  # an empty body
        self.assertEqual(a.requests, 2)

    def test_errors(self):
        a, _s = make(Resp(422, {"error": "Validation failed"}))
        with self.assertRaises(ApiError) as e:
            a.get("/p")
        self.assertEqual(e.exception.status, 422)
        self.assertIn("Validation failed", str(e.exception))
        a, _s = make(Resp(502, text="<html><body>Bad gateway</body></html>",
                          reason="Bad Gateway"))
        with self.assertRaises(ApiError) as e:
            a.get("/p")
        self.assertIn("not answering", str(e.exception))
        self.assertNotIn("<html", str(e.exception))
        a, _s = make(Resp(500, text="plain words"))
        with self.assertRaisesRegex(ApiError, "plain words"):
            a.get("/p")

    def test_markers_wait_less_than_the_rest(self):
        """A server stuck on markers once an hour held the whole round 30 s (31.10)."""
        a, s = make(Resp(body={}))
        a.markers()
        self.assertEqual(s.last[2]["timeout"], Api.MARKERS_TIMEOUT)
        self.assertLess(Api.MARKERS_TIMEOUT, 30)

    def test_network_errors_pass_through(self):
        a, _s = make(requests.ConnectionError("down"))
        with self.assertRaises(requests.ConnectionError):
            a.get("/p")

    def test_rate_limit(self):
        reset = time.time() + 120
        a, s = make(Resp(429, {"error": "Too many requests"},
                         headers={"X-RateLimit-Limit": "300", "X-RateLimit-Remaining": "0",
                                  "X-RateLimit-Reset": str(reset)}))
        with self.assertRaises(RateLimited) as e:
            a.get("/p")
        self.assertAlmostEqual(e.exception.until, reset, delta=1)
        # spent: the next call doesn't even go out
        with self.assertRaises(RateLimited):
            a.get("/p")
        self.assertEqual(len(s.calls), 1)

    def test_429_without_headers_waits_retry_after(self):
        a, _s = make(Resp(429, {}, headers={"Retry-After": "30"}))
        with self.assertRaises(RateLimited) as e:
            a.get("/p")
        self.assertAlmostEqual(e.exception.until, time.time() + 30, delta=2)

    def test_budget_from_headers(self):
        a, _s = make(Resp(body={}, headers={"X-RateLimit-Limit": "300",
                                             "X-RateLimit-Remaining": "299",
                                             "X-RateLimit-Reset": "2030-01-01T00:00:00Z"}))
        a.get("/p")
        self.assertEqual((a.budget.limit, a.budget.remaining), (300, 299))
        a, _s = make(Resp(body={}, headers={"X-RateLimit-Remaining": "lots"}))
        a.get("/p")  # nonsense: the budget stays what it was
        self.assertEqual(a.budget, Budget())

    def test_reset_and_retry_after_parsing(self):
        now = time.time()
        self.assertAlmostEqual(api_mod._when_reset(None), now + 60, delta=2)
        self.assertAlmostEqual(api_mod._when_reset("30"), now + 30, delta=2)
        self.assertEqual(api_mod._when_reset("1900000000"), 1900000000)
        self.assertAlmostEqual(api_mod._when_reset("garbage"), now + 60, delta=2)
        self.assertGreater(api_mod._when_reset("2030-01-01T00:00:00.000Z"), now)
        self.assertEqual(api_mod._retry_after({"Retry-After": "1"}), 5.0)
        self.assertEqual(api_mod._retry_after({"Retry-After": "soon"}), 60.0)
        self.assertEqual(api_mod._retry_after({}), 60.0)

    def test_error_text_odd_answers(self):
        class NoJson(Resp):
            def json(self):
                raise ValueError
        self.assertEqual(api_mod.error_text(NoJson(503, text="<!doctype html>x")),
                         "the server is overloaded")
        self.assertEqual(api_mod.error_text(NoJson(418, text="<html>")),
                         "an HTML page instead of JSON")
        self.assertEqual(api_mod.error_text(Resp(400, {"error": ""}, text='{"error": ""}')),
                         '{"error": ""}')

    def test_seg_keeps_ids_in_their_segment(self):
        self.assertEqual(api_mod.seg("01HXYZ"), "01HXYZ")
        self.assertEqual(api_mod.seg("1/../../x"), "1%2F..%2F..%2Fx")
        for bad in ("", ".", ".."):
            with self.assertRaises(ValueError):
                api_mod.seg(bad)

    def test_urls_for_other_servers(self):
        self.assertEqual(api_mod.search_url("https://a.test/"), "https://a.test/api/v2/search")
        self.assertEqual(api_mod.lookup_url("b.test", "bob smith"),
                         "https://b.test/api/v1/accounts/lookup?acct=bob%20smith")
        self.assertTrue(api_mod.statuses_url("b.test", "7", "9").endswith("&max_id=9"))
        self.assertNotIn("max_id", api_mod.statuses_url("b.test", "7"))

    def test_cleartext_ok(self):
        for ok in ("https://x.test", "x.test", "http://localhost:8080", "http://box.lan",
                   "http://127.0.0.1", "http://192.168.1.5", "http://[::1]:3000",
                   "http://pi.local"):
            self.assertTrue(api_mod.cleartext_ok(ok), ok)
        for bad in ("http://example.com", "http://8.8.8.8"):
            self.assertFalse(api_mod.cleartext_ok(bad), bad)


class InstanceTest(unittest.TestCase):
    def test_software_of(self):
        self.assertEqual(api_mod.software_of({"version": "4.3.0+glitch"}), ("glitch", True))
        self.assertEqual(api_mod.software_of({"version": "0.22.1+git",
                                              "account_domain": "x"}), ("gotosocial", True))
        self.assertEqual(api_mod.software_of({"configuration": {
            "accounts": {"allow_custom_css": True}}}), ("gotosocial", True))
        self.assertEqual(api_mod.software_of({"source_url": "https://github.com/mastodon/"
                                                            "mastodon"}), ("mastodon", True))
        self.assertEqual(api_mod.software_of({"version": "4.3.0"}), ("mastodon", False))
        self.assertEqual(api_mod.software_of(None), ("mastodon", False))

    def test_capabilities(self):
        inst = {"version": "4.4.0", "configuration": {
            "statuses": {"max_characters": 5000, "max_media_attachments": 8,
                         "supported_mime_types": ["text/plain", "text/markdown"]},
            "polls": {"max_options": 6},
            "media_attachments": {"image_size_limit": 100, "image_matrix_limit": 200},
            "urls": {"streaming": "wss://s.test"}}}
        c = api_mod.capabilities_from_instance(inst, {"source_url": "https://g/mastodon",
                                                      "configuration": {"translation": {
                                                          "enabled": True}}})
        self.assertEqual((c.max_characters, c.max_media, c.max_poll_options),
                         (5000, 8, 6))
        self.assertTrue(c.markdown and c.translation)
        self.assertEqual(c.streaming, "wss://s.test")
        self.assertEqual((c.image_bytes, c.image_pixels), (100, 200))
        self.assertTrue(c.software_sure)
        d = api_mod.capabilities_from_instance({"max_toot_chars": 1000}, "not a dict")
        self.assertEqual((d.max_characters, d.max_media), (1000, 4))
        self.assertFalse(d.translation)
        # a profile's fields: Mastodon says nothing (4), GoToSocial and Akkoma say theirs
        self.assertEqual(d.max_profile_fields, 4)
        gts = api_mod.capabilities_from_instance(
            {"configuration": {"accounts": {"max_profile_fields": 6}}}, {})
        akkoma = api_mod.capabilities_from_instance(
            {"pleroma": {"metadata": {"fields_limits": {"max_fields": 10}}}}, {})
        self.assertEqual((gts.max_profile_fields, akkoma.max_profile_fields), (6, 10))

    def test_instance_v2_missing_is_none(self):
        a, _s = make(Resp(404, {"error": "nope"}))
        self.assertIsNone(a.instance_v2())

    def test_flatten_groups(self):
        resp = {"accounts": [{"id": "A"}, {"id": "B"}, "junk"],
                "statuses": [{"id": "S"}],
                "notification_groups": [
                    {"group_key": "g1", "most_recent_notification_id": 9, "type": "favourite",
                     "notifications_count": 300, "sample_account_ids": ["B", "A", "Z"],
                     "status_id": "S", "latest_page_notification_at": "2026-01-01"},
                    {"group_key": "g2", "most_recent_notification_id": 8, "type": "follow",
                     "sample_account_ids": [], "report": {"id": "r"}},
                    {"no": "id"}, "junk"]}
        out = api_mod.flatten_groups(resp)
        self.assertEqual([n["id"] for n in out], ["9", "8"])
        self.assertEqual(out[0]["_group"]["count"], 300)
        self.assertEqual([x["id"] for x in out[0]["_group"]["accounts"]], ["B", "A"])
        self.assertEqual(out[0]["account"]["id"], "B")
        self.assertEqual(out[0]["status"]["id"], "S")
        self.assertEqual(out[1]["account"], {})
        self.assertEqual(out[1]["report"], {"id": "r"})
        self.assertEqual(api_mod.flatten_groups(None), [])


# (call, method, path, what the request must carry: {"params"|"json"|"data": {...}})
CALLS = [
    (lambda a: a.register_app(), "POST", "/api/v1/apps",
     {"data": {"redirect_uris": api_mod.OOB, "scopes": "read write"}}),
    (lambda a: a.revoke("cid", "sec", "T"), "POST", "/oauth/revoke",
     {"data": {"client_id": "cid", "token": "T"}}),
    (lambda a: a.verify_credentials(), "GET", "/api/v1/accounts/verify_credentials", {}),
    (lambda a: a.me(), "GET", "/api/v1/accounts/verify_credentials", {}),
    (lambda a: a.instance(), "GET", "/api/v1/instance", {}),
    (lambda a: a.instance_v2(), "GET", "/api/v2/instance", {}),
    (lambda a: a.home(20, "9", "1"), "GET", "/api/v1/timelines/home",
     {"params": {"limit": 20, "max_id": "9", "min_id": "1"}}),
    (lambda a: a.local(), "GET", "/api/v1/timelines/public",
     {"params": {"local": "true", "limit": 40}}),
    (lambda a: a.federated(), "GET", "/api/v1/timelines/public", {"params": {"limit": 40}}),
    (lambda a: a.account_statuses("7"), "GET", "/api/v1/accounts/7/statuses", {}),
    (lambda a: a.notification_policy(), "GET", "/api/v2/notifications/policy", {}),
    (lambda a: a.set_notification_policy(for_not_following="filter"), "PATCH",
     "/api/v2/notifications/policy", {"data": {"for_not_following": "filter"}}),
    (lambda a: a.notification_requests(), "GET", "/api/v1/notifications/requests", {}),
    (lambda a: a.answer_notification_request("r1", True), "POST",
     "/api/v1/notifications/requests/r1/accept", {}),
    (lambda a: a.answer_notification_request("r1", False), "POST",
     "/api/v1/notifications/requests/r1/dismiss", {}),
    (lambda a: a.announcements(), "GET", "/api/v1/announcements", {}),
    (lambda a: a.dismiss_announcement("5"), "POST", "/api/v1/announcements/5/dismiss", {}),
    (lambda a: a.scheduled(), "GET", "/api/v1/scheduled_statuses", {}),
    (lambda a: a.cancel_scheduled("5"), "DELETE", "/api/v1/scheduled_statuses/5", {}),
    (lambda a: a.domain_blocks(), "GET", "/api/v1/domain_blocks", {}),
    (lambda a: a.block_domain("bad.test"), "POST", "/api/v1/domain_blocks",
     {"params": {"domain": "bad.test"}}),
    (lambda a: a.block_domain("bad.test", False), "DELETE", "/api/v1/domain_blocks",
     {"params": {"domain": "bad.test"}}),
    (lambda a: a.set_note("7", "hi"), "POST", "/api/v1/accounts/7/note",
     {"json": {"comment": "hi"}}),
    (lambda a: a.translate("5", "ru"), "POST", "/api/v1/statuses/5/translate",
     {"json": {"lang": "ru"}}),
    (lambda a: a.translate("5"), "POST", "/api/v1/statuses/5/translate", {"json": None}),
    (lambda a: a.report("7", ["5"], "spam", True), "POST", "/api/v1/reports",
     {"json": {"account_id": "7", "status_ids": ["5"], "forward": True}}),
    (lambda a: a.pinned("7"), "GET", "/api/v1/accounts/7/statuses",
     {"params": {"pinned": "true"}}),
    (lambda a: a.custom_emojis(), "GET", "/api/v1/custom_emojis", {}),
    (lambda a: a.featured_tags("7"), "GET", "/api/v1/accounts/7/featured_tags", {}),
    (lambda a: a.endorsements("7"), "GET", "/api/v1/accounts/7/endorsements", {}),
    (lambda a: a.pin("5"), "POST", "/api/v1/statuses/5/pin", {}),
    (lambda a: a.pin("5", False), "POST", "/api/v1/statuses/5/unpin", {}),
    (lambda a: a.mentions(), "GET", "/api/v1/notifications",
     {"params": {"types[]": ["mention"]}}),
    (lambda a: a.notifications(("favourite", "follow")), "GET", "/api/v1/notifications",
     {"params": {"types[]": ["favourite", "follow"]}}),
    (lambda a: a.notification_groups(("favourite",)), "GET", "/api/v2/notifications",
     {"params": {"types[]": ["favourite"],
                 "grouped_types[]": ["favourite", "reblog", "follow"]}}),
    (lambda a: a.dismiss_notification_group("ungrouped-1"), "POST",
     "/api/v2/notifications/ungrouped-1/dismiss", {}),
    (lambda a: a.status("5"), "GET", "/api/v1/statuses/5", {}),
    (lambda a: a.context("5"), "GET", "/api/v1/statuses/5/context", {}),
    (lambda a: a.async_refresh("R"), "GET", "/api/v1_alpha/async_refreshes/R", {}),
    (lambda a: a.follow_requests(), "GET", "/api/v1/follow_requests", {}),
    (lambda a: a.relationship("7"), "GET", "/api/v1/accounts/relationships",
     {"params": {"id[]": ["7"]}}),
    (lambda a: a.follow("7"), "POST", "/api/v1/accounts/7/follow", {}),
    (lambda a: a.follow("7", False), "POST", "/api/v1/accounts/7/unfollow", {}),
    (lambda a: a.tag_timeline("c++"), "GET", "/api/v1/timelines/tag/c%2B%2B", {}),
    (lambda a: a.relationships(["1", "2"]), "GET", "/api/v1/accounts/relationships",
     {"params": {"id[]": ["1", "2"]}}),
    (lambda a: a.tag("fedi"), "GET", "/api/v1/tags/fedi", {}),
    (lambda a: a.follow_tag("fedi"), "POST", "/api/v1/tags/fedi/follow", {}),
    (lambda a: a.follow_tag("fedi", False), "POST", "/api/v1/tags/fedi/unfollow", {}),
    (lambda a: a.markers(), "GET", "/api/v1/markers",
     {"params": {"timeline[]": ["home", "notifications"]}}),
    (lambda a: a.set_markers({"home": "9"}), "POST", "/api/v1/markers",
     {"data": {"home[last_read_id]": "9"}}),
    (lambda a: a.followed_tags(), "GET", "/api/v1/followed_tags", {}),
    (lambda a: a.account("7"), "GET", "/api/v1/accounts/7", {}),
    (lambda a: a.search("@bob@x.test", "accounts", False), "GET", "/api/v2/search",
     {"params": {"q": "@bob@x.test", "type": "accounts", "resolve": "false"}}),
    (lambda a: a.search("x"), "GET", "/api/v2/search", {"params": {"resolve": "true"}}),
    (lambda a: a.mute("7"), "POST", "/api/v1/accounts/7/mute", {}),
    (lambda a: a.mute("7", False), "POST", "/api/v1/accounts/7/unmute", {}),
    (lambda a: a.block("7"), "POST", "/api/v1/accounts/7/block", {}),
    (lambda a: a.block("7", False), "POST", "/api/v1/accounts/7/unblock", {}),
    (lambda a: a.filters(), "GET", "/api/v2/filters", {}),
    (lambda a: a.create_filter("t", ["w1", "w2"], "hide", ("home",)), "POST",
     "/api/v2/filters", {"data": {"title": "t", "filter_action": "hide",
                                  "context[]": ["home"],
                                  "keywords_attributes[1][keyword]": "w2",
                                  "keywords_attributes[0][whole_word]": "true"}}),
    (lambda a: a.delete_filter("3"), "DELETE", "/api/v2/filters/3", {}),
    (lambda a: a.lists(), "GET", "/api/v1/lists", {}),
    (lambda a: a.list_timeline("L"), "GET", "/api/v1/timelines/list/L", {}),
    (lambda a: a.create_list("Friends", True), "POST", "/api/v1/lists",
     {"data": {"title": "Friends", "exclusive": "true"}}),
    (lambda a: a.update_list("L", "F", False), "PUT", "/api/v1/lists/L",
     {"data": {"title": "F", "exclusive": "false"}}),
    (lambda a: a.delete_list("L"), "DELETE", "/api/v1/lists/L", {}),
    (lambda a: a.list_add("L", "7"), "POST", "/api/v1/lists/L/accounts",
     {"data": {"account_ids[]": ["7"]}}),
    (lambda a: a.list_remove("L", "7"), "DELETE", "/api/v1/lists/L/accounts",
     {"data": {"account_ids[]": ["7"]}}),
    (lambda a: a.edit_status("5", "new", "cw", ["m"], True), "PUT", "/api/v1/statuses/5",
     {"json": {"status": "new", "spoiler_text": "cw", "media_ids": ["m"],
               "content_type": "text/markdown"}}),
    (lambda a: a.status_source("5"), "GET", "/api/v1/statuses/5/source", {}),
    (lambda a: a.status_history("5"), "GET", "/api/v1/statuses/5/history", {}),
    (lambda a: a.delete_status("5"), "DELETE", "/api/v1/statuses/5", {}),
    (lambda a: a.favourite("5"), "POST", "/api/v1/statuses/5/favourite", {}),
    (lambda a: a.favourite("5", False), "POST", "/api/v1/statuses/5/unfavourite", {}),
    (lambda a: a.poll("P"), "GET", "/api/v1/polls/P", {}),
    (lambda a: a.vote("P", (0, 2)), "POST", "/api/v1/polls/P/votes",
     {"json": {"choices": [0, 2]}}),
    (lambda a: a.bookmark("5"), "POST", "/api/v1/statuses/5/bookmark", {}),
    (lambda a: a.bookmark("5", False), "POST", "/api/v1/statuses/5/unbookmark", {}),
    (lambda a: a.notify_posts("7", False), "POST", "/api/v1/accounts/7/follow",
     {"json": {"notify": False}}),
    (lambda a: a.follow_options("7", reblogs=False, languages=["ru"]), "POST",
     "/api/v1/accounts/7/follow", {"json": {"reblogs": False, "languages": ["ru"]}}),
    (lambda a: a.follow_options("7"), "POST", "/api/v1/accounts/7/follow", {"json": {}}),
    (lambda a: a.reblog("5"), "POST", "/api/v1/statuses/5/reblog", {}),
    (lambda a: a.reblog("5", False), "POST", "/api/v1/statuses/5/unreblog", {}),
    (lambda a: a.authorize_follow("7"), "POST", "/api/v1/follow_requests/7/authorize", {}),
    (lambda a: a.reject_follow("7"), "POST", "/api/v1/follow_requests/7/reject", {}),
    (lambda a: a.revoke_quote("5", "6"), "POST", "/api/v1/statuses/5/quotes/6/revoke", {}),
    (lambda a: a.mute_conversation("5"), "POST", "/api/v1/statuses/5/mute", {}),
    (lambda a: a.mute_conversation("5", False), "POST", "/api/v1/statuses/5/unmute", {}),
    (lambda a: a.conversations(10), "GET", "/api/v1/conversations", {"params": {"limit": 10}}),
    (lambda a: a.read_conversation("C"), "POST", "/api/v1/conversations/C/read", {}),
    (lambda a: a.dismiss_notification("N"), "POST", "/api/v1/notifications/N/dismiss", {}),
    (lambda a: a.clear_notifications(), "POST", "/api/v1/notifications/clear", {}),
    (lambda a: a.notifications_unread(), "GET", "/api/v1/notifications/unread_count", {}),
    (lambda a: a.remove_from_followers("7"), "POST",
     "/api/v1/accounts/7/remove_from_followers", {}),
    (lambda a: a.endorse("7"), "POST", "/api/v1/accounts/7/endorse", {}),
    (lambda a: a.endorse("7", False), "POST", "/api/v1/accounts/7/unendorse", {}),
    (lambda a: a.my_featured_tags(), "GET", "/api/v1/featured_tags", {}),
    (lambda a: a.feature_tag("#fedi"), "POST", "/api/v1/featured_tags",
     {"data": {"name": "fedi"}}),
    (lambda a: a.unfeature_tag("3"), "DELETE", "/api/v1/featured_tags/3", {}),
    (lambda a: a.familiar_followers(["1"]), "GET", "/api/v1/accounts/familiar_followers",
     {"params": {"id[]": ["1"]}}),
    (lambda a: a.suggestions(), "GET", "/api/v2/suggestions", {}),
    (lambda a: a.dismiss_suggestion("7"), "DELETE", "/api/v1/suggestions/7", {}),
    (lambda a: a.directory(40, True), "GET", "/api/v1/directory",
     {"params": {"offset": 40, "local": "true", "order": "active"}}),
    (lambda a: a.trends("tags"), "GET", "/api/v1/trends/tags", {}),
    (lambda a: a.instance_rules(), "GET", "/api/v1/instance/rules", {}),
    (lambda a: a.instance_page("privacy_policy"), "GET", "/api/v1/instance/privacy_policy",
     {}),
    (lambda a: a.preferences(), "GET", "/api/v1/preferences", {}),
    (lambda a: a.react_announcement("5", "🎉"), "PUT",
     "/api/v1/announcements/5/reactions/%F0%9F%8E%89", {}),
    (lambda a: a.react_announcement("5", "🎉", False), "DELETE",
     "/api/v1/announcements/5/reactions/%F0%9F%8E%89", {}),
    (lambda a: a.interaction_requests("5"), "GET", "/api/v1/interaction_requests",
     {"params": {"status_id": "5", "limit": 80}}),
    (lambda a: a.account_statuses("7", exclude_replies=True), "GET",
     "/api/v1/accounts/7/statuses", {"params": {"exclude_replies": "true", "limit": 40}}),
    (lambda a: a.account_statuses("7", only_media=True, tagged="#cats",
                                  exclude_reblogs=True), "GET",
     "/api/v1/accounts/7/statuses",
     {"params": {"only_media": "true", "tagged": "cats", "exclude_reblogs": "true"}}),
    (lambda a: a.mute("7", duration=3600, notifications=False), "POST",
     "/api/v1/accounts/7/mute", {"json": {"duration": 3600, "notifications": False}}),
    (lambda a: a.mute("7"), "POST", "/api/v1/accounts/7/mute",
     {"json": {"notifications": True}}),
    (lambda a: a.create_filter("t", ["w"], "warn", ("home",), expires_in=86400), "POST",
     "/api/v2/filters", {"data": {"expires_in": "86400", "filter_action": "warn"}}),
    (lambda a: a.filter_statuses("F"), "GET", "/api/v2/filters/F/statuses", {}),
    (lambda a: a.filter_status("F", "S"), "POST", "/api/v2/filters/F/statuses",
     {"data": {"status_id": "S"}}),
    (lambda a: a.unfilter_status("X"), "DELETE", "/api/v2/filters/statuses/X", {}),
    (lambda a: a.create_list("Friends", False, replies_policy="followed"), "POST",
     "/api/v1/lists", {"data": {"replies_policy": "followed", "exclusive": "false"}}),
    (lambda a: a.update_list("L", "F", True, replies_policy="none"), "PUT",
     "/api/v1/lists/L", {"data": {"replies_policy": "none", "exclusive": "true"}}),
    (lambda a: a.update_filter("F", title="t", action="hide", contexts=("home",),
                               expires_in=0, add=("w",), remove=("K1",)), "PUT",
     "/api/v2/filters/F", {"data": {"title": "t", "filter_action": "hide", "expires_in": "",
                                    "keywords_attributes[0][keyword]": "w",
                                    "keywords_attributes[1][id]": "K1",
                                    "keywords_attributes[1][_destroy]": "true"}}),
    (lambda a: a.update_media("M", "alt", (0.5, -1)), "PUT", "/api/v1/media/M",
     {"data": {"description": "alt", "focus": "0.50,-1.00"}}),
    (lambda a: a.edit_status("S", "t", media_ids=["M"],
                             media_attributes=[{"id": "M", "description": "d"}]), "PUT",
     "/api/v1/statuses/S", {"json": {"media_attributes": [{"id": "M", "description": "d"}]}}),
    (lambda a: a.report("7", ["S"], rule_ids=[3]), "POST", "/api/v1/reports",
     {"json": {"category": "violation", "rule_ids": ["3"]}}),
    (lambda a: a.update_credentials(hide_collections=True, indexable=False,
                                    attribution_domains=[]), "PATCH",
     "/api/v1/accounts/update_credentials",
     {"data": {"hide_collections": "true", "indexable": "false",
               "attribution_domains[]": [""]}}),
    (lambda a: a.link_timeline("https://x/a"), "GET", "/api/v1/timelines/link",
     {"params": {"url": "https://x/a", "limit": 20}}),
    (lambda a: a.instance_domain_blocks(), "GET", "/api/v1/instance/domain_blocks", {}),
    (lambda a: a.terms_of_service(), "GET", "/api/v1/instance/terms_of_service", {}),
    (lambda a: a.translation_languages(), "GET", "/api/v1/instance/translation_languages",
     {}),
    (lambda a: a.featured_tag_suggestions(), "GET", "/api/v1/featured_tags/suggestions", {}),
    (lambda a: a.push_subscription(), "GET", "/api/v1/push/subscription", {}),
    (lambda a: a.push_subscribe("https://p/e", "K", "A", {"mention": True}), "POST",
     "/api/v1/push/subscription",
     {"json": {"subscription": {"endpoint": "https://p/e", "keys": {"p256dh": "K",
                                                                   "auth": "A"}},
               "data": {"alerts": {"mention": True}, "policy": "all"}}}),
    (lambda a: a.push_unsubscribe(), "DELETE", "/api/v1/push/subscription", {}),
    (lambda a: a.interaction_requests(), "GET", "/api/v1/interaction_requests",
     {"params": {"limit": 80}}),
    (lambda a: a.answer_interaction("Q", True), "POST",
     "/api/v1/interaction_requests/Q/authorize", {}),
    (lambda a: a.answer_interaction("Q", False), "POST",
     "/api/v1/interaction_requests/Q/reject", {}),
]


class ContractTest(unittest.TestCase):
    def test_each_call_makes_its_request(self):
        for i, (call, method, path, carries) in enumerate(CALLS):
            with self.subTest(i=i, path=path):
                a, s = make()
                call(a)
                got_method, got_url, kw = s.last
                got_path = got_url.split("?")[0]
                self.assertEqual((got_method, got_path), (method, path))
                for part, want in carries.items():
                    have = kw.get(part)
                    if want is None:
                        self.assertIsNone(have)
                        continue
                    for k, v in want.items():
                        self.assertEqual((have or {}).get(k), v, f"{part}.{k}")

    def test_ids_never_leave_their_segment(self):
        a, s = make()
        a.status("1/../../accounts/2/follow")
        self.assertEqual(s.last[1], "/api/v1/statuses/1%2F..%2F..%2Faccounts%2F2%2Ffollow")


class AuthTest(unittest.TestCase):
    def test_authorize_url_and_token(self):
        a, s = make(Resp(body={"access_token": "NEW"}))
        url = a.authorize_url("cid")
        self.assertTrue(url.startswith("https://example.test/oauth/authorize?"))
        self.assertIn("response_type=code", url)
        self.assertIn("scope=read+write", url)
        self.assertEqual(a.get_token("cid", "sec", "  CODE \n"), "NEW")
        self.assertEqual(s.last[2]["data"]["code"], "CODE")
        self.assertEqual(s.last[2]["data"]["grant_type"], "authorization_code")

    def test_update_credentials(self):
        with tempfile.TemporaryDirectory() as d:
            pic = Path(d) / "me.png"
            pic.write_bytes(b"\x89PNG")
            a, s = make()
            a.update_credentials(display_name="Me", note="bio", fields=[("site", "x.test")],
                                 locked=True, bot=False, avatar=str(pic))
            method, path, kw = s.last
            self.assertEqual((method, path), ("PATCH", "/api/v1/accounts/update_credentials"))
            self.assertEqual(kw["data"]["display_name"], "Me")
            self.assertEqual(kw["data"]["locked"], "true")
            self.assertEqual(kw["data"]["bot"], "false")
            self.assertNotIn("discoverable", kw["data"])
            self.assertEqual(kw["data"]["fields_attributes[0][value]"], "x.test")
            self.assertEqual(kw["files"]["avatar"][0], "me.png")
            self.assertTrue(kw["files"]["avatar"][1].closed)  # closed after sending
            a.update_credentials(note="only")
            self.assertIsNone(s.last[2]["files"])


class PagingTest(unittest.TestCase):
    def test_get_page_reads_the_link_header(self):
        nxt = {"next": {"url": "https://example.test/api/v1/x?limit=40&max_id=77"}}
        a, s = make(Resp(body=[{"id": "1"}], links=nxt), Resp(body=[], links={}))
        items, cursor = a.following("7")
        self.assertEqual((items, cursor), ([{"id": "1"}], "77"))
        self.assertEqual(a.followers("7", "77"), ([], None))
        self.assertEqual(s.calls[-1][2]["params"]["max_id"], "77")

    def test_get_page_error(self):
        a, _s = make(Resp(404, {"error": "Record not found"}))
        with self.assertRaisesRegex(ApiError, "Record not found"):
            a.favourited_by("5")

    def test_reacted_and_quotes(self):
        a, s = make()
        a.reblogged_by("5", "c")
        self.assertTrue(s.calls[-1][1].endswith("/api/v1/statuses/5/reblogged_by"))
        a.quotes("5")
        self.assertEqual(s.calls[-1][2]["params"]["limit"], 40)

    def test_all_pages_stop_at_a_short_page(self):
        full = [{"id": str(i)} for i in range(80)]
        a, s = make(Resp(body=full, links={"next": {"url": "?max_id=5"}}),
                    Resp(body=[{"id": "x"}], links={"next": {"url": "?max_id=1"}}))
        self.assertEqual(len(a.mutes()), 81)
        self.assertEqual(len(s.calls), 2)
        a, s = make(Resp(body=full, links={}))
        self.assertEqual(len(a.blocks()), 80)
        self.assertEqual(len(s.calls), 1)

    def test_bookmarks_and_favourites_keep_the_cursor(self):
        a, _s = make(Resp(body=[{"id": "1"}], links={"next": {"url": "?max_id=B"}}),
                     Resp(body=[], links={}))
        self.assertEqual(a.bookmarks(), [{"id": "1"}])
        self.assertEqual(a.bookmarks_next, "B")
        a.favourites()
        self.assertIsNone(a.favourites_next)

    def test_list_accounts_falls_back_to_pages(self):
        a, _s = make(Resp(body=[{"id": "1"}]))
        self.assertEqual(a.list_accounts("L"), [{"id": "1"}])
        a, s = make(Resp(body=[]),
                    Resp(body=[{"id": "1"}], links={"next": {"url": "?max_id=1"}}),
                    Resp(body=[{"id": "2"}], links={}))
        self.assertEqual([x["id"] for x in a.list_accounts("L")], ["1", "2"])
        self.assertEqual(s.calls[2][2]["params"]["max_id"], "1")
        a, _s = make(Resp(body=[]), Resp(body=[], links={}))
        self.assertEqual(a.list_accounts("L"), [])


class WritingTest(unittest.TestCase):
    def test_post_status_body(self):
        a, s = make(Resp(body={"id": "5"}))
        a.post_status("hi", "public", "4", "cw", ["m1"], True, "ru", True,
                      {"options": ["a", "b"], "expires_in": 60}, "Q", "followers",
                      {"can_reply": {"always": ["me"]}}, "2030-01-01T00:00:00Z", "KEY")
        method, path, kw = s.last
        self.assertEqual((method, path), ("POST", "/api/v1/statuses"))
        body = kw["json"]
        self.assertEqual(body["content_type"], "text/markdown")
        self.assertEqual(body["quoted_status_id"], "Q")
        self.assertEqual(body["quote_approval_policy"], "followers")
        self.assertEqual(body["scheduled_at"], "2030-01-01T00:00:00Z")
        self.assertEqual(body["media_ids"], ["m1"])
        self.assertTrue(body["sensitive"])
        self.assertEqual(body["poll"]["expires_in"], 60)
        self.assertEqual(kw["headers"], {"Idempotency-Key": "KEY"})
        a.post_status("plain")
        self.assertEqual(s.last[2]["json"], {"status": "plain", "visibility": "private"})
        self.assertIsNone(s.last[2]["headers"])

    def test_upload_media_v2_waits_until_processed(self):
        with tempfile.TemporaryDirectory() as d:
            pic = Path(d) / "cat.jpg"
            pic.write_bytes(b"jpeg")
            a, s = make(Resp(202, {"id": "M", "url": None}),
                        Resp(body={"id": "M", "url": "https://x/cat.jpg"}))
            real_sleep = api_mod.time.sleep
            api_mod.time.sleep = lambda _s: None
            try:
                media = a.upload_media(str(pic), "a cat", (0.5, -0.25))
            finally:
                api_mod.time.sleep = real_sleep
            self.assertEqual(media["url"], "https://x/cat.jpg")
            first = s.calls[0]
            self.assertTrue(first[1].endswith("/api/v2/media"))
            self.assertEqual(first[2]["data"], {"description": "a cat",
                                                "focus": "0.50,-0.25"})
            self.assertEqual(first[2]["files"]["file"][2], "image/jpeg")
            self.assertTrue(s.calls[1][1].endswith("/api/v1/media/M"))

    def test_upload_media_v1_on_old_servers(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "x.unknownext"
            f.write_bytes(b"?")
            a, s = make(Resp(404, {"error": "no"}), Resp(body={"id": "M", "url": "u"}))
            self.assertEqual(a.upload_media(str(f))["url"], "u")
            self.assertTrue(s.calls[1][1].endswith("/api/v1/media"))
            self.assertEqual(s.calls[1][2]["data"], {})
            self.assertEqual(s.calls[1][2]["files"]["file"][2], "application/octet-stream")
            a, _s = make(Resp(500, {"error": "boom"}))
            with self.assertRaises(ApiError):
                a.upload_media(str(f))

    def test_endorse_falls_back_to_pin(self):
        a, s = make(Resp(404, {"error": "no"}), Resp(body={}))
        a.endorse("7")
        self.assertTrue(s.calls[-1][1].endswith("/api/v1/accounts/7/pin"))
        a, s = make(Resp(404, {"error": "no"}), Resp(body={}))
        a.endorse("7", False)
        self.assertTrue(s.calls[-1][1].endswith("/api/v1/accounts/7/unpin"))
        a, _s = make(Resp(403, {"error": "forbidden"}))
        with self.assertRaises(ApiError):
            a.endorse("7")

    def test_async_refresh(self):
        a, _s = make(Resp(body={}, headers={
            "Mastodon-Async-Refresh": 'id="R1", retry=7, result_count=3'}))
        a.context("5")
        self.assertEqual(a.last_async_refresh(), ("R1", 7))
        a, _s = make(Resp(body={}, headers={"Mastodon-Async-Refresh": 'id="R2"'}))
        a.context("5")
        self.assertEqual(a.last_async_refresh(), ("R2", 3))
        a, _s = make(Resp(body={}, headers={"Mastodon-Async-Refresh": "nonsense"}))
        a.context("5")
        self.assertIsNone(a.last_async_refresh())
        a, _s = make()
        self.assertIsNone(a.last_async_refresh())  # nothing asked yet in this thread
        a, _s = make(Resp(body={"async_refresh": {"status": "running"}}), Resp(body=None))
        self.assertEqual(a.async_refresh("R"), "running")
        self.assertEqual(a.async_refresh("R"), "finished")

    def test_relationship_of_nobody(self):
        a, _s = make(Resp(body=[]))
        self.assertEqual(a.relationship("7"), {})
        a, _s = make(Resp(body=[{"id": "7", "following": True}]))
        self.assertTrue(a.relationship("7")["following"])

    def test_empty_answers_become_empty_lists(self):
        for name, args in (("notification_requests", ()), ("announcements", ()),
                           ("scheduled", ()), ("domain_blocks", ()), ("pinned", ("7",)),
                           ("custom_emojis", ()), ("filters", ()), ("lists", ()),
                           ("conversations", ()), ("suggestions", ()), ("directory", ()),
                           ("trends", ("tags",)), ("instance_rules", ()),
                           ("followed_tags", ()), ("status_history", ("5",))):
            a, _s = make(Resp(body=None))
            self.assertEqual(getattr(a, name)(*args), [], name)
        for name, args in (("markers", ()), ("search", ("x",)), ("preferences", ()),
                           ("notifications_unread", ()), ("instance_page", ("rules",))):
            a, _s = make(Resp(body=None))
            self.assertEqual(getattr(a, name)(*args), {}, name)


if __name__ == "__main__":
    unittest.main()
