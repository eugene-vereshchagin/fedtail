"""What a window does that is no toolkit's business: the flows every interface runs the
same way, written once. Each had its copy — logging out in the Qt window, the GTK window
and the accounts place; sending a bug report in Qt, GTK and the terminal; acting as
another account in all four (the audit of 23.11: a rule an interface has to copy is in
the wrong place). An interface gives its own ways to ask, to say and to wait
(``call(future, ok, fail)``, ``say(text, seconds)``); what is decided is here."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from ...i18n import _

log = logging.getLogger(__name__)


# ---- logging out ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Logout:
    """What logging this profile out means: asked first (title, text), then done."""
    profile: str                 # the profile logged out
    target: str | None           # the profile the window goes over to; None — the login
    text: tuple[str, ...] = field(default_factory=tuple)  # the question, by paragraphs

    @property
    def title(self):
        return _("logout_title")

    @property
    def yes(self):
        return _("logout_yes")

    def words(self, between="\n\n"):
        """The question as one text (a window's dialog: paragraphs its own way)."""
        return between.join(self.text)


def logout_plan(profile, handle=""):
    """The plan of logging `profile` out. handle: who it is ("me@server"; the profile's
    name without one). The window goes over to another profile logged in — the main one
    if there is one — and the main profile's ★ moves with it; none left: the login."""
    from ...core import paths, profiles
    acct = "@" + (handle or profile)
    others = [p for p in profiles.listing() if p["logged_in"] and p["name"] != profile]
    main = paths.main_profile()
    target = next((p for p in others if p["name"] == main), others[0]) if others else None
    text = [_("logout_q", acct=acct)]
    if target is not None:
        if profile == main:
            text.append(_("logout_main_moves", to=profiles.label(target)))
        text.append(_("logout_switch", to=profiles.label(target)))
    else:
        text.append(_("logout_last"))
    return Logout(profile, target["name"] if target is not None else None, tuple(text))


def logout(core, plan):
    """Do it: the token gone (here and on the server), the ★ handed on. → the profile
    to go over to, or None — the login."""
    from ...core import profiles
    log.info("logout: profile %s", plan.profile)
    core.logout()
    profiles.hand_over_main(plan.profile)
    return plan.target


# ---- a bug report sent on -----------------------------------------------------------------

def send_report(core, out, call, say):
    """The report made (the archive at `out`) goes into debug.report_repo too, if one is
    set (fedtail/reportsend.py): git and ssh take a while — in the background, said
    when it began, when it is there, and when it failed. → whether it was sent at all."""
    from ... import reportsend
    cfg = core.cfg
    repo = cfg["debug"].get("report_repo", "")
    if not repo:
        return False
    say(_("bugreport_sending", repo=repo), 0)
    call(core.submit(reportsend.send_report, out, cfg, core.paths.data_dir),
         lambda where: say(_("bugreport_sent", where=where), 15),
         lambda err: say(_("bugreport_send_failed", repo=repo, err=err), 30))
    return True


# ---- acting as another account -------------------------------------------------------------

def act_as_done(view, got):
    """The words after ★ or ♻ went from another account: which one did it."""
    via = view.via(got) if got is not None else ""
    me = view.me
    return _("act_as_done", acct=via or "@" + (me.handle if me else ""))


def act_as(view, post, tag, action, call, say, compose, fail=None):
    """★ / ♻ / ↩ from another account of the window (all accounts in one): the post is
    found on that account's server and the action done there; a reply opens the editor
    on the post as that account sees it (compose(post))."""
    say(_("act_as_wait"), 4)

    def done(got):
        if action == "reply":
            if got is not None:
                compose(got)
            return
        say(act_as_done(view, got), 5)
    call(view.act_as(post, tag, "find" if action == "reply" else action), done, fail)
