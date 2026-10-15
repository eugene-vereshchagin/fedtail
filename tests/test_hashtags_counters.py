import unittest

from fedtail.core.counters import merge, origin_api_url
from fedtail.core.hashtags import flat_tags

from .fakes import BOB, status


class HashtagTest(unittest.TestCase):
    def test_flat_tags(self):
        text = "#georgianews #GeorgiaNews #linux #бесконечноелето #Бесконечное_лето a#notatag"
        self.assertEqual(flat_tags(text), ["georgianews", "бесконечноелето"])
        self.assertEqual(flat_tags("#Georgianews"), ["Georgianews"])  # only the first capital
        self.assertEqual(flat_tags(""), [])


class CountersTest(unittest.TestCase):
    def setUp(self):
        self.st = status("1", BOB, vis="public")
        self.st["uri"] = "https://mastodon.social/users/bob/statuses/112233"
        self.st["favourites_count"] = 1

    def test_origin_url(self):
        self.assertEqual(origin_api_url(self.st, "https://my.node"),
                         "https://mastodon.social/api/v1/statuses/112233")
        self.assertIsNone(origin_api_url(self.st, "mastodon.social"))  # it's ours
        private = dict(self.st, visibility="private")
        self.assertIsNone(origin_api_url(private, "https://my.node"))

    def test_merge_takes_the_bigger_numbers_of_the_same_post(self):
        origin = {"uri": self.st["uri"], "favourites_count": 40, "reblogs_count": 3,
                  "replies_count": 0}
        better = merge(self.st, origin)
        self.assertEqual((better["favourites_count"], better["reblogs_count"]), (40, 3))
        self.assertIsNone(merge(self.st, dict(origin, uri="https://elsewhere/x")))
        boost = {"id": "b", "reblog": self.st, "account": BOB}
        self.assertEqual(merge(boost, origin)["reblog"]["favourites_count"], 40)


if __name__ == "__main__":
    unittest.main()
