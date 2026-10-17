"""Small pure helpers, no server and no Qt: reading an outbox page by page, fedtail's
line in a private note."""

import unittest

from fedtail.core import replies
from fedtail.core.model import note_followed, note_text, note_with_followed

PUB = "https://www.w3.org/ns/activitystreams#Public"
BASE = "https://far.example/outbox"


def create(n, to=(PUB,)):
    return {"type": "Create", "to": list(to), "object": f"https://far.example/n/{n}"}


class OutboxPageTest(unittest.TestCase):
    def docs(self):
        return {
            BASE: {"type": "OrderedCollection", "first": f"{BASE}?p=1"},
            f"{BASE}?p=1": {"type": "OrderedCollectionPage", "next": f"{BASE}?p=2",
                            "orderedItems": [create(5), create(4, to=["followers"])]},
            f"{BASE}?p=2": {"type": "OrderedCollectionPage",
                            "orderedItems": [{"type": "Announce", "to": [PUB],
                                              "object": "https://else.example/x"},
                                             create(3), create(2)]},
        }

    def test_pages_and_the_end(self):
        docs = self.docs()
        uris, nxt = replies.outbox_page(docs.get, BASE, limit=1)
        self.assertEqual(uris, ["https://far.example/n/5"])  # not followers-only
        self.assertEqual(nxt, f"{BASE}?p=2")
        uris, nxt = replies.outbox_page(docs.get, nxt, limit=10)
        self.assertEqual(uris, ["https://far.example/n/3", "https://far.example/n/2"])
        self.assertIsNone(nxt)  # no boosts, and that was the last page

    def test_skip_what_is_here(self):
        docs = self.docs()
        uris, _nxt = replies.outbox_page(docs.get, BASE, limit=10,
                                         skip={"https://far.example/n/5"})
        self.assertNotIn("https://far.example/n/5", uris)
        self.assertIn("https://far.example/n/3", uris)

    def test_broken_answers(self):
        self.assertEqual(replies.outbox_page(lambda u: None, BASE), ([], None))
        self.assertEqual(replies.outbox_page(lambda u: "html", BASE), ([], None))
        docs = {BASE: {"type": "OrderedCollection", "first": f"{BASE}?p=1"}}
        self.assertEqual(replies.outbox_page(docs.get, BASE), ([], None))  # page gone

    def test_newest_posts_keep_their_limit(self):
        docs = self.docs()
        self.assertEqual(replies.outbox_post_uris(docs.get, BASE, limit=2),
                         ["https://far.example/n/5", "https://far.example/n/3"])


class NoteLineTest(unittest.TestCase):
    def test_round_trip(self):
        self.assertIsNone(note_followed(""))
        self.assertIsNone(note_followed(None))
        n = note_with_followed("друг детства", "2026-10-18")
        self.assertEqual(n, "друг детства\n\n[fedtail followed 2026-10-18]")
        self.assertEqual(note_followed(n), "2026-10-18")
        self.assertEqual(note_text(n), "друг детства")
        # an empty note: just the line; editing keeps one line, never two
        self.assertEqual(note_with_followed("", "2026-10-18"), "[fedtail followed 2026-10-18]")
        self.assertEqual(note_with_followed(n, "2026-10-19").count("[fedtail"), 1)
        # taken out
        self.assertEqual(note_with_followed(n, None), "друг детства")

    def test_my_own_brackets_stay(self):
        n = "[мой тег] не путать"
        self.assertIsNone(note_followed(n))
        self.assertEqual(note_text(n), n)


if __name__ == "__main__":
    unittest.main()
