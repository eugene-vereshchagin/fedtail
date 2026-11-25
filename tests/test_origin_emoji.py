"""An emoji a post names without a picture: found on the author's server (NOTES/22)."""

from unittest import mock

from fedtail.core import remote
from fedtail.core.view import View
from tests.fakes import BOB, status

from .test_custom import FreeBase

PIC = "https://social.example/emoji/acceptable.png"


def bare_post():
    st = status("1", BOB, minute=1, text="I'm in shock :acceptable:")
    st["spoiler_text"] = "headphones :acceptable:"
    st["emojis"] = [{"shortcode": "acceptable", "url": "", "static_url": ""},
                    {"shortcode": "smug", "url": "https://x.example/s.png",
                     "static_url": "https://x.example/s.png"}]
    return st


class OriginEmojiTest(FreeBase):
    def make(self, rules):
        core, w = super().make(rules)
        # the background's job at once, here: what it did is there to look at
        self.enterContext(mock.patch.object(core.bg, "submit", lambda f, *a: f(*a)))
        return core, w

    def test_a_bare_emoji_gets_the_authors_picture(self):
        """GoToSocial passed `:acceptable:` on with an empty url: every interface left
        it as text. The author's server's list fills it in; asked once, in the background,
        without a token; the lanes drawn anew when it answers."""
        core, _w = self.make([])
        st = bare_post()
        asked = []

        def get_json(url, **kw):
            asked.append((url, kw.get("headers")))
            return [{"shortcode": "acceptable", "url": PIC, "static_url": PIC},
                    {"shortcode": "evil", "url": "http://plain.example/e.png"}]
        with mock.patch.object(remote, "get_json", get_json):
            core.emoji_filled(st)  # not known yet: asked (here at once)
            self.assertEqual(asked, [("https://social.example/api/v1/custom_emojis", None)])
            self.assertIn(("lanes_updated", {lane.name: [] for lane in core.lanes}),
                          self.events)
            post = View(core).entry(st)
            urls = {e.shortcode: e.static_url for e in post.emojis}
            self.assertEqual(urls, {"acceptable": PIC, "smug": "https://x.example/s.png"})
            core.emoji_filled(st)
            self.assertEqual(len(asked), 1)  # kept: not asked again
        self.assertEqual(core.store.kv_get("origin_emoji:social.example")["emojis"],
                         {"acceptable": PIC})  # a plain http picture never

    def test_a_boost_and_the_switch(self):
        core, _w = self.make([])
        boost = status("2", BOB, minute=2)
        boost["reblog"] = bare_post()
        core.store.kv_set("origin_emoji:social.example",
                          {"at": 9e12, "emojis": {"acceptable": PIC}})
        inner = core.emoji_filled(boost)["reblog"]
        self.assertEqual(inner["emojis"][0]["url"], PIC)
        core.cfg["feed"]["emoji_from_origin"] = False
        self.assertIsNone(core.emoji_filled(boost))

    def test_a_server_that_gives_nothing_is_asked_again_a_day_later(self):
        core, _w = self.make([])
        with mock.patch.object(remote, "get_json", lambda url, **kw: None):
            core.emoji_filled(bare_post())
        kept = core.store.kv_get("origin_emoji:social.example")
        self.assertEqual(kept["emojis"], {})
        calls = []
        with mock.patch.object(remote, "get_json", lambda url, **kw: calls.append(url)):
            core.emoji_filled(bare_post())
        self.assertEqual(calls, [])  # within the day: not again
