"""Terminal interface (Textual): `fedtail --ui tui`, or ui.frontend = "tui".

Over ssh, in a console without a desktop: the same lanes, threads, read marks and
command line as the window, in text."""


import logging
import os
import sys

log = logging.getLogger(__name__)


def run(core, instance, argv):
    from . import pictures
    # textual-image asks the terminal what it can show: only before Textual takes it
    pictures.prepare(pictures.mode(core.cfg))
    from .app import FedtailApp
    app = FedtailApp(core, instance)
    try:
        app.run()
        code = app.return_code or 0
    finally:
        core.shutdown()
    name = getattr(app, "relaunch", None)
    if name:
        relaunch(name, instance)
    return code


def relaunch(name, instance=None):
    """Another account (Accounts → Open, a login done, a logout): fedtail started anew
    with that profile, in this same terminal — the process replaced, not a second one
    beside it. A whole new start rather than a core swapped in place: every screen,
    picture worker and notifier of the terminal is the old account's, and a start is
    what makes them all right (as a window opens the other profile in a window of its
    own). The terminal is the user's again by now (Textual has given it back)."""
    from ...core import profiles
    argv, cwd = profiles.command(name)
    argv = argv + ["--ui", "tui"] + list(profiles.RUN_FLAGS)
    if instance is not None:
        instance.close()  # this profile's lock: free before the process is replaced
    log.info("tui: switching to profile %s: %s", name, argv)
    sys.stdout.flush()
    sys.stderr.flush()
    if cwd:
        os.chdir(cwd)
    os.execv(argv[0], argv)
