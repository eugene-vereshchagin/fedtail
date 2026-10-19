"""Debug → Federation status: Core.federation_status() as a page (HTML for the window,
plain text for the clipboard and bug reports). No Qt here.

What it is for: the problems that don't depend on the client — a server that hasn't got
something, a post deleted at its home, a server that won't answer strangers, a follow
request nobody answered — counted, grouped, with a word on what each means.
"""

import time

from ..i18n import _
from .richtext import esc

SHOW_HOSTS = 15
SHOW_PROBLEMS = 40


def ago(t, now):
    if not t:
        return "—"
    s = max(0, int(now - t))
    if s < 90:
        return _("fed_ago_s", n=s)
    if s < 5400:
        return _("fed_ago_m", n=round(s / 60))
    if s < 172800:
        return _("fed_ago_h", n=round(s / 3600))
    return _("fed_ago_d", n=round(s / 86400))


def hint(p):
    """What a failure most likely means — the cause is mostly not on this computer."""
    o, path, mine = p["outcome"], p["path"], p["kind"] == "mine"
    if isinstance(o, str):
        if o.startswith("refused"):
            return _("fed_hint_refused")
        if o == "timeout":
            return _("fed_hint_timeout_mine" if mine else "fed_hint_timeout")
        if o == "no connection":
            return _("fed_hint_noconn_mine" if mine else "fed_hint_noconn")
        if o == "TLS error":
            return _("fed_hint_tls")
        return ""
    if mine:
        if o == 404 and "/lists/" in path and path.endswith("/accounts"):
            return _("fed_hint_list_not_followed")
        if o in (404, 405, 501) and not any(x in path for x in ("/statuses/:id",
                                                               "/accounts/:id")):
            return _("fed_hint_missing")
        if o == 404:
            return _("fed_hint_gone_mine")
        if o in (401, 403):
            return _("fed_hint_auth_mine")
        if o == 422:
            return _("fed_hint_refused_by_server")
    if o in (404, 410):
        return _("fed_hint_gone")
    if o in (401, 403):
        return _("fed_hint_auth")
    if o == 429:
        return _("fed_hint_rate")
    if o in (502, 503, 504, 520, 521, 522, 523, 524):
        return _("fed_hint_down_mine" if mine else "fed_hint_down")
    if o >= 500:
        return _("fed_hint_server_error")
    return ""


def _ms(v):
    return "—" if v is None else f"{v} ms"


def _mine(data):
    hosts = [h for h in data["hosts"] if h["kind"] == "mine"]
    return hosts[0] if hosts else None


def facts(data, now=None):
    """[(label, value)] about my server: what it runs, how it answers, polls, stream."""
    now = now or time.time()
    out = [(_("fed_server"), data["server"] or "—")]
    if data.get("version") or data.get("software"):
        out.append((_("fed_software"), data.get("version") or data.get("software")))
    if data.get("me"):
        out.append((_("fed_me"), "@" + data["me"]))
    h = _mine(data)
    if h:
        out.append((_("fed_answers"), _("fed_answers_v", n=h["answers"], bad=h["failures"],
                                         median=_ms(h["median_ms"]), p95=_ms(h["p95_ms"]))))
    p = data["polls"]
    poll = _("fed_polls_v", n=p["count"], every=p["interval_s"], last=ago(p["last_ok"], now),
             took=p["last_s"] if p["last_s"] is not None else "—")
    if p["failures"]:
        poll += " · " + _("fed_polls_failed", n=p["failures"], last=p["last_error"])
    out.append((_("fed_polls"), poll))
    s = data.get("stream")
    if s is None:
        out.append((_("fed_stream"), _("fed_stream_off", mode=data.get("stream_mode", ""))))
    else:
        v = _("fed_stream_open", since=ago(s["since"], now)) if s["open"] else \
            _("fed_stream_down")
        if s["last_event"]:
            v += " · " + _("fed_stream_event", when=ago(s["last_event"], now))
        if s["drops"]:
            v += " · " + _("fed_stream_drops", n=s["drops"], why=s["last_error"])
        out.append((_("fed_stream"), v))
    out.append((_("fed_since"), ago(data["since"], now)))
    return out


