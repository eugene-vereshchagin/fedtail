"""Decisions made once — in the core or frontends/common — so that a setting does the same
in every interface. A sweep of every setting through the five interfaces (21.11) found
switches only Qt honoured, because Qt decided them itself: "Add to list" with
lists.enabled off, "Scheduled" with post.schedule off, notify.filtered."""

import time
import unittest

from fedtail import i18n
from fedtail.core.view import View
from fedtail.frontends.common import actions
from fedtail.frontends.common import profile as prof
from fedtail.frontends.common.places import Places
from fedtail.model import Relationship

from .fakes import BOB, status
from .test_slow import Base


class ListsOffTest(Base):
    def setUp(self):
        i18n.setup("en")

    def test_no_add_to_list_anywhere(self):
        core, w = self.make()
        w.add(status("070", BOB, minute=1), home=True)
        core.poll_once()
        view = View(core)
        p = view.by_id("070")
        ctx = actions.Ctx(core.cfg, "ME", supports=core.supports, lists=True)
        acc = p.author
        rel = Relationship(following=True)
        self.assertIn("lists", [i.kind for i in actions.menu(p, ctx)])
        self.assertIn("lists", [a.key for a in prof.actions(acc, rel, False, core.cfg,
                                                            core.supports, lists=True)])
        core.cfg["lists"]["enabled"] = False
        self.assertNotIn("lists", [i.kind for i in actions.menu(p, ctx)])
        self.assertNotIn("lists", [a.key for a in prof.actions(acc, rel, False, core.cfg,
                                                               core.supports, lists=True)])


class PlacesMenuTest(Base):
    def setUp(self):
        i18n.setup("en")

    def names(self, core):
        return [n for n, _t in Places(View(core)).menu()]

    def test_scheduled_and_filtered_follow_their_switches(self):
        core, w = self.make()
        w.policy = {"for_not_following": "accept"}
        core.connect().result()
        core.supports = lambda _what: True
        self.assertIn("scheduled", self.names(core))
        self.assertIn("filtered", self.names(core))
        core.cfg["post"]["schedule"] = False  # no posting later: no place for it
        core.cfg["notify"]["filtered"] = "off"  # "off": not in the menu either
        self.assertNotIn("scheduled", self.names(core))
        self.assertNotIn("filtered", self.names(core))
        core.cfg["notify"]["filtered"] = "menu"
        self.assertIn("filtered", self.names(core))


class FilteredRemindTest(Base):
    def start(self, mode):
        core, w = self.make(notify={"filtered": mode})
        time.sleep(0.1)  # make()'s own first round asked with nobody held back
        core.unsupported.discard("notification_policy")  # (404 there: a server upgraded)
        w.policy = {"for_not_following": "filter"}
        w.held = [{"id": "r1", "account": BOB, "notifications_count": "2"}]
        heard = []
        core.events.on("filtered_waiting", lambda _n, p: heard.append(p))
        core._poll_count = 0  # the start again
        core.poll_once()
        for _i in range(50):
            if heard:
                break
            time.sleep(0.02)
        return core, heard

    def test_said_once_at_start_by_the_core(self):
        core, heard = self.start("remind")
        self.assertEqual(heard, [1])
        core.poll_once()  # not every round
        time.sleep(0.1)
        self.assertEqual(heard, [1])

    def test_quiet_unless_remind(self):
        _core, heard = self.start("menu")
        self.assertEqual(heard, [])


class WebProfileButtonsTest(unittest.TestCase):
    def test_the_page_and_the_phone_take_every_button(self):
        """The page lets through the buttons it knows (web/server.py WEB_PROFILE_ACTS),
        and the phone draws what the page gets: "Not in Home", "Follow their replies",
        "My name for them", "Name colour" were missing there (21.11)."""
        import re
        from pathlib import Path

        from fedtail.frontends.web.server import WEB_PROFILE_ACTS
        src = (Path(prof.__file__)).read_text("utf-8")
        keys = set(re.findall(r'Act\("([a-z_]+)"', src)) | {"following", "followers"}
        self.assertEqual(sorted(keys - set(WEB_PROFILE_ACTS)), [])


