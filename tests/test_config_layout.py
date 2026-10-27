"""config.toml's layout (config.FILE_LAYOUT), both reference files and the settings
window are one and the same: an option in exactly one table, the tables in the files in
that order and under the chapters the window shows, and a file of 0.20 and before read
the same as one of now."""

import copy
import re
import tomllib
import unittest
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

from fedtail.core import config
from fedtail.core.config_update import parse_example
from fedtail.frontends.common import settings

_BANNER = re.compile(r"^#\s+(\d+)\.\s+(.+?)\s*$")
_RULE = re.compile(r"^#\s*══")
_TABLE = re.compile(r"^\[([a-z_]+)\]\s*$")


def chapters_of(text):
    """[(number, title, [tables])] as the reference file has them."""
    out, lines = [], text.splitlines()
    for i, line in enumerate(lines):
        m = _BANNER.match(line)
        if m and i and _RULE.match(lines[i - 1]):
            out.append((int(m.group(1)), m.group(2), []))
            continue
        m = _TABLE.match(line)
        if m and out:
            out[-1][2].append(m.group(1))
    return out


class LayoutTest(unittest.TestCase):
    def test_every_option_has_one_place(self):
        every = [opt for _t, opts in config.FILE_LAYOUT for opt in opts]
        self.assertEqual([o for o, n in Counter(every).items() if n > 1], [])
        self.assertEqual(set(every),
                         {(s, k) for s, values in config.DEFAULTS.items() for k in values})
        names = [(t, k) for t, opts in config.FILE_LAYOUT for _s, k in opts]
        self.assertEqual([n for n, c in Counter(names).items() if c > 1], [])
        for (section, key), table in config.FILE_TABLE.items():
            self.assertEqual(config.internal_place(table, key), (section, key))
            self.assertEqual(config.file_place(section, key), (table, key))

    def test_the_reference_files_are_the_layout(self):
        want = [(t, [k for _s, k in opts]) for t, opts in config.FILE_LAYOUT]
        books = {}
        for lang in config.EXAMPLE_LANGS:
            text = config.example_text(lang)
            with self.subTest(lang=lang):
                got = [(t, [k for k, _b in opts]) for t, opts in parse_example(text).items()
                       if "." not in t]
                self.assertEqual(got, want)
                tomllib.loads(text)  # and it reads
                book = chapters_of(text)
                self.assertEqual([n for n, _t, _x in book], list(range(1, len(book) + 1)))
                self.assertEqual([t for _n, _w, ts in book for t in ts], list(config.FILE_TABLES))
                # the contents at the top name the same chapters and tables
                for n, title, tables in book:
                    line = next(x for x in text.splitlines()
                                if re.match(rf"^#\s+{n}\. {re.escape(title)} \.", x))
                    self.assertTrue(line.endswith(" ".join(f"[{t}]" for t in tables)), line)
                # no option is named by its older place in the explanations
                self.assertFalse(re.findall(r"\b(?:ui|feed|read|subs|poll|account)\."
                                            r"(?:[a-z_]+)\b", re.sub(r"`[^`]*--ui[^`]*`", "",
                                                                     text)),
                                 lang)
                books[lang] = [ts for _n, _w, ts in book]
        self.assertEqual(books["ru"], books["en"])  # the same chapters in both

    def test_the_settings_window_is_the_file(self):
        view = SimpleNamespace(paths=SimpleNamespace(config_file=Path("/nowhere")),
                               supports=lambda _x: True, lane_title=lambda _n: None)
        for lang in config.EXAMPLE_LANGS:
            with self.subTest(lang=lang):
                book = chapters_of(config.example_text(lang))
                window = settings.model(view, lang=lang, text="")
                self.assertEqual([(c.number, c.title) for c in window],
                                 [(n, t) for n, t, _x in book])
                for ch, (_n, _t, tables) in zip(window, book, strict=True):
                    self.assertEqual(ch.sections, tables)
                    for o in ch.options:
                        self.assertIn((o.section, o.key), config.INTERNAL, o.name)
                        self.assertIn(o.section, tables, o.name)
                shown = {(o.section, o.key) for c in window for o in c.options}
                left = {(config.FILE_TABLE[st], k) for st in settings.TABLES for k in [st[1]]}
                self.assertEqual(shown | left, set(config.INTERNAL))

    def test_an_older_file_reads_the_same(self):
        """A file of 0.20 and before ([ui], [feed], [read], [subs], [poll], [account]) and
        the same options in the tables of now give one config; the file's own place wins
        over the older one, and validate says once that there are options to move."""
        values = {"ui": {"theme": "nord", "esc": "tray", "merge": ["all"],
                         "image_height": 300, "announcements": "off"},
                  "feed": {"order": "oldest_first", "thread_news": False,
                           "complete_threads": False, "remote_posts": 10,
                           "prefetch": "all", "emoji": False},
                  "read": {"mark_read": "manual", "sync_markers": False},
                  "subs": {"max_threads": 7}, "poll": {"interval_seconds": 120},
                  "account": {"markdown": "on"}, "lanes": {"unsorted": False}}
        old, old_w = config.validate(copy.deepcopy(values))
        new, new_w = config.validate(config.to_file(copy.deepcopy(values)))
        self.assertEqual(old, new)
        self.assertEqual(new_w, [])
        self.assertEqual(len(old_w), 1)
        self.assertIn("--rebuild-config", old_w[0])
        both = config.to_file(copy.deepcopy(values))
        both["ui"] = {"theme": "paper"}
        self.assertEqual(config.validate(both)[0]["ui"]["theme"], "nord")


if __name__ == "__main__":
    unittest.main()
