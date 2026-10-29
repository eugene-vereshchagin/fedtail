"""fedtail.model and the Mastodon adapter: server JSON in, our types out."""

import dataclasses
import time
import unittest
from datetime import UTC, datetime

from fedtail.core.store import sort_key as store_sort_key
from fedtail.model import Account, Activity, Post, Share, real
from fedtail.protocols.mastodon import adapter

from .fakes import BOB, ME, status

T = "2026-10-20T08:15:30.000Z"


def gts_status(**over):
    """A status as GoToSocial gives it: interaction policy, local_only, ULID ids."""
    st = {
        "id": "01JAXQ7Z5V3K2M8N9P0R1S2T3U", "created_at": T, "edited_at": None,
        "in_reply_to_id": "01JAXQ6000000000000000000A",
        "in_reply_to_account_id": "01ACC000000000000000000000",
        "sensitive": True, "spoiler_text": "еда", "visibility": "private",
        "local_only": True, "language": "ru",
        "uri": "https://gts.example/users/mira/statuses/01JAXQ7Z5V3K2M8N9P0R1S2T3U",
        "url": "https://gts.example/@mira/statuses/01JAXQ7Z5V3K2M8N9P0R1S2T3U",
        "replies_count": 2, "reblogs_count": 1, "favourites_count": 5,
        "favourited": True, "reblogged": False, "muted": False, "bookmarked": True,
        "pinned": False, "content": "<p>Хинкали :khinkali: <a href=\"#\">#еда</a></p>",
        "reblog": None, "application": {"name": "fedtail"},
        "text": "Хинкали :khinkali: #еда", "content_type": "text/markdown",
        "account": {
            "id": "01ME00000000000000000000AA", "username": "mira", "acct": "mira",
            "display_name": "Мира :cat:", "locked": True, "bot": False, "group": False,
            "discoverable": True, "created_at": "2024-01-01T00:00:00.000Z",
            "note": "<p>bio</p>", "url": "https://gts.example/@mira",
            "avatar": "https://gts.example/a.webp", "avatar_static": "",
            "header": "", "header_static": "", "followers_count": 10,
            "following_count": 20, "statuses_count": 30, "last_status_at": "2026-10-20",
            "emojis": [{"shortcode": "cat", "url": "https://gts.example/e/cat.png",
                        "static_url": "https://gts.example/e/cat_s.png"}],
            "fields": [{"name": "site", "value": "<a href=\"https://croco.example\">x</a>",
                        "verified_at": "2026-01-02T03:04:05.000Z"}],
        },
        "media_attachments": [{
            "id": "01MEDIA", "type": "image", "url": "https://gts.example/m/1.jpg",
            "preview_url": "https://gts.example/m/1s.jpg", "remote_url": None,
            "description": "тарелка", "blurhash": "LKO2?U%2Tw=w",
            "meta": {"original": {"width": 1600, "height": 1200},
                     "focus": {"x": 0.25, "y": -0.5}},
        }],
        "mentions": [{"id": "01ACC000000000000000000000", "username": "bob",
                      "acct": "bob@social.example", "url": "https://social.example/@bob"}],
        "tags": [{"name": "еда", "url": "https://gts.example/tags/еда"}],
        "emojis": [{"shortcode": "khinkali", "url": "https://gts.example/e/k.png",
                    "static_url": "https://gts.example/e/k_s.png"}],
        "card": None, "poll": None,
        "interaction_policy": {
            "can_favourite": {"always": ["public", "me"], "with_approval": []},
            "can_reply": {"always": ["author", "followers", "mentioned"],
                          "with_approval": ["public"]},
            "can_reblog": {"always": ["author"], "with_approval": []},
        },
    }
    st.update(over)
    return st


