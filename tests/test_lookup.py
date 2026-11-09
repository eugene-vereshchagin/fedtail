"""A picture in the image searches, a post's claim in a fact-checker (core/lookup.py):
the links the config's templates make, when they're offered, and where every interface
shows them — a picture's own menu (common/actions.media_items; the page's
/api/media_menu: test_web) and a post's menu."""

import dataclasses
import unittest
from urllib.parse import unquote

from fedtail import i18n
from fedtail.core import config, lookup
from fedtail.frontends.common import actions
from fedtail.model import Card, Media, Ref
from fedtail.protocols.mastodon.adapter import post as to_post

from .fakes import BOB, status


def post(vis="public", text="Breaking: the moon is made of cheese, scientists say. More soon.",
         card=None):
    p = to_post(status("1", BOB, vis=vis, text=text))
    return dataclasses.replace(p, card=card)


PIC = Media(Ref("m", "", "m1"), "image", url="https://my.test/p.png?a=1&b=2",
            preview="https://my.test/small.png")


class LookupTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_services_parse_the_config_lines(self):
        self.assertEqual(lookup.services(["Lens|https://l.test/?u={image}",
                                          "https://t.test/s?u={image}", "Bad|ftp://x",
                                          " Spaced | https://s.test/{image} "]),
                         [("Lens", "https://l.test/?u={image}"),
                          ("t.test", "https://t.test/s?u={image}"),
                          ("Spaced", "https://s.test/{image}")])

    def test_a_picture_goes_to_every_search_its_address_encoded(self):
        got = lookup.image_search(config.DEFAULTS, PIC)
        self.assertEqual([n for n, _u in got], ["Google Lens", "Yandex", "TinEye", "Bing"])
        lens = got[0][1]
        self.assertTrue(lens.startswith("https://lens.google.com/uploadbyurl?url=https%3A"))
        self.assertIn("p.png%3Fa%3D1%26b%3D2", lens)  # its own & doesn't break the link
        self.assertEqual(unquote(lens.split("url=", 1)[1]), PIC.url)

    def test_a_video_by_its_still_frame_audio_not_at_all(self):
        video = dataclasses.replace(PIC, kind="video")
        self.assertIn("small.png", lookup.image_search(config.DEFAULTS, video)[0][1])
        audio = Media(Ref("m", "", "a"), "audio", url="https://my.test/a.mp3")
        self.assertEqual(lookup.image_search(config.DEFAULTS, audio), [])
        none = dict(config.DEFAULTS, ui=dict(config.DEFAULTS["ui"], image_search=[]))
        self.assertEqual(lookup.image_search(none, PIC), [])

    def test_the_query_is_the_link_s_title_else_the_first_sentence(self):
        self.assertEqual(lookup.query(post()), "Breaking: the moon is made of cheese, "
                                               "scientists say.")
        with_card = post(card=Card("https://news.test/a", title="Moon cheese  claim"))
        self.assertEqual(lookup.query(with_card), "Moon cheese claim")
        noisy = post(text='@bob <a href="https://x.test/q">https://x.test/q</a> #tag ' +
                     "word " * 60)
        q = lookup.query(noisy)
        self.assertNotIn("x.test", q)
        self.assertNotIn("#tag", q)
        self.assertLessEqual(len(q), lookup.QUERY_CHARS)
        self.assertFalse(q.endswith(" "))

    def test_fact_check_only_public_posts_unless_asked(self):
        got = lookup.fact_check(config.DEFAULTS, post())
        self.assertEqual(len(got), 1)
        name, url = got[0]
        self.assertEqual(name, "Google Fact Check")
        self.assertIn("/search/Breaking%3A%20the%20moon", url)
        self.assertTrue(url.endswith(";hl=en"))
        for vis in ("private", "direct"):
            self.assertEqual(lookup.fact_check(config.DEFAULTS, post(vis)), [])
        bold = dict(config.DEFAULTS, feed=dict(config.DEFAULTS["feed"],
                                               fact_check_private=True))
        self.assertEqual(len(lookup.fact_check(bold, post("direct"))), 1)
        self.assertEqual(lookup.fact_check(config.DEFAULTS, post(text="")), [])

    def test_link_and_unknown_placeholders(self):
        c = dict(config.DEFAULTS, feed=dict(config.DEFAULTS["feed"],
                                            fact_check=["X|https://x.test/?u={link}&k={nope}"]))
        got = lookup.fact_check(c, post(card=Card("https://news.test/a?b=1", title="T")))
        self.assertEqual(got, [("X", "https://x.test/?u=https%3A%2F%2Fnews.test%2Fa%3Fb%3D1"
                                     "&k={nope}")])

    def test_the_config_checks_the_lines(self):
        with self.assertRaises(config.ConfigError) as e:
            config.validate({"media": {"image_search": ["Lens"]}})
        self.assertIn("media.image_search", str(e.exception))
        cfg, _w = config.validate({"card": {"fact_check": []}})
        self.assertEqual(lookup.fact_check(cfg, post()), [])


class MenusTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_a_post_s_menu_has_the_fact_check(self):
        ctx = actions.Ctx(cfg=config.DEFAULTS, me_id="ME")
        opens = [it for it in actions.menu(post(), ctx) if it.kind == "open"]
        self.assertIn("Fact-check — Google Fact Check", [it.label for it in opens])
        private = actions.menu(post("private"), ctx)
        self.assertFalse([it for it in private if "Fact-check" in it.label])

    def test_a_picture_s_menu(self):
        items = actions.media_items(config.DEFAULTS, PIC)
        self.assertEqual([it.kind for it in items[:4]], ["save", "open", "copy", "separator"])
        self.assertEqual(items[1].url, PIC.url)
        self.assertEqual(len([it for it in items if it.label.startswith("Search for it")]), 4)
