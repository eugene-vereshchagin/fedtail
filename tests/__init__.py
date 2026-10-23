import os as _os

# the tests and the tools that build on them never play through the speakers
# (frontends/common/sound.py): hundreds of chimes and beeps a run
_os.environ.setdefault("FEDTAIL_SOUND", "off")
