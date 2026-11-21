"""tools/stats.py: the READMEs' numbers — what counts as which code, the words of the
numbers, and the tokens' ledger that outlives Claude Code's logs."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import stats  # noqa: E402


def session(first, output, cache_read, model="claude-opus-5-5"):
    return {"first": first, "last": first, "input": 1, "output": output, "cache_write": 10,
            "cache_read": cache_read, "models": {model: output}}


class StatsTest(unittest.TestCase):
    def test_kinds(self):
        k = stats.kind_of
        self.assertEqual(k("fedtail/core/app.py"), "python")
        self.assertEqual(k("tests/test_core.py"), "tests")
        self.assertEqual(k("tools/stats.py"), "tools")
        self.assertEqual(k(".github/workflows/ci.yml"), "tools")
        self.assertEqual(k("android/app/src/main/java/online/dmesg/fedtail/App.kt"), "kotlin")
        self.assertEqual(k("fedtail/data/web/app.js"), "web")
        self.assertEqual(k("README.md"), "docs")
        self.assertIsNone(k("docs/en/features.md"))           # generated
        self.assertIsNone(k("fedtail/_vendor/textual_image/x.py"))  # not ours
        self.assertIsNone(k("fedtail/data/icons/x.png"))

    def test_words_of_numbers(self):
        self.assertEqual(stats.big(2_313_443_845, "en"), "2.31 billion")
        self.assertEqual(stats.big(2_313_443_845, "ru"), "2,31 миллиарда")
        self.assertEqual(stats.big(16_453_270, "ru"), "16,5 миллиона")
        self.assertEqual(stats.big(1_000_000, "ru"), "1 миллион")
        self.assertEqual(stats.big(5_000_000, "ru"), "5 миллионов")
        self.assertEqual(stats.approx(87_279, "en"), "~87 000")
        self.assertEqual(stats.approx(9_418, "en"), "~9 400")
        self.assertEqual(stats.day("2026-10-29", "ru", False), "29 октября")
        self.assertEqual(stats.day("2026-10-29", "en"), "29 October 2026")
        self.assertEqual(stats.model_name("claude-opus-5-5"), "Claude Opus")

    def test_a_session_whose_log_is_gone_stays_counted(self):
        ledger = {"a": session("2026-10-15", 100, 1000), "b": session("2026-10-20", 50, 500)}
        got = stats.merged(ledger, {"b": session("2026-10-20", 80, 900),  # grew
                                    "c": session("2026-11-01", 5, 5)})
        self.assertEqual(set(got), {"a", "b", "c"})
        self.assertEqual(got["b"]["output"], 80)
        t = stats.totals(got)
        self.assertEqual((t["output"], t["since"], t["model"]), (185, "2026-10-15",
                                                                 "claude-opus-5-5"))

    def test_logs_read_each_answer_once_and_no_words(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "s.jsonl"
            answer = {"sessionId": "S", "requestId": "R1", "timestamp": "2026-11-21T09:00:00Z",
                      "message": {"id": "M1", "model": "claude-opus-5-5",
                                  "content": [{"type": "text", "text": "a secret"}],
                                  "usage": {"input_tokens": 3, "output_tokens": 7,
                                            "cache_read_input_tokens": 11}}}
            log.write_text("\n".join(json.dumps(x) for x in (answer, answer, {"x": 1})) + "\n")
            got = stats.sessions([Path(d)])
        self.assertEqual(got["S"]["output"], 7)  # the same answer twice: once
        self.assertEqual(got["S"]["cache_read"], 11)
        self.assertNotIn("secret", json.dumps(got))

    def test_the_section_between_its_markers(self):
        text = stats.text("en", dict.fromkeys(stats.KINDS, 1500), 10, 2, "2026-10-15",
                          "2026-11-21", stats.totals({"a": session("2026-10-29", 9, 9)}),
                          838)
        self.assertIn("the earlier logs are gone", text)  # logs begin after the first commit
        readme = f"a\n{stats.BEGIN}\nold\n{stats.END}\nb"
        self.assertEqual(stats.put(readme, "new"), f"a\n{stats.BEGIN}\nnew\n{stats.END}\nb")
        for path in stats.READMES.values():  # the real READMEs have the markers
            s = path.read_text("utf-8")
            self.assertLess(s.index(stats.BEGIN), s.index(stats.END))


if __name__ == "__main__":
    unittest.main()
