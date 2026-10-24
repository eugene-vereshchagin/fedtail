"""What a profile offers — the line about the person and the buttons under it — and
what each button does, once for every toolkit (the Qt window has its own still; GTK
and the web take it from here, so they offer the same).

`actions()` says which buttons, in which order, with which words, from who they are to
me (Relationship) and what my server can do. `do()` carries one out through a `host`
(the window):

  call(future, ok=None, fail=None)   in the GUI thread when done
  confirm(title, text, then)         ask first; then() on yes
  ask_text(title, question, then, text="")   a line to type; then(text)
  compose(text=...)  open_people(acc, which)  copy_handle(handle)  open_url(url)
  edit_profile()  open_lists(acc)
  status(text)  error(text)

and `changed(rel)` gets the relationship as it is afterwards (the server's answer, or
the old one with the change made when the server says nothing)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from ...i18n import _
from ...model import Relationship
from ...model.text import note_text


@dataclass(frozen=True)
class Act:
    key: str            # what do() is asked to do
    label: str
    tip: str = ""
    primary: bool = False


def meta(acc, rel, date, followed_since=None, software=""):
    """The line under the name: @handle, a bot, locked, since when, follows me, how
    long I follow them, the server's software. Plain text pieces."""
    bits = ["@" + acc.handle]
    if acc.bot:
        bits.append(_("bot"))
    if acc.locked:
        bits.append("🔒 " + _("acc_locked"))
    if acc.created:
        bits.append(_("acc_since", date=acc.created.strftime("%d.%m.%Y")))
    if rel is not None and rel.followed_by:
        bits.append(_("acc_follows_you"))
    if software:
        bits.append("🖥 " + software)
    if followed_since:
        bits.append(_("acc_followed_since", when=date(followed_since)))
    return bits


def actions(acc, rel, mine, cfg, supports, lists=False, details=False):
    """The profile's buttons, in order. details: "Profile…" — the head's details as a
    place of its own (the web page and the terminal: the windows show them in the tab)."""
    rel = rel or Relationship()
    out = []
    if mine:
        out.append(Act("edit_profile", _("edit_profile")))
    if not mine:
        following = rel.following
        out.append(Act("follow", _("unfollow") if following else
                       (_("follow_requested") if rel.requested else _("follow")),
                       primary=not following))
        if following:
            out.append(Act("bell", "🔔 " + (_("bell_off") if rel.notifying else _("bell_on")),
                           _("bell_tip")))
            if cfg["feed"].get("per_person_follow", True):
                out.append(Act("boosts", "♻ " + (_("boosts_hide") if rel.showing_shares
                                                 else _("boosts_show")),
                               _("boosts_person_tip")))
                langs = list(rel.languages or ())
                out.append(Act("langs", "🌐 " + (", ".join(langs) if langs else _("langs_all")),
                               _("langs_person_tip")))
        out.append(Act("mention", _("mention")))
        out.append(Act("mute", _("unmute") if rel.muting else _("mute")))
        out.append(Act("block", _("unblock") if rel.blocking else _("block")))
        if rel.followed_by and supports("remove_follower"):
            out.append(Act("remove_follower", _("remove_follower")))
        if following and supports("endorse"):
            out.append(Act("endorse", _("unendorse") if rel.endorsed else _("endorse"),
                           _("endorse_tip")))
        if lists:
            out.append(Act("lists", _("add_to_list")))
    for which, n in (("following", acc.following), ("followers", acc.followers)):
        if n:
            out.append(Act(which, _(f"people_{which}_n", n=n)))
    if not mine:
        out.append(Act("note", _("note_edit"), _("note_tip")))
    out.append(Act("copy_handle", _("copy_handle"), _("copy_handle_tip")))
    if acc.url:
        out.append(Act("open_browser", _("open_browser")))
    if details:
        out.append(Act("details", "ℹ " + _("profile_title") + "…"))
    return out


def note_line(rel, mine):
    """My private note on them, to show under the buttons ("" if none)."""
    note = note_text(rel.note if rel is not None else "").strip()
    return "" if mine or not note else "📝 " + note


def parse_langs(text):
    return [x.strip().lower() for x in (text or "").replace(";", ",").replace(" ", ",")
            .split(",") if x.strip()]


def do(key, acc, rel, view, host, changed):
    """Carry out a profile button (key from actions())."""
    rel = rel or Relationship()

    def after(**now):
        return lambda r: changed(r if isinstance(r, Relationship) else replace(rel, **now))
    if key == "follow":
        on = not (rel.following or rel.requested)
        host.call(view.follow(acc.id, on), changed)
    elif key == "bell":
        on = not rel.notifying
        host.call(view.notify_posts(acc.id, on), after(notifying=on), host.error)
    elif key == "boosts":
        on = not rel.showing_shares
        host.call(view.follow_options(acc.id, reblogs=on), after(showing_shares=on),
                  host.error)
    elif key == "langs":
        def set_langs(text):
            langs = parse_langs(text)
            host.call(view.follow_options(acc.id, languages=langs),
                      after(languages=tuple(langs) or None), host.error)
        host.ask_text(_("langs_person_title", acct=acc.handle), _("langs_person_ask"),
                      set_langs, ", ".join(rel.languages or ()), allow_empty=True)
    elif key == "mention":
        host.compose(text=f"@{acc.handle} ")
    elif key == "mute":
        on = not rel.muting
        host.call(view.mute(acc.id, on), after(muting=on))
    elif key == "block":
        on = not rel.blocking

        def go():
            host.call(view.block(acc.id, on), after(blocking=on))
        if on:
            host.confirm(_("block"), _("block_q", acct=acc.handle), go)
        else:
            go()
    elif key == "remove_follower":
        def go():
            done = after(followed_by=False)
            host.call(view.remove_follower(acc.id),
                      lambda r: (done(r), host.status(_("follower_removed",
                                                         acct=acc.handle))), host.error)
        host.confirm(_("remove_follower"), _("remove_follower_q", acct=acc.handle), go)
    elif key == "endorse":
        on = not rel.endorsed
        host.call(view.endorse(acc.id, on), after(endorsed=on), host.error)
    elif key in ("following", "followers"):
        host.open_people(acc, key)
    elif key == "note":
        old = rel.note
        host.ask_text(_("note_title", acct=acc.handle), _("note_tip"),
                      lambda text: host.call(view.set_note(acc.id, text.strip(), old),
                                             after(note=text.strip()), host.error),
                      note_text(old), allow_empty=True)
    elif key == "edit_profile":
        host.edit_profile()
    elif key == "lists":  # "Add to list": which lists they're in, a tick each
        host.open_lists(acc)
    elif key == "copy_handle":
        host.copy_handle(acc.handle)
    elif key == "open_browser":
        host.open_url(acc.url)
    elif key == "details":  # the place of the profile's details (common/placesmore.py)
        host._place("profile_info", acc.id)
