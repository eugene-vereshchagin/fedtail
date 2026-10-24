"""A profile's line and buttons and what each button does (frontends/common/profile.py),
through a host that notes every call: the relationship after each change is the server's
answer, or the old one with the change made."""

import dataclasses
import unittest
from datetime import datetime

from fedtail import i18n
from fedtail.frontends.common import profile
from fedtail.model import Account, Ref, Relationship

ACC = Account(Ref("m", "", "B"), "bob@x.test", "bob", bot=True, locked=True,
              created=datetime(2020, 5, 1), followers=3, following=0,
              url="https://x.test/@bob")


class Host:
    def __init__(self, answers=None):
        self.done = []
        self.answers = answers or {}

    def call(self, fut, ok=None, fail=None):
        self.done.append(("call", fut))
        if ok:
            ok(None)

    def choose(self, title, text, options, done, check=None):
        """How long and the like: the first choice, the box unticked."""
        self.done.append(("choose", title))
        done(options[0][0], False)

    def confirm(self, title, text, then):
        self.done.append(("confirm", title))
        then()

    def ask_text(self, title, question, then, text="", allow_empty=False):
        self.done.append(("ask", text))
        then(self.answers.get("text", ""))

    def __getattr__(self, name):  # compose, open_people, copy_handle, open_url…
        return lambda *a, **k: self.done.append((name, a, k))


class View:
    def __getattr__(self, name):  # each call: its name and arguments, as the "future"
        return lambda *a, **k: (name, a, k)


class ProfileTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")

    def test_meta(self):
        bits = profile.meta(ACC, Relationship(followed_by=True), lambda d: "D",
                            followed_since=datetime(2024, 1, 1), software="gotosocial")
        self.assertEqual(bits[0], "@bob@x.test")
        self.assertIn(i18n._("bot"), bits)
        self.assertIn("🔒 " + i18n._("acc_locked"), bits)
        self.assertIn(i18n._("acc_since", date="01.05.2020"), bits)
        self.assertIn(i18n._("acc_follows_you"), bits)
        self.assertIn("🖥 gotosocial", bits)
        self.assertIn(i18n._("acc_followed_since", when="D"), bits)

    def test_actions(self):
        cfg = {"feed": {"per_person_follow": True}}
        rel = Relationship(following=True, followed_by=True, notifying=True,
                           showing_shares=False, languages=("ru",), endorsed=True)
        keys = [a.key for a in profile.actions(ACC, rel, False, cfg, lambda _w: True,
                                               lists=True)]
        self.assertEqual(keys, ["follow", "bell", "boosts", "langs", "mention", "mute",
                                "block", "remove_follower", "endorse", "lists", "followers",
                                "note", "copy_handle", "open_browser"])
        acts = {a.key: a for a in profile.actions(ACC, rel, False, cfg, lambda _w: True)}
        self.assertIn(i18n._("bell_off"), acts["bell"].label)
        self.assertIn(i18n._("boosts_show"), acts["boosts"].label)
        self.assertIn("ru", acts["langs"].label)
        mine = [a.key for a in profile.actions(dataclasses.replace(ACC, url=""), None, True,
                                               cfg, lambda _w: False)]
        self.assertEqual(mine, ["edit_profile", "followers", "copy_handle"])
        req = profile.actions(ACC, Relationship(requested=True), False, cfg, lambda _w: False)
        self.assertEqual(req[0].label, i18n._("follow_requested"))

    def test_note_line_and_langs(self):
        note = "met at fosdem\n\n[fedtail followed 2024-01-01]"  # fedtail's line: not shown
        self.assertEqual(profile.note_line(Relationship(note=note), False), "📝 met at fosdem")
        self.assertEqual(profile.note_line(Relationship(note="x"), True), "")
        self.assertEqual(profile.note_line(None, False), "")
        self.assertEqual(profile.parse_langs("RU; en  ka,"), ["ru", "en", "ka"])
        self.assertEqual(profile.parse_langs(None), [])

    def run_key(self, key, rel=None, text=""):
        host, changed = Host({"text": text}), []
        profile.do(key, ACC, rel, View(), host, changed.append)
        return host.done, changed

    def test_each_button(self):
        done, changed = self.run_key("bell", Relationship(following=True))
        self.assertEqual(done[0][1][:2], ("notify_posts", ("B", True)))
        self.assertTrue(changed[0].notifying)
        _d, changed = self.run_key("boosts", Relationship(following=True))
        self.assertFalse(changed[0].showing_shares)
        done, changed = self.run_key("langs", Relationship(languages=("en",)), "ru, ka")
        self.assertEqual(done[0], ("ask", "en"))
        self.assertEqual(done[1][1][2], {"languages": ["ru", "ka"]})
        self.assertEqual(changed[0].languages, ("ru", "ka"))
        _d, changed = self.run_key("langs", None, "")
        self.assertIsNone(changed[0].languages)  # all of them again
        done, _c = self.run_key("mention")
        self.assertEqual(done[0], ("compose", (), {"text": "@bob@x.test "}))
        _d, changed = self.run_key("mute")
        self.assertTrue(changed[0].muting)
        done, changed = self.run_key("block")
        self.assertEqual(done[0][0], "confirm")  # blocking: asked first
        self.assertTrue(changed[0].blocking)
        done, changed = self.run_key("block", Relationship(blocking=True))
        self.assertEqual(done[0][0], "call")  # unblocking: at once
        self.assertFalse(changed[0].blocking)
        done, changed = self.run_key("remove_follower", Relationship(followed_by=True))
        self.assertEqual(done[0][0], "confirm")
        self.assertFalse(changed[0].followed_by)
        self.assertEqual(done[-1][0], "status")
        _d, changed = self.run_key("endorse", Relationship(following=True))
        self.assertTrue(changed[0].endorsed)
        done, _c = self.run_key("followers")
        self.assertEqual(done[0][0], "open_people")
        done, changed = self.run_key("note", Relationship(note="old"), "  new  ")
        self.assertEqual(done[1][1][1], ("B", "new", "old"))
        self.assertEqual(changed[0].note, "new")
        for key, call in (("edit_profile", "edit_profile"), ("lists", "open_lists"),
                          ("copy_handle", "copy_handle"), ("open_browser", "open_url")):
            done, _c = self.run_key(key)
            self.assertEqual(done[0][0], call, key)
        done, _c = self.run_key("nothing such")
        self.assertEqual(done, [])

    def test_the_servers_answer_wins(self):
        host, changed = Host(), []
        answer = Relationship(following=True, notifying=False)

        class Answering(Host):
            def call(self, fut, ok=None, fail=None):
                ok(answer)
        profile.do("bell", ACC, Relationship(following=True), View(), Answering(),
                   changed.append)
        self.assertIs(changed[0], answer)
        profile.do("follow", ACC, Relationship(requested=True), View(), host, changed.append)
        self.assertEqual(host.done[0][1][1], ("B", False))  # a request taken back


if __name__ == "__main__":
    unittest.main()
