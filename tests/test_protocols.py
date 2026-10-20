"""The protocol layer stays a layer (docs/PROTOCOLS.md, stage 3): the Mastodon API's
paths live only under protocols/, the core calls only the client methods listed in
protocols/base.py, the Mastodon client has every one of them, and frontends don't
import a protocol's insides."""

import ast
import re
import unittest
from pathlib import Path

from fedtail import protocols
from fedtail.protocols.base import CLIENT, Protocol, ServerError

ROOT = Path(__file__).resolve().parent.parent / "fedtail"


def _code_strings(path):
    """String constants of a module that are not docstrings (f-string parts too)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant):
                docs.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and \
                id(node) not in docs:
            yield node.lineno, node.value


def _outside_protocols():
    for p in sorted(ROOT.rglob("*.py")):
        rel = p.relative_to(ROOT)
        if rel.parts[0] != "protocols" and "__pycache__" not in rel.parts:
            yield rel, p


class ProtocolLayerTest(unittest.TestCase):
    def test_no_api_paths_outside_protocols(self):
        hits = [f"{rel}:{n}: {s[:60]!r}" for rel, p in _outside_protocols()
                for n, s in _code_strings(p) if re.search(r"/api/v\d", s)]
        self.assertEqual(hits, [], "\n".join(hits))

    def test_the_core_calls_only_the_listed_client(self):
        used = {}
        for p in (ROOT / "core").glob("*.py"):
            for m in re.finditer(r"(?<![\w.])(?:self\.api|api)\.([a-z_]\w*)",
                                 p.read_text(encoding="utf-8")):
                used.setdefault(m.group(1), p.name)
        self.assertEqual({k: v for k, v in used.items() if k not in CLIENT}, {})

    def test_mastodon_has_the_whole_client(self):
        proto = protocols.get("mastodon")
        self.assertIsInstance(proto, Protocol)
        missing = sorted(n for n in CLIENT if n != "base" and not hasattr(proto.client, n))
        self.assertEqual(missing, [])
        self.assertTrue(issubclass(proto.error, ServerError))
        self.assertEqual(proto.capabilities({"version": "4.3.0"}).software, "mastodon")
        with self.assertRaises(KeyError):
            protocols.get("matrix")

    def test_frontends_import_no_protocol_insides(self):
        bad = []
        for p in sorted((ROOT / "frontends").rglob("*.py")):
            for n, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if re.search(r"protocols\.mastodon|core\.api\b|from \.\.\.?core import .*\bapi\b",
                             line):
                    bad.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()}")
        self.assertEqual(bad, [], "\n".join(bad))


if __name__ == "__main__":
    unittest.main()
