"""Wider than my server knows (core/wider.py): other servers' public and tag lanes, read
without an account, each post fetched into my server by its address."""

from .fakes import BOB, status
from .test_custom import FreeBase


def remote(i, text="text", tags=()):
    st = status(i, BOB, minute=int(i[-2:]) % 60, vis="public", text=text)
    st["uri"] = st["url"] = f"https://far.example/s/{i}"
    st["tags"] = [{"name": t} for t in tags]
    return st


class WiderTest(FreeBase):
    def setUp(self):
        super().setUp()
        self.core, self.w = self.make([])
        self.core.connect().result()
        self.served = {}  # url → the JSON their server answers
        self.asked = []

        def origin(url):
            self.asked.append(url)
            for key, page in self.served.items():
                if url.startswith(key):
                    return page
            return None
        self.core._origin_get = origin

    def put_remote(self, *sts):
        for st in sts:
            self.w.remote[st["uri"]] = dict(st, id="L" + st["id"])  # my server's own id
        return [dict(st) for st in sts]

    def test_federated_takes_their_public_lane(self):
        self.core.cfg["lanes"]["federated_extra"] = ["far.example", "https://far.example/"]
        page = self.put_remote(remote("R01"), remote("R02"))
        self.served["https://far.example/api/v1/timelines/public"] = page
        self.assertFalse(self.core.wider.due(False))  # Federated isn't open: nothing
        self.assertTrue(self.core.wider.due(True))
        got = self.core.wider.run(True)
        self.assertEqual(sorted(got["federated"]), ["LR01", "LR02"])  # my server's ids
        self.assertEqual(len(self.asked), 1)  # the same server named twice: once
        self.assertFalse(self.core.wider.due(True))  # not again before extra_minutes
        self.core.store.kv_set("wider.at", {})
        self.assertEqual(self.core.wider.run(True), {})  # what was fetched isn't again

    def test_closed_lane_left_alone(self):
        self.core.cfg["lanes"]["federated_extra"] = ["gts.example"]
        self.served["https://gts.example/"] = {"error": "unauthorized"}
        self.assertEqual(self.core.wider.run(True), {})
        self.core.store.kv_set("wider.at", {})
        self.assertFalse(self.core.wider.due(True))  # closed: a few hours' rest

    def test_tag_lanes_from_other_servers(self):
        self.core.cfg["lanes"]["tags_extra"] = ["far.example"]
        self.core.save_tag_group({"any": ["linux"]}).result()
        lane = next(n for n in self.core.lane_by_name if n.startswith("tags:"))
        page = self.put_remote(remote("T11", "#linux", ["linux"]), remote("T12", "no", ["x"]))
        self.served["https://far.example/api/v1/timelines/tag/linux"] = page
        got = self.core.wider.run(False)
        self.assertEqual(got, {lane: ["LT11"]})  # the one without the tag stays out
        self.assertIn("LT11", [st["id"] for _i, st in self.core.lane_entries(lane)])

    def test_my_own_server_isnt_asked(self):
        self.core.cfg["lanes"]["federated_extra"] = ["example.test"]
        self.assertFalse(self.core.wider.due(True))
