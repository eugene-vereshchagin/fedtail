"""fedtail in a terminal: read lanes, follow them as they grow, post, mark read.

    fedtail lanes                        the lanes and how much is unread in each
    fedtail show comments -n 20          the newest posts of a lane
    fedtail tail comments mentions       new posts as they come (Ctrl+C to stop)
    fedtail post "text"                  a new post ("-" or nothing: the text from stdin)
    fedtail post --reply a3f "text"      a reply to #a3f
    fedtail read comments                mark a lane read
    fedtail sync status|key|join|login|now   sync with your other devices (docs/en/sync.md)

Plain Python, no Qt: works over ssh, in scripts, in pipes (colour only on a
terminal, `cli.color`). It is the same Core as the window — the same profile, the
same database, the same read marks.
"""

import argparse
import os
import queue
import shutil
import sys
import textwrap
from datetime import datetime

from ..core import config
from ..core.view import View
from ..i18n import _
from ..model import Share, real
from ..model.text import html_to_text

COMMANDS = ("lanes", "show", "tail", "post", "read", "sync")

_C = {"dim": "2", "bold": "1", "id": "36", "who": "1;34", "warn": "33", "new": "1;32"}


class Out:
    def __init__(self, cfg, stream=None):
        self.stream = stream or sys.stdout
        try:  # a Windows console in cp1252 must not fail on ✉ or Cyrillic
            self.stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
        mode = cfg.get("color", "auto")
        self.color = mode == "always" or (mode == "auto" and self.stream.isatty()
                                          and not os.environ.get("NO_COLOR"))
        self.max_lines = int(cfg.get("max_lines", 0) or 0)
        self.width = shutil.get_terminal_size((100, 20)).columns

    def c(self, kind, text):
        return f"\033[{_C[kind]}m{text}\033[0m" if self.color else text

    def line(self, text=""):
        print(text, file=self.stream, flush=True)


def _when(t):
    if t is None:
        return "?"
    dt = t.astimezone()
    return dt.strftime("%H:%M") if dt.date() == datetime.now().astimezone().date() \
        else dt.strftime("%d.%m %H:%M")


def print_post(out, core, entry, alias, unread=False):
    p = real(entry)
    head = [out.c("id", f"#{alias}") if alias else "",
            out.c("dim", _when(p.created)),
            out.c("who", "@" + (p.author.handle or "?"))]
    if isinstance(entry, Share):
        head.append(out.c("dim", "♻ @" + (entry.by.handle or "?")))
    if p.reply_to:
        head.append(out.c("dim", "↳"))
    if p.visibility == "direct":
        head.append(out.c("warn", "✉"))
    if unread:
        head.append(out.c("new", "•"))
    out.line(" ".join(h for h in head if h))
    body = []
    if p.warning:
        body.append(out.c("warn", "⚠ " + p.warning))
    if not p.warning or config.expand_cw(core.cfg):
        for para in html_to_text(p.text).split("\n"):
            body += textwrap.wrap(para, max(20, out.width - 4)) or [""]
    if p.media:
        body.append(out.c("dim", _("cli_media", n=len(p.media))))
    if out.max_lines and len(body) > out.max_lines:
        body = body[:out.max_lines] + [out.c("dim", "…")]
    for b in body:
        out.line("  " + b)
    out.line()


def _entries(core, lane, ids=None):
    entries = core.entries(lane)
    if ids is not None:
        entries = [e for e in entries if e[0] in ids]
    return entries


def _lane_name(core, name):
    """A lane by its name (an old one too: "comments"), or a list by its title
    ("Друзья" or "list:Друзья")."""
    from ..core.lanes import canonical
    name = canonical(name)
    if name in core.lane_by_name:
        return name
    title = name[5:] if name.startswith("list:") else name
    for lane in core.lane_by_name:
        if (core.lane_title(lane) or "").casefold() == title.casefold():
            return lane
    raise SystemExit(_("cli_no_lane", name=name, known=", ".join(core.lane_by_name)))


def cmd_lanes(core, out, _args):
    for name, lane in core.lane_by_name.items():
        title = core.lane_title(name) or _("lane_" + name)
        n = 0 if lane.lazy or lane.source is None else core.unread_count(name)
        count = out.c("new", str(n)) if n else out.c("dim", "0")
        out.line(f"{name:<24} {title:<28} {count}")


