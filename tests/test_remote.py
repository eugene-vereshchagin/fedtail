"""core.remote: what fedtail fetches from someone else's server, and what it won't."""

import unittest

from fedtail.core import remote


class Resp:
    def __init__(self, status=200, chunks=(b"{}",), headers=None, location=None):
        self.status_code, self.chunks = status, list(chunks)
        self.headers = dict(headers or {})
        if location:
            self.headers["Location"] = location
        self.is_redirect = bool(location)
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        self.closed = True
        return False

    def iter_content(self, _size):
        yield from self.chunks

    def close(self):
        self.closed = True


class Session:
    """Answers in turn; records what was asked and how."""

    def __init__(self, *answers):
        self.answers, self.asked = list(answers), []

    def get(self, url, **kw):
        self.asked.append((url, kw))
        return self.answers.pop(0)


class RemoteTest(unittest.TestCase):
    def test_refused_addresses(self):
        for url in ("http://93.184.216.34/x",            # JSON: https only
                    "file:///etc/passwd", "ftp://93.184.216.34/x", "javascript:x",
                    "https://127.0.0.1/x", "https://10.0.0.1/x", "https://192.168.1.1/x",
                    "https://172.16.0.1/x", "https://169.254.169.254/latest/meta-data/",
                    "https://100.64.0.1/x", "https://0.0.0.0/x", "https://224.0.0.1/x",
                    "https://[::1]/x", "https://[fe80::1]/x", "https://[fd00::1]/x",
                    "https://[::ffff:127.0.0.1]/x",
                    "https://localhost/x", "https://box.local/x", "https://a.localhost/x",
                    "https://user:pw@93.184.216.34/x", "https:///x", "https://a.example:99999/"):
            with self.assertRaises(remote.Refused, msg=url):
                remote.check(url)

    def test_allowed_addresses(self):
        remote.check("https://93.184.216.34/users/a")
        remote.check("https://[2606:2800:220:1:248:1893:25c8:1946]/x")
        remote.check("http://93.184.216.34/media/a.png", schemes=("https", "http"))
        # my own server may live at home, on a private address
        remote.check("https://10.0.0.5/media/a.png", own_hosts={"10.0.0.5"})

    def test_a_redirect_is_checked_before_it_is_followed(self):
        s = Session(Resp(302, location="http://127.0.0.1:8080/admin"))
        with self.assertRaises(remote.Refused):
            remote.open_url(s, "https://93.184.216.34/obj", timeout=5)
        self.assertEqual(len(s.asked), 1)  # never went there
        self.assertFalse(s.asked[0][1]["allow_redirects"])
        self.assertTrue(s.asked[0][1]["stream"])
        s = Session(Resp(301, location="/moved"), Resp(200, [b'{"a": 1}']))
        with remote.open_url(s, "https://93.184.216.34/obj", timeout=5) as r:
            self.assertEqual(remote.read(r, 100), b'{"a": 1}')
        self.assertEqual(s.asked[1][0], "https://93.184.216.34/moved")
        loop = Session(*[Resp(302, location="/again") for _ in range(10)])
        with self.assertRaises(remote.Refused):
            remote.open_url(loop, "https://93.184.216.34/a", timeout=5)

    def test_the_body_is_capped(self):
        with self.assertRaises(remote.Refused):  # it says so up front
            remote.read(Resp(headers={"Content-Length": "5000"}), 100)
        with self.assertRaises(remote.Refused):  # or it just keeps coming
            remote.read(Resp(chunks=[b"x" * 64] * 10), 100)
        self.assertEqual(remote.read(Resp(chunks=[b"ab", b"cd"]), 4), b"abcd")

    def test_get_json(self):
        s = Session(Resp(200, [b'{"type": "Note"}']))
        self.assertEqual(remote.get_json("https://93.184.216.34/n", session=s),
                         {"type": "Note"})
        self.assertNotIn("Authorization", s.asked[0][1].get("headers") or {})
        self.assertIsNone(remote.get_json("https://93.184.216.34/n",
                                          session=Session(Resp(404))))
        self.assertIsNone(remote.get_json("https://93.184.216.34/n",
                                          session=Session(Resp(200, [b"not json"]))))
        big = Session(Resp(200, [b" " * (1 << 20)] * 3))
        self.assertIsNone(remote.get_json("https://93.184.216.34/n", session=big))
        nobody = Session()
        with self.assertLogs("fedtail.core.remote", "WARNING") as logs:
            self.assertIsNone(remote.get_json("https://127.0.0.1/n?sig=secret",
                                              session=nobody))
        self.assertEqual(nobody.asked, [])
        self.assertNotIn("secret", "".join(logs.output))  # the host only


if __name__ == "__main__":
    unittest.main()