def _table(head, rows):
    cells = "".join(f"<th align=left>{esc(h)}</th>" for h in head)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return f"<table cellspacing=0 cellpadding=3 width=100%><tr>{cells}</tr>{body}</table>"


def html(data, now=None):
    now = now or time.time()
    parts = [f"<h3>{esc(_('fed_mine'))}</h3>",
             _table(("", ""), [(f"<b>{esc(k)}</b>", esc(str(v))) for k, v in facts(data, now)])]
    if data["unsupported"]:
        parts += [f"<h3>{esc(_('fed_unsupported'))}</h3>",
                  f"<p>{esc(', '.join(data['unsupported']))}</p>"]
    if data["list_waiting"]:
        parts += [f"<h3>{esc(_('fed_waiting'))}</h3>",
                  _table((_("fed_col_who"), _("fed_col_list"), _("fed_col_since")),
                         [(esc("@" + w["account"]), esc(w["list"]), esc(ago(w["since"], now)))
                          for w in data["list_waiting"]])]
    for kind, title in (("mine", "fed_problems_mine"), ("remote", "fed_problems_remote")):
        rows = [p for p in data["problems"] if p["kind"] == kind][:SHOW_PROBLEMS]
        parts.append(f"<h3>{esc(_(title))}</h3>")
        if not rows:
            parts.append(f"<p>{esc(_('fed_none'))}</p>")
            continue
        parts.append(_table(
            (_("fed_col_n"),) + ((_("fed_col_host"),) if kind == "remote" else ()) +
            (_("fed_col_what"), _("fed_col_answer"), _("fed_col_last"), _("fed_col_means")),
            [(str(p["count"]),) + ((esc(p["host"]),) if kind == "remote" else ()) +
             (f"<code>{esc(p['method'])} {esc(p['path'])}</code>", esc(str(p["outcome"])),
              esc(ago(p["last"], now)), esc(hint(p)))
             for p in rows]))
    remote = [h for h in data["hosts"] if h["kind"] == "remote"]
    if remote:
        remote.sort(key=lambda h: (-h["failures"], -h["answers"]))
        parts += [f"<h3>{esc(_('fed_hosts'))}</h3>",
                  _table((_("fed_col_host"), _("fed_col_answers"), _("fed_col_failed"),
                          _("fed_col_median")),
                         [(esc(h["host"]), str(h["answers"]), str(h["failures"]),
                           esc(_ms(h["median_ms"]))) for h in remote[:SHOW_HOSTS]])]
    parts.append(f"<p><i>{esc(_('fed_note'))}</i></p>")
    return "".join(parts)


def text(data, now=None):
    """The same as plain text: to paste into a message or an issue."""
    now = now or time.time()
    lines = [f"== {_('fed_mine')}"] + [f"{k}: {v}" for k, v in facts(data, now)]
    if data["unsupported"]:
        lines += ["", f"== {_('fed_unsupported')}", ", ".join(data["unsupported"])]
    if data["list_waiting"]:
        lines += ["", f"== {_('fed_waiting')}"] + [
            f"@{w['account']} → {w['list']} ({ago(w['since'], now)})"
            for w in data["list_waiting"]]
    for kind, title in (("mine", "fed_problems_mine"), ("remote", "fed_problems_remote")):
        rows = [p for p in data["problems"] if p["kind"] == kind][:SHOW_PROBLEMS]
        lines += ["", f"== {_(title)}"]
        lines += [f"{p['count']:>5}  " + (f"{p['host']}  " if kind == "remote" else "") +
                  f"{p['method']} {p['path']} -> {p['outcome']}  ({ago(p['last'], now)})"
                  + (f"  — {hint(p)}" if hint(p) else "") for p in rows] or [_("fed_none")]
    return "\n".join(lines) + "\n"
