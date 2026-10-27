"""No class defines a method twice: the later one silently wins (27.10: the profile's
buttons in Qt — Follow, Unfollow — called a `_changed` that a second `_changed` below
had replaced, and failed). Properties' setters and @overload are the exceptions."""

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _decorated(fn, names):
    for d in fn.decorator_list:
        text = ast.unparse(d)
        if any(n in text for n in names):
            return True
    return False


class ShadowedTest(unittest.TestCase):
    def test_no_method_defined_twice(self):
        found = []
        for path in sorted((ROOT / "fedtail").rglob("*.py")):
            tree = ast.parse(path.read_text("utf-8"))
            for cls in ast.walk(tree):
                if not isinstance(cls, ast.ClassDef):
                    continue
                seen = {}
                for fn in cls.body:
                    if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        continue
                    if _decorated(fn, (".setter", ".deleter", "overload")):
                        continue
                    if fn.name in seen:
                        found.append(f"{path.relative_to(ROOT)}:{fn.lineno} {cls.name}."
                                     f"{fn.name} (first at {seen[fn.name]})")
                    seen[fn.name] = fn.lineno
        self.assertEqual(found, [])


if __name__ == "__main__":
    unittest.main()
