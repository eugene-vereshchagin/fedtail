"""The developer docs come in two languages, docs/ru/dev/ and docs/en/dev/, and the two stay
twins: the same files, the same skeleton (headings by level, code blocks, tables of the same
shape), relative links that lead somewhere. tools.md lists every tool, ci.md every CI job."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEV = {lang: ROOT / "docs" / lang / "dev" for lang in ("ru", "en")}
LINK = re.compile(r"\]\(([^)#\s]+)(#[^)\s]*)?\)")


def skeleton(text):
    """(heading levels in order, number of code blocks, rows of each table)."""
    blocks = text.count("```") // 2
    body = re.sub(r"```.*?```", "", text, flags=re.S)
    heads = [len(m) for m in re.findall(r"^(#+) ", body, re.M)]
    tables, rows = [], 0
    for line in body.split("\n"):
        if line.startswith("|"):
            rows += 1
        elif rows:
            tables.append(rows)
            rows = 0
    if rows:
        tables.append(rows)
    return heads, blocks, tables


def ci_jobs():
    jobs = set()
    for wf in ("ci.yml", "site.yml", "vendor.yml"):
        text = (ROOT / ".github" / "workflows" / wf).read_text("utf-8")
        jobs |= set(re.findall(r"^  ([\w-]+):$", text.split("\njobs:\n", 1)[1], re.M))
    return jobs


class DevDocsTest(unittest.TestCase):
    def test_same_files(self):
        names = {lang: sorted(p.name for p in d.glob("*.md")) for lang, d in DEV.items()}
        self.assertEqual(names["ru"], names["en"])
        self.assertIn("index.md", names["en"])

    def test_same_skeleton(self):
        for ru in sorted(DEV["ru"].glob("*.md")):
            en = DEV["en"] / ru.name
            with self.subTest(doc=ru.name):
                self.assertEqual(skeleton(ru.read_text("utf-8")),
                                 skeleton(en.read_text("utf-8")))

    def test_relative_links_lead_somewhere(self):
        for d in DEV.values():
            for doc in d.glob("*.md"):
                for target, _ in LINK.findall(doc.read_text("utf-8")):
                    if "://" in target or target.startswith(("/", "mailto:")):
                        continue
                    with self.subTest(doc=str(doc.relative_to(ROOT)), link=target):
                        self.assertTrue((doc.parent / target).exists())

    def test_every_tool_listed(self):
        tools = {p.name for p in (ROOT / "tools").glob("*.py")}
        for d in DEV.values():
            text = (d / "tools.md").read_text("utf-8")
            listed = set(re.findall(r"^\| `([\w]+\.py)`", text, re.M))
            self.assertEqual(listed, tools, d)

    def test_every_ci_job_listed(self):
        jobs = ci_jobs()
        self.assertIn("release", jobs)
        for d in DEV.values():
            text = (d / "ci.md").read_text("utf-8")
            listed = set(re.findall(r"^\| `([\w-]+)`", text, re.M))
            self.assertEqual(listed, jobs, d)

    def test_no_old_paths(self):
        old = re.compile(r"docs/(ARCHITECTURE|DESIGN|PROTOCOLS|GTK|LAYOUTS|TESTPLAN|ROADMAP|"
                         r"DEBUGGING|WINDOWS|TESTING)\.md")
        for path in ("AGENTS.md", "README.md", "README.ru.md", "CONTRIBUTING.md"):
            with self.subTest(path=path):
                self.assertIsNone(old.search((ROOT / path).read_text("utf-8")))


if __name__ == "__main__":
    unittest.main()
