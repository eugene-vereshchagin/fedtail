"""The web interface's server beyond tests/test_web.py: what each piece of a post becomes
for the page (polls, cards, quotes, media, shares, missing parents), the window stand-in
links and profiles talk to (_WebHost), the API's odd corners (an unknown lane, a bad
attachment, a scheduled post, an account not offered, a command that opens something),
the handler's refusals, and `fedtail --ui web`'s run()."""

import io
import json
import threading
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from unittest import mock

from fedtail import i18n
from fedtail.core import auth, config, paths
from fedtail.core.app import Core
from fedtail.frontends.web import server as web
from fedtail.model import (
    Account,
    Card,
    Media,
    Poll,
    PollOption,
    Quote,
    Ref,
)

from . import fakes
from .fakes import BOB, ME, FakeApi, status
from .test_core import TmpDir


def make_core(tmp, **over):
    FakeApi.world = fakes.World()
    user = {"feed": {"first_run_mark_read": False}, "ui": {"language": "en"},
            "lanes": {"enabled": fakes.CLASSIC_LANES}}
    for k, v in over.items():
        user.setdefault(k, {}).update(v)
    cfg, _ = config.validate(user)
    p = paths.resolve("t", config=str(tmp / "c.toml"), data=str(tmp / "d"))
    auth.save(p.auth_file, {"server": "https://example.test", "token": "tok"})
    core = Core(cfg, p, api_class=FakeApi)
    core._origin_json = lambda url: None
    return core, FakeApi.world


R = Ref("mastodon", "", "1")


class PiecesTest(TmpDir):
    def setUp(self):
        super().setUp()
        i18n.setup("en")

    def test_account_media_card(self):
        self.assertEqual(web.account_json(None)["id"], None)
        m = Media(R, "image", url="", preview="http://plain/p.png",
                  remote_url="https://far/x.png", alt="a", width=3, height=4)
        self.assertEqual(web.media_json(m), {"kind": "image", "preview": "",
                                             "url": "/pic?u=https%3A%2F%2Ffar%2Fx.png", "alt": "a",
                                             "w": 3, "h": 4})
        self.assertIsNone(web.card_json(None))
        self.assertIsNone(web.card_json(Card("http://plain")))  # not https: no card
        self.assertEqual(web.card_json(Card("https://a", "T", image="https://i",
                                            provider="P"))["image"], "/pic?u=https%3A%2F%2Fi")

    def test_poll(self):
        self.assertIsNone(web.poll_json(None))
        later = datetime.now(UTC) + timedelta(days=1)
        p = Poll(R, (PollOption("a", 3), PollOption("b", 1)), multiple=True, expires=later,
                 votes=4, my_votes=(0,))
        got = web.poll_json(p)
        self.assertEqual([o["share"] for o in got["options"]], [75, 25])
        self.assertIn(i18n._("poll_multiple"), got["summary"])
        self.assertEqual(got["mine"], [0])
        closed = web.poll_json(Poll(R, (PollOption("a", None),), expired=True))
        self.assertIn(i18n._("poll_closed"), closed["summary"])
        self.assertEqual(closed["options"][0]["share"], 0)

    def test_quote(self):
        self.assertIsNone(web.quote_json(None, None))
        self.assertEqual(web.quote_json(None, Quote("revoked", None, "9"))["note"],
                         i18n._("quote_revoked"))
        self.assertEqual(web.quote_json(None, Quote("weird", None, "9"))["note"],
                         i18n._("quote_unavailable"))
        core, w = make_core(self.tmp)
        self.addCleanup(core.shutdown)
        w.add(status("001", BOB, minute=1, text="quoted"), home=True)
        core.connect().result()
        core.poll_once()
        from fedtail.core.view import View
        post = View(core).by_id("001")
        got = web.quote_json(None, Quote("accepted", post, "001"))
        self.assertEqual((got["id"], got["text"]), ("001", "quoted"))

    def test_dates_and_errors(self):
        self.assertEqual(web.web_date(None), "")
        now = datetime.now(UTC)
        self.assertEqual(web.web_date(now), now.astimezone().strftime("%H:%M"))
        self.assertIn(".", web.web_date(now - timedelta(days=3)))
        from fedtail.protocols.base import ServerError
        self.assertIn("nope", web._api_error(ServerError(422, "nope")))
        self.assertEqual(web._api_error(OSError("https://secret/?q=x")), "OSError")
        self.assertEqual(web.Web._date(None), "")
        self.assertEqual(web.Web._date_time(None), "")
        self.assertEqual(web._int("x", 7), 7)


