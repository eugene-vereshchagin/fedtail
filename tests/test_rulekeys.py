"""The keys of a lane's rule that say how it is read: sort, mode = "catch_up" / window,
filter_context (docs/en/dev/feeds.md §4)."""

from datetime import UTC, datetime, timedelta

from .fakes import BOB, status
from .test_custom import FreeBase


def at(hours_ago):
    return (datetime.now(UTC) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def post(i, hours_ago, likes=0, boosts=0, replies=0, text="text"):
    st = status(i, BOB, text=text)
    st.update(created_at=at(hours_ago), favourites_count=likes, reblogs_count=boosts,
              replies_count=replies)
    return st


class RuleKeysTest(FreeBase):
    def lane(self, **keys):
        rule = dict({"name": "x", "source": "home", "any": [{}]}, **keys)
        core, w = self.make([rule])
        core.cfg["lanes"]["enabled"] = ["x"]
        core._apply_lists([], {})
        w.add(post("001", 30, likes=50), home=True)
        w.add(post("002", 5, likes=3, replies=9), home=True)
        w.add(post("003", 1, likes=10, boosts=1), home=True)
        core.connect().result()
        core.poll_once()
        return core, w

    def ids(self, core):
        return [st["id"] for _i, st in core.lane_entries("x")]

    def test_sort_by_likes_best_where_reading_starts(self):
        core, _w = self.lane(sort="likes")
        core.cfg["feed"]["order"] = "oldest_first"
        core._lane_cache.clear()
        self.assertEqual(self.ids(core), ["001", "003", "002"])
        core.cfg["feed"]["order"] = "newest_first"  # the window turns it round
        core._lane_cache.clear()
        self.assertEqual(self.ids(core), ["002", "003", "001"])

    def test_replies_and_density(self):
        core, _w = self.lane(sort="replies")
        core.cfg["feed"]["order"] = "oldest_first"
        core._lane_cache.clear()
        self.assertEqual(self.ids(core)[0], "002")
        core, _w = self.lane(sort="density")
        core.cfg["feed"]["order"] = "oldest_first"
        core._lane_cache.clear()
        self.assertEqual(self.ids(core)[0], "003")  # 11 in an hour beats 50 in 30 hours

    def test_catch_up_window(self):
        core, _w = self.lane(mode="catch_up")  # 12 hours by default
        self.assertEqual(sorted(self.ids(core)), ["002", "003"])
        core, _w = self.lane(window="2h")
        self.assertEqual(self.ids(core), ["003"])

    def test_filter_context(self):
        core, w = self.lane(filter_context="public")
        w.add(post("004", 1, text="crypto news"), home=True)
        w.add(post("005", 1, text="cryptography"), home=True)
        w.add(post("006", 1, text="football"), home=True)
        core.poll_once()
        core._server_filters = [
            {"id": "f1", "title": "noise", "context": ["public"], "filter_action": "hide",
             "keywords": [{"keyword": "crypto", "whole_word": True}]},
            {"id": "f2", "title": "sport", "context": ["public"], "filter_action": "warn",
             "keywords": [{"keyword": "foot", "whole_word": False}]},
            {"id": "f3", "title": "home only", "context": ["home"], "filter_action": "hide",
             "keywords": [{"keyword": "text", "whole_word": True}]}]
        core._silence_version += 1
        got = {st["id"]: st for _i, st in core.lane_entries("x")}
        self.assertNotIn("004", got)          # hidden in this context
        self.assertIn("005", got)             # whole word only
        self.assertEqual(got["006"]["filtered"][0]["filter"]["title"], "sport")  # folded
        self.assertIn("001", got)             # a home filter isn't this lane's


class OncePerPostTest(FreeBase):
    """A post in several lanes notified about is said once, by the most personal lane."""

    def test_most_personal_lane(self):
        from .fakes import ME
        core, w = self.make([])
        core.cfg["notify"]["lanes"] = ["home", "to_me", "direct"]
        core.cfg["notify"]["except"] = []
        core.connect().result()
        core.poll_once()
        got = []
        core.events.on("notify", lambda _n, pl: got.extend(pl))
        reply = status("950", BOB, reply_to="900", reply_acc="ME", minute=5, vis="public")
        w.add(status("900", ME, minute=1, vis="public"), home=True)
        w.add(reply, home=True, mention=True)  # in Home and in To me
        core.poll_once()
        lanes_of = [n for n, st in got if st.get("id") == "950"]
        self.assertEqual(lanes_of, ["to_me"])
        self.assertLess(core.lane_rank("direct"), core.lane_rank("to_me"))
        self.assertLess(core.lane_rank("to_me"), core.lane_rank("home"))


class WhyTest(FreeBase):
    """"Why is it here?" and --explain-lane: which condition took a post, or what didn't
    match."""

    def test_explain_post_and_place(self):
        from fedtail.core.view import View
        from fedtail.frontends.common.places import Places

        from .fakes import NEWS
        core, w = self.make([])
        w.add(status("700", BOB, minute=1), home=True)
        w.add(status("701", NEWS, minute=2), home=True)  # a bot
        core.connect().result()
        core.poll_once()
        got = {g["lane"]: g for g in core.explain_post("701")}
        self.assertTrue(got["bots"]["taken"])
        self.assertTrue(got["bots"]["in_lane"])
        self.assertFalse(got["home"]["in_lane"])
        self.assertIsNotNone(got["home"]["out"])  # Home's "none" keeps bots out
        page = Places(View(core)).page("why", "701")
        rows = {r.key: r for r in page.rows}
        self.assertTrue(rows["bots"].title.startswith("✓"))
        self.assertIn("author", rows["home"].line)

    def test_explain_lane(self):
        from .fakes import NEWS
        core, w = self.make([])
        w.add(status("700", BOB, minute=1), home=True)
        w.add(status("701", NEWS, minute=2), home=True)
        core.connect().result()
        core.poll_once()
        got = core.explain_lane("bots")
        self.assertEqual(got["feeds"], ["home"])
        taken = {r["id"]: r["taken"] for r in got["rows"]}
        self.assertEqual(taken, {"700": False, "701": True})
        self.assertIsNone(core.explain_lane("nope"))


class ParentsFirstTest(FreeBase):
    """A routed lane asking about the parent sorts a reply once its parent is known: the
    parent is fetched before the rules (feeds.md §8, atoms known late)."""

    def test_reply_to_my_post_routed_right(self):
        from .fakes import ME
        rule = {"name": "under_mine", "any": [{"source": ["home", "mentions"],
                                                "me": "reply_to_post"}]}
        core, w = self.make([rule])
        core.cfg["lanes"]["enabled"] = ["under_mine"]
        core._apply_lists([], {})
        mine = status("600", ME, minute=1, vis="public")
        w.statuses["600"] = mine  # on the server, not in my store yet
        core.connect().result()
        core.poll_once()
        self.assertIsNone(core.store.get_status("600"))
        w.add(status("601", BOB, reply_to="600", reply_acc="ME", minute=2), mention=True)
        core.poll_once()
        self.assertIn("601", [st["id"] for _i, st in core.lane_entries("under_mine")])


class MoreSourcesTest(FreeBase):
    """Sources of feeds.md §2.1 for lanes of rules: trends, direct, bubble, account:,
    link:, quotes:, remote:."""

    def lane(self, rule):
        core, w = self.make([dict({"name": "x"}, **rule)])
        core.cfg["lanes"]["enabled"] = ["x"]
        core._apply_lists([], {})
        return core, w

    def ids(self, core):
        return sorted(st["id"] for _i, st in core.lane_entries("x"))

    def test_trends_and_direct(self):
        core, w = self.lane({"source": "trends", "any": [{}]})
        w.trends["statuses"] = [w.add(status("510", BOB, minute=1, vis="public"))]
        core.connect().result()
        core.poll_once()
        self.assertEqual(self.ids(core), ["510"])
        core, w = self.lane({"source": "direct", "any": [{}]})
        dm = w.add(status("520", BOB, minute=1, vis="direct"))
        w.conversations.append({"id": "c1", "unread": True, "accounts": [BOB],
                                "last_status": dm})
        core.connect().result()
        core.poll_once()
        self.assertEqual(self.ids(core), ["520"])

    def test_bubble(self):
        from .fakes import acct
        core, w = self.lane({"source": "bubble", "any": [{}]})
        core.cfg["lanes"]["bubble"] = ["near.example"]
        near = acct("N", "nina@near.example")
        w.local.append(w.add(status("530", near, minute=1, vis="public")))
        w.local.append(w.add(status("531", BOB, minute=2, vis="public")))
        core.connect().result()
        core.poll_once()
        self.assertEqual(self.ids(core), ["530"])

    def test_account_link_quotes(self):
        from .fakes import NEWS
        core, w = self.lane({"source": ["account:B", "quotes:900"], "any": [{}]})
        w.add(status("540", BOB, minute=1, vis="public"), home=True)
        w.add(status("541", NEWS, minute=2, vis="public"), home=True)
        w.quotes["900"] = [w.add(status("542", NEWS, minute=3, vis="public"))]
        core.connect().result()
        core.poll_once()
        core.poll_once()
        self.assertEqual(self.ids(core), ["540", "542"])
        self.assertIn("account:B", core.sources)
        core2, w2 = self.lane({"source": "link:https://news.example/a", "any": [{}]})
        st = status("550", BOB, minute=1, vis="public")
        st["card"] = {"url": "https://news.example/a"}
        w2.add(st, home=True)
        core2.connect().result()
        core2.poll_once()
        core2.poll_once()
        self.assertEqual(self.ids(core2), ["550"])
