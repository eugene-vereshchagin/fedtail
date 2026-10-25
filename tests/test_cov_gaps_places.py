"""The places' last untested turns (frontends/common/places.py): a filter gone or kept
for an odd time, someone else's collections and one I'm in, leaving it, a collection
made for someone, the failures that are only logged (their server, the rules, the
tag suggestions, the profile flags), a server blocking no one, a link's next page, a
server name that isn't one."""

import tempfile
import unittest
from concurrent.futures import Future
from unittest import mock

from fedtail import i18n
from fedtail.core.view import View
from fedtail.frontends.common.places import Places

from . import scenario
from .fakes import ME, status


def _done(value):
    f = Future()
    f.set_result(value)
    return f


def failed(exc):
    f = Future()
    f.set_exception(exc)
    return f


class GapsTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.core, self.w = scenario.make_core(self._tmp.name)
        self.addCleanup(self.core.shutdown)
        self.view = View(self.core)
        self.pl = Places(self.view)

    def test_filter_gone_and_odd_time(self):
        with self.assertRaises(LookupError):
            self.pl.page("filter", "nope")
        fid = self.core.add_filter("шум", ["nft"]).result()["id"]
        out = self.pl.act("filter", "save", fid, values={"words": "nft", "expires": "soon"})
        self.assertEqual(out.error, "")  # an end that doesn't read: the one it has stays

    def bobs(self, state="pending"):
        self.w.collections["C9"] = {
            "id": "C9", "account_id": "B", "name": "Bob's", "description": "",
            "discoverable": True, "sensitive": True,
            "members": {"I1": (ME["id"], state)}}

    def test_someone_elses_collections_and_one_im_in(self):
        self.bobs()
        page = self.pl.page("collections", "B")
        self.assertIn("@", page.title)
        [row] = page.rows
        self.assertIn(i18n._("collection_sensitive"), row.line)
        self.assertEqual([b.act[1] for b in row.buttons], ["open"])  # not mine: no delete
        self.assertEqual(self.pl.act(*row.buttons[0].act).open,
                         {"page": "collection", "arg": "C9"})
        coll = self.pl.page("collection", "C9")
        [me] = coll.rows
        self.assertIn(i18n._("collection_pending"), me.line)
        leave = me.buttons[-1]
        self.assertEqual(leave.act[:2], ("collection", "leave"))
        self.assertTrue(self.pl.act(*leave.act).confirm)  # sure?
        out = self.pl.act(*leave.act, confirmed=True)
        self.assertEqual(out.message, i18n._("collection_left"))
        self.assertEqual(self.w.collections["C9"]["members"], {})
        self.assertFalse(coll.form)  # someone else's: nothing to edit
        with mock.patch.object(self.view, "account", return_value=_done(None)):
            self.assertIn("@B", self.pl.page("collections", "B").title)  # not known: the id

    def test_names_wanted_and_sure(self):
        self.assertTrue(self.pl.act("collections", "new", values={"name": " "}).error)
        cid = self.core.save_collection(None, "Мои").result()["id"]
        self.assertTrue(self.pl.act("collections", "delete", cid).confirm)
        self.assertTrue(self.pl.act("collection", "save", cid, values={}).error)
        self.assertTrue(self.pl.act("collect", "new", "B", values={"name": ""}).error)

    def test_a_collection_made_for_someone_and_taken_out(self):
        out = self.pl.act("collect", "new", "B", values={"name": "Для Боба"})
        self.assertIn("Для Боба", out.message)
        page = self.pl.page("collect", "B")
        row = next(r for r in page.rows if "Для Боба" in r.title)
        self.assertTrue(row.title.startswith("☑"))
        out = self.pl.act(*row.buttons[0].act)  # in already: out again
        self.assertEqual(out.message, i18n._("collection_taken_out"))
        self.w.no_featuring.add("N")
        out = self.pl.act("collect", "new", "N", values={"name": "Для Н"})
        self.assertTrue(out.error and out.refresh)  # made, but they don't allow it

    def test_failures_only_logged(self):
        with mock.patch.object(self.view, "account", return_value=failed(OSError("x"))):
            self.assertEqual(self.pl._origin_host("B"), "")
        with mock.patch.object(self.view, "server_info", return_value=failed(OSError("x"))):
            self.assertEqual(self.pl._rules(), ())
        page = self.pl.page("profile_edit")
        with mock.patch.object(self.view, "supports", return_value=False):
            before = len(page.rows)
            self.pl._tag_suggestions(page)
            self.assertEqual(len(page.rows), before)  # no featured tags here: nothing
        with mock.patch.object(self.view, "featured_tag_suggestions",
                               return_value=failed(OSError("x"))):
            before = len(page.rows)
            self.pl._tag_suggestions(page)
            self.assertEqual(len(page.rows), before)
        with mock.patch.object(self.view, "my_profile", return_value=failed(OSError("x"))):
            self.assertEqual(self.pl._profile_flags({"indexable": True}), {})

    def test_a_server_blocking_no_one(self):
        self.core.api.instance_domain_blocks = lambda: []
        page = self.pl.page("server")
        self.assertIn(i18n._("server_blocks_none"), [r.title for r in page.rows])

    def test_a_links_next_page(self):
        url = "https://news.example/story"
        for i in range(3):
            st = status(f"9{i}0", ME, minute=i, text="link", vis="public")
            st["card"] = {"url": url, "title": "Story"}
            self.w.add(st, home=True)
        self.core.poll_once()
        with mock.patch.dict(self.view.cfg["feed"], {"page_size": 2}):
            page = self.pl.page("link", url)
        self.assertIsNotNone(page.more)
        self.assertEqual(page.more.act[:2], ("link", "more"))

    def test_a_server_name_that_isnt_one(self):
        with mock.patch.object(self.view, "remote_public",
                               return_value=failed(ValueError("?"))):
            page = self.pl.page("remote", "not a server")
        self.assertEqual(page.empty, i18n._("remote_public_bad", text="not a server"))


if __name__ == "__main__":
    unittest.main()
