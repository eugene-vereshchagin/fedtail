import unittest

from fedtail import i18n
from fedtail.frontends import notifytext
from fedtail.protocols.mastodon import adapter

from .fakes import BOB, ME, NEWS, status


def build(items, privacy="full"):
    """notifytext.build over the model, as the window hands it over."""
    def model(lane, obj):
        if lane == "activity":
            return adapter.activity(obj)
        return adapter.account(obj) if "acct" in obj else adapter.post(obj)
    return notifytext.build([(lane, model(lane, obj)) for lane, obj in items], privacy)


class NotifyTextTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("ru")
        self.c1 = status("1", BOB, "p", "ME", text="секретный текст про работу")
        self.c2 = status("2", NEWS, "p", "ME", text="ещё один")

    def test_full(self):
        [n] = build([("replies", self.c1)], "full")
        self.assertIn("bob", n.title.lower())
        self.assertIn("секретный", n.body)
        self.assertEqual(n.thread, "1")
        [n] = build([("replies", self.c1), ("replies", self.c2)], "full")
        self.assertEqual(n.title, "2 новых коммента к твоим")
        self.assertIn("секретный", n.body)

    def test_sender_hides_text(self):
        for items in ([("replies", self.c1)], [("replies", self.c1), ("replies", self.c2)]):
            [n] = build(items, "sender")
            self.assertNotIn("секретный", n.title + n.body)
            self.assertIn("bob", (n.title + n.body).lower())

    def test_count_hides_everything(self):
        [n] = build([("replies", self.c1), ("mentions", self.c2)][:1], "count")
        self.assertEqual(n.body, "1 новый коммент к твоим")
        self.assertNotIn("bob", (n.title + n.body).lower())
        self.assertEqual(n.thread, "")

    def test_grouping_and_requests(self):
        notes = build([("requests", ME), ("replies", self.c1),
                                  ("home", self.c2)], "full")
        self.assertEqual([n.lane for n in notes], ["replies", "requests", "home"])
        self.assertIn("Мира", notes[1].title)
        self.assertIn("«Лента»", notes[2].title)



    def test_activity(self):
        mine = status("100", ME, text="фото гор")
        items = [("activity", {"id": "a1", "type": "favourite", "account": BOB, "status": mine}),
                 ("activity", {"id": "a2", "type": "favourite", "account": NEWS,
                               "status": mine}),
                 ("activity", {"id": "a3", "type": "follow", "account": NEWS, "status": None})]
        follow, fav = build(items, "full")
        self.assertEqual(fav.title, "★ 2 в избранное")
        self.assertIn("фото гор", fav.body)
        self.assertEqual(fav.thread, "100")
        self.assertEqual(follow.title, "1 новый подписчик")
        [_f, fav] = build(items, "sender")
        self.assertNotIn("фото", fav.body)
        self.assertIn("bob", fav.body.lower())
        [_f, fav] = build(items, "count")
        self.assertEqual((fav.title, fav.body), ("fedtail", "★ 2 в избранное"))
    def test_desktop_body_is_text_not_markup(self):
        # a post that says "<a href=…>" in plain letters: the desktop shows those letters,
        # it doesn't get a link (or, on some desktops, a picture from a share)
        st = status("3", BOB, "p", "ME", text='&lt;a href="file:///etc/passwd"&gt;click'
                                              '&lt;/a&gt; &lt;img src="https://x.example/p"&gt;')
        [n] = build([("replies", st)], "full")
        self.assertIn('<a href="file:///etc/passwd">', n.body)  # what the post says
        argv = notifytext.desktop_argv(["notify-send", "--wait"], n)
        self.assertEqual(argv[:3], ["notify-send", "--wait", "--"])  # a name is no option
        self.assertEqual(argv[3], n.title)
        self.assertNotIn("<a", argv[4])
        self.assertNotIn("<img", argv[4])
        self.assertIn("&lt;a href=", argv[4])


if __name__ == "__main__":
    unittest.main()
