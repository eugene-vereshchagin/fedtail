"""A timer's lambda in the Qt frontend runs only while its object lives: every
`QTimer.singleShot(ms, lambda …)` names a context object (`self`, the window), which Qt
uses to drop the call once that object is gone. Without it a place closed within 8 s
crashed: "Internal C++ object (QLabel) already deleted" (28.10's report)."""

import re
import unittest
from pathlib import Path

QT = Path(__file__).resolve().parent.parent / "fedtail" / "frontends" / "qt"
BARE = re.compile(r"QTimer\.singleShot\(\s*[^,()]+,\s*lambda")


class TimersTest(unittest.TestCase):
    def test_no_lambda_without_a_context(self):
        bad = [f"{f.name}:{n}: {line.strip()}"
               for f in sorted(QT.glob("*.py"))
               for n, line in enumerate(f.read_text("utf-8").splitlines(), 1)
               if BARE.search(line)]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