def mastodon_status(**over):
    """Mastodon 4.5: snowflake ids, quotes, quote approval, filters, a poll, a card."""
    st = {
        "id": "113275987654321098", "created_at": T, "visibility": "public",
        "in_reply_to_id": None, "in_reply_to_account_id": None, "sensitive": False,
        "spoiler_text": "", "language": "en", "uri": "https://m.example/users/a/statuses/1",
        "url": "https://m.example/@a/1", "replies_count": 0, "reblogs_count": 0,
        "favourites_count": 0, "quotes_count": 3, "edited_at": "2026-10-20T09:00:00.000Z",
        "content": "<p>poll time</p>", "account": dict(BOB), "media_attachments": [],
        "mentions": [], "tags": [], "emojis": [],
        "card": {"url": "https://news.example/a", "title": "News", "description": "d",
                 "type": "link", "image": "https://news.example/i.jpg",
                 "provider_name": "News Ltd", "author_name": "", "width": 400, "height": 200},
        "poll": {"id": "77", "expires_at": "2026-10-21T08:00:00.000Z", "expired": False,
                 "multiple": True, "votes_count": 7, "voters_count": 5, "voted": True,
                 "own_votes": [0, 2],
                 "options": [{"title": "a", "votes_count": 4},
                             {"title": "b", "votes_count": None}, {"title": "c"}],
                 "emojis": []},
        "quote": {"state": "accepted",
                  "quoted_status": status("113275900000000000", ME, text="quoted")},
        "quote_approval": {"automatic": ["public"], "manual": [],
                           "current_user": "automatic"},
        "filtered": [{"filter": {"title": "politics", "filter_action": "warn"},
                      "keyword_matches": ["vote"]}],
    }
    st.update(over)
    return st


