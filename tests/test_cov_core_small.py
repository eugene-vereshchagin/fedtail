"""The small parts of the core, at their edges: events, threads, tag groups, sources,
links, health, remote addresses, auth, paths, sounds, config and its editing."""

import logging
import socket
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from fedtail.core import (
    auth,
    config,
    config_edit,
    config_update,
    health,
    links,
    paths,
    remote,
    sounds,
    sources,
    taggroups,
    threads,
)
from fedtail.core.events import Events
from fedtail.core.store import Store


class EventsTest(unittest.TestCase):
    def test_off_and_a_broken_handler(self):
        ev, got = Events(), []

        def h(n, p):
            got.append(p)
        ev.on("x", h)
        ev.emit("x", 1)
        ev.off("x", h)
        ev.off("x", h)  # twice: nothing to remove
        ev.off("never", h)
        ev.emit("x", 2)
        self.assertEqual(got, [1])

        def bad(_n, _p):
            raise RuntimeError("boom")
        ev.on("y", bad)
        ev.on("y", h)
        with self.assertLogs("fedtail.core.events", logging.ERROR):
            ev.emit("y", 3)
        self.assertEqual(got, [1, 3])  # the next handler still ran


class ThreadsTest(unittest.TestCase):
    def test_root_climbs_and_loops_stay_once(self):
        a = {"id": "a", "created_at": "1"}
        b = {"id": "b", "in_reply_to_id": "a", "created_at": "2"}
        c = {"id": "c", "in_reply_to_id": "b", "created_at": "3"}
        # the focus's ancestors given from b: the root is still a
        nodes = threads.build(c, {"ancestors": [b, a], "descendants": [dict(c)]})
        self.assertEqual([n.status["id"] for n in nodes], ["a", "b", "c"])
        self.assertEqual([n.depth for n in nodes], [0, 1, 2])

    def test_conversations_stop_at_a_loop_and_a_missing_parent(self):
        x = {"id": "x", "in_reply_to_id": "y"}
        y = {"id": "y", "in_reply_to_id": "x"}
        store = {"x": x, "y": y}
        got = threads.conversations([("1", x)], store.get, set())
        self.assertEqual(len(got), 1)
        lone = {"id": "z", "in_reply_to_id": "gone"}
        got = threads.conversations([("2", lone)], store.get, {"z"})
        self.assertEqual((got[0]["key"], got[0]["unread"]), ("z", 1))


class TagGroupsTest(unittest.TestCase):
    def test_edges(self):
        self.assertIsNone(taggroups.parse(""))
        self.assertIsNone(taggroups.parse("-#politics"))  # nothing to show
        self.assertIsNone(taggroups.parse("#a"))
        self.assertEqual(taggroups.parse("#a", one_ok=True)["any"], ["a"])
        self.assertIsNone(taggroups.spec_of("home"))
        st = {"tags": [{"name": "a"}, {"name": "b"}]}
        self.assertFalse(taggroups.matches(st, {"all": ["a", "c"]}))
        self.assertTrue(taggroups.matches(st, {"all": ["a", "b"]}))
        self.assertFalse(taggroups.matches(st, {"any": ["c"]}))


class FakeSource:
    def __init__(self, name, pages):
        self.name = name
        self.pages = list(pages)
        self.asked = []
        self.entry = sources._status_entry

    def fetch(self, limit=40, max_id=None, min_id=None):
        self.asked.append((limit, max_id))
        return self.pages.pop(0) if self.pages else []


def st(i, t):
    return {"id": i, "created_at": t, "account": {"id": "A"}, "content": ""}


class SourcesTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.store = Store(Path(self._tmp.name) / "s.db")
        self.addCleanup(self.store.close)

    def test_notification_without_a_post(self):
        self.assertIsNone(sources.notification_entry({"id": "1", "type": "follow"}))

    def test_fill_empty_walks_back_to_when_watching_began(self):
        self.store.kv_set("source_since:home", "2026-01-01T00:00:01")
        src = FakeSource("home", [[st("9", "2026-01-01T00:00:09"),
                                   st("8", "2026-01-01T00:00:08")],
                                  [st("7", "2026-01-01T00:00:00"),
                                   st("6", "2026-01-01T00:00:00")]])
        new = sources._fill_empty(self.store, src, 2, 100)
        self.assertEqual(len(src.asked), 2)  # stopped once past the watching start
        self.assertEqual(src.asked[1][1], "8")
        self.assertEqual(len(new), 2)
        # the oldest already before then: no walking back at all
        self.store.kv_set("source_since:fed", "2026-06-01")
        src = FakeSource("fed", [[st("1", "2026-01-01"), st("2", "2026-01-02")]])
        sources._fill_empty(self.store, src, 2, 100)
        self.assertEqual(len(src.asked), 1)

    def test_fetch_older_of_an_empty_lane(self):
        src = FakeSource("local", [[st("1", "2026-01-01")]])
        got = sources.fetch_older(self.store, src, 20)
        self.assertEqual([s["id"] for s in got], ["1"])
        self.assertEqual(src.asked, [(20, None)])


class LinksTest(unittest.TestCase):
    def test_edges(self):
        self.assertFalse(links.looks_fediverse("http://[::1"))
        html = '<a class="mention" href="https://x.test/tags/fedi">#fedi</a>'
        self.assertIn("fedtail:tag/fedi", links.in_app(html))


class HealthTest(unittest.TestCase):
    def test_outcome_names(self):
        class SSLError(Exception):
            pass

        class Weird(Exception):
            pass
        self.assertEqual(health.outcome_of(SSLError()), "TLS error")
        self.assertEqual(health.outcome_of(Weird()), "Weird")


