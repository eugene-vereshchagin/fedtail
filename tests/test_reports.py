"""Bug reports leaving the machine: into a private repository over git
(fedtail/reportsend.py, a local bare repository standing in for GitHub) and as a public
issue drafted with everything personal scrubbed (fedtail/issue.py, the "issue" place,
--bug-report)."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from fedtail import i18n, issue, reportsend

HAVE_GIT = shutil.which("git") is not None


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True,
                          check=True).stdout


class RemoteUrlTest(unittest.TestCase):
    def test_spellings(self):
        self.assertEqual(reportsend.remote_url("me/reports"), "git@github.com:me/reports.git")
        self.assertEqual(reportsend.remote_url("me/r.git"), "git@github.com:me/r.git")
        for url in ("git@example.org:me/r.git", "ssh://git@example.org/me/r.git",
                    "https://example.org/me/r.git", "/srv/git/r.git", "file:///srv/r.git",
                    "user@box:repos/r.git"):
            self.assertEqual(reportsend.remote_url(url), url)
        self.assertIsNone(reportsend.remote_url("  "))
        with self.assertRaises(reportsend.SendError):
            reportsend.remote_url("not a repository at all")

    def test_no_git(self):
        with mock.patch.object(reportsend.shutil, "which", return_value=None):
            with self.assertRaisesRegex(reportsend.SendError, "git is not installed"):
                reportsend.send(__file__, "/nowhere/r.git", tempfile.mkdtemp())

    def test_send_report_only_when_set(self):
        self.assertIsNone(reportsend.send_report(__file__, {"debug": {"report_repo": ""}},
                                                 "/tmp"))
        self.assertIsNone(reportsend.send_report(__file__, None, "/tmp"))
        with self.assertRaises(reportsend.SendError):
            reportsend.send(__file__, "", "/tmp")


@unittest.skipUnless(HAVE_GIT, "no git")
class SendTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.remote = self.tmp / "remote.git"
        git("init", "-q", "--bare", "-b", "main", str(self.remote))
        git("config", "uploadpack.allowFilter", "true", cwd=self.remote)
        self.url = str(self.remote)

    def report(self, name, data=None):
        f = self.tmp / name
        f.write_bytes(data or f"logs of {name}".encode())
        return f

    def files(self, branch="main"):
        return git("ls-tree", "-r", "--name-only", branch, cwd=self.remote).split()

    def test_into_an_empty_repository_then_on_top(self):
        where = reportsend.send(self.report("a.tar.gz"), self.url, self.tmp / "cache1")
        self.assertRegex(where, r"^reports/\d{4}-\d{2}/a\.tar\.gz$")
        self.assertEqual(self.files(), [where])
        # another machine (its own cache) adds its own: the first one stays
        second = reportsend.send(self.report("b.tar.gz"), self.url, self.tmp / "cache2",
                                 folder="selfcheck", message="selfcheck: b")
        self.assertEqual(sorted(self.files()), sorted([where, second]))
        self.assertIn("selfcheck: b", git("log", "-1", "--format=%s", "main",
                                          cwd=self.remote))
        self.assertEqual(git("log", "-1", "--format=%an", "main", cwd=self.remote).strip(),
                         "fedtail")
        # the first cache again, behind now: it fetches and goes on top
        third = reportsend.send(self.report("c.tar.gz"), self.url, self.tmp / "cache1")
        self.assertEqual(len(self.files()), 3)
        self.assertIn(third, self.files())
        # a cache never downloads the others' reports: only the trees come down
        theirs = git("hash-object", str(self.tmp / "b.tar.gz")).strip()
        listed = git("rev-list", "--objects", "--missing=print", "FETCH_HEAD",
                     cwd=self.tmp / "cache1")  # "?<id>": known of, never fetched
        self.assertIn("?" + theirs, listed.split())

    def test_the_remote_moved_by_another_branch_name(self):
        git("symbolic-ref", "HEAD", "refs/heads/trunk", cwd=self.remote)
        where = reportsend.send(self.report("a.tar.gz"), self.url, self.tmp / "c")
        self.assertEqual(self.files("main"), [where])  # empty: "main" all the same

    def test_a_race_is_retried(self):
        reportsend.send(self.report("a.tar.gz"), self.url, self.tmp / "c1")
        real = reportsend._git
        state = {"n": 0}

        def flaky(repo, *args, **kw):
            if args[0] == "push" and not state["n"]:
                state["n"] += 1
                # someone else pushed meanwhile
                reportsend.send(self.report("other.tar.gz"), self.url, self.tmp / "c2")
            return real(repo, *args, **kw)
        with mock.patch.object(reportsend, "_git", flaky):
            reportsend.send(self.report("mine.tar.gz"), self.url, self.tmp / "c1")
        names = [Path(x).name for x in self.files()]
        self.assertEqual(sorted(names), ["a.tar.gz", "mine.tar.gz", "other.tar.gz"])

    def test_no_access_says_so_and_doesnt_retry(self):
        with self.assertRaises(reportsend.SendError) as e:
            reportsend.send(self.report("a.tar.gz"), str(self.tmp / "missing.git"),
                            self.tmp / "c")
        self.assertTrue(str(e.exception))

    def test_a_rejected_push_that_isnt_a_race(self):
        real = reportsend._git

        def refuse(repo, *args, **kw):
            if args[0] == "push":
                return SimpleNamespace(returncode=1, stdout="",
                                       stderr="ERROR: Permission to me/r denied\n")
            return real(repo, *args, **kw)
        with mock.patch.object(reportsend, "_git", refuse):
            with self.assertRaisesRegex(reportsend.SendError, "Permission"):
                reportsend.send(self.report("a.tar.gz"), self.url, self.tmp / "c")

    def test_always_rejected_gives_up(self):
        real = reportsend._git

        def race(repo, *args, **kw):
            if args[0] == "push":
                return SimpleNamespace(returncode=1, stdout="",
                                       stderr=" ! [rejected] (fetch first)\n")
            return real(repo, *args, **kw)
        with mock.patch.object(reportsend, "_git", race):
            with self.assertRaisesRegex(reportsend.SendError, "rejected"):
                reportsend.send(self.report("a.tar.gz"), self.url, self.tmp / "c")

    def test_cache_follows_a_changed_address_and_timeouts(self):
        reportsend.send(self.report("a.tar.gz"), self.url, self.tmp / "c")
        other = self.tmp / "other.git"
        git("init", "-q", "--bare", "-b", "main", str(other))
        git("config", "uploadpack.allowFilter", "true", cwd=other)
        reportsend.send(self.report("b.tar.gz"), str(other), self.tmp / "c")
        self.assertEqual(len(git("ls-tree", "-r", "--name-only", "main", cwd=other).split()),
                         1)
        with mock.patch.object(reportsend.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired("git", 1)):
            with self.assertRaisesRegex(reportsend.SendError, "no answer"):
                reportsend._git(self.tmp, "status")
        r = reportsend._git(self.tmp / "c", "rev-parse", "--verify", "nope", check=False)
        self.assertNotEqual(r.returncode, 0)
        with self.assertRaises(reportsend.SendError):
            reportsend._git(self.tmp / "c", "rev-parse", "--verify", "nope^{commit}")

    def test_fetch_failing_otherwise_is_an_error(self):
        real = reportsend._git

        def broken(repo, *args, **kw):
            if args[0] == "fetch":
                return SimpleNamespace(returncode=128, stdout="",
                                       stderr="fatal: Could not read from remote repository.")
            return real(repo, *args, **kw)
        with mock.patch.object(reportsend, "_git", broken):
            with self.assertRaisesRegex(reportsend.SendError, "Could not read"):
                reportsend.send(self.report("a.tar.gz"), self.url, self.tmp / "c")

    def test_send_report_from_the_config(self):
        cfg = {"debug": {"report_repo": self.url}}
        words = reportsend.send_report(self.report("r.tar.gz"), cfg, self.tmp)
        self.assertTrue(words.startswith(self.url + ": reports/"))
        self.assertTrue((self.tmp / "report-repo" / "HEAD").exists())


class SaidTest(unittest.TestCase):
    def test_the_last_meaningful_line(self):
        self.assertEqual(reportsend._said("hint: x\nwarning: y\nfatal: no\n\n"), "fatal: no")
        self.assertEqual(reportsend._said(""), "")


class ScrubTest(unittest.TestCase):
    def test_what_says_who_or_where(self):
        text = ("GET https://my.server/api/v1/x from @mira@my.server, @bob@other.example, "
                "mail bob@other.example at 10.1.2.3 and fe80:0:0:0:1:2:3:4; Bearer "
                "abcdefghijklmnop; token=SECRETSECRET; id 01HXYZABCDEFGHJKMNPQRSTVWXYZ0123 "
                f"in {Path.home()}/x; https://github.com/eugene-vereshchagin/fedtail/issues")
        got = issue.scrub(text, ["my.server", "mira"])
        for gone in ("my.server", "mira", "bob", "other.example", "10.1.2.3", "fe80",
                     "abcdefghijklmnop", "SECRETSECRET", "01HXYZ", str(Path.home())):
            self.assertNotIn(gone, got)
        self.assertIn("https://github.com/eugene-vereshchagin/fedtail/issues", got)
        self.assertIn("~/x", got)

    def test_the_login_name(self):
        with mock.patch.dict("os.environ", {"USER": "veresk"}):
            self.assertEqual(issue.scrub("veresk ran it"), "<user> ran it")


class DraftTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.logs = Path(self._tmp.name) / "logs"
        self.logs.mkdir()

    def test_recent_errors(self):
        (self.logs / "2026-10-01_10-00-00.log").write_text(
            "2026-10-01 10:00:00.000 INFO    [t] x: fine\n"
            "2026-10-01 10:00:01.000 WARNING [t] fedtail.api: GET /x -> 502\n"
            "2026-10-01 10:00:02.000 ERROR   [t] fedtail: boom\n"
            "Traceback (most recent call last):\n"
            '  File "x.py", line 1\n'
            "ValueError: bad\n"
            "2026-10-01 10:00:03.000 INFO    [t] x: fine again\n", "utf-8")
        (self.logs / "latest.log").write_text("2026-10-01 10:00:09.000 ERROR [t] x: dup\n")
        got = issue.recent_errors(self.logs)
        self.assertEqual(got[0], "2026-10-01 10:00:01.000 WARNING [t] fedtail.api: GET /x -> 502")
        self.assertIn("ValueError: bad", got)
        self.assertNotIn("fine again", " ".join(got))
        self.assertNotIn("dup", " ".join(got))
        self.assertEqual(issue.recent_errors(self.logs / "none"), [])
        self.assertEqual(len(issue.recent_errors(self.logs, limit=2)), 2)

    def test_draft_and_its_address(self):
        (self.logs / "s.log").write_text(
            "2026-10-01 10:00:01.000 ERROR   [t] fedtail: at https://my.server/x\n", "utf-8")
        paths = SimpleNamespace(profile="work", data_dir=Path(self._tmp.name))
        cfg = {"ui": {"theme": "paper", "layout": "single", "frontend": "qt"},
               "debug": {"issue_repo": ""}}
        with mock.patch("fedtail.diag.logs_dir", return_value=self.logs):
            d = issue.draft(paths, cfg, known=["my.server"], toolkit="gtk")
        self.assertIn("### " + i18n._("issue_what"), d.body)
        self.assertIn("interface gtk", d.body)
        self.assertIn("theme paper", d.body)
        self.assertNotIn("my.server", d.body)
        url = issue.issue_url(cfg, "", d.body)
        self.assertTrue(url.startswith(
            "https://github.com/eugene-vereshchagin/fedtail/issues/new?title=&body="))
        self.assertIn("fedtail", parse_qs(urlsplit(url).query)["body"][0])
        cfg["debug"]["issue_repo"] = "me/fork.git"
        self.assertEqual(issue.repo_of(cfg), "me/fork")
        self.assertEqual(issue.repo_of(None), "eugene-vereshchagin/fedtail")

    def test_a_long_body_is_cut_to_fit(self):
        body = "### x\n```\n" + "\n".join(f"line {i} " + "я" * 60 for i in range(400))
        url = issue.issue_url({}, "t", body)
        self.assertLessEqual(len(url), issue.MAX_URL)
        self.assertIn("…", parse_qs(urlsplit(url).query)["body"][0])
        with mock.patch.object(issue.sys, "frozen", True, create=True), \
                mock.patch("fedtail.diag.logs_dir", return_value=self.logs):
            d = issue.draft(SimpleNamespace(profile="default"), {}, toolkit="")
        self.assertIn("one-file build", d.body)
        self.assertIn("interface ?", d.body)


class PlaceAndFlagTest(unittest.TestCase):
    def setUp(self):
        i18n.setup("en")
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)

    def test_the_issue_place(self):
        from fedtail.core.view import View
        from fedtail.frontends.common.places import MENU, Places

        from . import scenario
        core, _w = scenario.make_core(self._tmp.name)
        self.addCleanup(core.shutdown)
        self.assertIn("issue", MENU)
        pl = Places(View(core))
        page = pl.page("issue")
        self.assertEqual(page.form[0].kind, "text")
        self.assertIn(i18n._("issue_system"), page.form[0].value)
        out = pl.act("issue", "open", "", {"body": "broke at https://example.test/@mira/1"})
        url = out.open["url"]
        self.assertTrue(url.startswith("https://github.com/"))
        body = parse_qs(urlsplit(url).query)["body"][0]
        self.assertNotIn("example.test", body)  # typed in by hand: scrubbed all the same
        self.assertEqual(out.message, i18n._("issue_opened"))
        self.assertIn("example.test", pl._mine())


if __name__ == "__main__":
    unittest.main()