class AdapterPostTest(unittest.TestCase):
    def test_gotosocial_status(self):
        p = adapter.post(gts_status(), profile="main")
        self.assertIsInstance(p, Post)
        self.assertEqual(p.id, "01JAXQ7Z5V3K2M8N9P0R1S2T3U")
        self.assertEqual((p.ref.proto, p.ref.profile), ("mastodon", "main"))
        self.assertEqual(p.created, datetime(2026, 10, 20, 8, 15, 30, tzinfo=UTC))
        self.assertEqual(p.visibility, "followers")  # Mastodon's "private"
        self.assertTrue(p.local_only)
        self.assertEqual((p.warning, p.sensitive, p.lang), ("еда", True, "ru"))
        self.assertEqual(p.reply_to, "01JAXQ6000000000000000000A")
        self.assertEqual(p.reply_to_author, "01ACC000000000000000000000")
        self.assertEqual((p.counts.replies, p.counts.shares, p.counts.likes), (2, 1, 5))
        self.assertTrue(p.mine.liked and p.mine.bookmarked and not p.mine.shared)
        self.assertEqual(p.tags, ("еда",))
        self.assertEqual(p.emojis[0].shortcode, "khinkali")
        self.assertEqual(p.mentions[0].handle, "bob@social.example")
        self.assertEqual(p.app, "fedtail")
        self.assertEqual((p.source, p.source_type), ("Хинкали :khinkali: #еда", "text/markdown"))
        m = p.media[0]
        self.assertEqual((m.kind, m.width, m.height, m.alt), ("image", 1600, 1200, "тарелка"))
        self.assertEqual(m.focus, (0.25, -0.5))
        self.assertEqual(p.policy.reply, ("author", "followers", "mentioned"))
        self.assertEqual(p.policy.reply_approval, ("public",))
        self.assertEqual(p.policy.share, ("author",))

    def test_gotosocial_account(self):
        a = adapter.post(gts_status()).author
        self.assertIsInstance(a, Account)
        self.assertEqual((a.handle, a.username, a.name), ("mira", "mira", "Мира :cat:"))
        self.assertTrue(a.locked and a.discoverable)
        self.assertEqual(a.avatar_static, "https://gts.example/a.webp")  # empty → avatar
        self.assertEqual((a.posts, a.followers, a.following), (30, 10, 20))
        self.assertEqual(a.last_post, datetime(2026, 10, 20, tzinfo=UTC))  # a bare date
        self.assertEqual(a.fields[0].verified, datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC))
        self.assertEqual(a.emojis[0].static_url, "https://gts.example/e/cat_s.png")

    def test_mastodon_quote_poll_card_filters(self):
        p = adapter.post(mastodon_status())
        self.assertEqual(p.visibility, "public")
        self.assertIsNotNone(p.edited)
        self.assertEqual(p.counts.quotes, 3)
        self.assertEqual(p.quote.state, "accepted")
        self.assertEqual(p.quote.id, "113275900000000000")
        self.assertEqual(p.quote.post.author.handle, "mira")
        self.assertEqual(p.policy.quote, ("public",))
        self.assertEqual(p.policy.can_quote, "automatic")
        self.assertEqual([o.votes for o in p.poll.options], [4, None, None])
        self.assertEqual((p.poll.multiple, p.poll.voters, p.poll.my_votes), (True, 5, (0, 2)))
        self.assertEqual((p.card.provider, p.card.kind), ("News Ltd", "link"))
        self.assertEqual((p.filtered, p.hidden), (("politics",), False))
        hidden = adapter.post(mastodon_status(
            filtered=[{"filter": {"title": "x", "filter_action": "hide"}}]))
        self.assertTrue(hidden.hidden)

    def test_quote_shapes(self):
        only_id = adapter.post(mastodon_status(quote={"state": "pending",
                                                      "quoted_status_id": "9"}))
        self.assertEqual((only_id.quote.state, only_id.quote.post, only_id.quote.id),
                         ("pending", None, "9"))
        whole = status("5", BOB, text="akkoma")  # Akkoma, Fedibird: the status itself
        akkoma = adapter.post(status("6", ME) | {"quote": whole})
        self.assertEqual(akkoma.quote.post.text, "<p>akkoma</p>")
        old = adapter.post(status("7", ME) | {"quote_id": "5"})
        self.assertEqual((old.quote.id, old.quote.post), ("5", None))
        self.assertIsNone(adapter.post(status("8", ME)).quote)

    def test_quotes_stop_at_a_depth(self):
        st = status("1", ME)
        for i in range(2, 7):
            st = status(str(i), ME) | {"quote": {"state": "accepted", "quoted_status": st}}
        p, depth = adapter.post(st), 0
        while p.quote and p.quote.post:
            p, depth = p.quote.post, depth + 1
        self.assertEqual(depth, adapter.QUOTE_DEPTH)
        self.assertIsNotNone(p.quote.id)  # deeper: the id only

    def test_boost_is_a_share(self):
        inner = status("10", BOB, text="original")
        boost = status("11", ME, vis="public") | {"reblog": inner, "content": ""}
        s = adapter.post(boost)
        self.assertIsInstance(s, Share)
        self.assertEqual((s.id, s.by.handle, s.post.id), ("11", "mira", "10"))
        self.assertEqual(real(s).text, "<p>original</p>")
        self.assertIs(real(s.post), s.post)
        self.assertEqual(s.sort, store_sort_key(boost["created_at"], "11"))

    def test_akkoma_reactions_and_local(self):
        st = status("1", BOB, vis="local") | {
            "pleroma": {"emoji_reactions": [{"name": "👍", "count": 3, "me": True},
                                            {"name": "blob", "count": 1, "me": False,
                                             "url": "https://a.example/e/blob.png"}]}}
        p = adapter.post(st)
        self.assertEqual((p.visibility, p.local_only), ("public", True))
        self.assertEqual([(r.name, r.count, r.me) for r in p.reactions],
                         [("👍", 3, True), ("blob", 1, False)])
        self.assertEqual(p.reactions[1].url, "https://a.example/e/blob.png")

    def test_media_kinds_and_durations(self):
        st = status("1", BOB) | {"media_attachments": [
            {"id": "a", "type": "gifv", "url": "u", "meta": {"original": {"duration": 2.5}}},
            {"id": "b", "type": "audio", "url": "", "remote_url": "https://r.example/a.mp3",
             "meta": {"duration": "61.2"}},
            {"id": "c", "type": "something-new", "url": "u2"}]}
        kinds = [(m.kind, m.duration, m.url) for m in adapter.post(st).media]
        self.assertEqual(kinds, [("gifv", 2.5, "u"), ("audio", 61.2, "https://r.example/a.mp3"),
                                 ("unknown", 0.0, "u2")])

    def test_moved_account(self):
        old = dict(BOB, moved=dict(ME))
        a = adapter.account(old)
        self.assertEqual(a.moved.handle, "mira")
        self.assertIsNone(a.moved.moved)

    def test_odd_values_never_raise(self):
        junk = {"id": "1", "created_at": "not a date", "account": None, "visibility": 5,
                "media_attachments": [None, "x", {"meta": "y", "type": None}],
                "poll": {"options": "no"}, "card": [], "mentions": [None],
                "tags": [{"name": None}], "emojis": "e", "replies_count": "many",
                "quote": "q", "filtered": [None], "interaction_policy": []}
        p = adapter.post(junk)
        self.assertIsNone(p.created)
        self.assertEqual((p.visibility, p.counts.replies, p.tags), ("public", 0, ()))
        self.assertEqual(p.author.handle, "")
        self.assertIsNone(p.poll)
        self.assertEqual(len(p.media), 1)
        self.assertIsInstance(adapter.post(None), Post)
        self.assertIsInstance(adapter.activity({}), Activity)

    def test_frozen(self):
        p = adapter.post(status("1", BOB))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            p.text = "x"
        liked = dataclasses.replace(p, mine=dataclasses.replace(p.mine, liked=True))
        self.assertTrue(liked.mine.liked)
        self.assertFalse(p.mine.liked)

    def test_sort_matches_the_store(self):
        for sid in ("113275987654321098", "01JAXQ7Z5V3K2M8N9P0R1S2T3U", "7"):
            st = status(sid, BOB)
            self.assertEqual(adapter.post(st).sort, store_sort_key(st["created_at"], sid))

    def test_a_thousand_posts_quickly(self):
        sts = [gts_status(id=f"{i:026d}") for i in range(1000)]
        t = time.perf_counter()
        for st in sts:
            adapter.post(st)
        self.assertLess(time.perf_counter() - t, 1.0)  # ~50 µs each on a laptop