class Host:
    """A view stand-in for _WebHost."""

    def __init__(self, found=None, fail=False):
        self.found, self.fail = found, fail

    def resolve(self, url):
        from concurrent.futures import Future
        f = Future()
        if self.fail:
            f.set_exception(OSError("down"))
        else:
            f.set_result(self.found)
        return f

    def source(self, post):
        from concurrent.futures import Future
        f = Future()
        f.set_result(("src", "cw"))
        return f


class WebHostTest(TmpDir):
    def test_calls_and_places(self):
        from concurrent.futures import Future
        h = web._WebHost(Host(), confirmed=False)
        bad = Future()
        bad.set_exception(RuntimeError("no"))
        h.call(bad)
        self.assertEqual(h.out["error"], "no")
        seen = []
        h.call(bad, fail=seen.append)
        self.assertEqual(seen, ["no"])
        ok = Future()
        ok.set_result(5)
        h = web._WebHost(Host(), confirmed=False)
        h.call(ok, ok=seen.append)
        self.assertEqual((seen[-1], h.out["refresh"]), (5, True))
        h.status("hi")
        h.confirm("t", "sure?", lambda: seen.append("did"))
        self.assertEqual(h.out["confirm"], "sure?")
        web._WebHost(Host(), True).confirm("t", "x", lambda: seen.append("did"))
        self.assertEqual(seen[-1], "did")
        post = mock.Mock(id="P")
        acc = mock.Mock(id="A")
        for call, want in ((lambda: h.open_url("u"), {"url": "u"}),
                           (lambda: h.open_tag("t"), {"page": "tag", "arg": "t", "tab": ""}),
                           (lambda: h.report(post), {"page": "report", "arg": "P", "tab": ""}),
                           (lambda: h.open_reactions(post, "k"),
                            {"page": "reactions", "arg": "P", "tab": "k"}),
                           (lambda: h.open_quotes(post), {"page": "quotes", "arg": "P",
                                                          "tab": ""}),
                           (lambda: h.open_people(acc, "followers"),
                            {"page": "people", "arg": "A", "tab": "followers"}),
                           (lambda: h.edit_profile(), {"page": "profile_edit", "arg": "",
                                                       "tab": ""}),
                           (lambda: h.open_lists(acc), {"page": "list_of", "arg": "A",
                                                        "tab": ""})):
            call()
            self.assertEqual(h.out["open"], want)
        with mock.patch.object(web, "real", lambda p: p):
            h.show_history(post)
        self.assertEqual(h.out["open"]["page"], "history")
        h.put_alias("ab")
        h.copy_handle("@me@x")
        h.view = mock.Mock(stored=lambda _i: None)  # nothing shown: that post alone
        h.read_up_to("9")
        self.assertEqual((h.out["alias"], h.out["copy"], h.out["read"]),
                         ("ab", "@me@x", ["9"]))
        h.view.mark_read.assert_called_once_with(["9"])

    def test_resolve_link(self):
        acc = Account(Ref("mastodon", "", "A"), "a", "a")
        h = web._WebHost(Host(found=acc), False)
        h.resolve_link("https://x/@a")
        self.assertEqual(h.out["open"], {"account": "A"})
        h = web._WebHost(Host(found=mock.Mock(id="S")), False)
        h.resolve_link("https://x/1")
        self.assertEqual(h.out["open"], {"thread": "S", "at": "post"})
        h = web._WebHost(Host(fail=True), False)
        h.resolve_link("https://x/1")
        self.assertEqual(h.out["open"], {"url": "https://x/1"})
        h = web._WebHost(Host(), False)
        h.resolve_link("fedtail:nothing")
        self.assertNotIn("open", h.out)

    def test_compose_and_redraft(self):
        h = web._WebHost(Host(), False)
        post = mock.Mock(id="P")
        pic = mock.Mock(ref=mock.Mock(id="m1"), alt="a", kind="image", preview="",
                        url="https://x/m1.png", focus=(0.5, -0.5))
        with mock.patch.object(web, "real", lambda p: mock.Mock(
                visibility="public", id="R", author=mock.Mock(handle="bob@x"),
                media=(pic,))):
            h.compose(edit=post)
            self.assertEqual(h.out["compose"], {
                "edit": "P", "text": "src", "cw": "cw", "visibility": "public",
                "media": [{"id": "m1", "alt": "a", "kind": "image",
                           "url": "/pic?u=https%3A%2F%2Fx%2Fm1.png", "focus": [0.5, -0.5]}]})
            h.compose(quote=post)
            self.assertEqual(h.out["compose"], {"quote": "R", "quote_of": "@bob@x"})
        h.compose(reply_to=post, invite=True)
        self.assertEqual(h.out["compose"], {"reply_to": "P", "invite": True, "text": "@"})
        h.compose(text="hi")
        self.assertEqual(h.out["compose"], {"text": "hi"})
        got = []
        h.answer = "yes"
        h.ask_text("t", "q", got.append)
        self.assertEqual(got, ["yes"])
        h.answer = None
        h.ask_text("t", "q", got.append, text="x")
        self.assertEqual(h.out["ask"], {"title": "t", "question": "q", "text": "x"})
        d = mock.Mock(text="t", warning="", visibility="public", language="", reply_to=None,
                      media=2)
        h.redrafted(d)
        self.assertEqual(h.out["compose"]["text"], "t")
        self.assertEqual(h.out["message"], i18n._("redraft_media", n=2))


