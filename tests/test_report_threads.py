"""Threads from the competitors' report: only the replies of people I follow, an open
thread asked again by itself, the author's server first ("remote"), and "Around this
post"."""

import time
from unittest import mock

from tests import fakes
from tests.fakes import BOB, ME, status

from .test_custom import FreeBase

FRIEND = fakes.acct("F", "friend@far.example")


class ThreadsTest(FreeBase):
    def thread(self, core, w):
        root = w.add(status("100", ME, minute=1, vis="public"), home=True)
        a = w.add(status("101", BOB, "100", "ME", minute=2))          # a stranger
        b = w.add(status("102", FRIEND, "101", "B", minute=3))        # a friend answers him
        c = w.add(status("103", BOB, "100", "ME", minute=4))          # the stranger again
        return root, a, b, c

    def ids(self, nodes):
        return [n.post["id"] if isinstance(n.post, dict) else n.post.id for n in nodes] \
            if nodes and hasattr(nodes[0], "post") else [x["id"] for x in nodes]

    def test_only_the_followed_and_what_they_answer(self):
        core, w = self.make([])
        core.connect().result()
        self.thread(core, w)
        core._following = {"F"}
        core._refresh_following = lambda: None
        full = core._thread_nodes("100")
        core.cfg["feed"]["thread_followed_only"] = True
        some = core._thread_nodes("100")
        flat = lambda t: [it.status["id"] for it in t]  # noqa: E731
        self.assertEqual(sorted(flat(full)), ["100", "101", "102", "103"])
        # the friend's reply stays, and the stranger's it answers; the other one goes
        self.assertEqual(sorted(flat(some)), ["100", "101", "102"])

    def test_an_open_thread_grows_by_itself(self):
        core, w = self.make([])
        core.connect().result()
        self.thread(core, w)
        core._thread_nodes("100")
        self.assertEqual(core.recheck_threads(), [])  # off by default
        core.cfg["feed"]["thread_recheck_minutes"] = 1
        core._rechecked["100"] = time.monotonic() - 120
        w.add(status("104", FRIEND, "100", "ME", minute=6))
        self.events.clear()
        self.assertEqual(core.recheck_threads(), ["100"])
        self.assertIn(("thread_grew", "100"), self.events)
        self.assertIsNotNone(core.store.get_status("104"))
        self.assertEqual(core.recheck_threads(), [])  # not due again yet

    def test_local_and_remote(self):
        core, w = self.make([])
        core.connect().result()
        self.thread(core, w)
        asked = []
        core._complete_thread = lambda root, known, emit=True: asked.append(emit) or \
            ([w.add(status("105", FRIEND, "100", "ME", minute=7))] if not emit else [])
        core.cfg["feed"]["thread_from"] = "local"
        core._thread_nodes("100")
        self.assertEqual(asked, [])  # never asks the author's server
        core.cfg["feed"]["thread_from"] = "remote"
        nodes = core._thread_nodes("100")
        self.assertEqual(asked, [False])  # asked first, waited for
        self.assertIn("105", [it.status["id"] for it in nodes])


class AroundTest(FreeBase):
    def test_around_a_post(self):
        from fedtail import i18n
        from fedtail.core import config
        from fedtail.core.view import View
        from fedtail.frontends.common import actions
        from fedtail.frontends.common.places import Places
        i18n.setup("en")
        core, w = self.make([])
        for i in range(1, 12):
            w.add(status(f"{i:03d}", BOB, minute=i, vis="public"), home=True)
        core.connect().result()
        core.poll_once()
        got = [st["id"] for st in core.around("006").result()]
        self.assertIn("006", got)
        self.assertIn("005", got)
        self.assertIn("007", got)
        self.assertEqual(got, sorted(got, reverse=True))
        page = Places(View(core)).page("around", "006")
        self.assertIn("006", [r.key for r in page.rows])
        # the menu item: only with feed.around_post (off by default)
        cfg, _w = config.validate({})
        self.assertFalse(cfg["feed"]["around_post"])
        self.assertTrue(callable(actions.menu))


if __name__ == "__main__":
    import unittest
    unittest.main()


class ProgressTest(FreeBase):
    def test_fetching_replies_says_how_it_goes(self):
        from fedtail import i18n
        from fedtail.frontends.common.progress import bar, thread_words
        i18n.setup("en")
        core, w = self.make([])
        core.connect().result()
        root = w.add(status("100", ME, minute=1, vis="public"), home=True)
        root["uri"] = "https://example.test/s/100"
        far = [f"https://far.example/s/{i}" for i in range(3)]
        from fedtail.core import replies
        steps = []
        core.events.on("thread_progress", lambda _n, p: steps.append(
            (core.thread_progress(p) or {}).get("stage")))
        with mock.patch.object(replies, "context_uris", return_value=far):
            core._complete_thread(dict(root), set())
        self.assertEqual(steps, [])  # threads.thread_progress off: nothing said
        core.cfg["feed"]["thread_progress"] = True
        core._completed.clear()
        with mock.patch.object(replies, "context_uris", return_value=far):
            core._complete_thread(dict(root), set())
        self.assertEqual(steps[0], "asking")
        self.assertEqual(steps.count("fetching"), 4)  # 0 of 3, then each one
        self.assertEqual(steps[-1], "done")
        step = core.thread_progress("100")
        self.assertEqual(step["total"], 3)
        self.assertEqual(thread_words(step),  # the fake server resolves none of them
                         "⇣ 3 replies there, but my server couldn't fetch them")
        self.assertEqual(thread_words({"stage": "fetching", "done": 1, "total": 4}),
                         "⇣ fetching replies: 1 of 4")
        self.assertEqual(bar({"stage": "fetching", "done": 1, "total": 4}, 4), "▰▱▱▱")
        core._thread_steps["100"]["at"] -= 60
        self.assertIsNone(core.thread_progress("100"))  # said long enough ago
