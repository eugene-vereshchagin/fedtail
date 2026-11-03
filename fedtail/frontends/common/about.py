"""What the About window says, without a toolkit: Qt and GTK draw it as cards (a header
with the opossum, a grid of tiles, rows), the web page and the terminal as a place
(common/places.py). "Copy the information" copies text() — what a bug report wants.

    a = about.facts(view, "Qt", "6.8.2")
    a.version, a.tagline, a.tiles, a.rows, a.text()
"""

from __future__ import annotations

import platform
import sys
from dataclasses import dataclass, field
from datetime import datetime

from ...i18n import _


@dataclass
class About:
    version: str
    tagline: str
    tiles: list = field(default_factory=list)   # [(label, value)]: three to a row
    rows: list = field(default_factory=list)    # [(label, value)]: one to a row
    made_by: str = ""
    links: list = field(default_factory=list)   # [(words, url)]
    update: tuple = ("", None)  # the "Updates" row and its button: (words, newer or None)

    def text(self):
        """Everything above as plain lines: for the clipboard, a bug report, a chat."""
        from ... import version as _version
        out = [f"{_version.NAME} {self.version}"]
        out += [f"{k}: {v}" for k, v in self.tiles + self.rows if v]
        if self.update[0]:
            out.append(f"{_('about_updates')}: {self.update[0]}")
        return "\n".join(out)


def platform_name():
    if sys.platform.startswith("win"):
        rel = platform.release()
        return f"Windows {rel}" if rel else "Windows"
    if sys.platform == "darwin":
        return "macOS " + (platform.mac_ver()[0] or "")
    try:  # "Debian GNU/Linux 13 (trixie)"
        import platform as pf
        name = pf.freedesktop_os_release().get("PRETTY_NAME")
        if name:
            return name
    except (OSError, AttributeError):
        pass
    return platform.system() or sys.platform


def _accounts(view):
    """["@name@server", …]: every account of the window, the main one first."""
    core = getattr(view, "_core", view)
    pick = getattr(core, "post_accounts", None)
    accounts = pick(None)[0] if pick is not None else []
    if accounts:
        return [h for _k, h in accounts]
    from ...core.merged import full_handle
    h = full_handle(core)
    return [h] if h else []


def _when(epoch):
    """Epoch seconds → '10:15' today, '02.11 10:15' before."""
    t = datetime.fromtimestamp(epoch).astimezone()
    today = datetime.now().astimezone().date()
    return t.strftime("%H:%M") if t.date() == today else t.strftime("%d.%m %H:%M")


def update_line(view):
    """About's "Updates" row: (words, the newer version or None) — what the website
    said last (core/updates.py), when, and whether it is asked by itself."""
    fn = getattr(view, "update_status", None) or getattr(
        getattr(view, "_core", None), "update_status", None)
    try:
        st = fn() if fn else None
    except Exception:  # noqa: BLE001 — About must open whatever the store says
        st = None
    if not st:
        return "", None
    if not st["at"]:
        words = _("about_upd_never")
    elif st["newer"]:
        words = _("about_update", v=st["latest"]) + " · " + _("about_upd_at", time=_when(st["at"]))
    elif st["ok"]:
        words = _("about_upd_latest", time=_when(st["at"]))
    else:
        words = _("about_upd_failed", time=_when(st["at"]))
    if not st["on"]:
        words += " · " + _("about_upd_off")
    return words, st["latest"] if st["newer"] else None


def facts(view, toolkit="", toolkit_version=""):
    """The About of this window. toolkit: "Qt", "GTK", "Textual", "" (the web page)."""
    from ... import version
    from ...model.text import html_to_text
    info = version.info()
    tagline = html_to_text(_("about_text", version=info["version"])).split("\n")[-1]
    dev = ".dev" in info["version"] or "+g" in info["version"]
    a = About(version=info["version"], tagline=tagline.strip(), made_by=_("made_by_long"))
    paths = getattr(view, "paths", None) or getattr(getattr(view, "_core", None), "paths", None)
    a.tiles = [
        (_("about_version"), info["version"].split("+")[0]),
        (_("about_platform"), platform_name()),
        (_("about_arch"), platform.machine() or "?"),
        (_("about_build_kind"), _("about_dev") if dev else _("about_release")),
        (_("about_commit_date"), info.get("date") or "—"),
        (_("about_profile"), getattr(paths, "profile", "") or "default"),
    ]
    rows = [("Python", platform.python_version())]
    if toolkit:
        rows.append((toolkit, toolkit_version))
    if info.get("commit"):
        rows.append((_("about_commit"), info["commit"]))
    accounts = _accounts(view)
    if accounts:
        rows.append((_("about_accounts") if len(accounts) > 1 else _("about_account"),
                     ", ".join(accounts)))
    caps = getattr(view, "caps", None)
    if caps is not None and getattr(caps, "software", ""):
        rows.append((_("about_server"), (caps.software + " " + (caps.version or "")).strip()))
    cfg = getattr(view, "cfg", None) or {}
    theme = (cfg.get("ui") or {}).get("theme")
    if theme:
        rows.append((_("about_theme"), theme))
    from . import syncline
    rows.append((_("about_sync"), syncline.about(getattr(view, "_core", view))))
    if paths is not None:
        rows.append((_("about_data"), str(paths.data_dir)))
    a.rows = rows
    a.links = [("GitHub", version.HOMEPAGE), (version.AUTHOR, version.AUTHOR_URL)]
    a.update = update_line(view)
    return a


__all__ = ["About", "facts", "platform_name", "update_line"]
