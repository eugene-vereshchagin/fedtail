"""Is a newer fedtail out? Once a day (updates.every_hours) the project's website is
asked (updates.url): no token, no account, no id of any kind — the version, the
interface and the system in the address, as the User-Agent says them anyway. A newer
release is a row of Activity ("FedTail 0.22.4 — a new version is out"), its name leading
to the release's page; About says what the last answer was and checks at once on its
button. updates.check = false — never asked by itself."""

import logging
import sys
import time

from .. import __version__
from ..version import HOMEPAGE, USER_AGENT

log = logging.getLogger("fedtail.core.app")  # the Core's log: one name for all its parts

TYPE_RELEASE = "fedtail.release"


def _vkey(v):
    """0.22.4 → (0, 22, 4, 1); 0.22.4.dev3 → (0, 22, 4, 0): a dev build is before its
    release. Not a version — None."""
    base, dev, _rest = str(v or "").strip().partition(".dev")
    try:
        nums = tuple(int(x) for x in base.split("."))
    except ValueError:
        return None
    return (*nums, 0 if dev else 1) if len(nums) == 3 else None


def newer(theirs, mine=None):
    a, b = _vkey(theirs), _vkey((mine or __version__).split("+")[0])
    return a is not None and b is not None and a > b


def release_page(version):
    return f"{HOMEPAGE}/releases/tag/v{version}"


# the names kept for tests and examples (RFC 2606, RFC 6761): the made-up worlds of the
# demo, the screenshots and the tools live there — their rounds don't ask (nor count)
_RESERVED = (".test", ".example", ".invalid", ".localhost")
_EXAMPLES = {"example.com", "example.org", "example.net"}


def _made_up(hosts):
    return any(h.endswith(_RESERVED) or h in _EXAMPLES or h.endswith(
        tuple("." + e for e in _EXAMPLES)) for h in hosts)


def _system():
    if sys.platform.startswith("linux"):
        from .. import diag
        return "android" if diag.device() else "linux"
    return {"win32": "windows", "darwin": "macos"}.get(sys.platform, sys.platform)


class UpdatesMixin:
    """A part of Core (core/app.py): see the module's words."""

    def updates_due(self):
        u = self.cfg["updates"]
        if not u.get("check") or not str(u.get("url") or "").startswith("https://"):
            return False
        if _made_up(self._own_hosts()):  # a demo, a screenshot, a test tool: not counted
            return False
        every = max(1, int(u.get("every_hours") or 24)) * 3600
        return time.time() - float(self.store.kv_get("updates.at") or 0) >= every

    def check_updates(self):
        """Ask the website once (the poll calls it when due, in the background): → the
        newer version out, or None. Said in Activity once per version."""
        from urllib.parse import urlencode

        from .. import diag
        from . import remote
        self.store.kv_set("updates.at", time.time())
        url = str(self.cfg["updates"]["url"])
        mine = __version__.split("+")[0]
        query = urlencode({"v": mine, "ui": diag.interface(self.cfg), "os": _system()})
        got = remote.get_json(f"{url}?{query}", headers={"User-Agent": USER_AGENT},
                              timeout=15)
        latest = str((got or {}).get("version") or "") if isinstance(got, dict) else ""
        latest = latest if _vkey(latest) else ""  # {"version": 7}: not an answer
        self.store.kv_set("updates.ok", bool(latest))
        if not latest:
            log.info("updates: no answer")
            return None
        self.store.kv_set("updates.latest", latest)
        if not newer(latest, mine):
            log.info("updates: %s is the newest", mine)
            return None
        log.info("updates: %s is out (this is %s)", latest, mine)
        self._tell_release(latest)
        return latest

    def check_updates_now(self):
        """About's "Check now": asked at once, updates.check on or off (the reader asked)
        → update_status(). Not in a made-up world: the tools press every button."""
        if _made_up(self._own_hosts()):
            log.info("updates: a made-up world, not asked")
        else:
            self.check_updates()
        return self.update_status()

    def update_status(self):
        """Plain data for About: {"mine": this version, "latest": the last answer ("" —
        none yet), "newer": it is newer than this, "at": when last asked (epoch
        seconds, 0 — never), "ok": the website answered then, "on": updates.check}."""
        kv = self.store.kv_get
        latest = str(kv("updates.latest") or "")
        return {"mine": __version__.split("+")[0], "latest": latest,
                "newer": bool(latest) and newer(latest),
                "at": float(kv("updates.at") or 0), "ok": bool(kv("updates.ok")),
                "on": bool(self.cfg["updates"].get("check"))}

    def update_out(self):
        """The newer release known to be out (the last answer), or None."""
        latest = self.store.kv_get("updates.latest")
        return latest if latest and newer(latest) else None

    def _tell_release(self, version):
        from ..version import NAME
        from .store import LOCAL_EVENT, now_iso
        row = {"id": f"{LOCAL_EVENT}release:{version}", "type": TYPE_RELEASE,
               "account": {"id": f"release:{version}", "acct": "", "username": NAME,
                           "display_name": f"{NAME} {version}",
                           "url": release_page(version)},
               "created_at": now_iso()}
        if self.store.activity_put([row]):
            self.emit("activity_updated", 1)
            lanes_in = {c.name: [] for c in self._event_lanes()}
            if lanes_in:
                self.emit("lanes_updated", lanes_in)
