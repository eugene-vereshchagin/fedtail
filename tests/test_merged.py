"""All accounts in one window (core/merged.py), beyond tests/test_core.py's MergedTest:
every call the window makes is routed to the account the post, person or list came by
— ids prefixed on the way out, unprefixed on the way in — and every event of the other
account reaches the window in the window's terms."""

import unittest
from concurrent.futures import Future

from fedtail.core import auth, config, paths
from fedtail.core.app import Core
from fedtail.core.merged import MergedCore, full_handle

from . import fakes
from .fakes import BOB, ME, NEWS, FakeApi, status
from .test_core import TmpDir

T = 10


def done(value):
    f = Future()
    f.set_result(value)
    return f


class MergedRoutingTest(TmpDir):
    def setUp(self):
        super().setUp()
        FakeApi.world = home = fakes.World()
        work = fakes.World()
        work.me = dict(ME, id="W", acct="w", username="w")
        FakeApi.worlds = {"https://work.example": work}
        self.addCleanup(setattr, FakeApi, "worlds", {})
        cfg, _ = config.validate({"feed": {"first_run_mark_read": False,
                                           "complete_threads": False}})
        cores = []
        for name, server in (("home", "https://example.test"),
                             ("work", "https://work.example")):
            p = paths.resolve(name, config=str(self.tmp / f"{name}.toml"),
                              data=str(self.tmp / name))
            auth.save(p.auth_file, {"server": server, "token": "tok"})
            core = Core(cfg, p, api_class=FakeApi)
            core._origin_json = lambda url: None
            self.addCleanup(core.shutdown)
            cores.append(core)
        self.home, self.work = home, work
        self.p, self.w = cores
        self.m = MergedCore(self.p, {"work": self.w})
        self.events = []
        self.m.events.on("*", lambda n, pl: self.events.append((n, pl)))
        home.add(status("010", BOB, minute=10, text="дома"), home=True)
        work.add(status("500", NEWS, minute=11, text="через work"), home=True)
        work.add(status("501", BOB, "500", "N", minute=12, text="ответ через work"),
                 home=True)
        work.lists["WL"] = {"title": "Коллеги", "exclusive": False, "members": {"B"}}
        for core in (self.p, self.w):
            core.connect().result(timeout=T)
            core.poll_once()

    def emitted(self, name):
        return [pl for n, pl in self.events if n == name]

    # ---- ids ------------------------------------------------------------------------
    def test_handles_and_ids(self):
        m = self.m
        self.assertEqual(m.handle(None), "@mira@example.test")
        self.assertEqual(m.via("work"), "@w@work.example")
        self.assertEqual(m.post_accounts(), ([("", "@mira@example.test"),
                                              ("work", "@w@work.example")], ""))
        self.assertEqual(m.post_accounts("work~501")[1], "work")
        self.assertEqual(m.post_accounts({"id": "010"})[1], "")
        self.assertEqual(m.split("nope~1"), (self.p, None, "nope~1"))  # not a profile
        self.assertEqual(m.split(None), (self.p, None, None))
        self.assertIsNone(m.wrap("work", None))
        self.assertEqual(m.wrap(None, {"id": "1"}), {"id": "1"})

    def test_full_handle(self):
        class C:
            me = None
        self.assertEqual(full_handle(C()), "")
        C.me = {"acct": "a@b.test"}
        self.assertEqual(full_handle(C()), "@a@b.test")
        C.me = {"username": "a", "url": "https://c.test/@a"}
        self.assertEqual(full_handle(C()), "@a@c.test")
        C.me, C.auth = {"username": "a"}, {"server": "d.test"}
        self.assertEqual(full_handle(C()), "@a@d.test")

    def test_wrap_and_unwrap_round_trip(self):
        m = self.m
        st = {"id": "1", "in_reply_to_id": "0", "in_reply_to_account_id": "A",
              "account": {"id": "B"}, "mentions": [{"id": "C"}],
              "reblog": {"id": "2", "account": {"id": "D"}}}
        w = m.wrap("work", st)
        self.assertEqual((w["id"], w["in_reply_to_id"], w["account"]["id"],
                          w["mentions"][0]["id"], w["reblog"]["id"], w["_profile"]),
                         ("work~1", "work~0", "work~B", "work~C", "work~2", "work"))
        back = m._unwrap("work", w)
        self.assertEqual(back["id"], "1")
        self.assertEqual(back["reblog"]["account"]["id"], "D")
        self.assertNotIn("_via", back)
        self.assertEqual(m._unwrap("work", "x"), "x")
        # a status the other account's store doesn't have: unwrapped from what we hold
        core, tag, own = m.own({"id": "work~999", "account": {"id": "work~Z"}})
        self.assertEqual((core, tag, own["id"], own["account"]["id"]),
                         (self.w, "work", "999", "Z"))

    def test_then_passes_errors_on(self):
        bad = Future()
        bad.set_exception(KeyError("x"))
        with self.assertRaises(KeyError):
            self.m._then(bad, lambda r: r).result(timeout=T)
        with self.assertRaises(ZeroDivisionError):
            self.m._then(done(1), lambda r: r / 0).result(timeout=T)

    # ---- events of the other account ---------------------------------------------------
    def test_events_of_the_other_account(self):
        ev = self.w.events
        self.events.clear()
        ev.emit("lanes_updated", {"home": ["500"], "list:WL": ["501"]})
        self.assertEqual(self.emitted("lanes_updated")[-1],
                         {"home": ["work~500"], "list:work~WL": ["work~501"]})
        ev.emit("status_updated", {"id": "500"})
        self.assertEqual(self.emitted("status_updated")[-1]["id"], "work~500")
        ev.emit("status_deleted", "500")
        self.assertEqual(self.emitted("status_deleted")[-1], "work~500")
        ev.emit("arrived", [("a", "b")])
        self.assertEqual(self.emitted("arrived")[-1], [("work~a", "work~b")])
        ev.emit("thread_grew", "500")
        self.assertEqual(self.emitted("thread_grew")[-1], "work~500")
        ev.emit("notify", [("home", {"id": "500"}),
                           ("activity", {"id": "x", "type": "favourite"}),  # an event
                           ("list:WL", {"id": "501"})])
        self.assertEqual([(lane, st["id"]) for lane, st in self.emitted("notify")[-1]],
                         [("home", "work~500"), ("list:work~WL", "work~501")])
        n = len(self.emitted("notify"))
        ev.emit("notify", [("requests", {"id": "x", "type": "follow_request"})])  # main's only
        self.assertEqual(len(self.emitted("notify")), n)
        for name in ("parents", "lists_changed", "subs_changed", "sound"):
            ev.emit(name, {"p": 1})
            self.assertEqual(self.emitted(name)[-1], {"p": 1})
        ev.emit("ready", None)
        self.assertTrue(self.emitted("lists_changed"))
        ev.emit("error", "boom")
        self.assertEqual(self.emitted("error")[-1], "@w@work.example: boom")
        before = len(self.events)
        ev.emit("me_updated", {})  # stays the other account's
        self.assertEqual(len(self.events), before)
        self.p.events.emit("custom", 1)  # the main account's: as they are
        self.assertEqual(self.emitted("custom"), [1])

    # ---- lanes ---------------------------------------------------------------------
    def test_lists_of_the_other_account_are_lanes(self):
        m = self.m
        self.w._refresh_lists()
        lists = m.lists
        self.assertIn({"id": "work~WL", "title": "Коллеги · @w@work.example"},
                      [{"id": x["id"], "title": x["title"]} for x in lists])
        self.assertIn("list:work~WL", m.lane_by_name)
        self.assertEqual(m.lane_title("list:work~WL"), "Коллеги · @w@work.example")
        self.assertEqual(m.lane_title("list:nope"), "?")
        self.assertIsNone(m.lane_title("home"))
        self.assertEqual(m._own_lane("list:work~WL"), [(self.w, "work", "list:WL")])
        self.assertEqual(m.lane_entries("list:nope"), [])  # a lane nobody has

    def test_active_lanes_and_older(self):
        m = self.m
        seen = []
        for core, tag in ((self.p, "p"), (self.w, "w")):
            core.set_active_lane = lambda n, t=tag: seen.append((t, n))
            core.set_active_lanes = lambda ns, t=tag: seen.append((t, tuple(ns)))
        m.set_active_lane("home")
        self.assertEqual(seen, [("p", "home"), ("w", "home")])
        seen.clear()
        m.set_active_lane(None)
        self.assertEqual(seen, [("p", None), ("w", None)])
        seen.clear()
        m.set_active_lanes(["home", "list:work~WL"])
        self.assertEqual(sorted(seen), [("p", ("home",)), ("w", ("home", "list:WL"))])
        del self.p.set_active_lane, self.p.set_active_lanes
        del self.w.set_active_lane, self.w.set_active_lanes
        self.assertIsInstance(m.load_older("home").result(timeout=T), int)
        self.w._refresh_lists()
        self.assertIsInstance(m.load_older("list:work~WL").result(timeout=T), int)

    # ---- what cards need -----------------------------------------------------------
    def test_parents_and_replies_of_the_other_account(self):
        m = self.m
        reply = m.store.get_status("work~501")
        self.assertEqual(reply["in_reply_to_id"], "work~500")
        parents = m.parents_for([reply, m.store.get_status("010")])
        self.assertEqual(parents["work~501"]["id"], "work~500")  # by the reply's id
        self.assertIsNone(parents["010"])
        self.assertEqual(m.parent_of(reply)["id"], "work~500")
        self.assertIsNone(m.parent_of(m.store.get_status("010")))
        m.ensure_parents([reply])
        self.work.add(status("503", self.work.me, "500", "N", minute=13, text="мой ответ"),
                      home=True)
        self.w.poll_once()
        mine = m.my_replies([m.store.get_status("work~500")])
        self.assertEqual(list(mine), ["work~500"])
        self.assertTrue(all(x["id"].startswith("work~") for v in mine.values() for x in v))
        self.assertIs(m.cfg, self.p.cfg)  # the rest is the main account's
        self.assertTrue(m.thread("010").result(timeout=T))
        m.check_my_replies([reply])
        self.assertEqual(set(m.short_ids([m.store.get_status("010"), reply])), {"010"})
        self.assertEqual(m.store.read_set(["010", "work~501"]), set())
        m.mark_read(["010", "work~501"])
        self.assertEqual(m.store.read_set(["010", "work~501"]), {"010", "work~501"})
        self.assertTrue(callable(m.store.get_draft))  # the rest: the main store's

    # ---- actions -------------------------------------------------------------------
    def test_actions_go_from_the_account_that_got_the_post(self):
        m = self.m
        st = m.store.get_status("work~500")
        self.assertEqual(m.boost(st).result(timeout=T)["id"], "work~500")
        self.assertTrue(self.work.statuses["500"].get("reblogged"))
        m.bookmark(st, True).result(timeout=T)
        self.assertTrue(self.work.statuses["500"].get("bookmarked"))
        self.assertEqual(m.mute_thread(st).result(timeout=T)["id"], "work~500")
        self.assertIsInstance(m.history(st).result(timeout=T), list)
        self.assertEqual(m.reply_visibility(None), self.p.reply_visibility(None))
        self.assertTrue(m.reply_visibility(st))
        m.subscribe(st).result(timeout=T)
        self.assertTrue(m.subscribed(st))
        m.thread_quiet(st)
        m.unsubscribe(st).result(timeout=T)
        self.assertFalse(m.subscribed(st))

    def test_own_posts_of_the_other_account(self):
        m = self.m
        mine = m.post("мой через work", "public", account="work").result(timeout=T)
        self.assertTrue(mine["id"].startswith("work~"))
        self.assertEqual(self.work.posted[-1][0], "мой через work")
        sid = mine["id"].split("~", 1)[1]
        self.assertEqual(m.source(mine).result(timeout=T)["text"], "мой через work")
        m.edit(mine, "поправил").result(timeout=T)
        self.assertIn("поправил", self.work.statuses[sid]["content"])
        m.delete(mine).result(timeout=T)
        self.assertNotIn(sid, self.work.statuses)

    def test_polls(self):
        m = self.m
        poll = status("502", NEWS, minute=13, text="опрос")
        poll["poll"] = {"id": "P", "options": [{"title": "a", "votes_count": 0},
                                               {"title": "b", "votes_count": 0}],
                        "multiple": False, "expired": False, "voted": False,
                        "votes_count": 0}
        self.work.add(poll, home=True)
        self.w.poll_once()
        st = m.store.get_status("work~502")
        self.assertEqual(m.vote(st, [1]).result(timeout=T)["id"], "work~502")
        self.assertEqual(m.refresh_poll(st).result(timeout=T)["id"], "work~502")

    def test_reply_from_another_account_looks_the_post_up(self):
        m = self.m
        theirs = m.store.get_status("work~500")
        # the main account's server finds the post by its address
        self.home.remote[theirs["uri"]] = dict(status("700", NEWS, minute=11),
                                               uri=theirs["uri"])
        st = m.post("ответ с главного", "public", reply_to="work~500", account="",
                    draft_key="reply:work~500").result(timeout=T)
        self.assertEqual(st["id"], st["id"].split("~")[-1])  # the main account's
        self.assertEqual(self.home.posted[-1][2], "700")
        # the same account as the post's: straight there
        m.post("ответ с work", "public", reply_to="work~500", account="work").result(
            timeout=T)
        self.assertEqual(self.work.posted[-1][2], "500")
        # nowhere to be found: said plainly
        lost = dict(m.store.get_status("010"), uri="https://nowhere/1", url="")
        with self.assertRaises(LookupError):
            m.post("x", "public", reply_to=lost, account="work").result(timeout=T)
        # a quote goes the same way
        self.work.remote["https://example.test/statuses/010"] = dict(
            status("800", BOB, minute=10), uri="https://example.test/statuses/010")
        m.post("с цитатой", "public", account="work",
               quote=dict(m.store.get_status("010"),
                          uri="https://example.test/statuses/010")).result(timeout=T)
        self.assertTrue(self.work.posted)

    def test_lookup_tries_the_web_address_and_survives_errors(self):
        m = self.m
        calls = []

        def search(q, kind=None, resolve=True, limit=5):
            calls.append(q)
            if q == "https://u/1":
                raise RuntimeError("server error")
            return {"statuses": [dict(status("900", BOB), uri=q)]}
        self.w.api.search = search
        st = m._lookup({"id": "010", "uri": "https://u/1", "url": "https://w/1"}, self.w,
                       "@w")
        self.assertEqual((st["id"], calls), ("900", ["https://u/1", "https://w/1"]))
        # an id of the target's own store: no search at all
        self.assertEqual(m._lookup("work~500", self.w, "@w")["id"], "500")
        # an id nobody holds, asked on its own account: as it was given
        self.assertEqual(m._lookup("unknown-id", self.p, "@me"), {"id": "unknown-id"})

    def test_act_as(self):
        m = self.m
        st = m.store.get_status("work~500")
        self.assertEqual(m.act_accounts(st), [(None, "@mira@example.test")])
        self.assertEqual(m.act_accounts(m.store.get_status("010")),
                         [("work", "@w@work.example")])
        self.home.remote[st["uri"]] = dict(status("701", NEWS, minute=11), uri=st["uri"])
        got = m.act_as(st, None, "fav").result(timeout=T)
        self.assertEqual(got["id"], "701")
        self.assertTrue(self.home.statuses["701"]["favourited"])
        m.act_as(st, None, "boost").result(timeout=T)
        self.assertTrue(self.home.statuses["701"]["reblogged"])
        self.assertEqual(m.act_as(st, None, "find").result(timeout=T)["id"], "701")

    # ---- people ---------------------------------------------------------------------
    def test_people_through_their_account(self):
        m = self.m
        self.assertEqual(m.account("work~B").result(timeout=T)["id"], "work~B")
        self.assertEqual(m.account("B").result(timeout=T)["id"], "B")
        m.follow("work~N").result(timeout=T)
        self.assertIn("N", self.work.following)
        m.mute("work~N").result(timeout=T)
        self.assertIn("N", self.work.muted)
        m.mute("work~N", duration=60, notifications=False).result(timeout=T)
        self.assertEqual(self.work.mute_terms["N"], {"duration": 60, "notifications": False})
        m.block("work~N").result(timeout=T)
        self.assertIn("N", self.work.blocked)
        page = m.account_statuses("work~N").result(timeout=T)
        self.assertTrue(all(s["id"].startswith("work~") for s in page))
        m.account_statuses("work~N", "work~500").result(timeout=T)
        media = m.account_statuses("work~N", show="media").result(timeout=T)
        self.assertTrue(all(s["media_attachments"] for s in media))
        m.hide_post("work~500").result(timeout=T)  # the work account's filter, its id
        hid = [f for f in self.work.filters.values() if f["title"] == self.w.HIDDEN_POSTS]
        self.assertEqual([x["status_id"] for x in hid[0]["statuses"]], ["500"])
        self.assertIn("500", self.w.hidden_posts)
        self.assertTrue(m.unhide_post({"id": "work~500"}).result(timeout=T))
        m.hide_post("010").result(timeout=T)  # my own account's
        self.assertIn("010", self.p.hidden_posts)
        self.assertIsInstance(m.familiar("work~N").result(timeout=T), list)
        m.endorse("work~N").result(timeout=T)
        m.remove_follower("work~N").result(timeout=T)
        self.assertEqual(m.followed_among([]).result(timeout=T), [])
        among = m.followed_among([{"id": "work~N", "acct": "news"}]).result(timeout=T)
        self.assertTrue(all(a["id"].startswith("work~") for a in among))
        self.w._refresh_lists()
        self.assertEqual(m.lists_of("work~B"), {"work~WL"})
        m.set_in_list("work~WL", "work~N", True).result(timeout=T)
        self.assertIn("N", self.work.lists["WL"]["members"])

    def test_wrap_any(self):
        m = self.m
        self.assertEqual(m._wrap_any("work", [{"id": "1", "content": "x"}, 3])[0]["id"],
                         "work~1")
        self.assertEqual(m._wrap_any("work", {"id": "1", "acct": "a"})["id"], "work~1")
        self.assertEqual(m._wrap_any("work", 5), 5)

    def test_reactions_and_quotes(self):
        m = self.m
        self.work.reactions["500"] = {"favourited_by": [dict(BOB)], "reblogged_by": []}
        st = m.store.get_status("work~500")
        res, _nxt = m.who_reacted(st, "favourited_by").result(timeout=T)
        self.assertEqual([a["id"] for a in res["accounts"]], ["work~B"])
        self.assertTrue(all(k.startswith("work~") for k in res["relations"]))
        mine = m.who_reacted(m.store.get_status("010"), "favourited_by").result(timeout=T)
        self.assertEqual(mine[0]["accounts"], [])
        res, _n = m.who_reacted_from_origin(st, "favourited_by", ["work~B"]).result(
            timeout=T)
        self.assertIn("accounts", res)
        quote = status("600", BOB, minute=14, text="цитата")
        self.work.add(quote)
        self.work.quotes["500"] = [quote]
        quotes, _n = m.quotes_of(st).result(timeout=T)
        self.assertEqual([q["id"] for q in quotes], ["work~600"])
        m.revoke_quote(st, quotes[0]).result(timeout=T)

    # ---- the family ------------------------------------------------------------------
    def test_poll_state_over_every_account(self):
        """Busy while any account is starting or in a round (the curtain's opossum
        swings in the merged window too); failing as the worst; ok_at the stalest; the
        poll_state events of the other account reach the window."""
        m = self.m
        self.assertFalse(m.poll_state()["busy"])  # both polled once in setUp
        self.events.clear()
        self.w._polling = True
        self.w.emit("poll_state", True)
        self.assertTrue(m.poll_state()["busy"])
        self.assertIn(("poll_state", True), self.events)
        self.w._polling = False
        self.p._last_poll_ok, self.w._last_poll_ok = 2000.0, 1000.0
        self.p._fails_in_row, self.w._fails_in_row = 0, 3
        self.assertEqual(m.poll_state(), {"busy": False, "ok_at": 1000.0, "failing": 3})
        # one that never had a good round, or can't say, doesn't hide the others' time
        self.w._last_poll_ok = None
        self.w.poll_state = lambda: (_ for _ in ()).throw(AttributeError("old core"))
        self.assertEqual(m.poll_state(), {"busy": False, "ok_at": 2000.0, "failing": 0})
        from fedtail.core.view import View
        from fedtail.frontends.common import sidebar
        self.p._starting = True  # the main one starting: the View says busy
        self.assertTrue(sidebar.polling(View(m)))

    def test_connect_poll_shutdown_reach_every_account(self):
        m = self.m
        seen = []
        for core, t in ((self.p, "p"), (self.w, "w")):
            core.poll_now = lambda t=t: seen.append(("poll", t))
            core.start_polling = lambda t=t: seen.append(("start", t))
        m.poll_now()
        self.assertEqual(seen, [("poll", "p"), ("poll", "w")])
        seen.clear()
        m.connect().result(timeout=T)
        for _ in range(100):
            if ("start", "w") in seen:
                break
            import time
            time.sleep(0.02)
        self.assertIn(("start", "w"), seen)  # the other one polls once connected
        m.start_polling()
        self.assertIn(("start", "p"), seen)
        # one that can't connect stays quiet (a warning, nothing else)
        bad = Future()
        bad.set_exception(OSError("down"))
        self.w.connect = lambda: bad
        m.connect().result(timeout=T)
        closed = []
        self.p.shutdown = lambda: closed.append("p")
        self.w.shutdown = lambda: closed.append("w")
        m.shutdown()
        self.assertEqual(closed, ["w", "p"])
        self.assertTrue(self.w.logged_in)
        from unittest import mock
        self.w.connect = lambda: self.fail("connected an account not logged in")
        with mock.patch.object(type(self.w), "logged_in", new_callable=mock.PropertyMock,
                               return_value=False):
            self.p.connect = lambda: done(None)
            m.connect().result(timeout=T)  # one not logged in isn't connected at all

    # ---- the web page (and the phone, through it) -----------------------------------
    def test_web_act_as_from_the_menu(self):
        """A post's ⋯ on the page offers ★ ♻ ↩ from the other account, as the windows'
        menu does; the other account's ids ("work~500") are ids there too."""
        from fedtail.core.view import View
        from fedtail.frontends.web.server import Web
        web = Web(View(self.m), None)
        st = self.m.store.get_status("work~500")
        menu = web.post_menu("work~500")
        acts = [i for i in menu["items"] if i["kind"] == "act_as"]
        self.assertEqual(len(acts), 1)
        choices = acts[0]["choices"]
        self.assertEqual({c["action"] for c in choices}, {"fav", "boost", "reply"})
        self.assertEqual({c["tag"] for c in choices}, {""})  # the main account
        self.home.remote[st["uri"]] = dict(status("701", NEWS, minute=11), uri=st["uri"])
        got = web.act_as("work~500", "", "fav")
        self.assertIn("@mira", got["message"])
        self.assertTrue(self.home.statuses["701"]["favourited"])
        got = web.act_as("work~500", "", "reply")
        self.assertEqual(got["compose"]["reply_to"], "701")
        self.assertEqual(got["post"]["sid"], "701")
        with self.assertRaises(ValueError):
            web.act_as("work~500", "", "delete")
        # one account alone: no such item, no such act
        alone = Web(View(self.p), None)
        self.assertFalse([i for i in alone.post_menu("010")["items"] if i["kind"] == "act_as"])


if __name__ == "__main__":
    unittest.main()
