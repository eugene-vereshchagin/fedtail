"""fedtail entry point:  python3 -m fedtail [--profile NAME] …"""

import argparse
import logging
import os
import sys

if not __package__:
    # started as `python3 fedtail` (the folder) instead of `python3 -m fedtail`
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from fedtail.__main__ import main

    sys.exit(main())

from . import frontends, i18n, version  # noqa: E402
from .core import config, config_update, paths  # noqa: E402
from .core.app import Core  # noqa: E402
from .core.instance import SingleInstance  # noqa: E402
from .frontends import cli  # noqa: E402


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="fedtail",
        description="Desktop fediverse client. One profile = one account = one window.")
    p.add_argument("-p", "--profile", help="profile name (default: %(default)s)",
                   default=paths.DEFAULT_PROFILE)
    p.add_argument("-c", "--config", help="config file (overrides the profile's one)")
    p.add_argument("-d", "--data", help="data directory (overrides the profile's one)")
    p.add_argument("--ui", choices=sorted(frontends.FRONTENDS), help="frontend to use")
    p.add_argument("--update-config", action="store_true",
                   help="add options your config doesn't mention yet (with explanations; "
                        "a .bak copy is kept) and exit")
    p.add_argument("--rebuild-config", action="store_true",
                   help="write your config anew, in the chapters of this version, with your "
                        "values in place (your own comments are dropped; a .bak copy is "
                        "kept) and exit")
    p.add_argument("--profiles", action="store_true",
                   help="list the profiles (accounts) there are and exit")
    p.add_argument("--install-desktop", action="store_true",
                   help="add fedtail (this profile) to the desktop menu, with its icon, and exit")
    p.add_argument("--debug", action="store_true",
                   help="also print the full log to the terminal (the log file is always kept)")
    p.add_argument("--bug-report", action="store_true",
                   help="pack logs, crash traces and system info into an archive in your home "
                        "folder (no token, no database) and exit")
    p.add_argument("-V", "--version", action="version", version=f"fedtail {version.full()}")
    p.add_argument("command", nargs="?", choices=(*cli.COMMANDS, "open"), metavar="COMMAND",
                   help="work in the terminal instead of opening the window: "
                        + ", ".join(cli.COMMANDS) + " (`fedtail COMMAND -h` for each)")
    p.add_argument("rest", nargs=argparse.REMAINDER, help=argparse.SUPPRESS)
    p.epilog = ("terminal: fedtail lanes | show LANE [-n N] [--unread] | tail [LANE…] | "
                "read LANE | post [--reply ALIAS] [-v VIS] [--cw TEXT] TEXT|-")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.profiles:
        from .core import profiles
        for prof in profiles.listing():
            state = "" if prof["logged_in"] else "  (not logged in)"
            print(f"{prof['name']:<16} {profiles.label(prof)}{state}")
        return 0
    if args.install_desktop:
        from .desktop import install
        entry, icon = install(args.profile)
        print(f"fedtail: menu entry {entry}\nfedtail: icon {icon}")
        return 0
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.WARNING,
                        format="fedtail: %(levelname)s %(name)s: %(message)s")
    try:
        where = paths.resolve(args.profile, args.config, args.data)
        where.ensure()
        cfg, warnings = config.load(where.config_file)
    except ValueError as e:
        print(f"fedtail: {e}", file=sys.stderr)
        return 2
    except config.ConfigError as e:
        print(f"fedtail: config error in {where.config_file}:\n{e}", file=sys.stderr)
        return 2
    for w in warnings:
        print(f"fedtail: {where.config_file}: {w}", file=sys.stderr)

    # the full reference for this version always sits next to the user's config
    example = config.example_text()
    ref = where.config_file.with_name("config.example.toml")
    try:
        if not ref.exists() or ref.read_text("utf-8") != example:
            ref.write_text(example, "utf-8")
    except OSError:
        pass
    user_text = where.config_file.read_text("utf-8")
    new_options = config_update.missing(user_text, example)
    if args.rebuild_config:
        report = {}
        new_text = config_update.rebuild(user_text, example, report)
        where.config_file.with_name(where.config_file.name + ".bak").write_text(user_text,
                                                                                 "utf-8")
        where.config_file.write_text(new_text, "utf-8")
        print(f"fedtail: rebuilt {where.config_file} (the old one is config.toml.bak)")
        if report["kept"]:
            print("  your values:\n    " + "\n    ".join(report["kept"]))
        if report["extra"]:
            print("  kept, though this version doesn't know them:\n    "
                  + "\n    ".join(report["extra"]))
        return 0
    if args.update_config:
        report = {}
        new_text = config_update.update(user_text, example, report)
        if new_text == user_text:
            print(f"fedtail: {where.config_file} is up to date.")
            return 0
        where.config_file.with_name(where.config_file.name + ".bak").write_text(user_text,
                                                                                 "utf-8")
        where.config_file.write_text(new_text, "utf-8")
        print(f"fedtail: updated {where.config_file} (the old one is config.toml.bak)")
        for what, keys in (("added", report["added"]),
                           ("explanation refreshed", report["refreshed"]),
                           ("dropped (no longer exists, was commented out)",
                            report["dropped"])):
            if keys:
                print(f"  {what}:\n    " + "\n    ".join(keys))
        return 0
    if new_options:
        print(f"fedtail: your config doesn't mention {len(new_options)} option(s): "
              f"{', '.join(new_options)}.\n  Run `python3 -m fedtail --update-config` to add them "
              f"(or --rebuild-config to lay the file out anew), or see {ref}", file=sys.stderr)

    if args.bug_report:
        from . import diag
        out = diag.bug_report(where, cfg=cfg)
        print(f"fedtail: report {out}\n  Send this file. It has the logs and the config, "
              f"no token and no database.")
        return 0

    i18n.setup(cfg["ui"]["language"])

    open_url = None
    if args.command == "open":  # `fedtail open URL`: in the window, running or not
        if not args.rest:
            print("fedtail: open what? fedtail open https://server/@someone/123",
                  file=sys.stderr)
            return 2
        open_url = args.rest[0]
    elif args.command:
        return _terminal(args, cfg, where)

    instance = SingleInstance(where.socket_file)
    if open_url and instance.poke_existing("open " + open_url):
        print(f"fedtail: opened in the running '{where.profile}'.", file=sys.stderr)
        return 0
    if instance.poke_existing():
        print(f"fedtail: profile '{where.profile}' is already running — brought it to front.",
              file=sys.stderr)
        return 0

    from . import diag
    folder = diag.setup(where, cfg, console_debug=args.debug)
    diag.session_header(where.profile, {"logs": str(folder)})
    diag.start_stats(cfg)

    ui = args.ui or cfg["ui"]["frontend"]
    frontend = frontends.load(ui)
    if ui == "tui":
        diag.quiet_console()
    core = Core(cfg, where)
    core.new_options = new_options
    core.open_at_start = open_url  # `fedtail open URL` with no window yet: once it's up
    core, held = merge_accounts(core, where.profile)
    try:
        code = frontend.run(core, instance, sys.argv[:1])
    finally:
        instance.close()
        for other in held:
            other.close()
    return _leave(code)


