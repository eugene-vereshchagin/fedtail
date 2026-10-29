"""What a lane shows (frontends/common/lane.py) against a stand-in View that says
exactly what it is asked: cards with the account they came by, a picture's box and the
size it is decoded at, "as conversations", newest first, a browse lane that came back
empty, the divider, where reading starts, read up to here without times, and the line
under a conversation card."""

import dataclasses
import types
import unittest

from fedtail import i18n
from fedtail.frontends.common import lane
from fedtail.model import Media, Ref
from fedtail.protocols.mastodon.adapter import post as to_post

from .fakes import BOB, status

CFG = {"feed": {"order": "oldest_first", "start_at": "first_unread", "old_days": 30},
       "read": {"mark_read": "on_scroll"},
       "ui": {"image_height": 300, "max_width": 0, "image_decode": "box"}}


def post(i, reply_to=None, **kw):
    p = to_post(status(i, BOB, reply_to, "B" if reply_to else None, minute=int(i) % 60))
    return dataclasses.replace(p, **kw) if kw else p


class View:
    def __init__(self, entries, unread=(), cfg=CFG, name="replies", lazy=False,
                 conversations=None, browse_empty=(), via=None):
        self.cfg = cfg
        self._entries = entries
        self._unread = set(unread)
        self.choices = {}
        self.lane_by_name = {name: types.SimpleNamespace(lazy=lazy, source="src")}
        self._conv = conversations
        self.browse_empty = browse_empty
        self._via = via
        self.ensured, self.checked = [], []

    def entries(self, _name):
        return list(self._entries)

    def lane_rank(self, name):  # the core's, by the rule: here by the preset's
        return {"replies": 1, "mentions": 2, "subs": 3}.get(name, 4)

    def unread(self, entries):
        return {e.id for _i, e in entries if e.id in self._unread}

    def parents(self, posts):
        return {}

    def parent(self, p):
        return "missing"

    def my_replies(self, posts):
        return {}

    def short_ids(self, posts):
        return {p.id: "a" + p.id for p in posts}

    def check_my_replies(self, posts):
        self.checked.append(len(posts))

    def ensure_parents(self, posts):
        self.ensured += [p.id for p in posts]

    def conversations(self, entries, unread):
        return self._conv(entries, unread)

    def via(self, entry):
        return self._via

    def choice(self, key):
        return self.choices.get(key)

    def set_choice(self, key, value):
        self.choices[key] = value

    def posts_only(self, _name):
        return False


class PicturesTest(unittest.TestCase):
    def test_account_color(self):
        c = lane.account_color("Work")
        self.assertRegex(c, r"^#[0-9a-f]{6}$")
        self.assertEqual(c, lane.account_color("work"))
        self.assertNotEqual(c, lane.account_color("play"))

    def test_boxes(self):
        self.assertEqual(lane.thumb_box(0, 0, 100, 300), (100, 100))
        self.assertEqual(lane.thumb_box(200, 100, 100, 300), (200, 100))
        self.assertEqual(lane.thumb_box(1, 100, 100, 300), (24, 100))
        self.assertEqual(lane.thumb_box(1000, 100, 100, 300), (300, 30))
        one = (Media(Ref("m", "", "m1"), kind="image", url="u"),)
        self.assertEqual(lane.card_boxes(one, CFG), (300, 840))
        self.assertEqual(lane.card_boxes(one * 2, CFG), (150, 230))
        self.assertEqual(lane.card_boxes((), CFG, small=(1, 2)), (1, 2))

    def test_decode_side(self):
        self.assertEqual(lane.decode_side(200, 100, 400, 100, CFG), 400)  # filled
        self.assertEqual(lane.decode_side(200, 100, 400, 100, CFG, dpr=2), 800)
        self.assertEqual(lane.decode_side(200, 100, 400, 100, CFG, dpr=4), 1200)  # at most
        self.assertEqual(lane.decode_side(30, 30, 0, 0, CFG), 100)
        self.assertEqual(lane.decode_side(150, 230, 0, 0, CFG), 500)
        full = {"ui": {"image_decode": "full"}}
        self.assertIsNone(lane.decode_side(1, 1, 1, 1, full))


class LaneModelTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_cards_carry_the_account_and_ask_for_parents(self):
        a, b = post("1"), post("2", reply_to="0")
        v = View([("i1", a), ("i2", b)], unread={"2"}, via="@w@y.test")
        built = lane.LaneModel(v, "replies").build(positioned=False)
        self.assertEqual(built.specs[0].extra["via"], "@w@y.test")
        self.assertEqual(v.ensured, ["2"])  # its parent isn't known: asked for
        self.assertEqual(v.checked, [2])  # replies: are my answers all known?
        self.assertEqual([s.key for s in built.specs], ["i1", lane.SEPARATOR, "i2"])
        self.assertEqual(built.unread, 1)

    def test_newest_first_and_where_reading_starts(self):
        cfg = dict(CFG, feed=dict(CFG["feed"], order="newest_first"))
        v = View([("i1", post("1")), ("i2", post("2")), ("i3", post("3"))],
                 unread={"2", "3"}, cfg=cfg, name="home")
        m = lane.LaneModel(v, "home")
        specs = m.build(positioned=True).specs
        self.assertEqual([s.key for s in specs], ["i3", "i2", "i1"])  # no divider: placed
        self.assertEqual(m.start(specs), ("i2", "bottom"))
        nothing = [s for s in specs if not s.unread]
        self.assertEqual(m.start_key(nothing), "i1")  # the newest end, at the top here

    def test_start_without_a_divider_and_by_hand(self):
        v = View([("i1", post("1"))], unread={"1"}, name="home")
        m = lane.LaneModel(v, "home")
        specs = m.build(positioned=False).specs
        self.assertEqual(m.start(specs), ("i1", "top"))  # all unread: no divider
        self.assertIsNone(m.start_key([]))
        cfg = dict(CFG, read={"mark_read": "manual"})
        self.assertEqual(lane.LaneModel(View([], cfg=cfg), "replies").read(["x"]), [])

    def test_it_opens_where_the_reader_stood(self):
        """Where the reader stood (any interface: LaneModel.stood) is where the lane
        opens, before its first unread — while that card is in the lane; by the card's
        key or its post's id (the web page says what its card shows)."""
        v = View([("i1", post("1")), ("i2", post("2")), ("i3", post("3"))],
                 unread={"1", "3"}, name="home")
        state = {}
        v.get_state = lambda k, d=None: state.get(k, d)
        v.set_state = state.__setitem__
        m = lane.LaneModel(v, "home")
        specs = m.build(positioned=True).specs
        self.assertEqual(m.start(specs), ("i1", "top"))  # never stood: the first unread
        m.stood("i2")
        m.stood(lane.SEPARATOR)  # the divider is no place
        self.assertEqual(state, {"stood.home": "i2"})
        again = lane.LaneModel(v, "home")  # another interface, a later start
        self.assertEqual(again.start(specs), ("i2", "top"))
        state["stood.home"] = "3"  # a post's id
        self.assertEqual(again.start(specs), ("i3", "top"))
        m.stood("i3", at_end=True)  # read to the lane's end: no place, it opens as ever
        self.assertEqual(state["stood.home"], "")
        self.assertEqual(again.start(specs), ("i1", "top"))
        state["stood.home"] = "gone"  # no longer in the lane: the first unread again
        self.assertEqual(again.start(specs), ("i1", "top"))
        newest = dict(CFG, feed=dict(CFG["feed"], start_at="newest"))
        v.cfg = newest
        state["stood.home"] = "i2"
        self.assertEqual(lane.LaneModel(v, "home").start(specs), (None, "end"))

    def test_a_card_twice_is_shown_once(self):
        """The same item twice in what the view gives (a post come by two ways): one card
        — a key twice left a blank place and threw the windows' places off (29.10)."""
        lane._TWICE_SAID.discard("home")
        v = View([("i1", post("1")), ("i2", post("2")), ("i1", post("1"))], name="home")
        with self.assertLogs("fedtail.frontends.common.lane", "WARNING"):
            specs = lane.LaneModel(v, "home").build(positioned=True).specs
        self.assertEqual([s.key for s in specs], ["i1", "i2"])

    def test_conversations(self):
        top, r1, r2 = post("1"), post("2", reply_to="1"), post("3", reply_to="2")
        groups = [{"key": "1", "top": top, "members": ["1", "2", "3"], "unread": 2,
                   "last": r2}]
        v = View([("i1", top), ("i2", r1), ("i3", r2)], unread={"2", "3"},
                 conversations=lambda e, u: groups)
        m = lane.LaneModel(v, "replies")
        self.assertTrue(m.conversations_offered())
        m.set_conversations(True)
        self.assertTrue(m.conversations())
        specs = m.build(positioned=False).specs
        self.assertEqual([s.key for s in specs], ["conv:1"])
        self.assertEqual(specs[0].parent, "missing")
        self.assertEqual(specs[0].extra["short_id"], "a1")
        self.assertEqual(m.read(["1"]), ["1", "2", "3"])  # the card seen: all of it
        line, last = lane.conversation_line(specs[0])
        self.assertEqual(last, "3")
        self.assertIn("3", line)
        alone = dataclasses.replace(specs[0], extra={"conversation": {
            "members": ["1"], "unread": 0, "last": top}})
        self.assertIsNone(lane.conversation_line(alone))
        self.assertIsNone(lane.conversation_line(lane.CardSpec("x")))

    def test_unread_only_forgets_on_leaving(self):
        v = View([("i1", post("1"))], unread={"1"}, name="home")
        m = lane.LaneModel(v, "home")
        m.set_filter("unread")
        m.build(positioned=False)
        self.assertTrue(m.left())
        self.assertIsNone(m.kept)
        m.set_filter("all")
        self.assertFalse(m.left())

    def test_a_browse_lane_that_came_back_empty(self):
        v = View([], name="tag:x", lazy=True, browse_empty=("src",))
        built = lane.LaneModel(v, "tag:x").build(positioned=False)
        self.assertTrue(built.empty)
        self.assertNotIn("unread", lane.LaneModel(v, "tag:x").filters)


class FiltersTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_media_funnel_and_posts_only(self):
        from fedtail.model import Share
        pic = post("1", media=(Media(Ref("m", "", "m"), kind="image", url="a.jpg"),))
        clip = Media(Ref("m", "", "v"), kind="image", url="https://x/v.MP4?sig=1")
        self.assertEqual(lane.true_kind(clip).kind, "video")
        self.assertIs(lane.true_kind(pic.media[0]), pic.media[0])
        boost = Share(Ref("m", "", "s"), BOB and to_post(status("9", BOB)).author, pic,
                      None, "9")
        v = View([("i1", pic), ("i2", post("2")), ("i3", boost)], name="home")
        posts = {"on": False}
        v.posts_only = lambda _n: posts["on"]
        v.set_posts_only = lambda _n, on: posts.update(on=on)
        m = lane.LaneModel(v, "home")
        m.media.toggle("text", False)
        m.media.boosts = False
        built = m.build(positioned=True)
        self.assertEqual([s.key for s in built.specs], ["i1"])
        self.assertIn("1", built.info)
        m.media.reset()
        self.assertFalse(m.media.active())
        m.set_filter("posts")
        self.assertEqual(m.current_filter(), "posts")
        self.assertEqual(m.start_key(m.build(positioned=True).specs), "i3")

    def test_read_up_to_a_boost(self):
        from datetime import UTC, datetime

        from fedtail.model import Share
        t = datetime(2026, 1, 1, tzinfo=UTC)
        inner = post("5", created=t)
        boost = Share(Ref("m", "", "b5"), inner.author, inner, t, "5")
        self.assertEqual(lane.read_up_to([boost], "b5"), ["b5", "5"])


class ReadUpToTest(unittest.TestCase):
    def test_without_times_by_place(self):
        a, b, c = (post(i, created=None) for i in ("1", "2", "3"))
        self.assertEqual(lane.read_up_to([a, None, b, c], "2"), ["1", "2"])

    def test_age(self):
        from datetime import UTC, datetime, timedelta
        old = post("1", created=datetime.now(UTC) - timedelta(days=100))
        self.assertGreaterEqual(lane.age_days(old, CFG), 99)
        self.assertEqual(lane.age_days(post("2", created=None), CFG), 0)
        self.assertEqual(lane.age_days(old, {"feed": {"old_days": 0}}), 0)


if __name__ == "__main__":
    unittest.main()
