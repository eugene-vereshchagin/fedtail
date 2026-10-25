"""The web interface: `fedtail --ui web` (or ui.frontend = "web") — fedtail in a
browser tab, on this computer or (web.host) a phone at home.

Standard library only. The link with the key is printed at start (and opened in
the browser, web.open_browser); the page keeps the key in a cookie."""

import logging
import signal
import sys
import threading
import webbrowser

from ...i18n import _

log = logging.getLogger(__name__)


def run(core, instance, argv):
    from .server import load_key, make_server
    wcfg = core.cfg["web"]
    if not core.logged_in:
        print("fedtail: " + _("cli_login_first"), file=sys.stderr)
        return 1
    core.connect().result()
    key = load_key(core.paths.data_dir)
    srv = make_server(core, wcfg["host"], wcfg["port"], key)
    srv.web.instance = instance  # given over when the page switches accounts
    host, port = srv.server_address[:2]
    shown = "127.0.0.1" if host in ("0.0.0.0", "") else host
    base = f"http://{shown}:{port}"
    # a one-time link, good for a quarter of an hour: the key itself stays in the cookie
    # and out of the browser's history, the terminal and journald
    url = srv.web.login_link(base)
    print("fedtail: " + _("web_open", url=url), flush=True)
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("fedtail: " + _("web_lan", host=host), flush=True)
    log.info("web: listening on %s:%s", host, port)
    if instance is not None:  # started again: a fresh link, opened here
        instance.listen(lambda _m: webbrowser.open(srv.web.login_link(base)))
    core.start_polling()
    if wcfg["open_browser"]:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_a: stop.set())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *_a: stop.set())
    t = threading.Thread(target=srv.serve_forever, name="fedtail-web", daemon=True)
    t.start()
    try:
        while not stop.wait(0.5):
            pass
    finally:
        srv.shutdown()
        srv.server_close()
        srv.web.core.shutdown()  # the account the page ended on (it may have switched)
        if srv.web.instance is not instance and srv.web.instance is not None:
            srv.web.instance.close()
    return 0