class LinkCardTest(unittest.TestCase):
    def test_one_rule_for_every_interface(self):
        """Qt hid the link card beside a quote, GTK, the page and the terminal drew both
        (21.11): common/cardtext.link_card says for all of them."""
        from types import SimpleNamespace as NS

        from fedtail.frontends.common.cardtext import link_card
        from fedtail.model import Card, Quote
        card = Card("https://e.test/a", title="A page", image="https://e.test/a.png")
        cfg = {"feed": {"link_cards": "full", "quotes": "card"}}
        post = NS(card=card, media=(), quote=None)
        self.assertIs(link_card(post, cfg), card)
        self.assertIsNone(link_card(NS(card=card, media=("m",), quote=None), cfg))
        quoted = NS(card=card, media=(), quote=Quote())
        self.assertIsNone(link_card(quoted, cfg))  # the quote is shown: no card
        cfg["feed"]["quotes"] = "off"
        self.assertIs(link_card(quoted, cfg), card)  # quotes not shown: the card is
        cfg["feed"]["link_cards"] = "off"
        self.assertIsNone(link_card(post, cfg))
        cfg["feed"]["link_cards"] = "text"
        self.assertIsNone(link_card(NS(card=Card("https://e.test/b"), media=(), quote=None),
                                    cfg))  # no title, no picture: nothing to draw


class AppIconTest(unittest.TestCase):
    def test_one_choice_for_both_windows(self):
        """ui.app_icon / ui.themed_icon: the file is iconart's choice, Qt's and GTK's."""
        import tempfile

        from fedtail.frontends import iconart
        with tempfile.TemporaryDirectory() as d:
            got = iconart.app_icon_file({"ui": {"app_icon": "possum"}}, "night", {},
                                        "#336699", "#ff6600", d)
            self.assertTrue(got.endswith("fedtail.png"))
            got = iconart.app_icon_file({"ui": {"app_icon": "bubble", "themed_icon": False}},
                                        "night", {}, "#336699", "#ff6600", d)
            self.assertTrue(got.endswith("fedtail.svg"))
            got = iconart.app_icon_file({"ui": {"app_icon": "bubble", "themed_icon": True}},
                                        "night", {}, "#336699", "#ff6600", d)
            self.assertTrue(got.endswith("icon-night.svg"))
            from pathlib import Path
            self.assertIn("<svg", Path(got).read_text("utf-8"))


if __name__ == "__main__":
    unittest.main()


class ConnectTroubleTest(unittest.TestCase):
    """A connect that failed means one thing everywhere (common/connecting): the phone
    showed "the core didn't start" for one slow answer and stayed there (23.11)."""

    def test_slow_and_refused(self):
        from fedtail.frontends.common.connecting import trouble
        i18n.setup("en")
        slow = trouble("ReadTimeout: Read timed out. (read timeout=30)")
        self.assertFalse(slow["relogin"])
        self.assertEqual(slow["again"], 20)
        self.assertIn("Read timed out", slow["text"])
        refused = trouble("HTTP 401: The access token is invalid")
        self.assertTrue(refused["relogin"])
        self.assertEqual(refused["text"], i18n._("auth_failed"))


class WebSlowServerTest(Base):
    """The page asks /api/me while the server doesn't answer: said and asked again —
    not an error; a refused token: the login place, with the words."""

    def test_me_while_the_server_is_down(self):
        from concurrent.futures import Future
        from unittest import mock

        from fedtail.frontends.web.server import Web
        i18n.setup("en")
        core, _w = self.make()
        core.me = None  # not connected yet: the server is slow
        web = Web.__new__(Web)
        web.core = core

        def failing(text):
            f = Future()
            f.set_exception(OSError(text))
            return f
        with mock.patch.object(core, "connect", return_value=failing("timed out")):
            got = web.me()
        self.assertEqual(got["again"], 20)
        self.assertIn("timed out", got["down"])
        with mock.patch.object(core, "connect", return_value=failing("HTTP 401: no")), \
                mock.patch.object(core, "logout", wraps=core.logout) as out:
            got = web.me()
        out.assert_called_once_with(revoke=False)
        self.assertEqual(got["said"], i18n._("auth_failed"))
        self.assertIn("login", got)


