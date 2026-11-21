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


if __name__ == "__main__":
    unittest.main()
