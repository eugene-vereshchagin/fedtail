import unittest

from fedtail import i18n
from fedtail.frontends import notifytext

from .fakes import BOB, ME, NEWS, status


class NotifyTextTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("ru")
        self.c1 = status("1", BOB, "p", "ME", text="секретный текст про работу")
        self.c2 = status("2", NEWS, "p", "ME", text="ещё один")

    def test_full(self):
        [n] = notifytext.build([("comments", self.c1)], "full")
        self.assertIn("bob", n.title.lower())
        self.assertIn("секретный", n.body)
        self.assertEqual(n.thread, "1")
        [n] = notifytext.build([("comments", self.c1), ("comments", self.c2)], "full")
        self.assertEqual(n.title, "2 новых коммента к твоим")
        self.assertIn("секретный", n.body)

    def test_sender_hides_text(self):
        for items in ([("comments", self.c1)], [("comments", self.c1), ("comments", self.c2)]):
            [n] = notifytext.build(items, "sender")
            self.assertNotIn("секретный", n.title + n.body)
            self.assertIn("bob", (n.title + n.body).lower())

    def test_count_hides_everything(self):
        [n] = notifytext.build([("comments", self.c1), ("mentions", self.c2)][:1], "count")
        self.assertEqual(n.body, "1 новый коммент к твоим")
        self.assertNotIn("bob", (n.title + n.body).lower())
        self.assertEqual(n.thread, "")

    def test_grouping_and_requests(self):
        notes = notifytext.build([("requests", ME), ("comments", self.c1),
                                  ("people", self.c2)], "full")
        self.assertEqual([n.lane for n in notes], ["comments", "requests", "people"])
        self.assertIn("Вереск", notes[1].title)
        self.assertIn("«Лента»", notes[2].title)



    def test_activity(self):
        mine = status("100", ME, text="фото гор")
        items = [("activity", {"id": "a1", "type": "favourite", "account": BOB, "status": mine}),
                 ("activity", {"id": "a2", "type": "favourite", "account": NEWS,
                               "status": mine}),
                 ("activity", {"id": "a3", "type": "follow", "account": NEWS, "status": None})]
        follow, fav = notifytext.build(items, "full")
        self.assertEqual(fav.title, "★ 2 в избранное")
        self.assertIn("фото гор", fav.body)
        self.assertEqual(fav.thread, "100")
        self.assertEqual(follow.title, "1 новый подписчик")
        [_f, fav] = notifytext.build(items, "sender")
        self.assertNotIn("фото", fav.body)
        self.assertIn("bob", fav.body.lower())
        [_f, fav] = notifytext.build(items, "count")
        self.assertEqual((fav.title, fav.body), ("fedtail", "★ 2 в избранное"))

if __name__ == "__main__":
    unittest.main()