class EmojiOffEverywhereTest(Base):
    """feed.emoji = false: no emoji at all — the windows took them out; the page, the
    phone (the page's JSON) and the terminal showed every one, GTK in names (23.11).
    feed.custom_emoji = false: :blob: stays text, no picture. One rule: cardtext."""

    def post(self):
        from fedtail.protocols.mastodon import adapter

        from .fakes import status as st
        blob = [{"shortcode": "blob", "url": "https://x.example/blob.png",
                 "static_url": "https://x.example/blob.png"}]
        raw = st("095", dict(BOB, display_name="Bob :blob: 🔥", emojis=blob), minute=3,
                 text="hello :blob: world 🔥")
        raw["emojis"] = blob
        return adapter.post(raw)

    def shown(self, core, p):
        from fedtail.frontends.tui.model import show_post
        from fedtail.frontends.web.server import post_json
        view = View(core)
        page = post_json(view, p)
        tui = show_post(core, p)
        return (page["html"] + " " + page["account"]["name"] + " " +
                page["account"].get("name_html", ""),
                " ".join(tui.body) + " " + " ".join(t for _k, t in tui.head))

    def test_three_looks(self):
        core, _w = self.make()
        p = self.post()
        page, term = self.shown(core, p)
        self.assertIn('<img class="emoji"', page)  # pictures (the terminal: the code)
        core.cfg["feed"]["custom_emoji"] = False
        page, term = self.shown(core, p)
        self.assertNotIn("<img", page)
        self.assertIn(":blob:", page)
        core.cfg["feed"]["emoji"] = False
        page, term = self.shown(core, p)
        for where, text in (("page/phone", page), ("terminal", term)):
            self.assertIn("hello", text, where)
            self.assertIn("Bob", text, where)
            self.assertNotIn(":blob:", text, where)
            self.assertNotIn("🔥", text, where)
            self.assertNotIn("<img", text, where)

    def test_a_name_of_only_emoji_shows_the_login(self):
        from fedtail.frontends.common.cardtext import emoji_cut
        core, _w = self.make(feed={"emoji": False})
        self.assertEqual(emoji_cut(core.cfg, "🔥 :blob:", (), "bob"), "bob")
        self.assertEqual(emoji_cut(core.cfg, "Bob 🔥", ()), "Bob ")