def _terminal(args, cfg, where):
    """`fedtail show comments`: no window, no single-instance lock (the window of the
    same profile may well be open: they share the database and the read marks)."""
    if not cfg["cli"]["enabled"]:
        print("fedtail: terminal commands are off (cli.enabled = false)", file=sys.stderr)
        return 2
    from . import diag
    diag.setup(where, cfg, console_debug=args.debug)
    diag.session_header(where.profile, {"cli": args.command})
    core = Core(cfg, where)
    try:
        code = cli.run(core, [args.command, *args.rest])
    except SystemExit as e:
        if isinstance(e.code, str):
            print(f"fedtail: {e.code}", file=sys.stderr)
            code = 1
        else:
            code = e.code or 0
    except KeyboardInterrupt:
        code = 130
    return _leave(code)


def _leave(code):
    """Exit now. Workers still waiting on the network (a picture's original may take
    two minutes) would otherwise keep the process alive after the window is gone:
    their results are not needed any more, and everything worth keeping is saved."""
    import os
    import threading
    log = logging.getLogger("fedtail")
    busy = [t.name for t in threading.enumerate()
            if t is not threading.current_thread() and not t.daemon and t.is_alive()]
    if busy:
        log.info("exit: not waiting for %s", ", ".join(sorted(busy)))
    log.info("==== session end, exit code %s", code)
    logging.shutdown()
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(code or 0)


def merge_accounts(core, me):
    """ui.merge (or the window's "All accounts in one window"): the other profiles'
    Cores join this one behind a MergedCore. A profile already running in its own
    window stays there. Returns (the core to use, the instance locks held)."""
    from .core import profiles
    log = logging.getLogger("fedtail")
    want = core.cfg["ui"]["merge"] or core.get_state("merge") or []
    if not want:
        return core, []
    names = [p["name"] for p in profiles.listing() if p["logged_in"] and p["name"] != me] \
        if "all" in want else [n for n in want if n != me]
    others, held = {}, []
    for name in names:
        try:
            where = paths.resolve(name)
            cfg, _warn = config.load(where.config_file)
        except (ValueError, config.ConfigError) as e:
            log.warning("merge: profile %s skipped: %s", name, e)
            continue
        lock = SingleInstance(where.socket_file)
        if lock.poke_existing():
            log.warning("merge: profile %s runs in its own window, not merged", name)
            continue
        lock.listen(lambda _m: None)
        held.append(lock)
        others[name] = Core(cfg, where)
    if not others:
        return core, held
    from .core.merged import MergedCore
    log.info("merged window: %s + %s", me, ", ".join(others))
    return MergedCore(core, others), held


if __name__ == "__main__":
    sys.exit(main())
