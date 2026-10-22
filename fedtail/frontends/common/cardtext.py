"""The words around a post on its card, without a toolkit: who boosted it and when, the
line of facts under the name (the time, who sees it, "edited", "old"), what it answers,
the content warning (a server's filter folds it too), "you replied", the conversation's
line, the emoji reactions, a quote and why one can't be shown. The GTK card has them so
(gtk/card.py), Qt's alike; the web page and the terminal take them from here, so all
four say the same.

    words = card_words(spec, cfg, date)   # spec: common/lane.py CardSpec

Each bit is plain text and, where it leads somewhere, a fedtail: link (the window's
link handler opens it: a thread, a profile, the versions of an edit).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ...i18n import _
from ...model import Post, Share, real
from ...model.text import snippet
from . import actions
from .lane import age_days, conversation_line


def name_of(acc):
    return (acc.name or acc.username or acc.handle) if acc is not None else "?"


@dataclass
class Bit:
    """A piece of words; link: where a click goes (a fedtail: link), or ""; kind: what
    it is ("time", "vis", "edited", "old"…) — a window may draw one its own way (who
    sees it as the theme's picture)."""
    text: str
    link: str = ""
    tip: str = ""
    kind: str = ""


@dataclass
class CardWords:
    boosted: Bit | None = None        # "♻ Bob boosted · 14:20"
    meta: list = field(default_factory=list)    # [Bit]: the time, who sees, edited, old
    context: Bit | None = None        # what it answers ("↑ in reply to …"), or why not
    warning: str = ""                 # "Folded by filter «x» · ⚠ spoilers"; "" — none
    folded: bool = False              # closed whatever ui.expand_cw (a filter's "warn")
    my_replies: list = field(default_factory=list)  # [Bit] "↳ you replied …", newest few
    conversation: Bit | None = None   # "💬 3 in the conversation…"
    reactions: str = ""               # "👍 3 :blobcat: 2"
    quote: Bit | None = None          # a quote as a line (or why it can't be shown)


def quote_bit(quote, mode="card"):
    """A quoted post as one line: "❝ Bob's quote: …", or why it isn't shown and, where
    the reader may, a way to it all the same."""
    if quote is None or mode == "off":
        return None
    state, q, qid = quote.state, quote.post, quote.id
    if state != "accepted" or (q is None and not qid):
        key = "quote_" + state
        why = _(key) if _(key) != key else _("quote_unavailable")
        if qid and state in ("blocked_account", "blocked_domain", "muted_account"):
            return Bit("❝ " + why + " · " + _("quote_show_anyway"), f"fedtail:thread/{qid}")
        return Bit("❝ " + why)
    if q is None:
        return Bit("❝ " + _("quote_open"), f"fedtail:thread/{qid}")
    words = _("quote_by", name=name_of(q.author)) + ": " + (
        "⚠ " + q.warning if q.warning else snippet(q, 90))
    if q.media and not q.warning:
        words += " · " + _("quote_media", n=len(q.media))
    return Bit("❝ " + words, f"fedtail:thread/{q.id}")


def card_words(spec, cfg, date, in_thread=None):
    """The words of a card (spec: a CardSpec). date: a datetime in the theme's words."""
    entry = spec.entry
    p = real(entry)
    in_thread = spec.in_thread if in_thread is None else in_thread
    w = CardWords()
    if isinstance(entry, Share):
        by = entry.by
        text = "♻ " + _("boosted_by", name=name_of(by))
        if entry.created:
            text += " · " + _("boost_time", when=date(entry.created))
        w.boosted = Bit(text, f"fedtail:account/{by.id}")
    if p.created:
        w.meta.append(Bit(date(p.created), f"fedtail:thread/{p.id}", kind="time"))
    w.meta.append(Bit(actions.vis_word(p.visibility), tip=actions.vis_word(p.visibility),
                      kind="vis"))
    if p.edited:
        w.meta.append(Bit(_("edited_mark"), f"fedtail:history/{p.id}",
                          _("edited_tip", when=date(p.edited)), kind="edited"))
    days = age_days(p, cfg)
    if days:
        w.meta.append(Bit(_("old_post", n=days), tip=_("old_post_tip"), kind="old"))
    parent = spec.parent
    if not in_thread:
        if parent == "missing":
            w.context = Bit(_("ctx_missing"))
        elif parent is None and p.reply_to and cfg["feed"].get("show_reply_context", True):
            w.context = Bit(_("ctx_loading"))
        elif isinstance(parent, Post):
            w.context = Bit("↑ " + _("ctx_reply", name=name_of(parent.author),
                                     text=snippet(parent, 160)), f"fedtail:thread/{p.id}")
    warned = list(p.filtered) if not cfg["ui"].get("arts_mode") else []
    if p.warning or warned:
        w.warning = " · ".join(([_("filtered_by", title=", ".join(warned))] if warned else [])
                               + (["⚠ " + p.warning] if p.warning else []))
        w.folded = bool(warned)
    for mine in list(spec.extra.get("my_replies") or ())[:3]:
        when = date(mine.created) if mine.created else ""
        w.my_replies.append(Bit("↳ " + _("you_replied", when=when, text=snippet(mine, 80)),
                                f"fedtail:thread/{mine.id}"))
    conv = conversation_line(spec)
    if conv is not None:
        w.conversation = Bit("💬 " + conv[0], f"fedtail:thread/{conv[1]}")
    if cfg["feed"].get("emoji", True):
        reacted = sorted(((r.name, r.count) for r in p.reactions if r.count > 0),
                         key=lambda x: -x[1])
        w.reactions = " ".join((name if len(name) <= 4 else ":" + name.strip(":") + ":")
                               + f" {count}" for name, count in reacted[:12])
    w.quote = quote_bit(p.quote, cfg["feed"].get("quotes", "card"))
    return w


__all__ = ["Bit", "CardWords", "card_words", "name_of", "quote_bit"]
