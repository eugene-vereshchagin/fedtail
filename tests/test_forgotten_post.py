"""A post of another server my server has forgotten: a like, a boost, a bookmark fetch it
again by its address and act on it there (25.11: GoToSocial drops old remote posts — every
button on a bot's week-old post answered 404, and looked dead)."""

from tests import fakes
from tests.fakes import status

from .test_custom import FreeBase

FAR = fakes.acct("N", "neural_meduza@far.example", bot=True)
URI = "https://far.example/users/neural_meduza/statuses/1176"


class ForgottenPostTest(FreeBase):
    def forgotten(self, w):
        old = status("01OLD", FAR, minute=1, vis="public", text="penguins")
        old["uri"] = old["url"] = URI
        w.add(old, home=True)
        return old

    def forget(self, w, old):
        del w.statuses[old["id"]]                    # my server dropped it…
        w.remote[URI] = dict(old, id="01NEW")        # …its home still has it

    def test_like_boost_bookmark_on_a_forgotten_post(self):
        core, w = self.make([])
        core.connect().result()
        core.poll_once()
        old = self.forgotten(w)
        core.poll_once()
        st = core.store.get_status("01OLD")
        self.forget(w, old)
        liked = core.favourite(st).result()
        self.assertEqual(liked["id"], "01OLD")       # the lanes' id, the card follows
        self.assertTrue(w.statuses["01NEW"]["favourited"])
        self.assertTrue(core.store.get_status("01OLD")["favourited"])
        core.boost(core.store.get_status("01OLD")).result()
        self.assertTrue(w.statuses["01NEW"]["reblogged"])
        core.bookmark(core.store.get_status("01OLD"), True).result()
        self.assertTrue(w.statuses["01NEW"]["bookmarked"])

    def test_a_post_gone_everywhere_still_fails(self):
        core, w = self.make([])
        core.connect().result()
        old = self.forgotten(w)
        core.poll_once()
        st = core.store.get_status("01OLD")
        del w.statuses["01OLD"]  # gone from its home too: nothing to fetch
        from fedtail.core.proto import Error
        with self.assertRaises(Error):
            core.favourite(st).result()