class CardButtonsTest(Base):
    """The buttons under a post: one rule (common/actions.button_words) — the lane's own
    `buttons`, else by what the post is — for the windows, the page and the phone, which
    drew lists of their own, each in its own order (24.11)."""

    def setUp(self):
        i18n.setup("en")

    def test_a_lane_names_its_buttons_and_an_rss_item_has_its_own(self):
        import dataclasses

        from fedtail.frontends.common.lane import LaneModel
        from fedtail.frontends.web.server import Web
        core, w = self.make(lanes={"custom": [
            {"name": "quiet", "source": "home", "any": [{}],
             "buttons": ["thread", "like", "open", "nonsense"]},
            {"name": "bare", "source": "home", "any": [{}], "buttons": []}]})
        w.add(status("070", BOB, minute=1, vis="public"), home=True)
        w.add(status("071", BOB, minute=2), home=True)  # followers only: no boost
        core.poll_once()
        view = View(core)
        self.assertEqual(view.card_buttons("quiet"), ("thread", "like", "open"))
        self.assertEqual(view.card_buttons("bare"), ())
        self.assertIsNone(view.card_buttons("home"))
        self.assertIsNone(view.card_buttons())
        p, quiet = view.by_id("070"), view.by_id("071")
        ctx = actions.Ctx(core.cfg, "ME", supports=core.supports)
        act = lambda *a, **k: [b.action for b in actions.buttons(*a, **k)]  # noqa: E731
        # no lane's word: by what the post is, as it always was
        self.assertEqual(act(p, ctx), ["reply", "fav", "boost", "thread", "bookmark"])
        self.assertEqual(act(quiet, ctx), ["reply", "fav", "thread", "bookmark"])
        core.cfg["read"]["read_button"] = True
        self.assertEqual(act(p, ctx, unread=True)[-1], "readone")
        self.assertNotIn("readone", act(p, ctx))
        core.cfg["read"]["read_button"] = False
        # an RSS feed's item: no server to answer, like or boost it on
        item = dataclasses.replace(p, ref=dataclasses.replace(p.ref, id="rss-1"),
                                   url="https://feed.test/1")
        got = actions.buttons(item, ctx)
        self.assertEqual([b.action for b in got], ["open", "bookmark"])
        self.assertEqual(got[0].url, "https://feed.test/1")
        labels = [i.label for i in actions.menu(item, ctx)]
        self.assertNotIn("Reply", labels)
        self.assertNotIn("Favourite", labels)
        # the lane's own: its order; only what the post can take; the rest in the menu
        own = actions.Ctx(core.cfg, "ME", supports=core.supports,
                          buttons=("thread", "like", "open"))
        self.assertEqual(act(p, own), ["thread", "fav", "open"])
        labels = [i.label for i in actions.menu(p, own)]
        for word in ("Reply", "Boost", "Bookmark"):
            self.assertIn(word, labels)
        self.assertNotIn("Favourite", labels)  # under the post: not twice
        self.assertNotIn("Thread", labels)
        self.assertNotIn("Boost", [i.label for i in actions.menu(quiet, own)])
        usual = [i.label for i in actions.menu(p, ctx)]
        self.assertFalse({"Reply", "Boost", "Bookmark", "Thread"} & set(usual))
        inside = actions.Ctx(core.cfg, "ME", in_thread=True, buttons=("thread", "reply"))
        self.assertEqual(act(p, inside), ["reply"])
        self.assertEqual(act(p, actions.Ctx(core.cfg, "ME", buttons=())), [])
        # the cards of the lanes carry it, and the page and the phone are told the list
        specs = {n: [s for s in LaneModel(view, n).build(False).specs if s.entry is not None]
                 for n in ("quiet", "bare", "home")}
        self.assertTrue(all(s.buttons == ("thread", "like", "open") for s in specs["quiet"]))
        self.assertTrue(all(s.buttons == () for s in specs["bare"]))
        self.assertTrue(all(s.buttons is None for s in specs["home"]))
        web = Web(core, "k")
        by = lambda lane: {x["sid"]: x["buttons"] for x in web.lane(lane)["posts"]}  # noqa: E731
        self.assertEqual(by("home"), {"070": ["reply", "like", "boost", "thread", "bookmark"],
                                      "071": ["reply", "like", "thread", "bookmark"]})
        self.assertEqual(by("quiet"), {"070": ["thread", "like", "open"],
                                       "071": ["thread", "like", "open"]})
        self.assertEqual(by("bare"), {"070": [], "071": []})
        in_thread = web.thread("070")["posts"]
        self.assertNotIn("thread", in_thread[0]["buttons"])
        # the menu of a card that shows this row: what is off it
        flat = lambda m: [i["label"] for i in m["items"]]  # noqa: E731
        self.assertIn("Reply", flat(web.post_menu("070", row="thread,like")))
        self.assertNotIn("Reply", flat(web.post_menu("070")))
        self.assertNotIn("Reply", flat(web.post_menu("070", row="reply,nonsense")))

    def test_the_rule_and_the_editor(self):
        from fedtail.core import atoms
        from fedtail.frontends.common import lanesplace
        rule = atoms.Rule.parse({"name": "x", "any": [{}], "buttons": ["like", "like", "reply"]})
        self.assertEqual(rule.buttons, ("like", "reply"))
        self.assertEqual(rule.warnings, [])
        self.assertIsNone(atoms.Rule.parse({"name": "x", "any": [{}]}).buttons)
        bad = atoms.Rule.parse({"name": "x", "any": [{}], "buttons": "reply"})
        self.assertIsNone(bad.buttons)
        self.assertTrue(any("buttons" in x for x in bad.warnings))
        odd = atoms.Rule.parse({"name": "x", "any": [{}], "buttons": ["reply", "fly", 3]})
        self.assertEqual(odd.buttons, ("reply",))
        self.assertTrue(any("buttons" in x for x in odd.warnings))
        old = {"name": "x", "any": [{}]}
        table = lambda said: lanesplace._table_of("x", old, {"buttons": said})  # noqa: E731
        self.assertNotIn("buttons", table(""))
        self.assertEqual(table("thread, like  reply")["buttons"], ["thread", "like", "reply"])
        self.assertEqual(table("-")["buttons"], [])
        with self.assertRaises(ValueError):
            table("reply, fly")
        self.assertEqual(lanesplace._buttons_text(["reply", "like"]), "reply, like")
        self.assertEqual(lanesplace._buttons_text([]), "-")
        self.assertEqual(lanesplace._buttons_text(None), "")


