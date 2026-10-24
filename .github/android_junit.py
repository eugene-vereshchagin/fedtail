"""The UI tests' JUnit XML → a line per test into a text file, and ::error:: annotations
for the failures (readable through the API, where the job's log isn't).

    python3 .github/android_junit.py RESULTS_DIR OUT.txt
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main(folder, out):
    lines, failed = [], 0
    for f in sorted(Path(folder).rglob("*.xml")):
        for case in ET.parse(f).getroot().iter("testcase"):
            name = f"{case.get('classname', '').rsplit('.', 1)[-1]}.{case.get('name')}"
            bad = case.find("failure") if case.find("failure") is not None else case.find("error")
            if bad is not None:
                failed += 1
                first = (bad.get("message") or bad.text or "").strip().splitlines()[:3]
                why = " / ".join(first)[:900]
                print(f"::error::UI test {name}: {why}")
                lines.append(f"FAIL {name}: {why}")
            else:
                lines.append(f"ok   {name} ({case.get('time', '?')} s)")
    if not lines:
        print("::error::UI tests: no results (the run failed before the tests — uitests.log)")
        lines.append("no results")
    Path(out).write_text("\n".join(lines) + "\n", "utf-8")
    return 1 if failed or lines == ["no results"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
