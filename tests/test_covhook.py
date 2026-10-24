"""The self-check's coverage hook (tools/covhook/sitecustomize.py) and its report
(tools/coverage_lite.py --report): a process started with FEDTAIL_COVERAGE leaves the
lines of fedtail/ it ran — at exit, at fedtail's quick exit and when it is killed."""

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "tools" / "covhook"


@unittest.skipUnless(hasattr(sys, "monitoring"), "Python 3.12+")
class CovHookTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.hits = Path(self._tmp.name) / "hits"

    def start(self, code):
        env = dict(os.environ, FEDTAIL_COVERAGE=str(self.hits),
                   PYTHONPATH=os.pathsep.join([str(HOOK), str(ROOT)]))
        return subprocess.Popen([sys.executable, "-c", code], env=env, cwd=ROOT)

    def lines(self):
        out = {}
        for f in self.hits.glob("hits-*.json"):
            for rel, got in json.loads(f.read_text("utf-8")).items():
                out.setdefault(rel, set()).update(got)
        return out

    def test_lines_at_exit_and_quick_exit(self):
        p = self.start("from fedtail.core import config_edit; "
                       "config_edit.toml_value(True)")
        self.assertEqual(p.wait(60), 0)
        got = self.lines()
        self.assertIn("fedtail/core/config_edit.py", got)
        self.assertTrue(all(k.startswith("fedtail/") for k in got))  # nothing else
        p = self.start("import os, sys; from fedtail import sysenv; sysenv.child_env(); "
                       "sys.fedtail_coverage_flush(); os._exit(0)")
        self.assertEqual(p.wait(60), 0)
        self.assertIn("fedtail/sysenv.py", self.lines())

    @unittest.skipIf(os.name == "nt", "SIGTERM is Unix's")
    def test_killed_leaves_its_lines(self):
        p = self.start("import time; from fedtail import version; version.full(); "
                       "print('up', flush=True); time.sleep(60)")
        for _ in range(200):
            if list(self.hits.glob("hits-*.json")) or p.poll() is not None:
                break
            time.sleep(0.05)
        time.sleep(0.5)
        p.send_signal(signal.SIGTERM)
        p.wait(30)
        self.assertIn("fedtail/version.py", self.lines())

    def test_report_puts_processes_together(self):
        self.hits.mkdir(parents=True)
        (self.hits / "hits-1.json").write_text(json.dumps(
            {"fedtail/sysenv.py": [1, 2]}), "utf-8")
        (self.hits / "hits-2.json").write_text("broken", "utf-8")
        out = Path(self._tmp.name)
        r = subprocess.run([sys.executable, str(ROOT / "tools" / "coverage_lite.py"),
                            str(out), "--report"], capture_output=True, text=True,
                           timeout=120, cwd=ROOT)
        self.assertEqual(r.returncode, 0, r.stderr)
        report = (out / "report.md").read_text("utf-8")
        self.assertIn("processes of the self-check counted too: 2", report)
        missing = json.loads((out / "lines.json").read_text("utf-8"))
        self.assertNotIn(1, missing["fedtail/sysenv.py"])
        self.assertTrue((out / "notes.txt").exists())


if __name__ == "__main__":
    unittest.main()
