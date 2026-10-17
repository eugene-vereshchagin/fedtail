"""core/social.py against the fake server: who reacted (here and at the post's home),
quiet threads, conversations read in step, notifications dismissed, followers removed,
recommendations, people in common, suggestions, directory, trends, the server's pages
and preferences, quotes of my posts — and what happens on a server without them."""

import unittest

from fedtail.core import config, paths
from fedtail.core.api import ApiError
from fedtail.core.app import Core
from fedtail.core.social import NotSupported

from . import fakes
from .fakes import BOB, ME, NEWS, FakeApi, status
from .test_core import TmpDir


class SocialTest(TmpDir):
    def make(self, missing=(), **over):
        FakeApi.world = fakes.World()
        FakeApi.world.missing = set(missing)
        user = {"feed": {"first_run_mark_read": False}}
        for k, v in over.items():
            user.setdefault(k, {}).update(v)
        cfg, _ = config.validate(user)
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        from fedtail.core import auth
        auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
        core = Core(cfg, p, api_class=FakeApi)
        core._origin_json = lambda url: None
        self.addCleanup(core.shutdown)
        core.connect().result()
        return core, FakeApi.world

    def test_who_liked_and_boosted(self):
        core, w = self.make()
        st = w.add(status("100", ME, minute=1, vis="public"), home=True)
        w.reactions["100"] = {"favourited_by": [BOB, NEWS], "reblogged_by": [BOB]}
        got, nxt = core.who_reacted(st, "favourited_by").result()
        self.assertEqual([a["id"] for a in got["accounts"]], ["B", "N"])
        self.assertIsNone(nxt)
        got, _ = core.who_reacted(st, "reblogged_by").result()
        self.assertEqual([a["id"] for a in got["accounts"]], ["B"])

    def test_who_liked_at_the_posts_home(self):
        """My server knows only who reached it; the post's own server knows everyone."""
        core, w = self.make()
        far = fakes.acct("F", "far@social.example")
        w.add(status("190", far, minute=1), home=True)  # my server knows far
        st = dict(status("101", BOB, minute=1, vis="public"),
                  uri="https://social.example/users/bob/statuses/777")
        asked = []

        def origin(url):
            asked.append(url)
            return [{"acct": "far"}, {"acct": "nobody"}]
        core._origin_get = origin
        got, _ = core.who_reacted_from_origin(st, "favourited_by").result()
        self.assertEqual(asked, ["https://social.example/api/v1/statuses/777/favourited_by"
                                 "?limit=80"])
        self.assertEqual([a["id"] for a in got["accounts"]], ["F"])  # found through mine
        self.assertEqual(got["total"], 2)
        # a post from my own server: nothing to ask elsewhere
        mine = status("102", ME, minute=1, vis="public")
        got, _ = core.who_reacted_from_origin(mine, "favourited_by").result()
        self.assertEqual(got["accounts"], [])

    def test_mute_thread(self):
        core, w = self.make()
        st = w.add(status("110", BOB, minute=1), home=True)
        core.poll_once()
        seen = []
        core.events.on("status_updated", lambda _n, p: seen.append(p["id"]))
        core.mute_thread(st, True).result()
        self.assertTrue(core.store.get_status("110")["muted"])
        self.assertEqual(seen, ["110"])

    def test_conversations_read_here_read_there(self):
        core, w = self.make()
        dm = w.add(status("120", BOB, minute=1, vis="direct"), home=True)
        w.conversations.append({"id": "c1", "unread": True, "accounts": [BOB],
                                "last_status": dm})
        core.poll_once()
        core.mark_read(["120"])
        core.bg.submit(lambda: None).result()  # the read went out in the background
        self.assertEqual(w.read_conversations, ["c1"])
        core.mark_read(["120"])  # once is enough
        core.bg.submit(lambda: None).result()
        self.assertEqual(w.read_conversations, ["c1"])

    def test_dismiss_and_clear_activity(self):
        core, w = self.make()
        for i in range(3):
            w.act(f"a{i}", "favourite", BOB, minute=i)
        core.poll_once()
        self.assertEqual(len(core.store.activity_recent(10)), 3)
        core.dismiss_activity("a1").result()
        self.assertEqual({n["id"] for n in core.store.activity_recent(10)}, {"a0", "a2"})
        self.assertEqual({n["id"] for n in w.activity}, {"a0", "a2"})
        core.clear_activity().result()
        self.assertEqual(core.store.activity_recent(10), [])
        self.assertEqual(w.activity, [])

    def test_people_and_profile(self):
        core, w = self.make()
        w.followers.add("B")
        rel = core.remove_follower("B").result()
        self.assertFalse(rel["followed_by"])
        self.assertNotIn("B", w.followers)
        core.endorse("B", True).result()
        self.assertIn("B", w.endorsed)
        core.endorse("B", False).result()
        self.assertNotIn("B", w.endorsed)
        core.feature_tag("#linux").result()
        self.assertEqual(core.featured_tag_names().result(), {"linux"})
        core.feature_tag("linux", False).result()
        self.assertEqual(core.featured_tag_names().result(), set())
        w.familiar["N"] = [BOB]
        self.assertEqual([a["id"] for a in core.familiar("N").result()], ["B"])
        w.suggested = [BOB, NEWS]
        got, _ = core.suggestions().result()
        self.assertEqual([a["id"] for a in got["accounts"]], ["B", "N"])
        core.dismiss_suggestion("B").result()
        self.assertEqual([a["id"] for a in w.suggested], ["N"])
        w.directory = [BOB, NEWS, ME]
        got, nxt = core.directory().result()
        self.assertEqual((len(got["accounts"]), nxt), (3, 3))
        got, nxt = core.directory(nxt).result()
        self.assertEqual((got["accounts"], nxt), ([], None))

    def test_trends_server_preferences(self):
        core, w = self.make()
        w.trends = {"statuses": [status("130", BOB, vis="public")],
                    "tags": [{"name": "linux"}], "links": []}
        got = core.trends().result()
        self.assertEqual([s["id"] for s in got["statuses"]], ["130"])
        self.assertIsNotNone(core.store.get_status("130"))
        info = core.server_info().result()
        self.assertEqual(info["rules"][0]["text"], "Be kind")
        self.assertIn("extended_description", info["about"])
        self.assertEqual(core.server_prefs["posting:default:visibility"], "public")
        core.react_announcement("an1", "👍").result()
        self.assertEqual(w.reacted, [("an1", "👍", True)])

    def test_quotes_of_my_post(self):
        core, w = self.make()
        mine = w.add(status("140", ME, minute=1, vis="public"), home=True)
        q = w.add(dict(status("141", BOB, minute=2, vis="public"),
                       quote={"state": "accepted", "quoted_status": mine}), home=True)
        w.quotes["140"] = [q]
        got, _ = core.quotes_of(mine).result()
        self.assertEqual([s["id"] for s in got], ["141"])
        st = core.revoke_quote(mine, q).result()
        self.assertEqual(st["quote"]["state"], "revoked")
        self.assertEqual(core.quotes_of(mine).result()[0], [])

    def test_pins_from_their_own_server(self):
        """Someone my server knows little about: their pins as their server lists them."""
        core, w = self.make()
        pin = dict(status("160", BOB, minute=1, vis="public"),
                   uri="https://social.example/objects/160")
        w.remote[pin["uri"]] = pin
        core.api.get = lambda path, params=None: dict(BOB, uri="https://social.example/u/bob")
        objs = {"https://social.example/u/bob": {"featured": "https://social.example/u/bob/f"},
                "https://social.example/u/bob/f": {"type": "OrderedCollection",
                                                   "orderedItems": [pin["uri"]]}}
        core._origin_json = objs.get
        got = core.pinned("B").result()
        self.assertEqual([st["id"] for st in got], ["160"])
        self.assertTrue(got[0]["pinned"])
        core.cfg["feed"]["remote_profiles"] = False
        self.assertEqual(core.pinned("B").result(), [])

    def test_counters_through_my_other_accounts(self):
        """The author's server won't tell a stranger: ask as my account there, or as an
        account on a server that has the post; each token only to its own server."""
        from unittest import mock
        core, w = self.make(feed={"honest_counters": True})
        st = w.add(dict(status("170", BOB, minute=1, vis="public"),
                        uri="https://social.example/users/bob/statuses/170",
                        favourites_count=1), home=True)
        core.poll_once()
        core._origin_get = lambda url: None  # anonymous: refused
        core._other_accounts = lambda: [("https://social.example", "T1"),
                                        ("https://other.example", "T2")]
        sent = []

        class R:
            def __init__(self, data):
                self.status_code, self._d = 200, data

            def json(self):
                return self._d

        def get(url, headers=None, params=None, timeout=None):
            sent.append((url.split("/")[2], headers["Authorization"]))
            if url.startswith("https://social.example/"):
                return R(dict(st, favourites_count=7))
            return R({"statuses": [dict(st, favourites_count=4)]})
        with mock.patch("requests.get", get):
            core._honest_counts([st])
        self.assertEqual(core.store.get_status("170")["favourites_count"], 7)
        self.assertEqual(sorted(sent), [("other.example", "Bearer T2"),
                                        ("social.example", "Bearer T1")])

    def test_a_server_without_it(self):
        """404: the feature is remembered as missing and frontends are told."""
        core, w = self.make()
        w.missing = {"favourited_by", "trends_statuses", "trends_tags", "trends_links",
                     "suggestions"}
        told = []
        core.events.on("unsupported", lambda _n, p: told.append(p))
        st = w.add(status("150", BOB, vis="public"), home=True)
        with self.assertRaises(NotSupported):
            core.who_reacted(st, "favourited_by").result()
        self.assertFalse(core.supports("favourited_by"))
        self.assertTrue(core.supports("reblogged_by"))
        with self.assertRaises(NotSupported):
            core.trends().result()
        with self.assertRaises(ApiError):  # NotSupported is an ApiError: handled as such
            core.suggestions().result()
        self.assertEqual(told, ["favourited_by", "trends_statuses", "trends_tags",
                                "trends_links", "suggestions"])

    def test_no_preferences_no_trouble(self):
        core, _w = self.make(missing={"preferences"})
        self.assertEqual(core.server_prefs, {})
        self.assertTrue(core.me)


if __name__ == "__main__":
    unittest.main()