class WebBase(TmpDir):
    def setUp(self):
        super().setUp()
        i18n.setup("en")
        self.core, self.w = make_core(self.tmp)
        self.addCleanup(self.core.shutdown)
        self.w.add(status("001", ME, minute=1, text="mine", vis="public"), home=True)
        self.w.add(status("002", BOB, "gone", "X", minute=2, text="orphan"), home=True)
        self.core.connect().result()
        self.core.poll_once()
        old = self.core.paths.data_dir / "web-uploads"
        old.mkdir(parents=True, exist_ok=True)
        (old / "left.png").write_bytes(b"x")
        self.web = web.Web(self.core, "KEY")
        self.assertFalse((old / "left.png").exists())  # last run's attachments: gone


class WebEventLanesTest(WebBase):
    """Activity and Requests are lanes of rules like any (feeds.md, 28.10): the page gets
    their rows as events of the lane, each in its parts (common/activity.EventParts), its
    buttons fedtail: links done by /api/link; seen on screen through /api/read."""

    def like(self, nid, post_id="001", minute=1):
        self.core.store.activity_put([{
            "id": nid, "type": "favourite", "account": BOB,
            "created_at": f"2026-10-28T10:{minute:02d}:00.000Z",
            "status": status(post_id, ME, minute=1)}])
        self.core._events_cache = {}

    def follow(self, nid, minute=3):
        self.core.store.activity_put([{
            "id": nid, "type": "follow", "account": BOB,
            "created_at": f"2026-10-28T10:{minute:02d}:00.000Z"}])
        self.core._events_cache = {}

    def events(self, name):
        return {e["key"]: e["event"] for e in self.web.lane(name)["events"]}

    def test_likes_listed_as_full_rows(self):
        self.like("n1")
        got = self.web.lane("activity")
        self.assertNotIn("place", got)
        (ev,) = got["events"]
        self.assertEqual(ev["key"], "event:n1")
        self.assertIsNone(ev["before"])  # no posts: after the last of none
        x = ev["event"]
        self.assertEqual(x["kind"], "favourite")
        self.assertEqual([u for _n, u in x["people"]], ["fedtail:account/B"])
        self.assertTrue(x["people"][0][0])
        self.assertTrue(x["what"])
        self.assertEqual(x["post_link"], "fedtail:thread/001")
        self.assertIn("«", x["post"])
        self.assertTrue(x["hide"].startswith("fedtail:eventhide/"))
        self.assertEqual(x["answers"], [])
        self.assertEqual(len(x["answer_words"]), 2)
        self.assertTrue(x["unread"])
        self.assertEqual(got["clear"]["label"], i18n._("activity_clear"))
        self.assertIsNone(self.web.lane("home")["clear"])  # posts: nothing to clear

    def test_a_request_answered_by_its_button(self):
        self.w.requests.append(BOB)
        self.core.poll_once()
        x = self.events("requests")["event:follow_request:B"]
        self.assertEqual(x["kind"], "follow_request")
        yes, no = x["answers"][0]
        self.assertTrue(yes.startswith("fedtail:eventyes/") and no.startswith("fedtail:eventno/"))
        got = self.web.link(yes)
        self.assertTrue(got.get("refresh"))
        self.assertEqual(self.core.follow_requests, [])
        self.assertEqual(self.events("requests"), {})

    def test_x_hides_the_row(self):
        self.like("n2")
        x = self.events("activity")["event:n2"]
        self.web.link(x["hide"])
        self.assertEqual(self.events("activity"), {})

    def test_seen_counts_down(self):
        self.like("n3", minute=1)
        self.follow("n4", minute=2)
        self.core.store.kv_set("activity_seen", "")
        self.assertEqual(self.core.unread_count("activity"), 2)
        keys = sorted(self.events("activity"))
        older = min(keys, key=lambda k: self.web.model("activity").event_sorts[k])
        self.web.read([older])  # the older row seen on screen: the newer one still new
        self.assertEqual(self.core.unread_count("activity"), 1)
        self.assertEqual(sum(x["unread"] for x in self.events("activity").values()), 1)
        self.web.read([], lane="activity")  # "mark all read" over the lane: its events too
        self.assertEqual(self.core.unread_count("activity"), 0)
        self.assertFalse(any(x["unread"] for x in self.events("activity").values()))

    def test_chips_filter_the_rows(self):
        self.like("n5")
        self.follow("n8")
        got = self.web.lane("activity")
        self.assertEqual(len(got["events"]), 2)
        chips = {words: key for key, words, _tip in got["filters"]}
        self.web.lane_set({"name": "activity", "filter": chips[i18n._("actf_follows")]})
        kinds = {e["event"]["kind"] for e in self.web.lane("activity")["events"]}
        self.assertEqual(kinds, {"follow"})
        self.web.lane_set({"name": "activity", "filter": chips[i18n._("actf_reactions")]})
        kinds = {e["event"]["kind"] for e in self.web.lane("activity")["events"]}
        self.assertEqual(kinds, {"favourite"})

    def test_clear_asks_first(self):
        self.like("n6")
        self.assertIn("confirm", self.web.lane_clear("activity"))
        self.assertEqual(len(self.events("activity")), 1)
        self.assertEqual(self.web.lane_clear("activity", confirmed=True), {"refresh": True})
        self.core._events_cache = {}
        self.assertEqual(self.events("activity"), {})
        with self.assertRaises(ValueError):
            self.web.lane_clear("home")  # posts: not a lane of events only

    def test_events_wake_the_page(self):
        v = self.web.version
        self.core.emit("activity_seen", "x")
        self.core.emit("requests_updated", [])
        self.core.emit("activity_updated", None)
        self.assertEqual(self.web.version, v + 3)


