""""Report a bug on GitHub…": a draft of a public issue — what happened (for the person
to write), the version and the system, the latest warnings and errors of the log —
with everything that says who or where the person is taken out first (scrub), shown to
them to read and edit, then opened in the browser as a new issue of debug.issue_repo
(fedtail's own tracker by default). Nothing is sent from here: the person presses
"Submit" on GitHub themselves, after having seen every word.

    d = draft(paths, cfg, known=[server, acct])   # Draft(title, body)
    url = issue_url(cfg, d.title, d.body)          # https://github.com/…/issues/new?…
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote, urlsplit

from .i18n import _

# the address of the new issue, at most: 7500 went to the browser as nothing at all on
# KDE (29.10: the desktop's opener checks the page first, and the address was too long
# for it), so the text goes on the clipboard whole and into the address only as far as
# every opener takes it; past that the page says to paste it
MAX_URL = 1800
ERROR_LINES = 40      # the newest warnings and errors the draft carries
KEEP_HOSTS = {"github.com", "docs.joinmastodon.org", "codeberg.org"}  # not anyone's

_URL = re.compile(r"\b(?:https?|wss?)://[^\s\"'<>)\]]+", re.I)
_HANDLE = re.compile(r"@?\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")
_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_IPV6 = re.compile(r"\b(?:[0-9a-f]{1,4}:){3,7}[0-9a-f]{1,4}\b", re.I)
_SECRET = re.compile(r"(?i)(bearer\s+|token[\"'=:\s]+|key[\"'=:\s]+)[\w.~+/=-]{8,}")
_LONG = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")  # a token, a key, a hash: none is for public
_LEVEL = re.compile(r"^\S+ \S+ (WARNING|ERROR|CRITICAL)\b")


@dataclass
class Draft:
    title: str
    body: str


def scrub(text, known=()):
    """The text with what tells who or where the person is replaced by placeholders:
    the words in `known` (their server, their @name, a profile's name), any address
    of a server but a few public ones, @name@server, IP addresses, long tokens, the home
    folder."""
    home = str(Path.home())
    if home and home not in ("/", "."):
        text = text.replace(home, "~")
    user = os.environ.get("USER") or os.environ.get("USERNAME") or ""
    for word in sorted({w for w in known if w and len(w) > 2}, key=len, reverse=True):
        text = re.sub(re.escape(word), "<mine>", text, flags=re.I)
    text = _SECRET.sub(lambda m: m.group(1) + "<secret>", text)

    def url(m):
        host = (urlsplit(m.group(0)).hostname or "").lower()
        if host in KEEP_HOSTS:
            return m.group(0)
        return f"{urlsplit(m.group(0)).scheme}://<server>/…"
    text = _URL.sub(url, text)
    text = _HANDLE.sub("@<someone>@<server>", text)
    text = _IPV4.sub("<ip>", text)
    text = _IPV6.sub("<ip>", text)
    text = _LONG.sub("<id>", text)
    if len(user) > 2:
        text = re.sub(rf"\b{re.escape(user)}\b", "<user>", text)
    return text


def recent_errors(log_dir, limit=ERROR_LINES):
    """The newest warning and error lines of the latest session logs (a traceback that
    follows one comes along), oldest first."""
    folder = Path(log_dir)
    try:
        logs = sorted((f for f in folder.glob("*.log") if f.name != "latest.log"),
                      key=lambda f: f.stat().st_mtime)[-3:]
    except OSError:
        return []
    out = []
    for f in logs:
        try:
            lines = f.read_text("utf-8", errors="replace").splitlines()
        except OSError:
            continue
        keep = False
        for line in lines:
            if _LEVEL.match(line):
                keep = True
                out.append(line)
            elif keep and (line.startswith((" ", "Traceback")) or not line[:4].isdigit()):
                out.append(line)
            else:
                keep = False
    return out[-limit:]


def draft(paths, cfg, known=()):
    """The issue as the person will see it before anything leaves: the system as
    diag.system_lines tells it (the interface that runs, a phone's model and Android)."""
    from . import diag
    errors = recent_errors(diag.logs_dir(paths, cfg))
    known = list(known) + [paths.profile if paths.profile not in ("default", "main") else ""]
    ui = cfg.get("ui") or {}
    system = diag.system_lines(cfg, public=True) + [
        f"theme {ui.get('theme', '?')}, layout {ui.get('layout', '?')}"]
    body = "\n".join([
        "### " + _("issue_what"), "", _("issue_what_hint"), "",
        "### " + _("issue_steps"), "", "1. ", "",
        "### " + _("issue_system"), "", "```", *system, "```", "",
        "### " + _("issue_errors"), "", "```",
        *(errors or [_("issue_no_errors")]), "```", ""])
    return Draft("", scrub(body, known))


def repo_of(cfg):
    from . import version
    spec = ((cfg or {}).get("debug") or {}).get("issue_repo", "").strip()
    if spec:
        return spec.removesuffix(".git")
    return urlsplit(version.HOMEPAGE).path.strip("/")


def issue_url(cfg, title, body):
    """The new-issue page of the tracker with the title and the body filled in; the
    body cut (with a note) when the address would be too long for a browser."""
    base = f"https://github.com/{repo_of(cfg)}/issues/new?title={quote(title or '')}&body="
    room = MAX_URL - len(base)
    text = body
    while len(quote(text)) > room and text:
        cut = max(0, len(text) - max(200, (len(quote(text)) - room) // 3))
        text = body[:cut].rstrip() + "\n…\n```\n" + _("issue_cut") + "\n"
        body = body[:cut]
    return base + quote(text)


__all__ = ["Draft", "draft", "issue_url", "recent_errors", "repo_of", "scrub"]
