"""Turn unittest output into GitHub annotations, so failures are readable
from the run page (and through the API) without downloading logs.

usage: python .github/annotate.py test-output.txt
"""

import re
import sys

text = open(sys.argv[1], encoding="utf-8", errors="replace").read()
blocks = re.split(r"\n={50,}\n", text)
found = 0
for b in blocks[1:]:
    head, _, body = b.partition("\n")
    if not head.startswith(("FAIL:", "ERROR:")):
        continue
    msg = (head + "\n" + body.strip())[-6000:]
    print("::error title=" + head.replace(":", " ")[:200] + "::" +
          msg.replace("%", "%25").replace("\r", "").replace("\n", "%0A"))
    found += 1
    if found >= 9:
        break
# a hung run is killed with SIGABRT: faulthandler prints every thread's stack, keep them
hung = "Fatal Python error" in text
tail = "\n".join(text.strip().splitlines()[-(160 if hung else 40):])
print("::warning title=test output tail::" + tail.replace("%", "%25").replace("\n", "%0A"))
