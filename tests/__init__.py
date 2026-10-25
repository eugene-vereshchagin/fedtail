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


def _end_with_the_results():
    """A test run ends right after its results, with unittest's exit code: left to the
    interpreter's last collection, PySide's objects die in any order and Python crashed
    there now and then (exit 139 after "OK": 3.12, too late for faulthandler to say
    where; closing Qt's windows by hand first crashed 3.13 the same way). Nothing of the
    run is lost: the results are written and flushed before."""
    import sys
    main = (sys.argv[0] if sys.argv else "").replace("\\", "/")
    if "unittest" not in main:
        return
    real_exit = sys.exit

    def exit_now(code=0):
        # only unittest's own last word; a test's argparse error stays a SystemExit
        caller = sys._getframe(1).f_code.co_filename.replace("\\", "/")
        if not caller.endswith("unittest/main.py"):
            real_exit(code)
        sys.stdout.flush()
        sys.stderr.flush()
        code = code if isinstance(code, int) else (0 if code is None else 1)
        if sys.platform == "win32":
            # Windows crashed later still, unloading Qt's DLLs (exit 127 after "OK", with
            # _exit too): TerminateProcess skips that as well. Not os.kill: its 0 and 1
            # are Ctrl+C and Ctrl+Break to the whole console (the pipe's tee too)
            import ctypes
            from ctypes import wintypes
            k32 = ctypes.windll.kernel32
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            k32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
            k32.TerminateProcess(k32.GetCurrentProcess(), code)
        _os._exit(code)

    sys.exit = exit_now


_end_with_the_results()
