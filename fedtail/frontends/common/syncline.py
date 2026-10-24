"""Sync with the account's other devices, in a word for the status bar and a line for
About — the same in every toolkit. No toolkit here.

    text, tip = syncline.bar(view)      # "⇅ 21:40", "Synced at 21:40: https://…"
    syncline.about(view)                # "https://… · ⇅ 21:40", or "off (…)"

Sync is a service of its own: off unless sync.url (or sync.folder) is set, and the bar
says so rather than staying silent.
"""

from datetime import datetime

from ...i18n import _


def status(view):
    """Core.sync_status() through whatever the frontend holds (a Core, a view)."""
    fn = getattr(view, "sync_status", None) or getattr(getattr(view, "_core", None),
                                                       "sync_status", None)
    try:
        return fn() if fn else None
    except Exception:  # noqa: BLE001 — a status line must never take the window down
        return None


def local_time(iso):
    """'2026-10-23T19:40:00Z' → '23:40' in local time; '22.10 23:40' when not today."""
    try:
        t = datetime.fromisoformat(str(iso).replace("Z", "+00:00")).astimezone()
    except ValueError:
        return ""
    today = datetime.now().astimezone().date()
    return t.strftime("%H:%M") if t.date() == today else t.strftime("%d.%m %H:%M")


def bar(view):
    """(text, tooltip) for the status bar."""
    st = status(view)
    if st is None:
        return _("sync_bar_off"), _("sync_bar_off_tip")
    last = st.get("last") or {}
    where = st.get("where") or ""
    if last.get("error"):
        return _("sync_bar_bad"), _("sync_bar_bad_tip", where=where, error=last["error"])
    if not last.get("at"):
        return _("sync_bar_wait"), _("sync_bar_wait_tip", where=where)
    when = local_time(last["at"])
    return (_("sync_bar_ok", time=when),
            _("sync_bar_ok_tip", time=when, where=where, sent=last.get("sent", 0),
              got=last.get("got", 0), pending=st.get("pending", 0)))


def about(view):
    """The value of About's "Sync" row."""
    st = status(view)
    if st is None:
        return _("about_sync_off")
    return f"{st.get('where') or ''} · {bar(view)[0]}"


__all__ = ["about", "bar", "local_time", "status"]
