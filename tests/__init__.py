import os as _os

# the tests and the tools that build on them never play through the speakers
# (frontends/common/sound.py): hundreds of chimes and beeps a run
_os.environ.setdefault("FEDTAIL_SOUND", "off")
# and draw a theme's pictures in their own colours, not the development version's red
# for what comes from the fallback set (frontends/iconpack.py; its own test turns it on)
_os.environ.setdefault("FEDTAIL_MARK_MISSING", "0")