class AdapterActivityTest(unittest.TestCase):
    def test_kinds(self):
        st = status("1", ME)
        for raw, kind in (("favourite", "like"), ("reblog", "share"), ("mention", "mention"),
                          ("status", "post"), ("follow", "follow"), ("quote", "quote"),
                          ("pleroma:emoji_reaction", "reaction"), ("admin.report", "notice"),
                          ("brand_new_kind", "other")):
            a = adapter.activity({"id": "n", "type": raw, "account": BOB, "status": st,
                                  "created_at": T, "emoji": "🔥"})
            self.assertEqual(a.kind, kind, raw)
        self.assertEqual(a.post.id, "1")
        self.assertEqual(a.who.handle, "bob@social.example")
        self.assertEqual(a.emoji, "🔥")

    def test_notices_say_what_happened(self):
        sev = adapter.activity({"id": "n", "type": "severed_relationships", "created_at": T,
                                "account": BOB, "event": {"type": "domain_block",
                                                          "target_name": "bad.example"}})
        self.assertEqual((sev.kind, sev.notice), ("notice", "domain_block bad.example"))
        warn = adapter.activity({"id": "m", "type": "moderation_warning", "created_at": T,
                                 "moderation_warning": {"action": "silence",
                                                        "text": "be nice"}})
        self.assertEqual(warn.notice, "silence be nice")
        self.assertIsNone(warn.who)

    def test_requests_and_warnings(self):
        r = adapter.activity({"id": "p", "type": "pending.favourite", "account": BOB,
                              "status": status("1", ME), "created_at": T})
        self.assertEqual((r.kind, r.asks), ("request", "like"))
        w = adapter.activity({"id": "w", "type": "moderation_warning", "created_at": T,
                              "moderation_warning": {"action": "silence", "text": "x"}})
        self.assertEqual((w.details.kind, w.details.action, w.details.text),
                         ("warning", "silence", "x"))
        sev = adapter.activity({"id": "s", "type": "severed_relationships", "created_at": T,
                                "event": {"type": "account_suspension", "target_name": "t",
                                          "followers_count": 2, "following_count": "3"}})
        self.assertEqual((sev.details.lost, sev.details.reason), (5, "account_suspension"))

    def test_a_boosted_post_in_an_activity_is_the_post(self):
        boost = status("2", BOB) | {"reblog": status("1", ME)}
        a = adapter.activity({"id": "n", "type": "reblog", "account": BOB, "status": boost,
                              "created_at": T})
        self.assertEqual(a.post.id, "1")


