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


PROBE_MARKS = {"yes": "✓", "no": "✗", "closed": "🔒", "error": "⚠", "self": "◐", "info": "·"}
_PROBE_ORDER = {"no": 0, "closed": 1, "error": 2, "self": 3, "yes": 4, "info": 5}


def _has(key):
    return _(key) != key


def probe_rows(probe, date):
    """A Probe as the window shows it: (the line on top — when, what software —, and
    [(feature, "✓ answer", known)] the worst first). date(datetime) -> text; known:
    the answer is what fedtail knows of such servers, not asked."""
    if probe is None:
        return _("probe_never"), []
    when = date(probe.checked) if probe.checked else "?"
    note = _("probe_checked", when=when,
             software=" ".join(x for x in (probe.software, probe.version) if x))
    rows = []
    for f in sorted(probe.features, key=lambda f: _PROBE_ORDER.get(f.state, 9)):
        answer = f.detail if f.state == "info" else \
            _("probe_" + f.state) + (f" ({f.detail})" if f.detail and f.detail != "known"
                                     else "")
        what = _("probe_" + f.key) if _has("probe_" + f.key) else f.key
        rows.append((what, f"{PROBE_MARKS.get(f.state, '?')} {answer}", f.detail == "known"))
    return note, rows


def server_more_html(info, clean):
    """What the newer servers say on top (Mastodon 4.3–4.4): the terms, the servers it
    cut off, what its translator can do — after common/server.py's page."""
    from html import escape as esc
    parts = []
    if info.terms:
        parts.append(f"<h3>{esc(_('server_terms'))}</h3>" + clean(info.terms))
    parts.append(f"<h3>{esc(_('server_blocks'))}</h3>")
    if info.blocks:
        words = {"suspend": _("server_block_suspend"), "silence": _("server_block_silence")}
        parts.append("<ul>" + "".join(
            f"<li>{esc(domain)} — {esc(words.get(sev, sev))}"
            + (f"<br><small>{esc(why)}</small>" if why else "") + "</li>"
            for domain, sev, why in info.blocks) + "</ul>")
    else:
        parts.append(f"<p>{esc(_('server_blocks_none'))}</p>")
    langs = "; ".join(f"{src} → {', '.join(into)}" for src, into in info.translates if into)
    parts.append("<p>" + esc(_("server_translates", langs=langs) if langs
                             else _("server_translates_none")) + "</p>")
    return "".join(parts)


def flag_changes(prof, hide_collections, indexable, attribution):
    """The newer switches of a profile (Mastodon 4.x) that differ from the server's:
    whom I follow hidden, my posts found by words, sites naming me their author
    (attribution: as typed, comma-separated)."""
    out = {}
    for key, now in (("hide_collections", hide_collections), ("indexable", indexable)):
        was = getattr(prof, key, None)
        if was is not None and bool(now) != bool(was) or was is None and now:
            out[key] = bool(now)
    sites = [x.strip() for x in attribution.replace(";", ",").split(",") if x.strip()]
    if sites != list(getattr(prof, "attribution_domains", ()) or ()):
        out["attribution_domains"] = sites
    return out
