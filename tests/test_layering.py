"""Frontends read no protocol fields: they speak fedtail.model through core/view.py
(docs/en/dev/protocols.md, stage 2) — every file under frontends/."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "fedtail"

MOVED = sorted(str(p.relative_to(ROOT)) for p in (ROOT / "frontends").rglob("*.py"))
# the phone's Python is a frontend too (it slipped by: its overview read raw posts)
PHONE = sorted((ROOT.parent / "android/app/src/main/python").rglob("*.py"))

# what only a Mastodon status or account has; the model says it differently
RAW = re.compile(r'"(reblog|spoiler_text|in_reply_to_id|in_reply_to_account_id|'
                 r'media_attachments|favourited|reblogged|favourites_count|reblogs_count|'
                 r'replies_count|display_name|acct|statuses_count|followers_count|'
                 r'following_count|preview_url|remote_url)"|/api/v\d|\.lane_entries\(|'
                 r'\.unread_ids\(|\.parent_of\(|\.account_statuses\(|core\.model import|'
                 r'\.store\.|\bstore\.get_status\(|\bcore\._(?!core\b)[a-z]')

# the fields alone (RAW's first part): what the core's own logic still reads by Mastodon's
# names
FIELDS = re.compile(RAW.pattern.split(r"|/api/v")[0])

# Stage 7 of docs/en/dev/protocols.md, done on 23.11: the core reads the server's objects
# through the protocol's raw module (core/proto.raw), never by its field names. A module
# that still may (none does) would be named here with how many times.
CORE_RAW = {}


class CoreRawTest(unittest.TestCase):
    def test_the_core_reads_no_more_protocol_fields_than_it_did(self):
        core = ROOT / "core"
        over, under = [], []
        for path in sorted(core.rglob("*.py")):
            rel = str(path.relative_to(core))
            # (a line marked "# ours:" names fedtail's own words — a file of its own, the
            # config's vocabulary — that happen to be spelled as the server's)
            n = sum(len(FIELDS.findall(line))
                    for line in path.read_text(encoding="utf-8").splitlines()
                    if "# ours:" not in line)
            most = CORE_RAW.get(rel, 0)
            if n > most:
                over.append(f"{rel}: {n} (the ceiling is {most})")
            elif n < most:
                under.append(f"{rel}: {n} now — lower CORE_RAW from {most}")
        self.assertEqual(over, [], "the core reads more of the protocol's fields "
                         "(protocols.md, stage 7): through the model instead\n" +
                         "\n".join(over))
        self.assertEqual(under, [], "\n".join(under))


class CoreStateTest(unittest.TestCase):
    """The core's state is declared (core/state.py), not made up where first needed: no
    part of the Core reads an attribute of its own "if it is there" (the audit of 23.11:
    ``self.__dict__.setdefault(...)``, ``getattr(self, "_x", None)`` in a dozen modules —
    nothing said what state there is, nor which lock guards it)."""
    LAZY = re.compile(r'self\.__dict__\b|getattr\(self, "_')

    def test_no_part_of_the_core_makes_up_its_state(self):
        import ast
        hits = []
        for path in sorted((ROOT / "core").glob("*.py")):
            text = path.read_text(encoding="utf-8")
            lines = text.splitlines()
            for c in ast.parse(text).body:
                if isinstance(c, ast.ClassDef) and (c.name in ("Core", "View")
                                                    or c.name.endswith("Mixin")):
                    hits += [f"{path.name}:{n}: {lines[n - 1].strip()}"
                             for n in range(c.lineno, c.end_lineno + 1)
                             if self.LAZY.search(lines[n - 1])]
        self.assertEqual(hits, [], "declare it in core/state.py:\n" + "\n".join(hits))

    def test_every_core_gets_containers_of_its_own(self):
        from fedtail.core.state import CoreState
        a, b = CoreState(), CoreState()
        a._init_state()
        b._init_state()
        shared = [k for k, v in vars(a).items()
                  if not isinstance(v, (bool, int, float, str, type(None))) and v is vars(b)[k]]
        self.assertEqual(shared, [])
        # …and nothing mutable is a class attribute (it would be every core's at once)
        self.assertEqual([k for k, v in vars(CoreState).items() if isinstance(
            v, (dict, list, set))], [])


class LayeringTest(unittest.TestCase):
    def test_moved_frontends_read_no_protocol_fields(self):
        """A line marked "# ours:" reads fedtail's own data (auth.json), not a server's."""
        self.assertTrue(PHONE)
        for path in [ROOT / rel for rel in MOVED] + PHONE:
            text = path.read_text(encoding="utf-8")
            hits = [f"{path.name}:{n}: {line.strip()}"
                    for n, line in enumerate(text.splitlines(), 1)
                    if RAW.search(line) and "# ours:" not in line]
            self.assertEqual(hits, [], "\n".join(hits))

    def test_diag_imports_no_toolkit(self):
        """fedtail/diag.py is the core's side (AGENTS.md): what it says of a toolkit it
        reads from sys.modules — it imported PySide6 inside a function (23.11)."""
        text = (ROOT / "diag.py").read_text(encoding="utf-8")
        self.assertIsNone(re.search(r"^\s*(from|import)\s+(PySide6|gi\b|textual|shiboken)",
                                    text, re.M))

    def test_shared_frontend_code_imports_no_toolkit(self):
        """frontends/common, palette.py, pango.py and the other shared modules are for
        every toolkit: none of them may import one (docs/en/dev/gtk.md, stage 0)."""
        toolkit = re.compile(r"^\s*(from|import)\s+(PySide6|gi\b|textual|shiboken)", re.M)
        shared = [p for p in (ROOT / "frontends").rglob("*.py")
                  if p.parent.name in ("frontends", "common")]
        self.assertTrue(any(p.parent.name == "common" for p in shared))
        for p in shared:
            self.assertIsNone(toolkit.search(p.read_text(encoding="utf-8")), p.name)

    def test_the_page_speaks_the_model(self):
        js = (ROOT / "data/web/app.js").read_text(encoding="utf-8")
        for word in ("favourited", "reblogged", "spoiler", "acct", "private"):
            self.assertNotRegex(js, rf"\.{word}\b", word)


if __name__ == "__main__":
    unittest.main()
