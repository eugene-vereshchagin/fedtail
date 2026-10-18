"""fedtail in a terminal: read lanes, follow them as they grow, post, mark read.

    fedtail lanes                        the lanes and how much is unread in each
    fedtail show comments -n 20          the newest posts of a lane
    fedtail tail comments mentions       new posts as they come (Ctrl+C to stop)
    fedtail post "text"                  a new post ("-" or nothing: the text from stdin)
    fedtail post --reply a3f "text"      a reply to #a3f
    fedtail read comments                mark a lane read

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
from ..core.model import html_to_text, real
from ..i18n import _

COMMANDS = ("lanes", "show", "tail", "post", "read")

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


def _when(iso):
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except (ValueError, AttributeError):
        return "?"
    return dt.strftime("%H:%M") if dt.date() == datetime.now().astimezone().date() \
        else dt.strftime("%d.%m %H:%M")


def print_post(out, core, wrapper, alias, unread=False):
    st = real(wrapper)
    acc = st["account"]
    head = [out.c("id", f"#{alias}") if alias else "",
            out.c("dim", _when(st.get("created_at", ""))),
            out.c("who", "@" + acc.get("acct", "?"))]
    if wrapper.get("reblog"):
        head.append(out.c("dim", "♻ @" + wrapper["account"].get("acct", "?")))
    if st.get("in_reply_to_id"):
        head.append(out.c("dim", "↳"))
    if st.get("visibility") == "direct":
        head.append(out.c("warn", "✉"))
    if unread:
        head.append(out.c("new", "•"))
    out.line(" ".join(h for h in head if h))
    body = []
    if st.get("spoiler_text"):
        body.append(out.c("warn", "⚠ " + st["spoiler_text"]))
    if not st.get("spoiler_text") or config.expand_cw(core.cfg):
        text = html_to_text(st.get("content", ""))
        for para in text.split("\n"):
            body += textwrap.wrap(para, max(20, out.width - 4)) or [""]
    n = len(st.get("media_attachments") or [])
    if n:
        body.append(out.c("dim", _("cli_media", n=n)))
    if out.max_lines and len(body) > out.max_lines:
        body = body[:out.max_lines] + [out.c("dim", "…")]
    for b in body:
        out.line("  " + b)
    out.line()


def _entries(core, lane, ids=None):
    entries = core.lane_entries(lane)
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
    unread = core.unread_ids(entries)
    if args.unread:
        entries = [e for e in entries if e[1]["id"] in unread]
    entries = entries[-args.n:] if args.n else entries
    short = core.short_ids([st for _i, st in entries])
    for _item, st in entries:
        print_post(out, core, st, short.get(real(st)["id"]), st["id"] in unread)
    if args.mark_read:
        core.mark_read([st["id"] for _i, st in entries])


def cmd_read(core, out, args):
    lane = _lane_name(core, args.lane)
    entries = _entries(core, lane)
    ids = sorted(core.unread_ids(entries))
    core.mark_read(ids)
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
    core.events.on("lanes_updated", lambda _n, per_lane: got.put(per_lane))
    if args.n:
        for lane in wanted:
            entries = _entries(core, lane)[-args.n:]
            short = core.short_ids([st for _i, st in entries])
            for _item, st in entries:
                print_post(out, core, st, short.get(real(st)["id"]))
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
            entries = [e for e in _entries(core, lane, ids) if e[1]["id"] not in shown]
            short = core.short_ids([st for _i, st in entries])
            for _item, st in entries:
                shown.add(st["id"])
                print_post(out, core, st, short.get(real(st)["id"]), True)
            if args.mark_read:
                core.mark_read([st["id"] for _i, st in entries])


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
    vis = args.visibility or core.reply_visibility(parent)
    st = core.post(text, vis, real(parent)["id"] if parent else None, args.cw or "",
                   language=args.lang).result()
    alias = core.short_ids([st]).get(st["id"])
    out.line(_("cli_posted", alias=f"#{alias}" if alias else st["id"], vis=vis,
               url=st.get("url") or ""))


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
    w.add_argument("-v", "--visibility", choices=["public", "unlisted", "private", "direct"])
    w.add_argument("--cw", help="content warning")
    w.add_argument("--lang", help="language code (ru, en, ka…)")
    return p


def run(core, argv, stream=None):
    """argv: the command and its arguments ("show", "replies", "-n", "5")."""
    args = parser().parse_args(argv)
    out = Out(core.cfg.get("cli", {}), stream)
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
