"""Terminal interface (Textual): `fedtail --ui tui`, or ui.frontend = "tui".

Over ssh, in a console without a desktop: the same lanes, threads, read marks and
command line as the window, in text."""


def run(core, instance, argv):
    from .app import FedtailApp
    app = FedtailApp(core, instance)
    try:
        app.run()
        return app.return_code or 0
    finally:
        core.shutdown()
