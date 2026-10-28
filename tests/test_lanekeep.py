"""The lanes kept drawn while out of sight (common/lanekeep.py): the `keep` shown last,
one shown before them let go the moment another comes to the front; one on screen (a
column, a tab beside) stays whatever its turn."""

import unittest

from fedtail.frontends.common.lanekeep import KeptLanes


class KeptLanesTest(unittest.TestCase):
    def test_the_ones_shown_last_stay(self):
        k, gone = KeptLanes(2), []

        def unload(name):
            gone.append(name)
            return True
        for name in ("home", "local", "mentions"):
            self.assertEqual(k.shown(name, unload), [])
        self.assertEqual(k.shown("lists", unload), ["home"])  # four: the first goes
        self.assertEqual(k.shown("local", unload), [])  # back to a kept one: nothing goes
        self.assertEqual(k.recent, ["local", "lists", "mentions"])
        self.assertEqual(k.shown("home", unload), ["mentions"])
        self.assertEqual(gone, ["home", "mentions"])

    def test_one_on_screen_stays_and_goes_later(self):
        k = KeptLanes(1)
        on_screen = {"a"}
        k.shown("a", lambda n: n not in on_screen)
        k.shown("b", lambda n: n not in on_screen)
        self.assertEqual(k.shown("c", lambda n: n not in on_screen), [])  # a is a column
        on_screen.clear()
        self.assertEqual(k.shown("c", lambda n: n not in on_screen), ["a"])
        k.forget("b")
        self.assertEqual(k.recent, ["c"])

    def test_zero_keeps_only_the_front_one(self):
        k = KeptLanes(0)
        k.shown("a", lambda n: True)
        self.assertEqual(k.shown("b", lambda n: True), ["a"])


if __name__ == "__main__":
    unittest.main()