class WebApiTest(WebBase):

    def test_posts_with_shares_and_missing_parents(self):
        from fedtail.model import Share
        v = self.web.core
        p = v.by_id("002")
        share = Share(Ref("mastodon", "", "S1"), v.me, p, None, "S1")
        got = web.post_json(v, share, parent="missing")
        self.assertEqual(got["shared_by"]["id"], v.me.id)
        self.assertEqual(got["context"], {"missing": True})

    def test_lanes_find_and_choices(self):
        wb = self.web
        got = wb.lane("activity")  # a lane as any: no place in its stead
        self.assertNotIn("place", got)
        self.assertEqual(got["posts"], [])
        with self.assertRaises(KeyError):
            wb.lane("nope")
        self.assertEqual(wb.find("home", "  "), {"ids": [], "text": ""})
        got = wb.find("home", "orphan")
        self.assertEqual(got["ids"], ["002"])
        self.assertTrue(got["text"])
        self.assertEqual(wb.find("home", "zzzz")["ids"], [])
        m = wb.model("home")
        wb.lane_set({"name": "home", "media": "boosts", "on": False})
        self.assertFalse(m.media.boosts)
        wb.lane_set({"name": "home", "media": "image", "on": True})
        wb.lane_set({"name": "home", "media": "reset"})
        with mock.patch.object(m, "conversations_offered", return_value=True), \
                mock.patch.object(m, "set_conversations") as setc:
            wb.lane_set({"name": "home", "conversations": True})
        setc.assert_called_once_with(True)
        lane = wb.lane("home")
        self.assertTrue(lane["posts"])

    def test_newest_first_lane(self):
        self.core.cfg["feed"]["order"] = "newest_first"
        wb = web.Web(self.core, "K")
        ids = [p["id"] for p in wb.lane("home")["posts"]]
        self.assertEqual(ids, sorted(ids))  # the page turns it round itself

    def test_uploads(self):
        wb = self.web
        with self.assertRaises(ValueError):
            wb.upload(b"", "x.png")
        tok = wb.upload(b"data", "weird.name with spaces?")["token"]
        self.assertNotIn(".", tok)  # an odd extension is dropped
        self.assertTrue(wb.upload_path(tok).is_file())
        for bad in (None, "../x", "a/b"):
            with self.assertRaises(ValueError):
                wb.upload_path(bad)
        with self.assertRaises(ValueError):
            wb.upload_path("AAAAAAAAAAAAAAAA.png")  # gone

    def test_post_variants(self):
        wb = self.web
        with self.assertRaises(ValueError):
            wb.post({"text": "  "})
        with self.assertRaises(ValueError):
            wb.post({"text": "x", "visibility": "everyone"})
        r = wb.post({"text": "old page", "visibility": "private"})
        self.assertTrue(r["id"])
        self.assertEqual(self.w.posted[-1][1], "private")  # followers, the API's word
        r = wb.post({"text": "later", "scheduled_at": "2099-01-01T10:00"})
        self.assertTrue(r["scheduled"])
        with self.assertRaises(ValueError):
            wb.post({"text": "x", "account": "someone"})
        with mock.patch.object(wb.core, "post_accounts", return_value=([("", "@me")], "")):
            wb.post({"text": "from me", "account": ""})
        mine = wb.post({"text": "to edit"})
        got = wb.post({"text": "edited", "edit": mine["id"]})
        self.assertTrue(got["edited"])
        with mock.patch.object(wb.core, "edit") as ed:
            from concurrent.futures import Future
            f = Future()
            f.set_result(None)
            ed.return_value = f
            self.assertEqual(wb.post({"text": "e", "edit": "001"})["id"], None)
        with mock.patch.object(wb.core, "post") as po:
            f = Future()
            f.set_result(None)
            po.return_value = f
            self.assertEqual(wb.post({"text": "e"}), {"id": None, "url": ""})

    def test_editor_facts_with_several_accounts(self):
        with mock.patch.object(self.web.core, "post_accounts",
                               return_value=([("", "@me@x"), ("w", "@w@y")], "")):
            facts = self.web.editor_facts()
        self.assertEqual(len(facts["accounts"]), 2)

    def test_account_and_follow(self):
        wb = self.web
        with mock.patch.object(wb.core, "relationship", side_effect=RuntimeError):
            got = wb.account("B")
        self.assertFalse(got["relation"]["following"])
        with mock.patch.object(wb.core, "follow") as fo:
            from concurrent.futures import Future
            f = Future()
            f.set_result(None)
            fo.return_value = f
            self.assertEqual(wb.follow("B", True), {"following": True, "requested": False})

    def test_profile_and_link_errors(self):
        wb = self.web
        with self.assertRaises(ValueError):
            wb.profile_act("B", "nonsense")
        from fedtail.frontends.common import profile as prof
        with mock.patch.object(prof, "do", lambda key, acc, rel, core, host, done:
                               host.error("broken")):
            with self.assertRaises(ValueError):
                wb.profile_act("B", "follow")
        from fedtail.frontends.common import links
        with mock.patch.object(links.Links, "open", lambda self, url: self.host.error("bad")):
            with self.assertRaises(ValueError):
                wb.link("fedtail:x")
        with self.assertRaises(KeyError):
            wb.act("like", "nope")

    def test_post_menu_drops_leading_separators(self):
        from fedtail.frontends.common import actions
        sep = mock.Mock(kind="separator", label="", url="", text="")
        tr = mock.Mock(kind="translate", label="T", url="", text="")
        with mock.patch.object(actions, "menu", return_value=[sep, sep, tr]):
            got = self.web.post_menu("001")
        self.assertEqual([x["kind"] for x in got["items"]], ["translate"])

    def test_command_opens_a_profile(self):
        from concurrent.futures import Future
        f = Future()
        f.set_result(("profile", mock.Mock(id="B")))
        with mock.patch.object(self.web.cmds, "run", return_value=(f, "")):
            self.assertEqual(self.web.command("@bob")["open"], {"account": "B"})

    def test_page_rows_and_place_act(self):
        from fedtail.frontends.common import places
        pg = places.Page("x", "X", rows=[
            places.Row("account", "a", data=self.web.core.me),
            places.Row("pre", "<b>"),
            places.Row("html", "<p onclick=x>hi</p>")])
        with mock.patch.object(places.Places, "page", return_value=pg):
            got = self.web.page("about")
        kinds = [r["kind"] for r in got["rows"]]
        self.assertEqual(kinds, ["account", "html", "html"])
        self.assertEqual(got["rows"][1]["html"], "<pre>&lt;b&gt;</pre>")
        self.assertNotIn("onclick", got["rows"][2]["html"])
        with self.assertRaises(ValueError):
            self.web.place_act({"act": "nope"})
        out = places.Out(ask=("T", "Q", "x"))
        with mock.patch.object(places.Places, "act", return_value=out):
            self.assertEqual(self.web.place_act({"act": ["a", "b", "c"]})["ask"],
                             {"title": "T", "question": "Q", "text": "x"})
        with mock.patch.object(places.Places, "act", return_value=places.Out(error="E")):
            with self.assertRaises(ValueError):
                self.web.place_act({"act": ["a", "b", "c"]})
        with mock.patch.object(places.Places, "help_target",
                               return_value=places.Out(open={"page": "help"})):
            self.assertEqual(self.web.help_link("fedtail:help/x", "index"), {"page": "help"})

    def test_resolve(self):
        from concurrent.futures import Future

        def fut(v):
            f = Future()
            f.set_result(v)
            return f
        acc = Account(Ref("mastodon", "", "A"), "a", "a")
        for found, want in ((None, {"found": None}),
                            (acc, {"found": "account", "id": "A"}),
                            (mock.Mock(id="S"), {"found": "thread", "id": "S"})):
            with mock.patch.object(self.web.core, "resolve", return_value=fut(found)):
                self.assertEqual(self.web.resolve("u"), want)

    def test_notes_and_sounds(self):
        wb = self.web
        self.core.cfg["notify"]["enabled"] = False
        wb.notified([("home", {"id": "001"})])
        self.assertEqual(wb.note_seq, 0)
        self.core.cfg["notify"]["enabled"] = True
        from fedtail.frontends import notifytext
        with mock.patch.object(notifytext, "build", side_effect=RuntimeError), \
                self.assertLogs("fedtail", "ERROR"):
            wb.notified([("home", {"id": "001"})])
        self.assertEqual(wb.note_seq, 0)

        class Snd:
            def __init__(self, kind, value="", file=""):
                self.kind, self.value, self.file = kind, value, file
        f = self.tmp / "s.wav"
        f.write_bytes(b"RIFF")
        table = {"none": None, "bell": Snd("bell"), "empty": Snd("file", ""),
                 "desk": Snd("desktop", file=str(f)), "lost": Snd("file", "/no/such.wav")}
        sch = mock.Mock(find=lambda e: table.get(e))
        with mock.patch.object(wb, "scheme", return_value=sch):
            for e in table:
                wb.chime(e)
            self.assertEqual(wb.sounds_since(0)[0], [{"event": "lost", "kind": "file"}])
            wb.chime("none")
            self.assertEqual(wb.sounds_since(0)[0], [])
            wb.chime("empty")
            self.assertEqual(wb.sounds_since(0)[0], [])
            wb.chime("bell")
            self.assertEqual(wb.sounds_since(0)[0], [{"event": "bell", "kind": "bell"}])
            self.assertEqual(wb.sound_file("desk"), b"RIFF")
            self.assertIsNone(wb.sound_file("bell"))
            self.assertIsNone(wb.sound_file("none"))
            self.assertIsNone(wb.sound_file("lost"))
            self.assertIsNone(wb.sound_file("empty"))


