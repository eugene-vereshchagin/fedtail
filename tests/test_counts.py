"""The counts of the posts on screen kept fresh (core/counts.py): the interfaces say what
they show, the round asks my server again in one batch (one by one where it can't), a post
whose numbers changed is stored and said."""

from fedtail.core import counts
from fedtail.core.proto import Error as ApiError

from . import test_cli
from .fakes import BOB, status
from .test_core import TmpDir


class CountsTest(TmpDir):
    make = test_cli.CliTest.make

    def setUp(self):
        super().setUp()
        self.core, self.w = self.make()
        for i in range(1, 4):
            self.w.add(status(f"00{i}", BOB, minute=i, text=f"post {i}", vis="public"),
                       home=True)
        self.core.connect().result()
        self.core.poll_once()
        self.said = []
        self.core.events.on("status_updated", lambda _n, st: self.said.append(st["id"]))

    def test_the_posts_on_screen_are_asked_again(self):
        self.core.on_screen(["001", "002", "event:9", "__sep__"])
        self.w.statuses["001"]["replies_count"] = 4  # replies came on the server
        self.w.statuses["001"]["favourites_count"] = 2
        got = self.core.refresh_counts(force=True)
        self.assertEqual([st["id"] for st in got], ["001"])  # "002" didn't change
        self.assertEqual(self.said, ["001"])
        self.assertEqual(self.core.store.get_status("001")["replies_count"], 4)
        self.assertEqual(self.w.batches, 1)  # one request for all of them
        self.assertEqual(self.core.refresh_counts(), [])  # not due yet

    def test_more_replies_wake_a_followed_thread(self):
        """A followed thread whose post on screen has more replies: asked next round."""
        st = self.core.store.get_status("003")
        self.core.store.sub_add("003", "2000-01-01T00:00:00Z", "2000-01-01T00:00:00Z",
                                False, [])
        self.core.store.sub_checked("003", "2099-01-01T00:00:00Z", st["created_at"], [])
        self.core.on_screen(["003"])
        self.w.statuses["003"]["replies_count"] = 1
        self.core.refresh_counts(force=True)
        due = self.core.store.subs_due("", "2099-12-31", 10)
        self.assertEqual([r[0] for r in due], ["003"])

    def test_a_server_without_batches_is_asked_one_by_one(self):
        def refuse(_ids):
            raise ApiError(404, "not found")
        self.core.api.statuses = refuse
        self.core.on_screen(["002"])
        self.w.statuses["002"]["reblogs_count"] = 7
        self.assertEqual([st["id"] for st in self.core.refresh_counts(force=True)], ["002"])
        self.assertTrue(self.core._no_batches)  # remembered: one by one from now on

    def test_off_and_what_counts(self):
        self.core.cfg["feed"]["counts_minutes"] = 0
        self.core.on_screen(["001"])
        self.assertEqual(self.core.refresh_counts(), [])
        self.assertTrue(counts.changed({"replies_count": 0}, {"replies_count": 1}))
        self.assertFalse(counts.changed({"replies_count": 1, "content": "a"},
                                        {"replies_count": 1, "content": "b"}))
