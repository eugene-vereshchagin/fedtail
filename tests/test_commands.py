import unittest

from fedtail.core.commands import parse


class CommandsTest(unittest.TestCase):
    def check(self, line, kind, **want):
        c = parse(line)
        self.assertEqual(c.kind, kind, line)
        for k, v in want.items():
            self.assertEqual(getattr(c, k), v, f"{line}: {k}")

    def test_posts(self):
        self.check("#a3f", "open", alias="a3f", number=0)
        self.check("#a3f/2", "open", alias="a3f", number=2)
        self.check("#a3f спасибо!", "reply", alias="a3f", text="спасибо!")
        self.check("#a3f/12 и тебе\nвторая строка", "reply", number=12,
                   text="и тебе\nвторая строка")

    def test_letters(self):
        self.check("S #a3f", "sub", alias="a3f")
        self.check("U #k00", "unsub", alias="k00")
        self.check("S @kot@mastodon.ml", "follow", user="kot@mastodon.ml")
        self.check("U @bob", "unfollow", user="bob")
        self.check("! #a3f", "boost", alias="a3f")
        self.check("~#a3f", "bookmark", alias="a3f")
        self.check("D #a3f", "delete", alias="a3f")
        self.check("S что-то", "error")

    def test_people_and_text(self):
        self.check("@kot", "profile", user="kot")
        self.check("@kot привет", "direct", user="kot", text="@kot привет")
        self.check("просто пост", "post", text="просто пост")
        self.check("?", "help")
        self.check("   ", "error")


if __name__ == "__main__":
    unittest.main()