class WebMoreTest(WebBase):
    def test_a_core_without_a_profile_folder(self):
        from fedtail.core.view import View
        v = mock.Mock(spec=View)
        v.paths = None
        self.assertIs(web.Web(v, "K").core, v)

    def test_read_takes_a_conversation_whole(self):
        wb = self.web
        m = wb.model("home")
        m.conv_members = {"001": ["001", "002"]}
        wb.read(["001"])
        self.assertEqual(wb.core.unread([wb.core.by_id("002")]), set())

    def test_profile_fields(self):
        from concurrent.futures import Future

        from fedtail.model import Field
        acc = Account(Ref("mastodon", "", "B"), "bob@x", "bob",
                      fields=(Field("site", "<a href='https://b'>b</a>", None),
                              Field("ok", "y", datetime.now(UTC))))
        f = Future()
        f.set_result(acc)
        with mock.patch.object(self.web.core, "account", return_value=f):
            got = self.web.account("B")["account"]["fields"]
        self.assertEqual([x["verified"] for x in got], [False, True])

    def test_command_answers(self):
        from concurrent.futures import Future
        f = Future()
        f.set_result(42)
        with mock.patch.object(self.web.cmds, "run", return_value=(f, "done")):
            self.assertEqual(self.web.command("x"), {"ok": True, "message": "done"})
        f = Future()
        f.set_result("said")
        with mock.patch.object(self.web.cmds, "run", return_value=(f, "done")):
            self.assertEqual(self.web.command("x")["message"], "said")

    def test_page_with_posts(self):
        from fedtail.frontends.common import places
        post = self.web.core.by_id("002")
        pg = places.Page("x", "X", rows=[places.Row("post", data=post)])
        with mock.patch.object(places.Places, "page", return_value=pg):
            got = self.web.page("about")
        self.assertEqual(got["rows"][0]["post"]["id"], "002")
        self.assertEqual(got["rows"][0]["post"]["account"]["id"], "B")


