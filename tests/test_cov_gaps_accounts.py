"""The login place's other turns (common/placesmore.py): "log in" for a profile, a
server that won't start a login, a login begun anew, its page opened again or dropped,
a finish without a login or a code, and the same account whose reconnect fails."""

from unittest import mock

from fedtail.frontends.common import placesmore

from . import test_accounts_places as tap


class LoginTurnsTest(tap.AccountsTest):
    # the parent's own tests run there, not twice here
    test_add_an_account_through_a_login = None
    test_main_relogin_logout = None
    test_the_web_editor_spell_checks_by_the_option = None
    test_the_last_one_logged_out_goes_to_the_login = None
    test_the_web_page_goes_over_to_another_account = None

    def test_the_turns(self):
        out = self.pl.act("accounts", "login", "work")
        self.assertEqual(out.open, {"page": "login", "arg": "work"})
        # nothing begun yet: open gives the page again, finish too, again drops nothing
        self.assertTrue(self.pl.act("login", "open", "work").refresh)
        self.assertTrue(self.pl.act("login", "finish", "work", {"code": "x"}).refresh)
        self.assertTrue(self.pl.act("login", "again", "work").refresh)
        with mock.patch("fedtail.core.app.Core.begin_login", side_effect=OSError("down")):
            out = self.pl.act("login", "begin", "work", {"server": "example.test"})
        self.assertIn("down", out.error)
        self.assertNotIn("work", placesmore._LOGINS)
        self.pl.act("login", "begin", "work", {"server": "example.test"})
        first = placesmore._LOGINS["work"][0]
        self.pl.act("login", "begin", "work", {"server": "example.test"})  # anew
        self.assertIsNot(placesmore._LOGINS["work"][0], first)  # the old one let go
        url = placesmore._LOGINS["work"][1]
        self.assertEqual(self.pl.act("login", "open", "work").open, {"url": url})
        self.assertTrue(self.pl.act("login", "finish", "work", {"code": " "}).error)
        self.assertTrue(self.pl.act("login", "again", "work").refresh)
        self.assertNotIn("work", placesmore._LOGINS)

    def test_the_same_account_that_wont_reconnect(self):
        self.pl.act("login", "begin", "default", {"server": "example.test"})
        with mock.patch.object(self.core, "connect", side_effect=OSError("no net")):
            out = self.pl.act("login", "finish", "default", {"code": "good"})
        self.assertIn("no net", out.error)