def cmd_show(core, out, args):
    lane = _lane_name(core, args.lane)
    if lane in {name for name, x in core.lane_by_name.items() if x.lazy}:
        core.set_active_lane(lane)
        core.poll_once()
    entries = _entries(core, lane)
    unread = core.unread(entries)
    if args.unread:
        entries = [x for x in entries if x[1].id in unread]
    entries = entries[-args.n:] if args.n else entries
    short = core.short_ids(entries)
    for _item, e in entries:
        print_post(out, core, e, short.get(real(e).id), e.id in unread)
    if args.mark_read:
        core.mark_read([e.id for _i, e in entries])


def cmd_read(core, out, args):
    lane = _lane_name(core, args.lane)
    ids = core.mark_lane_read(lane)
    out.line(_("cli_marked", n=len(ids), lane=lane))


def cmd_tail(core, out, args, stop=None):
    default = core.cfg["cli"]["tail_lanes"] or core.cfg["notify"]["lanes"]
    if "all" in default:  # notify.lanes = ["all"]: every lane but notify.except
        never = set(core.cfg["notify"].get("except") or ())
        default = [n for n in core.lane_by_name if n not in never]
    wanted = [_lane_name(core, n) for n in args.lanes] or \
        [_lane_name(core, n) for n in default if n in core.lane_by_name
         or n.startswith("list:")] or ["home"]
    got = queue.Queue()
    core.on("lanes_updated", lambda _n, per_lane: got.put(per_lane))
    if args.n:
        for lane in wanted:
            entries = _entries(core, lane)[-args.n:]
            short = core.short_ids(entries)
            for _item, e in entries:
                print_post(out, core, e, short.get(real(e).id))
    out.line(out.c("dim", _("cli_tailing", lanes=", ".join(wanted))))
    core.start_polling()
    shown = set()
    while stop is None or not stop.is_set():
        try:
            per_lane = got.get(timeout=1)
        except queue.Empty:
            continue
        for lane in wanted:
            ids = set(per_lane.get(lane) or ())
            if not ids:
                continue
            entries = [x for x in _entries(core, lane, ids) if x[1].id not in shown]
            short = core.short_ids(entries)
            for _item, e in entries:
                shown.add(e.id)
                print_post(out, core, e, short.get(real(e).id), True)
            if args.mark_read:
                core.mark_read([e.id for _i, e in entries])


def cmd_post(core, out, args, stdin=None):
    text = " ".join(args.text).strip()
    if not text or text == "-":
        text = (stdin or sys.stdin).read().strip()
    if not text:
        raise SystemExit(_("cli_empty"))
    parent = None
    if args.reply:
        alias, _sep, number = args.reply.lstrip("#").partition("/")
        parent = core.target(alias, int(number) if number.isdigit() else 0).result()
        if parent is None:
            raise SystemExit(_("cli_no_post", alias=args.reply))
    vis = VIS_ALIASES.get(args.visibility, args.visibility) or core.reply_visibility(parent)
    p = core.post(text, vis, parent, args.cw or "", language=args.lang).result()
    alias = core.short_ids([p]).get(p.id)
    out.line(_("cli_posted", alias=f"#{alias}" if alias else p.id, vis=vis, url=p.url))