class MarkedLanesTest(Base):
    """No default names a lane (24.11): the options that pick lanes say "marked" — the
    lanes whose rules mark themselves (`marks`); the sets' words mark the very lanes the
    old default lists named."""

    OLD = {"notify": "direct to_me replies mentions subs commented important activity "
                     "requests",
           "sound": "direct to_me replies mentions subs commented important requests",
           # …and private messages, which the old list of the icon's count left out
           # though a note and a sound spoke of them (24.11)
           "icon_count": "direct to_me replies mentions subs commented important requests",
           "languages": "federated local", "hide_listed": "home bots federated local"}

    def test_the_sets_mark_what_the_old_lists_named(self):
        from fedtail.core import config, custom, presets
        for name in presets.names():
            cfg, _ = config.validate({"lanes": {"preset": name}})
            for c in custom.load(cfg)[0]:
                for mark, old in self.OLD.items():
                    self.assertEqual(mark in (c.rule.marks or ()), c.name in old.split(),
                                     f"{name}: {c.name}: {mark}")
        d = config.DEFAULTS
        for (section, key), _mark in config.MARK_OF.items():
            self.assertIn("marked", d[section][key])
            self.assertFalse(set(d[section][key]) & presets.known_names() - {"tags", "lists"})

    def test_a_lane_marks_itself(self):
        core, _w = self.make(lanes={"custom": [
            {"name": "work", "source": "home", "any": [{}], "marks": ["notify", "icon_count"]},
            {"name": "to_me", "any": [{"me": "reply"}]},                 # the set's name
            {"name": "direct", "any": [{"me": "direct"}], "marks": []},  # …its own word
            {"name": "odd", "source": "home", "any": [{}], "marks": ["notify", "fly"]}]})
        marks = lambda n: set(core.lane_by_name[n].marks)  # noqa: E731
        self.assertEqual(marks("work"), {"notify", "icon_count"})
        self.assertEqual(marks("to_me"), {"notify", "sound", "icon_count"})  # the sets'
        self.assertEqual(marks("direct"), set())
        self.assertEqual(marks("odd"), {"notify"})
        self.assertEqual(marks("home"), {"hide_listed"})
        n = core.cfg["notify"]
        n["lanes"] = ["marked"]  # the default (the tests' core names lanes of its own)
        chosen = lambda name, mark: core.lane_chosen(name, ["marked"], [], mark)  # noqa: E731
        self.assertTrue(chosen("work", "notify"))
        self.assertFalse(chosen("work", "sound"))
        self.assertFalse(chosen("home", "notify"))
        self.assertFalse(chosen("direct", "notify"))
        self.assertFalse(chosen("work", None))  # an option without a mark: by names only
        self.assertTrue(core._notify_wanted("work", n["lanes"], n["except"]))
        self.assertFalse(core.lane_chosen("work", ["marked"], ["work"], "notify"))  # except
        self.assertTrue(core.lane_chosen("home", ["marked", "home"], [], "notify"))
        from fedtail.core import lanes
        self.assertTrue(lanes.in_scope("x", ["marked"], True))
        self.assertFalse(lanes.in_scope("x", ["marked"], False))
        self.assertTrue(lanes.in_scope("list:1", ["lists"]))
        # the editor: its own word only when it differs from the sets'
        from fedtail.frontends.common import lanesplace
        old = {"name": "to_me", "any": [{}]}
        self.assertNotIn("marks", lanesplace._table_of(
            "to_me", old, {"marks": ["notify", "sound", "icon_count"]}))
        self.assertEqual(lanesplace._table_of("to_me", old, {"marks": ["sound"]})["marks"],
                         ["sound"])
        self.assertEqual(lanesplace._marks_of("home", {}), ["hide_listed"])
        self.assertEqual(lanesplace._marks_of("home", {"marks": ["notify"]}), ["notify"])
