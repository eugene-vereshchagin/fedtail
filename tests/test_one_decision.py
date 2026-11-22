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
