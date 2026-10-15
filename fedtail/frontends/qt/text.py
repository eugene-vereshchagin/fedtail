"""Server HTML → the rich-text subset QLabel understands."""

import html
import re
from datetime import UTC, datetime

_INVISIBLE = re.compile(r'<span class="invisible">.*?</span>', re.S)
_ELLIPSIS = re.compile(r'<span class="ellipsis">(.*?)</span>', re.S)
_ATTRS = re.compile(r'\s(class|rel|target|translate|data-[\w-]+)="[^"]*"')
_IMG = re.compile(r'<img[^>]*?alt="([^"]*)"[^>]*>|<img[^>]*>', re.S)
_SCRIPTY = re.compile(r"<(script|style|iframe)[^>]*>.*?</\1>", re.S | re.I)


def esc(s):
    return html.escape(s or "", quote=True)


def clean(content):
    h = _SCRIPTY.sub("", content or "")
    h = _INVISIBLE.sub("", h)
    h = _ELLIPSIS.sub(r"\1…", h)
    h = _IMG.sub(lambda m: esc(m.group(1) or ""), h)  # custom emoji → :shortcode:
    h = _ATTRS.sub("", h)
    return h


def display_name(account):
    return esc(account.get("display_name") or account.get("username") or account.get("acct"))


def when(iso, months):
    """'14 Oct 10:05' this year, '14 Oct 2024' before."""
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except (ValueError, AttributeError):
        return ""
    now = datetime.now(UTC).astimezone()
    mon = months[dt.month - 1]
    if dt.year != now.year:
        return f"{dt.day} {mon} {dt.year}"
    return f"{dt.day} {mon} {dt:%H:%M}"


def link(action, arg, label):
    return f'<a href="fedtail:{action}/{esc(str(arg))}">{label}</a>'