class SmallShapesTest(unittest.TestCase):
    """Lists, my profile's source, held-back senders, through View the same way."""

    def test_list_profile_held_back(self):
        from fedtail.protocols.mastodon import adapter
        lst = adapter.user_list({"id": "L1", "title": "Друзья", "exclusive": True,
                                 "replies_policy": "list"}, "main")
        self.assertEqual((lst.id, lst.title, lst.exclusive, lst.replies, lst.ref.profile),
                         ("L1", "Друзья", True, "list", "main"))
        prof = adapter.my_profile({"id": "M", "acct": "me", "username": "me",
                                   "display_name": "Мира", "header": "/headers/missing.png",
                                   "source": {"note": "о себе", "fields": [
                                       {"name": "web", "value": "x.org"}]}})
        self.assertEqual((prof.bio, prof.fields, prof.account.header),
                         ("о себе", (("web", "x.org"),), ""))
        held = adapter.held_back({"id": "R1", "notifications_count": "3",
                                  "account": {"id": "B", "acct": "b@x", "username": "b"},
                                  "last_status": {"id": "9", "content": "<p>hi</p>",
                                                  "account": {"id": "B"}}})
        self.assertEqual((held.id, held.count, held.who.handle, held.last.id),
                         ("R1", 3, "b@x", "9"))

    def test_word_filter_ends_and_single_posts(self):
        f = adapter.word_filter({"id": "F", "title": "t", "filter_action": "hide",
                                 "keywords": [{"keyword": "a"}],
                                 "expires_at": "2030-01-02T03:04:05Z",
                                 "statuses": [{"id": "1", "status_id": "9"}]})
        self.assertEqual((f.action, f.words, f.posts), ("hide", ("a",), 1))
        self.assertEqual(f.expires, datetime(2030, 1, 2, 3, 4, 5, tzinfo=UTC))
        plain = adapter.word_filter({"id": "G"})
        self.assertEqual((plain.expires, plain.posts, plain.action), (None, 0, "warn"))


class LayeringTest(unittest.TestCase):
    def test_the_model_knows_no_protocol(self):
        import ast
        from pathlib import Path

        import fedtail.model as m
        tree = ast.parse(Path(m.__file__).read_text(encoding="utf-8"))
        names = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | \
            {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertFalse({x for x in names if "protocols" in x or "core" in x
                          or "frontends" in x}, names)


class IndentTest(unittest.TestCase):
    def test_one_indent_for_every_interface(self):
        """How far in a thread's post is drawn is the model's (INDENT_MAX): each interface
        had its own 8, the web page's in its script."""
        from fedtail.model import INDENT_MAX, ThreadItem, indent
        self.assertEqual([indent(d) for d in (None, -1, 0, 3, INDENT_MAX, 40)],
                         [0, 0, 0, 3, INDENT_MAX, INDENT_MAX])
        self.assertEqual(ThreadItem(None, 40, 7).indent, INDENT_MAX)


if __name__ == "__main__":
    unittest.main()
