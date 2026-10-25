"""My emoji reactions to posts (Akkoma, Pleroma, Misskey's kin): offered where the
software has them, put on and taken off through the place every interface draws."""

import unittest

from fedtail.core.view import View
from fedtail.frontends.common import actions
from fedtail.frontends.common.places import Places, for_post
from fedtail.protocols.base import Capabilities

from .fakes import BOB, status
from .test_slow import Base


class CapsTest(unittest.TestCase):
    def test_only_where_the_software_has_them(self):
        self.assertFalse(Capabilities(software="mastodon").has("reactions"))
        self.assertFalse(Capabilities(software="gotosocial").has("reactions"))
        self.assertFalse(Capabilities().has("reactions"))
        self.assertTrue(Capabilities(software="Akkoma").has("reactions"))
        self.assertTrue(Capabilities(software="sharkey").has("reactions"))
        c = Capabilities(software="mastodon")
        c.present.add("reactions")  # the server said yes after all (glitch-soc forks)
        self.assertTrue(c.has("reactions"))


class ReactTest(Base):
    def make_akkoma(self):
        core, w = self.make()
        core.caps.software = "akkoma"
        w.add(status("070", BOB, minute=1), home=True)
        core.poll_once()
        return core, w

    def test_menu_and_place(self):
        core, w = self.make_akkoma()
        view = View(core)
        p = view.by_id("070")
        ctx = actions.Ctx(core.cfg, "ME", supports=core.supports)
        urls = [i.url for i in actions.menu(p, ctx) if i.kind == "link"]
        self.assertIn("fedtail:react/070", urls)
        self.assertEqual(for_post(p)["react"], ("react", "070"))
        places = Places(view)
        page = places.page("react", "070")
        [row] = page.rows
        self.assertEqual(row.kind, "post")
        self.assertEqual(len(row.buttons), 8)  # the quick ones: none on it yet
        out = places.act(*row.buttons[0].act)
        self.assertTrue(out.refresh)
        self.assertEqual(w.reacted[-1], ("070", "👍", True, "pleroma"))
        page = places.page("react", "070")
        first = page.rows[0].buttons[0]
        self.assertTrue(first.label.startswith("👍 1") and first.primary)  # mine, counted
        places.act(*first.act)  # again: off
        self.assertEqual(w.reacted[-1], ("070", "👍", False, "pleroma"))
        out = places.act("react", "put", "070", values={"emoji": ":blobcat:"})
        self.assertIn("blobcat", out.message)
        self.assertEqual(w.reacted[-1][1], "blobcat")  # by its shortcode
        out = places.act("react", "put", "070", values={"emoji": "two words"})
        self.assertTrue(out.error)

    def test_fedibird_style_and_none_on_mastodon(self):
        core, w = self.make_akkoma()
        core.caps.software = "sharkey"
        View(core).react(View(core).by_id("070"), "🔥").result()
        self.assertEqual(w.reacted[-1][3], "fedibird")
        core.caps.software = "mastodon"
        p = View(core).by_id("070")
        ctx = actions.Ctx(core.cfg, "ME", supports=core.supports)
        has_reactions = bool(p.reactions)
        urls = [i.url for i in actions.menu(p, ctx) if i.kind == "link"]
        self.assertEqual("fedtail:react/070" in urls, has_reactions)  # one on it: offered

    def test_empty_name(self):
        core, _w = self.make_akkoma()
        with self.assertRaises(ValueError):
            core.react(core.store.get_status("070"), " ")


if __name__ == "__main__":
    unittest.main()
