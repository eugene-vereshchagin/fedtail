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


class ThreadSizeTest(TmpDir):
    """The Thread button's number (core/threadsize.py): a boosted comment deep in a busy
    thread said its own direct replies — none (23.11); now the whole thread's comments."""
    make = test_cli.CliTest.make

    def setUp(self):
        super().setUp()
        self.core, self.w = self.make()
        self.w.add(status("010", BOB, minute=1, text="the root", vis="public"))
        self.w.add(status("011", BOB, reply_to="010", minute=2, vis="public"))
        self.w.add(status("012", BOB, reply_to="011", minute=3, vis="public",
                          text="the comment boosted"))
        self.w.add(status("013", BOB, reply_to="010", minute=4, vis="public"))
        self.w.statuses["010"]["replies_count"] = 2
        self.w.statuses["011"]["replies_count"] = 1
        boost = dict(status("020", BOB, minute=5, vis="public"),
                     reblog=self.w.statuses["012"])
        self.w.add(boost, home=True)
        self.core.connect().result()
        self.core.poll_once()
        self.core.bg.submit = lambda fn, *a, **kw: fn(*a, **kw)  # at once, here
        self.asked = []
        context = self.core.api.context
        self.core.api.context = lambda sid: (self.asked.append(sid), context(sid))[1]
        self.said = []
        self.core.events.on("status_updated", lambda _n, st: self.said.append(st["id"]))

    def test_a_boosted_comment_says_its_threads_comments(self):
        from fedtail.core.view import View
        from fedtail.frontends.common import actions
        view = View(self.core)
        before = view.entry(self.core.store.get_status("020"))
        self.assertEqual(actions.thread_count(before), 0)  # its own replies: none
        self.core.on_screen(["020"])
        self.assertEqual(self.said, ["020"])  # its card is drawn anew
        after = view.entry(self.core.store.get_status("020"))
        self.assertEqual(after.post.counts.thread, 3)  # 011, 012, 013
        self.assertEqual(actions.thread_count(after), 3)
        self.assertEqual(self.core.thread_size(self.w.statuses["013"]), 3)  # the same thread
        n = len(self.asked)
        self.core.on_screen(["020"])  # remembered: not asked again
        self.assertEqual(len(self.asked), n)
        ctx = actions.Ctx(cfg=self.core.cfg, me_id=None)
        thread = [b for b in actions.buttons(after, ctx) if b.action == "thread"][0]
        self.assertEqual(thread.count, " · 3")
        from fedtail.frontends.web.server import post_json  # the web page and the phone
        self.assertEqual(post_json(view, after)["counts"]["thread"], 3)

    def test_the_root_known_here_costs_one_request(self):
        for sid in ("010", "011"):  # the way up is in the store
            self.core.store.put_statuses([self.w.statuses[sid]])
        self.core.on_screen(["020"])
        self.assertEqual(self.asked, ["010"])

    def test_a_post_alone_is_not_asked_and_off_is_off(self):
        self.w.add(status("030", BOB, minute=6, vis="public"), home=True)
        self.core.poll_once()
        self.core.on_screen(["030"])
        self.assertEqual(self.asked, [])
        self.core.cfg["feed"]["thread_size_minutes"] = 0
        self.core.on_screen(["020"])
        self.assertEqual(self.asked, [])
        self.assertIsNone(self.core.thread_size(self.w.statuses["012"]))

    def test_an_opened_thread_tells_its_size(self):
        self.core.cfg["feed"]["complete_threads"] = False
        self.core.on_screen(["020"])
        self.w.add(status("014", BOB, reply_to="013", minute=7, vis="public"))
        self.core.thread("012").result()
        self.assertEqual(self.core.thread_size(self.w.statuses["012"]), 4)


class ThreadSizeCareTest(ThreadSizeTest):
    """What the first cut of the thread's size left out (the audit of 23.11): a thread the
    server didn't give was asked again at every scroll, the server's own limit wasn't
    looked at, two posts of one thread cost two rounds of requests, nothing was ever
    forgotten."""

    def test_a_thread_not_given_is_left_alone_for_a_while(self):
        def down(sid):
            self.asked.append(sid)
            raise OSError("no answer")
        self.core.api.context = down
        self.core.on_screen(["020"])
        self.assertEqual(len(self.asked), 1)
        for _ in range(5):  # still on screen, scrolled by again and again
            self.core.on_screen(["020"])
        self.assertEqual(len(self.asked), 1)
        from fedtail.core import threadsize
        with self.core._ts():  # the quiet time over: asked again
            for k in self.core._ts_failed:
                self.core._ts_failed[k] -= threadsize.FAILED_S + 1
        self.core.on_screen(["020"])
        self.assertEqual(len(self.asked), 2)

    def test_the_servers_limit_nearly_spent_asks_nothing(self):
        import time

        from fedtail.protocols.base import Budget
        self.core.api.budget = Budget(300, 3, time.time() + 120)  # a quarter of 3: none
        self.core.on_screen(["020"])
        self.assertEqual(self.asked, [])
        self.core.api.budget = Budget(300, 200, time.time() + 120)
        self.core.on_screen(["020"])
        self.assertTrue(self.asked)

    def test_two_posts_of_one_thread_are_asked_once(self):
        self.w.add(dict(status("021", BOB, minute=6, vis="public"),
                        reblog=self.w.statuses["013"]), home=True)
        self.core.poll_once()
        self.core.on_screen(["020", "021"])
        self.assertEqual(self.asked.count("010"), 1)  # the root's context: once
        self.assertLessEqual(len(self.asked), 2)  # (and one post's, to find the root)
        self.assertEqual(self.core.thread_size(self.w.statuses["013"]), 3)

    def test_the_window_thread_reads_nothing(self):
        """on_screen comes from a window's own thread while it scrolls: the store is
        asked in the background only."""
        ran = []
        self.core.bg.submit = lambda fn, *a, **kw: ran.append(fn)
        read = self.core.store.get_statuses
        self.core.store.get_statuses = lambda ids: self.fail("read in the caller's thread")
        self.core.on_screen(["020"])
        self.core.on_screen(["020"])
        self.assertEqual(len(ran), 1)  # one look, the second only noted
        self.core.store.get_statuses = read
        ran[0]()
        self.assertEqual(self.core.thread_size(self.w.statuses["012"]), 3)

    def test_what_left_the_screen_is_forgotten_with_counts_off(self):
        from fedtail.core import counts
        self.core.cfg["feed"]["counts_minutes"] = 0
        self.core.on_screen(["020"])
        with self.core._screen_lock():
            self.core._on_screen["020"] -= counts.SEEN_FOR + 1
        self.core.refresh_counts()
        self.assertEqual(self.core._on_screen, {})

    def test_threads_remembered_have_a_ceiling(self):
        from fedtail.core import threadsize
        old = threadsize.KEEP
        threadsize.KEEP = 10
        self.addCleanup(setattr, threadsize, "KEEP", old)
        for n in range(30):
            self.core.learn_thread_size(f"r{n}", [f"m{n}"], 1)
        self.assertLessEqual(len(self.core._ts_root), 12)
        self.assertLessEqual(len(self.core._ts_size), 12)
        self.assertEqual(self.core.thread_size({"id": "m29"}), 1)
