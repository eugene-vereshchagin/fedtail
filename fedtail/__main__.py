"""fedtail entry point:  python3 -m fedtail [--profile NAME] …"""

import argparse
import logging
import sys

from . import __version__, frontends, i18n
from .core import config, paths
from .core.app import Core
from .core.instance import SingleInstance


def parse_args(argv):
    p = argparse.ArgumentParser(
        prog="fedtail",
        description="Desktop fediverse client. One profile = one account = one window.")
    p.add_argument("-p", "--profile", help="profile name (default: %(default)s)",
                   default=paths.DEFAULT_PROFILE)
    p.add_argument("-c", "--config", help="config file (overrides the profile's one)")
    p.add_argument("-d", "--data", help="data directory (overrides the profile's one)")
    p.add_argument("--ui", choices=sorted(frontends.FRONTENDS), help="frontend to use")
    p.add_argument("--debug", action="store_true", help="verbose log to stderr")
    p.add_argument("-V", "--version", action="version", version=f"fedtail {__version__}")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
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

    i18n.setup(cfg["ui"]["language"])

    instance = SingleInstance(where.socket_file)
    if instance.poke_existing():
        print(f"fedtail: profile '{where.profile}' is already running — brought it to front.",
              file=sys.stderr)
        return 0

    frontend = frontends.load(args.ui or cfg["ui"]["frontend"])
    core = Core(cfg, where)
    try:
        return frontend.run(core, instance, sys.argv[:1])
    finally:
        instance.close()


if __name__ == "__main__":
    sys.exit(main())
