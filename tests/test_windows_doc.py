"""docs/{ru,en}/dev/windows.md stay true: their pip packages are CI's Windows job's, their
test command is CI's, the tools and the switches they name exist."""

import re
import shlex
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = [ROOT / "docs" / lang / "dev" / "windows.md" for lang in ("ru", "en")]
CI = ROOT / ".github" / "workflows" / "ci.yml"


def commands():
    """Every line of the doc's powershell blocks, as words."""
    out = []
    text = "".join(d.read_text("utf-8") for d in DOCS)
    for block in re.findall(r"```powershell\n(.*?)```", text, re.S):
        for line in block.splitlines():
            line = line.strip()
            if line and not line.startswith("#") and not line.startswith("$env:"):
                out.append(shlex.split(line))
    return out


def ci_windows_job():
    text = CI.read_text("utf-8")
    start = text.index("\n  windows:\n")
    end = text.index("\n  windows-build:", start)
    return text[start:end]


def after_python(words):
    """py -3.13 [-X faulthandler] REST → REST."""
    rest = words[1:]
    if rest and rest[0].startswith("-3"):
        rest = rest[1:]
    while rest[:1] == ["-X"]:
        rest = rest[2:]
    return rest


class WindowsDocTest(unittest.TestCase):
    def test_packages_are_ci_s(self):
        job = ci_windows_job()
        ci = set(re.search(r"pip install ([^\n]+)", job).group(1).split())
        pips = [after_python(w) for w in commands() if w[0] == "py" and "pip" in w]
        self.assertTrue(pips)
        for p in pips:
            self.assertEqual({x for x in p[p.index("install") + 1:] if not x.startswith("-")},
                             ci)

    def test_the_test_command_is_ci_s(self):
        job = ci_windows_job()
        ci = re.search(r"python (-X faulthandler -m unittest [^\n|]+?)\s*(?:2>|\||$)", job,
                       re.M).group(1).split()
        tests = [w for w in commands() if "unittest" in w]
        self.assertTrue(tests)
        for t in tests:  # (Russian and English)
            self.assertEqual(t[2:], ci)  # py -3.13 + the same words
        for var in re.findall(r"^\s+(\w+): \S+", job.split("steps:")[0], re.M):
            for doc in DOCS:
                self.assertIn(f"$env:{var}", doc.read_text("utf-8"))

    def test_tools_and_switches_exist(self):
        main = (ROOT / "fedtail" / "__main__.py").read_text("utf-8")
        for words in commands():
            if words[0] != "py":
                continue
            rest = after_python(words)
            if rest[:2] == ["-m", "fedtail"]:
                for flag in rest[2:]:
                    self.assertIn(f'"{flag}"', main, flag)
            elif rest and rest[0].startswith("tools/"):
                tool = ROOT / rest[0]
                self.assertTrue(tool.exists(), rest[0])
                src = tool.read_text("utf-8")
                for flag in (x for x in rest[1:] if x.startswith("--")):
                    self.assertIn(f'"{flag}"', src, f"{rest[0]} {flag}")

    def test_linked_from_the_testers_page(self):
        for lang in ("ru", "en"):
            page = ROOT / "docs" / lang / "dev" / "testing.md"
            self.assertIn("windows.md", page.read_text("utf-8"))


class WindowsCheckTest(unittest.TestCase):
    """tools/windows_check.py knows every command of the page: runs it, or says why not."""

    def test_every_command_is_planned(self):
        import sys
        sys.path.insert(0, str(ROOT / "tools"))
        try:
            import windows_check
        finally:
            sys.path.pop(0)
        for line in windows_check.commands():
            argv, why = windows_check.plan(line)
            self.assertNotEqual(why, "not a command of fedtail's", line)
            if argv is not None and argv[0] != "git":
                self.assertEqual(argv[0], sys.executable, line)
        planned = {line: windows_check.plan(line)[0] for line in windows_check.commands()}
        self.assertTrue(any(a and "--install-desktop" in a for a in planned.values()))
        self.assertTrue(any(a and "unittest" in a for a in planned.values()))


if __name__ == "__main__":
    unittest.main()
