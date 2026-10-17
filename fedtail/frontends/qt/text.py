"""Server HTML → the rich-text subset QLabel understands. The code has no Qt in it
and lives in frontends/richtext.py, shared with the web interface."""

from ..richtext import *  # noqa: F403
from ..richtext import ZWSP, clean, display_name, emojify, esc, link, sanitize, when  # noqa: F401
