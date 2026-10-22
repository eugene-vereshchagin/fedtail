"""Why the Android build failed, as annotations: the parts of Gradle's log that say it.

GitHub keeps a run's log in a store some readers can't reach; its annotations come with
the API itself. So on a failure this picks out Gradle's "What went wrong" blocks, Kotlin's
"e:" lines, Chaquopy's and pip's errors, and prints each as a ::error:: line.

    python3 .github/android_why.py gradle.log
"""

import re
import sys

MAX = 20       # annotations at most (GitHub shows 10 per step, keeps 50 per job)
LINES = 40     # lines of one block at most


def esc(text):
    return text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def blocks(lines):
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("* What went wrong:"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith(("* Try:", "* Exception is:",
                                                              "* Get more help")):
                j += 1
            out.append(("Gradle", lines[i + 1:j][:LINES]))
            i = j
            continue
        if re.match(r"^e: ", line):
            out.append(("Kotlin", [line]))
        elif re.search(r"(Chaquopy|pip).*(error|Error|ERROR)|ERROR: |^error: ", line):
            out.append(("Python packages", lines[max(0, i - 3):i + 6]))
        elif "AAPT: error" in line or re.search(r"Android resource linking failed", line):
            out.append(("Resources", lines[i:i + 6]))
        i += 1
    return out


def main(path):
    try:
        lines = open(path, encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        print(f"::error title=Android build::no log at {path}")
        return
    found = blocks(lines)
    if not found:  # nothing recognised: the end of the log is the best guess
        found = [("Android build (last lines)", lines[-LINES:])]
    seen = set()
    for title, body in found[:MAX]:
        text = "\n".join(x.rstrip() for x in body).strip()
        if text and text not in seen:
            seen.add(text)
            print(f"::error title={title}::{esc(text)}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "gradle.log")