class RemoteTest(unittest.TestCase):
    def test_unresolvable_passes(self):
        with mock.patch.object(socket, "getaddrinfo", side_effect=OSError("no dns")):
            self.assertIsNone(remote.check("https://nowhere.example/x"))


class AuthPathsTest(unittest.TestCase):
    def test_forget_a_missing_file_and_a_bad_main(self):
        with tempfile.TemporaryDirectory() as d:
            auth.forget(Path(d) / "none.json")
        with self.assertRaises(ValueError):
            paths.set_main("../x")
        with self.assertRaises(ValueError):
            paths.set_main(paths.MAIN_FILE)


class SoundsTest(unittest.TestCase):
    def test_old_true_false(self):
        self.assertIs(sounds.enabled({"sound": {"enabled": True}}), True)
        self.assertIs(sounds.enabled({"sound": {"enabled": False}}), False)


class ConfigTest(unittest.TestCase):
    def errors(self, user):
        with self.assertRaises(config.ConfigError) as e:
            config.validate(user)
        return str(e.exception)

    def test_validate_edges(self):
        self.assertIn("must be a section", self.errors({"ui": 5}))
        _cfg, w = config.validate({"debug": {"keep": 3}})
        self.assertTrue(any("debug.keep is gone" in x for x in w))
        # taken out in 0.21/0.22: said what says it now, by either layout's name
        _cfg, w = config.validate({"lanes": {"mentions_all": True, "bots_in_home": True},
                                   "feed": {"build_at_once": 5},
                                   "subs": {"replies_to_me": True}})
        self.assertFalse([x for x in w if x.startswith("unknown key")], w)
        self.assertTrue(any("lanes.mentions_all is gone (0.21)" in x for x in w))
        self.assertTrue(any("build_at_once is gone" in x for x in w))
        _cfg, w = config.validate({"reading": {"build_at_once": 5}, "threads": {
            "replies_to_me": True}})
        self.assertFalse([x for x in w if x.startswith("unknown key")], w)
        self.assertIn("activity.types", self.errors({"activity": {"types": ["nope"]}}))
        self.assertIn("threads.auto", self.errors({"subs": {"auto": ["nope"]}}))
        config.validate({"lanes": {"enabled": []}})  # empty: the set's own order (no error)
        self.assertIn("extra_bots", self.errors({"lanes": {"extra_bots": [1]}}))
        self.assertIn("accounts.merge", self.errors({"ui": {"merge": ["../x"]}}))
        self.assertIn("window.start_lane", self.errors({"ui": {"start_lane": "nowhere"}}))
        self.assertEqual(config.sensitive_media({"ui": {}, "feed": {}}), "hide")


class ConfigUpdateTest(unittest.TestCase):
    def test_toml_writes_every_kind(self):
        self.assertEqual(config_update._toml({"a": 1, "b": [True, "x"]}),
                         '{ a = 1, b = [true, "x"] }')
        self.assertEqual(config_update._toml(None), '"None"')

    def test_rebuild_keeps_a_table_and_skips_non_tables(self):
        ex = config.example_text("en")
        user = 'top = 1\n[ui]\ntheme = "paper"\n[ui.extra]\nx = 1\n'
        out = config_update.rebuild(user, ex, {})
        self.assertEqual(tomllib.loads(out)["appearance"]["theme"], "paper")
        self.assertEqual(tomllib.loads(out)["ui"]["extra"], {"x": 1})


class ConfigEditTest(unittest.TestCase):
    def test_values(self):
        self.assertEqual(repr(config_edit.UNSET), "UNSET")
        self.assertEqual(config_edit.toml_value(1.5), "1.5")
        with self.assertRaises(TypeError):
            config_edit.toml_value(object())

    def test_odd_files(self):
        # an escaped quote inside a list's string, a list that never closes
        text = '[ui]\ncolumns = ["a\\"]", "b"]\nfont = "x"\n'
        out = config_edit.set_value(text, "ui", "columns", ["c"])
        self.assertEqual(tomllib.loads(out)["ui"], {"columns": ["c"], "font": "x"})
        broken = "[ui]\ncolumns = [\n"
        self.assertIn('columns = ["c"]', config_edit.set_value(broken, "ui", "columns", ["c"]))
        # a new section after trailing blank lines; an option the reference lacks
        out = config_edit.set_value("[ui]\n\n\n", "web", "nosuch", 1,
                                    config.example_text("en"))
        self.assertTrue(out.endswith("[web]\nnosuch = 1\n"))
        # unset without a default keeps the value as written
        out = config_edit.unset('[ui]\ntheme = "nord"\n', "ui", "theme")
        self.assertIn('#theme = "nord"', out)

    def test_check_and_save_edges(self):
        with self.assertRaisesRegex(config_edit.SaveError, "wouldn't read"):
            config_edit.check("[ui\n", {})
        with self.assertRaisesRegex(config_edit.SaveError, "reads back"):
            config_edit.check('[ui]\ntheme = "a"\n', {("ui", "theme"): "b"})
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "sub" / "config.toml"
            config_edit.save(f, {("ui", "theme"): "paper"})  # no file yet: from the example
            self.assertEqual(tomllib.loads(f.read_text("utf-8"))["appearance"]["theme"],
                             "paper")
            before = f.stat().st_mtime_ns
            config_edit.save(f, {("ui", "theme"): "paper"})  # the same: not written again
            self.assertEqual(f.stat().st_mtime_ns, before)


if __name__ == "__main__":
    unittest.main()
