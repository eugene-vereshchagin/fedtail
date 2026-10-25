import os as _os

# the tests and the tools that build on them never play through the speakers
# (frontends/common/sound.py): hundreds of chimes and beeps a run
_os.environ.setdefault("FEDTAIL_SOUND", "off")
# and draw a theme's pictures in their own colours, not the development version's red
# for what comes from the fallback set (frontends/iconpack.py; its own test turns it on)
_os.environ.setdefault("FEDTAIL_MARK_MISSING", "0")


def _offline():
    """A test run never reaches the internet: a name other than this machine's doesn't
    resolve (an OSError, as with no network at all). A test that forgot to stub a call
    to another server fails here instead of asking example.test for real. The tools that
    build on the tests (tools/*.py, some with your own account) are not test runs and
    keep the network; FEDTAIL_TESTS_NETWORK=1 lets a test run have it too."""
    import socket
    import sys
    main = (sys.argv[0] if sys.argv else "").replace("\\", "/")
    test_run = "unittest" in main or main.endswith("tools/coverage_lite.py")
    if not test_run or _os.environ.get("FEDTAIL_TESTS_NETWORK") == "1" or \
            getattr(socket, "_fedtail_offline", False):
        return
    import ipaddress
    real, connect = socket.getaddrinfo, socket.socket.connect
    here = {"localhost", "", None}

    def literal(h):
        try:
            return ipaddress.ip_address(h.split("%")[0])
        except (ValueError, AttributeError):
            return None

    def getaddrinfo(host, *a, **k):
        h = host.decode() if isinstance(host, bytes) else host
        if h in here or literal(h) is not None or (isinstance(h, str)
                                                   and h.endswith(".localhost")):
            return real(host, *a, **k)  # a numeric address resolves to itself
        raise OSError(f"tests are offline: {h!r} not resolved (tests/__init__.py)")

    def guarded_connect(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            ip = literal(str(address[0]))
            if ip is not None and not (ip.is_loopback or ip.is_unspecified):
                raise OSError(f"tests are offline: no connection to {address[0]}")
        return connect(sock, address)
    socket.getaddrinfo = getaddrinfo
    socket.socket.connect = guarded_connect
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy",
                "all_proxy"):  # a proxy on this machine would reach out on our behalf
        _os.environ.pop(var, None)
    socket._fedtail_offline = True


_offline()


def _qt_goes_first():
    """At a test run's end Qt's windows go while Qt is still whole, and the process ends
    right after the results: left to the interpreter's last collection, PySide's objects
    die in any order, and Python 3.12 crashed there (exit 139 after "OK", too late in the
    shutdown for faulthandler to say where). The exit code is unittest's own."""
    import atexit
    import sys
    main = (sys.argv[0] if sys.argv else "").replace("\\", "/")
    # Windows never crashed there, and ending early cost it its exit code (127)
    if "unittest" not in main or sys.platform == "win32":
        return

    def close():
        widgets = sys.modules.get("PySide6.QtWidgets")
        app = widgets.QApplication.instance() if widgets else None
        if app is None:
            return
        try:
            for w in widgets.QApplication.topLevelWidgets():
                w.close()
                w.deleteLater()
            from PySide6.QtCore import QCoreApplication, QEvent
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
        except Exception:  # noqa: BLE001 — the run is over; nothing to report it to
            pass

    real_exit = sys.exit

    def exit_now(code=0):
        # only unittest's own last word; a test's argparse error stays a SystemExit
        caller = sys._getframe(1).f_code.co_filename.replace("\\", "/")
        if not caller.endswith("unittest/main.py"):
            real_exit(code)
        close()
        atexit._run_exitfuncs()
        sys.stdout.flush()
        sys.stderr.flush()
        _os._exit(code if isinstance(code, int) else (0 if code is None else 1))

    sys.exit = exit_now


_qt_goes_first()