class HandlerTest(TmpDir):
    def setUp(self):
        super().setUp()
        i18n.setup("en")
        self.core, self.w = make_core(self.tmp)
        self.addCleanup(self.core.shutdown)
        self.w.add(status("001", ME, minute=1, text="mine", vis="public"), home=True)
        self.core.connect().result()
        self.core.poll_once()
        self.srv = web.make_server(self.core, "127.0.0.1", 0, "KEY")
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.addCleanup(self.srv.server_close)
        self.addCleanup(self.srv.shutdown)
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def req(self, path, data=None, headers=None, method=None):
        h = {"Cookie": f"{web.COOKIE}=KEY", "X-Fedtail": "1"}
        h.update(headers or {})
        r = urllib.request.Request(self.base + path, data=data, headers=h, method=method)
        try:
            with urllib.request.urlopen(r, timeout=30) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read()

    def test_sounds_uploads_and_bad_bodies(self):
        with mock.patch.object(self.srv.web, "sound_file", return_value=None):
            self.assertEqual(self.req("/sound/x")[0], 404)
        with mock.patch.object(self.srv.web, "sound_file", return_value=b"RIFF"):
            self.assertEqual(self.req("/sound/x"), (200, b"RIFF"))
        code, _b = self.req("/api/upload", b"x", {"Content-Length": "nope"})
        self.assertIn(code, (400, 413))
        self.assertEqual(self.req("/api/read", b"[1, 2]",
                                  {"Content-Type": "application/json"})[0], 400)
        self.assertEqual(self.req("/api/read", b"{not json",
                                  {"Content-Type": "application/json"})[0], 400)

    def test_failures_become_the_pages_errors(self):
        with mock.patch.object(self.srv.web, "lanes", side_effect=OSError("secret url")), \
                self.assertLogs("fedtail", "WARNING"):
            code, body = self.req("/api/lanes")
        self.assertEqual(code, 502)
        self.assertEqual(json.loads(body), {"error": "OSError"})
        with mock.patch.object(self.srv.web, "lanes", side_effect=BrokenPipeError):
            # the page left: no answer, no error
            with self.assertRaises((urllib.error.URLError, ConnectionError, OSError)):
                urllib.request.urlopen(urllib.request.Request(
                    self.base + "/api/lanes", headers={"Cookie": f"{web.COOKIE}=KEY"}),
                    timeout=10).read()

    def test_a_page_gone_before_the_answer(self):
        with mock.patch.object(web.Handler, "_json", side_effect=BrokenPipeError):
            with self.assertRaises((urllib.error.URLError, ConnectionError, OSError)):
                urllib.request.urlopen(urllib.request.Request(
                    self.base + "/api/me", headers={"Cookie": f"{web.COOKIE}=KEY"}),
                    timeout=10).read()
        self.assertEqual(self.req("/api/me")[0], 200)

    def test_server_errors_are_logged_not_printed(self):
        with self.assertLogs("fedtail", "WARNING"):
            try:
                raise ValueError("x")
            except ValueError:
                self.srv.handle_error(None, ("1.2.3.4", 5))
        try:
            raise BrokenPipeError
        except BrokenPipeError:
            self.srv.handle_error(None, ("1.2.3.4", 5))  # quiet

    def test_process_request_gives_back_its_slot_on_failure(self):
        srv = self.srv
        before = srv.slots._value
        with mock.patch("socketserver.ThreadingMixIn.process_request",
                        side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                srv.process_request(mock.Mock(), ("1.2.3.4", 5))
        self.assertEqual(srv.slots._value, before)


class RunTest(TmpDir):
    def test_run_without_a_login_serves_the_login_page(self):
        """A profile not logged in: the page itself asks (the login place); nothing is
        connected or polled until then."""
        import types

        from fedtail.frontends import web as web_frontend
        from fedtail.frontends.web.server import Web
        FakeApi.world = fakes.World()
        cfg, _ = config.validate({"ui": {"language": "en"},
                                  "web": {"port": 0, "open_browser": False}})
        p = paths.resolve("t", config=str(self.tmp / "c.toml"), data=str(self.tmp / "d"))
        core = Core(cfg, p, api_class=FakeApi)
        self.addCleanup(core.shutdown)
        self.assertFalse(core.logged_in)
        me = Web(core, None).me()
        self.assertEqual(me["login"], "t")  # the page opens the login place, nothing else
        self.assertIn("words", me)

        class Stop(threading.Event):
            def wait(self, timeout=None):
                return True  # the loop ends at once
        fake = types.SimpleNamespace(Timer=threading.Timer, Event=Stop,
                                     Thread=threading.Thread)
        err, out = io.StringIO(), io.StringIO()
        with mock.patch.object(web_frontend.signal, "signal", lambda *_a: None), \
                mock.patch.object(web_frontend, "threading", fake), \
                mock.patch.object(core, "connect") as connect, \
                mock.patch.object(core, "start_polling") as polling, \
                mock.patch("sys.stderr", err), mock.patch("sys.stdout", out):
            self.assertEqual(web_frontend.run(core, None, []), 0)
        connect.assert_not_called()
        polling.assert_not_called()
        self.assertIn(i18n._("web_login_here"), err.getvalue())
        self.assertIn("http://127.0.0.1:", out.getvalue())  # the link to log in on

    def test_run_serves_until_asked_to_stop(self):
        import types

        from fedtail.frontends import web as web_frontend
        core, _w = make_core(self.tmp, web={"host": "0.0.0.0", "port": 0,
                                            "open_browser": True})
        handlers, timers = {}, []
        inst = mock.Mock()

        class Timer:
            def __init__(self, _delay, fn):
                timers.append(fn)

            def start(self):
                pass

        class Stop(threading.Event):
            """Ctrl+C at the second look: the loop goes round once, then ends."""
            looks = 0

            def wait(self, timeout=None):
                Stop.looks += 1
                if Stop.looks > 1:
                    handlers[int(web_frontend.signal.SIGINT)]()
                return super().wait(0)
        fake = types.SimpleNamespace(Timer=Timer, Event=Stop, Thread=threading.Thread)
        out = io.StringIO()
        with mock.patch.object(web_frontend.signal, "signal",
                               lambda sig, fn: handlers.__setitem__(int(sig), fn)), \
                mock.patch.object(web_frontend, "threading", fake), \
                mock.patch.object(web_frontend.webbrowser, "open") as browse, \
                mock.patch("sys.stdout", out):
            self.assertEqual(web_frontend.run(core, inst, []), 0)
            timers[0]()  # the browser opens the printed link
            inst.listen.call_args[0][0]("again")  # started again: a fresh link
            handlers[int(web_frontend.signal.SIGTERM)]()
        self.assertEqual(browse.call_count, 2)
        self.assertIn("http://127.0.0.1:", out.getvalue())
        self.assertIn("0.0.0.0", out.getvalue())  # open to the network: said so
