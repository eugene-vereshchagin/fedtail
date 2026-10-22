"""Do the four interfaces behave alike? The scenario (tests/scenario.py) done through
each one's own way in (tests/drivers.py), compared with what frontends/common says
should happen. An interface missing here is skipped (its toolkit isn't installed);
tools/behaviour.py writes the same comparison as a table for the self-check's report.

And the host contract: every window common/links.py talks to has every place a link may
ask for (open a thread, a profile, report a post…) — one without it says "not here
yet", and that is a difference too. Read from the code (ast), so it runs everywhere."""

import ast
import unittest
from pathlib import Path

from fedtail import i18n

from . import drivers, scenario

ROOT = Path(__file__).resolve().parent.parent

# what common/links.py and common/profile.py may ask of a window (links.py's docstring)
HOST_NEEDS = ("call", "status", "error", "confirm", "open_url", "open_thread",
              "open_account", "open_tag", "resolve_link", "copy_handle", "put_alias",
              "compose", "show_history", "report", "open_reactions", "open_quotes",
              "read_up_to", "redrafted", "ask_text", "open_people", "edit_profile",
              "open_lists")
# frontend -> (package folder, the host class, the class its __getattr__ hands over to)
HOSTS = {"qt": ("fedtail/frontends/qt", "_LinkHost", "MainWindow"),
         "gtk": ("fedtail/frontends/gtk", "MainWindow", None),
         "web": ("fedtail/frontends/web", "_WebHost", None),
         "tui": ("fedtail/frontends/tui", "TuiHost", None)}


def _classes(folder):
    """{class name: (base names, method names)} of every class in a package."""
    out = {}
    for f in (ROOT / folder).rglob("*.py"):
        tree = ast.parse(f.read_text("utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [b.id if isinstance(b, ast.Name) else getattr(b, "attr", "")
                         for b in node.bases]
                names = {n.name for n in node.body
                         if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
                names |= {t.id for n in node.body if isinstance(n, ast.Assign)
                          for t in n.targets if isinstance(t, ast.Name)}
                old = out.get(node.name, ((), set()))
                out[node.name] = (tuple(old[0]) + tuple(bases), old[1] | names)
    return out


def host_methods(frontend):
    """The methods of a frontend's host, its bases (in the same package) included;
    None when the frontend has no such class yet."""
    folder, name, delegate = HOSTS[frontend]
    classes = _classes(folder)
    if name not in classes:
        return None
    todo = [name]
    if delegate and "__getattr__" in classes[name][1]:
        todo.append(delegate)
    got, seen = set(), set()
    while todo:
        c = todo.pop()
        if c in seen or c not in classes:
            continue
        seen.add(c)
        bases, names = classes[c]
        got |= names
        todo += list(bases)
    return got


def host_gaps():
    """{frontend: [what its host lacks]}."""
    out = {}
    for fe in HOSTS:
        have = host_methods(fe)
        out[fe] = list(HOST_NEEDS) if have is None else [n for n in HOST_NEEDS
                                                         if n not in have]
    return out


def available():
    """The drivers this machine can run (a toolkit missing: its driver is left out)."""
    got = [drivers.Web()]
    for make in (getattr(drivers, "Tui", None), getattr(drivers, "Qt", None),
                 getattr(drivers, "Gtk", None)):
        if make is not None and make.can_run():
            got.append(make())
    return got


class HostContractTest(unittest.TestCase):
    def test_every_host_has_every_place(self):
        gaps = {fe: g for fe, g in host_gaps().items() if g}
        self.assertEqual(gaps, {}, "hosts lacking places common/links.py may ask for")


class BehaviourTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        i18n.setup("en")
        cls.ref = scenario.run(drivers.Reference())

    def test_reference_did_everything(self):
        r = self.ref
        self.assertEqual(r.cant, {})
        self.assertEqual(r.done["liked"], ["010"])
        self.assertEqual(r.done["gone"], ["030"])
        self.assertEqual(r.done["posted"],
                         [("@alice@other.example scenario: a reply", "private", "011")])
        self.assertEqual(r.done["following"], ["B"])
        self.assertEqual(r.done["subscribed"], ["020"])
        self.assertEqual(r.done["quiet_threads"], ["012"])
        self.assertEqual(r.done["unread_replies"], 0)
        self.assertEqual(r.shown["thread"], [("020", 0), ("021", 1), ("022", 2), ("023", 3)])

    def test_every_interface_alike(self):
        for d in available():
            with self.subTest(frontend=d.name):
                got = scenario.run(d)
                self.assertEqual(scenario.compare(self.ref, got), [])


if __name__ == "__main__":
    unittest.main()
