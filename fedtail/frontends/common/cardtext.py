"""The words around a post on its card, without a toolkit: who boosted it and when, the
line of facts under the name (the time, who sees it, "edited", "old"), what it answers,
the content warning (a server's filter folds it too), "you replied", the conversation's
line, someone new in a private talk, the emoji reactions, a quote and why one can't be
shown. The GTK card has them so (gtk/card.py), Qt's alike; the web page and the terminal
take them from here, so all four say the same.

    words = card_words(spec, cfg, date)   # spec: common/lane.py CardSpec

Each bit is plain text and, where it leads somewhere, a fedtail: link (the window's
link handler opens it: a thread, a profile, the versions of an edit).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ...i18n import _
from ...model import Post, Share, real
from ...model.text import snippet
from . import actions
from .lane import age_days, conversation_line
from .links import thread_url

# how much of the post answered stands over a reply ("↑ Bob: …"), in every interface
CONTEXT_CHARS = 160  # feed.reply_context_chars' default


def context_chars(cfg):
    """feed.reply_context_chars: the answered post's characters over a reply."""
    return int((cfg.get("feed") or {}).get("reply_context_chars", CONTEXT_CHARS))


def indent_of(cfg, depth):
    """How many steps in a thread's post of this depth is drawn: feed.thread_indent_max
    at most (the model's INDENT_MAX by default) — one number for every interface."""
    from ...model import INDENT_MAX, indent
    return indent(depth, int((cfg.get("feed") or {}).get("thread_indent_max", INDENT_MAX)))


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
    quote_inner: Bit | None = None    # "❝ quotes Bob's post" under a quote that quotes too
    newcomer: Bit | None = None       # "👤 New in this private talk: @eve" — see newcomers()
    thread_news: Bit | None = None    # "🔔 3 new in the thread": a followed thread's news


def newcomers(post, parent):
    """Who a private post brings into the talk: its author and those it mentions that the
    private post it answers neither came from nor named — they couldn't read the talk
    before, now they read this one (and what is quoted in it). [handle], in order; [] when
    it isn't a private answer to a private post, or the parent isn't known."""
    if post is None or post.visibility != "direct" or not isinstance(parent, Post) or \
            parent.visibility != "direct":
        return []
    known = {parent.author.id} | {m.id for m in parent.mentions}
    out = []
    for ident, handle in [(post.author.id, post.author.handle)] + \
            [(m.id, m.handle) for m in post.mentions]:
        if ident and ident not in known and handle not in out:
            out.append(handle)
    return out


def thread_news_bit(spec):
    """"🔔 3 new in the thread" under a post whose followed thread has new replies."""
    n = spec.extra.get("thread_news") if spec is not None else None
    p = spec.post if spec is not None else None
    if not n or p is None:
        return None
    # it is about the news: always at the first of them (threads.open_at aside)
    return Bit("🔔 " + _("thread_news", n=n), thread_url(p.id, "first_unread"),
               _("thread_news_tip"), kind="thread_news")


def newcomer_bit(post, parent):
    who = newcomers(post, parent)
    if not who:
        return None
    ids = {post.author.handle: post.author.id} | {m.handle: m.id for m in post.mentions}
    return Bit("👤 " + _("dm_newcomer", who=", ".join("@" + h for h in who)),
               f"fedtail:account/{ids[who[0]]}" if ids.get(who[0]) else "",
               _("dm_newcomer_tip"), kind="newcomer")


def shown_text(p, cfg):
    """A post's HTML as a card shows it: without the "RE: <link>" paragraph servers add for
    clients that can't show quotes, when fedtail shows the quote itself (feed.quotes not
    "off") — decided here for every interface: Qt took it out, GTK and the web page showed
    the quote twice."""
    from ...model.text import without_quote_fallback
    mode = (cfg.get("feed") or {}).get("quotes", "card")
    return without_quote_fallback(p.text) if p.quote is not None and mode != "off" else p.text


def inner_quote_bit(quoted, mode="card"):
    """The quoted post's own quote, as Mastodon's page shows it: one line under the quote —
    "❝ quotes Bob's post", a link to its thread — never a card in a card (Mastodon gives
    that level as an id only, Akkoma whole; no client draws it framed). quoted: the Post
    quoted (Quote.post); None — nothing to say, as for a quote not shown (feed.quotes off,
    or pending, rejected…)."""
    if quoted is None or mode == "off":
        return None
    inner = getattr(quoted, "quote", None)
    if inner is None or inner.state != "accepted" or not inner.id:
        return None
    words = _("quote_inner_by", name=name_of(inner.post.author)) if inner.post is not None \
        else _("quote_inner")
    return Bit("❝ " + words, f"fedtail:thread/{inner.id}")


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
        w.meta.append(Bit(date(p.created), thread_url(p.id, spec.open_at), kind="time"))
    w.meta.append(Bit(actions.vis_word(p.visibility), tip=actions.vis_word(p.visibility),
                      kind="vis"))
    if p.edited:
        w.meta.append(Bit(_("edited_mark"), f"fedtail:history/{p.id}",
                          _("edited_tip", when=date(p.edited)), kind="edited"))
    if spec.extra.get("via_tag"):  # card.why_home: in Home by a followed tag
        tag = spec.extra["via_tag"]
        w.meta.append(Bit("# " + _("via_tag", tag=tag), f"fedtail:tag/{tag}",
                          _("via_tag_tip", tag=tag), kind="via_tag"))
    if spec.extra.get("deleted"):  # gone from its server, kept here
        w.meta.append(Bit("🗑 " + _("deleted_mark"), tip=_("deleted_mark_tip"), kind="deleted"))
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
                                     text=snippet(parent, context_chars(cfg))),
                            f"fedtail:thread/{p.id}")
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
        w.conversation = Bit("💬 " + conv[0], thread_url(conv[1], spec.open_at))
    if cfg["feed"].get("emoji", True):
        reacted = sorted(((r.name, r.count) for r in p.reactions if r.count > 0),
                         key=lambda x: -x[1])
        w.reactions = " ".join((name if len(name) <= 4 else ":" + name.strip(":") + ":")
                               + f" {count}" for name, count in reacted[:12])
    w.quote = quote_bit(p.quote, cfg["feed"].get("quotes", "card"))
    if p.quote is not None and p.quote.state == "accepted":
        w.quote_inner = inner_quote_bit(p.quote.post, cfg["feed"].get("quotes", "card"))
    w.newcomer = newcomer_bit(p, parent)
    w.thread_news = thread_news_bit(spec)
    return w


__all__ = ["Bit", "CardWords", "card_words", "inner_quote_bit", "name_of", "newcomer_bit",
           "newcomers", "quote_bit", "shown_text", "thread_news_bit"]


def only_counts_differ(old, new):
    """Whether two versions of a lane's entry differ only in what the row of buttons
    under a post shows — the counts of replies, boosts, likes, and whether I liked,
    boosted, bookmarked it. A refresh brings such changes for most posts on screen;
    a whole card rebuilt for each froze the window (551 ms, 29.10) and made its
    pictures load again."""
    if old is new or old == new:
        return False
    if isinstance(old, Share) != isinstance(new, Share):
        return False
    if isinstance(old, Share):
        if replace(old, post=new.post) != new:
            return False
        old, new = old.post, new.post
    if not isinstance(old, Post) or not isinstance(new, Post):
        return False
    return replace(old, counts=new.counts, mine=new.mine) == new
