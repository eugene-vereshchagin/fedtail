"""My server, without a toolkit: what it says about itself as a page, and what it can
do (the probe) as a Markdown table."""

from __future__ import annotations

from ...i18n import _
from ..richtext import esc


def server_html(info, clean):
    """A ServerInfo as a page. clean(html): the toolkit's way to make someone's HTML
    safe to show (qt/text.clean with the theme's link colour, say)."""
    parts = [f"<h2>{esc(info.title or info.domain)}</h2>"]
    desc = info.description
    if desc:
        # HTML on GoToSocial and older Mastodon, plain text on Mastodon 4
        parts.append(clean(desc) if "<" in desc else f"<p>{esc(desc)}</p>")
    who = ", ".join(x for x in ("@" + info.contact.handle if info.contact else "",
                                info.email) if x)
    if who:
        parts.append(f"<p>{esc(_('server_contact', who=who))}</p>")
    if info.about:
        parts.append(clean(info.about))
    if info.rules:
        parts.append(f"<h3>{esc(_('server_rules'))}</h3><ol>" +
                     "".join(f"<li>{esc(text)}"
                             + (f"<br><small>{esc(hint)}</small>" if hint else "")
                             + "</li>" for text, hint in info.rules)
                     + "</ol>")
    if info.privacy:
        parts.append(f"<h3>{esc(_('server_privacy'))}</h3>" + clean(info.privacy))
    return "".join(parts)


def probe_markdown(domain, note, rows):
    """The probe's answers as a Markdown table (pasted into an issue, a chat, a note):
    the server and when it was checked (note), then a row per (feature, answer)."""
    head = f"{domain} — {note}".strip(" —")
    lines = [head, "", f"| {_('probe_what')} | {_('probe_answer')} |", "|---|---|"]
    lines += [f"| {what} | {answer} |" for what, answer in rows]
    return "\n".join(lines) + "\n"


def profile_changes(prof, name, bio, fields, flags, avatar=None, header=None):
    """What the profile editor would send: only what differs from the server (prof, a
    MyProfile), so nothing is overwritten by accident. fields: [(name, value)] as
    typed; flags: {"locked", "bot", "discoverable": bool}; avatar, header: new files."""
    me = prof.account
    out = {}
    if name != me.name:
        out["name"] = name
    if bio != prof.bio:
        out["bio"] = bio
    fields = [(n.strip(), v.strip()) for n, v in fields]
    fields = [f for f in fields if f[0] or f[1]]
    if fields != list(prof.fields):
        out["fields"] = fields
    was = {"locked": me.locked, "bot": me.bot, "discoverable": bool(me.discoverable)}
    for key, now in flags.items():
        if bool(now) != was[key]:
            out[key] = bool(now)
    if avatar:
        out["avatar"] = avatar
    if header:
        out["header"] = header
    return out
