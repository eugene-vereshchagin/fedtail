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

from . import __version__, frontends, i18n  # noqa: E402
from .core import config, config_update, paths  # noqa: E402
from .core.app import Core  # noqa: E402
from .core.instance import SingleInstance  # noqa: E402


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
                   help="add options your config doesn't mention yet (commented out, "
                        "with explanations; a .bak copy is kept) and exit")
    p.add_argument("--install-desktop", action="store_true",
                   help="add fedtail (this profile) to the desktop menu, with its icon, and exit")
    p.add_argument("--debug", action="store_true", help="verbose log to stderr")
    p.add_argument("-V", "--version", action="version", version=f"fedtail {__version__}")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
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
    if args.update_config:
        if not new_options:
            print(f"fedtail: {where.config_file} already lists every option.")
            return 0
        where.config_file.with_name(where.config_file.name + ".bak").write_text(user_text,
                                                                                 "utf-8")
        where.config_file.write_text(config_update.update(user_text, example), "utf-8")
        print(f"fedtail: added to {where.config_file} (commented out):\n  " +
              "\n  ".join(new_options))
        return 0
    if new_options:
        print(f"fedtail: your config doesn't mention {len(new_options)} option(s): "
              f"{', '.join(new_options)}.\n  Run `python3 -m fedtail --update-config` to add them "
              f"(commented out), or see {ref}", file=sys.stderr)

    i18n.setup(cfg["ui"]["language"])

    instance = SingleInstance(where.socket_file)
    if instance.poke_existing():
        print(f"fedtail: profile '{where.profile}' is already running — brought it to front.",
              file=sys.stderr)
        return 0

    frontend = frontends.load(args.ui or cfg["ui"]["frontend"])
    core = Core(cfg, where)
    core.new_options = new_options
    try:
        return frontend.run(core, instance, sys.argv[:1])
    finally:
        instance.close()


if __name__ == "__main__":
    sys.exit(main())