def cmd_sync(core, out, args, stdin=None):
    """`fedtail sync …`: the key, the sync server's token, a round now, how it stands."""
    what = args.what
    if what == "key":
        key = core.sync_key()
        out.line(_("sync_key_show") if key else _("sync_key_none"))
        if key:
            out.line(key)
        return
    if what == "join":
        try:
            kid = core.sync_join(args.arg or (stdin or sys.stdin).readline())
        except ValueError:
            raise SystemExit(_("sync_join_bad")) from None
        out.line(_("sync_join_ok", kid=kid))
        return
    if what in ("keep", "unlock"):  # the key in the journal under a password, and back
        import getpass

        from ..core.sync import crypto
        password = args.arg or getpass.getpass(_("sync_password") + ": ")
        try:
            if what == "keep":
                if len(password) < 8:
                    raise SystemExit(_("sync_password_short", n=8))
                if not args.arg and getpass.getpass(_("sync_password_again") + ": ") != password:
                    raise SystemExit(_("sync_password_differ"))
                core.sync_put_escrow(password)
                out.line(_("sync_escrow_done"))
            else:
                out.line(_("sync_join_ok", kid=core.sync_take_escrow(password)))
        except crypto.BadBlob:
            raise SystemExit(_("sync_password_wrong")) from None
        except ValueError:
            raise SystemExit(_("sync_join_bad")) from None
        except RuntimeError as e:
            raise SystemExit(str(e)) from None
        return
    if what == "login":
        if not core.logged_in:
            raise SystemExit(_("cli_login_first"))
        pending = core.sync_login_begin()
        out.line(_("sync_login_open", url=pending["url"]))
        print(_("sync_login_code"), end="", file=out.stream, flush=True)
        code = args.arg or (stdin or sys.stdin).readline()
        core.sync_login_end(pending, code)
        out.line(_("sync_login_ok", instance=pending["instance"]))
        return
    if core.sync_status() is None:
        raise SystemExit(_("sync_off"))
    if what == "now":
        if core.logged_in:
            core.connect().result()  # a thread's state from elsewhere asks the server
        done = core.sync_now()
        out.line(_("sync_round", sent=done[0], got=done[1]) if done
                 else _("sync_round_failed"))
    st = core.sync_status()
    last = st["last"]
    shown = " ".join(x for x in (last.get("at", ""), last.get("error", "")) if x)
    nothing = _("sync_nothing")
    out.line(_("sync_status", backend=st["backend"], where=st["where"] or nothing,
               login=st["login"] or nothing, device=st["device"], kid=st["key"] or nothing,
               pending=st["pending"], last=shown or nothing))


VIS_ALIASES = {"private": "followers"}  # the Mastodon word still works


def parser():
    p = argparse.ArgumentParser(prog="fedtail", add_help=True)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser("lanes", help="lanes and unread counts")
    s = sub.add_parser("show", help="the newest posts of a lane")
    s.add_argument("lane")
    s.add_argument("-n", type=int, default=20, help="how many (0: all stored)")
    s.add_argument("--unread", action="store_true", help="only the unread ones")
    s.add_argument("--mark-read", action="store_true", help="mark what was shown read")
    t = sub.add_parser("tail", help="new posts as they come")
    t.add_argument("lanes", nargs="*", help="lanes (default: those in notify.lanes)")
    t.add_argument("-n", type=int, default=0, help="first show the last N of each")
    t.add_argument("--mark-read", action="store_true", help="mark what was shown read")
    r = sub.add_parser("read", help="mark a lane read")
    r.add_argument("lane")
    w = sub.add_parser("post", help="a new post or a reply")
    w.add_argument("text", nargs="*", help='the text; "-" or none: from stdin')
    w.add_argument("--reply", help="the post to answer: a3f, #a3f or #a3f/2")
    w.add_argument("-v", "--visibility",
                   choices=["public", "unlisted", "followers", "private", "direct"],
                   help="who sees it (private = followers)")
    w.add_argument("--cw", help="content warning")
    w.add_argument("--lang", help="language code (ru, en, ka…)")
    y = sub.add_parser("sync", help="sync with your other devices")
    y.add_argument("what", choices=["status", "key", "join", "login", "now", "keep", "unlock"])
    y.add_argument("arg", nargs="?", help="join: the key; login: the code; keep / unlock: "
                                          "the password (else asked)")
    return p


def run(core, argv, stream=None):
    """argv: the command and its arguments ("show", "replies", "-n", "5")."""
    args = parser().parse_args(argv)
    core = core if isinstance(core, View) else View(core)
    out = Out(core.cfg.get("cli", {}), stream)
    if args.command == "sync":  # some of it works before logging in, none needs a poll
        try:
            cmd_sync(core, out, args)
        finally:
            core.shutdown()
        return 0
    if not core.logged_in:
        raise SystemExit(_("cli_login_first"))
    core.connect().result()
    if args.command in ("lanes", "show", "read", "tail"):
        core.poll_once()
    try:
        {"lanes": cmd_lanes, "show": cmd_show, "tail": cmd_tail, "post": cmd_post,
         "read": cmd_read}[args.command](core, out, args)
    except KeyboardInterrupt:
        pass
    finally:
        core.shutdown()
    return 0
