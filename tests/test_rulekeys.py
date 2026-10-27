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
