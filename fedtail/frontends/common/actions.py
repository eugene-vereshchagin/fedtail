"""Which actions a post offers — the buttons under it and its ⋯ menu — and the link
each one follows (common/links.py). The card of either toolkit lays them out; what is
offered, when, and in which order is decided here.

`Ctx` is what the decisions need to know about the window: the config, who I am,
what the server can do, and the optional abilities (lists, other accounts, the whole
text from the author's server, translation…) a frontend may not have yet.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import quote as urlquote

from ...i18n import _, current_language
from ...model import Share, real
from .links import make, thread_url

MUTE_TAGS_SHOWN = 3  # a post's hashtags offered for muting in its menu, at most

# words for a visibility in i18n: vis_public, vis_private (followers), vis_direct…
VIS_KEY = {"followers": "private"}


def vis_word(vis):
    return _("vis_" + VIS_KEY.get(vis, vis))


# fedtail's own pictures (frontends/iconpack.py) for a post's buttons and who sees it
ACTION_PICTURE = {"reply": "reply", "fav": "star", "boost": "boost", "thread": "thread",
                  "bookmark": "bookmark"}


def action_picture(action, active=False):
    """The picture of a button under a post (a done favourite: a full star), or None."""
    pic = ACTION_PICTURE.get(action)
    return "star_full" if pic == "star" and active else pic


def vis_picture(vis):
    return {"followers": "private"}.get(vis, vis)


@dataclass
class Ctx:
    cfg: dict
    me_id: str | None
    supports: Callable[[str], bool] = lambda _what: False
    subscribed: Callable | None = None      # fn(entry) -> bool, or None: no subscriptions
    thread_quiet: Callable | None = None    # fn(entry) -> bool, or None
    lists: bool = False                     # "Add to list" submenus
    act_as: Callable | None = None          # fn(entry) -> [(tag, label)] other accounts
    long_form: bool = False                 # "the whole text" from the author's server
    translate: bool = False
    translates: dict | None = None          # {from: [into]} the server's translator; None — ?
    quote_reply: bool = False               # "Reply with a quote" (needs an editor)
    in_thread: bool = False


def can_translate(translates, lang, into=None):
    """Can the server's translator turn lang into mine (into)? Yes when it didn't say
    what it can (translates None or empty) or the post's language isn't known."""
    if not translates or not lang:
        return True
    into = (into or current_language()).split("-")[0]
    return any(t.split("-")[0] == into for t in translates.get(lang) or ())


@dataclass(frozen=True)
class Button:
    """One button under a post. action: what its link does (fedtail:<action>/<id>);
    icons: freedesktop icon names to try; glyph: when there is no icon; count: "" or
    " · 3"; who: the link a right click follows (who liked / boosted), or ""."""
    action: str
    icons: tuple
    glyph: str
    label: str
    count: str = ""
    active: bool = False
    url: str = ""
    who: str = ""


def buttons(entry, ctx, unread=False, open_at="post"):
    """The buttons under a post, in order. open_at: where its thread opens (the card's
    CardSpec.open_at)."""
    p = real(entry)
    sid = entry.id  # a boost: its own id (the window finds the post in it)
    n = lambda x: f" · {x}" if x else ""  # noqa: E731
    fav, boosted = p.mine.liked, p.mine.shared
    out = [Button("reply", ("mail-reply-sender",), "↩", _("reply"))]
    out.append(Button("fav", ("rating", "starred-symbolic") if fav else
                      ("rating-unrated", "non-starred-symbolic"), "★" if fav else "☆",
                      _("faved") if fav else _("fav"), n(p.counts.likes), fav))
    if p.visibility in ("public", "unlisted"):
        out.append(Button("boost", ("media-playlist-repeat", "retweet"), "♻",
                          _("boosted") if boosted else _("boost"), n(p.counts.shares),
                          boosted))
    if not ctx.in_thread:
        out.append(Button("thread", ("view-list-tree", "format-indent-more"), "⤷",
                          _("thread"), n(p.counts.replies)))
    if ctx.cfg["ui"].get("bookmark_button", True):
        marked = p.mine.bookmarked
        out.append(Button("bookmark", ("bookmark-new", "bookmarks"), "🔖",
                          _("unbookmark") if marked else _("bookmark"), "", marked))
    if unread and ctx.cfg["read"].get("read_button", False):
        out.append(Button("readone", ("mail-mark-read", "object-select-symbolic"), "✓",
                          _("mark_one_read")))
    done = []
    for b in out:
        who = {"fav": ("favourited_by", p.counts.likes),
               "boost": ("reblogged_by", p.counts.shares)}.get(b.action)
        right = make(who[0], sid) if who and who[1] and ctx.supports(who[0]) else ""
        url = thread_url(sid, open_at) if b.action == "thread" else make(b.action, sid)
        done.append(Button(b.action, b.icons, b.glyph, b.label, b.count, b.active, url,
                           right))
    return done


@dataclass(frozen=True)
class Item:
    """One line of a post's menu. kind:
      link        follow url (a fedtail: link, through the window's on_link)
      open        open url outside (the browser)
      copy        put text on the clipboard
      lists       a submenu "Add to list" for the account in data
      act_as      a submenu: data = [(label, entry, tag, action)] — do it as another account
      long_form   the whole text from the author's server (data: the entry)
      translate   translate the post
      quote_reply reply quoting the post's text
      separator   a line
    """
    kind: str
    label: str = ""
    url: str = ""
    text: str = ""
    data: object = None


SEP = Item("separator")


def menu(entry, ctx, short_id=None, unread=False):
    """The ⋯ menu of a post, top to bottom."""
    p = real(entry)
    sid = entry.id
    url = p.url or p.uri
    out = [Item("open", _("open_browser"), url=url), Item("copy", _("copy_link"), text=url)]
    if short_id:
        out.append(Item("copy", _("copy_id", id="#" + short_id), text="#" + short_id))
    author = p.author
    booster = entry.by if isinstance(entry, Share) and entry.by.id != author.id else None
    # @user@server of who wrote it (and who boosted it): to call them anywhere
    for acc in [author] + ([booster] if booster else []):
        out.append(Item("link", _("copy_handle_of", acct="@" + acc.handle),
                        url="fedtail:copyhandle/" + urlquote(acc.handle, safe="")))
    if ctx.lists:
        # a boost has two people: the one who wrote it and the one who boosted it (a
        # relay bot, say) — each by name, so it's clear who goes into the list
        who = [(author, "add_to_list_author")]
        if booster:
            who.append((booster, "add_to_list_booster"))
        for acc, key in who:
            if acc.id == ctx.me_id:
                continue
            out.append(Item("lists", _(key, acct="@" + acc.handle) if len(who) > 1
                            else _("add_to_list"), data=acc))
    approval = p.policy.can_quote if p.policy else ""
    if ctx.cfg["post"].get("quote_action", True) and approval in ("automatic", "manual"):
        out.append(Item("link", _("quote") if approval == "automatic" else _("quote_ask"),
                        url=make("quote", p.id)))
    if ctx.act_as is not None:
        others = ctx.act_as(entry)
        if others:
            out.append(Item("act_as", _("act_as"), data=[
                (_(key, acct=label), entry, tag, action) for tag, label in others
                for action, key in (("fav", "act_as_fav"), ("boost", "act_as_boost"),
                                    ("reply", "act_as_reply"))]))
    if ctx.long_form and "@" in author.handle and p.uri:
        out.append(Item("long_form", _("long_form"), data=entry))
    lang = p.lang.split("-")[0]
    every = ctx.cfg.get("feed", {}).get("translate_all", False)  # Fedilab's way: any post at all
    if ctx.translate and p.text and (every or (lang and lang != current_language())) and \
            can_translate(ctx.translates, lang):
        out.append(Item("translate", _("translate")))
    if ctx.quote_reply and ctx.me_id:
        out.append(Item("quote_reply", _("reply_quote")))
    if ctx.cfg["post"].get("invite", True):
        out.append(Item("link", _("invite"), url=make("invite", sid)))
    out.append(Item("link", _("unbookmark") if p.mine.bookmarked else _("bookmark"),
                    url=make("bookmark", sid)))
    if unread:  # by hand, whatever read.mark_read says
        out.append(Item("link", _("mark_one_read"), url=make("readone", sid)))
        out.append(Item("link", _("mark_read_upto"), url=make("readupto", sid)))
    # who liked, who boosted; quotes of my post; my post out of someone's quote
    sup = ctx.supports
    if sup("reactions") or p.reactions:  # an emoji of mine on it (Akkoma, Misskey…)
        out.append(Item("link", _("react_menu") + "…", url=make("react", sid)))
    for kind, count in (("favourited_by", p.counts.likes), ("reblogged_by", p.counts.shares)):
        if sup(kind) and count:
            out.append(Item("link", _("who_" + kind + "_n", n=count), url=make(kind, sid)))
    if p.card and p.card.url.startswith("https://") and sup("link_timeline"):
        out.append(Item("link", _("link_posts"), url=make("linkposts", sid)))
    if author.id == ctx.me_id and sup("quotes") and p.visibility in ("public", "unlisted"):
        out.append(Item("link", _("quotes_of"), url=make("quotes", sid)))
    quoted_post = p.quote.post if p.quote else None
    if quoted_post is not None and quoted_post.author.id == ctx.me_id and \
            sup("quotes") and author.id != ctx.me_id:
        out.append(Item("link", _("revoke_quote"), url=make("revokequote", sid)))
    # always offered: a server that can't mute a thread (GoToSocial) gets it done here
    if ctx.thread_quiet is not None or sup("mute_thread"):
        muted = bool(p.mine.muted) or bool(ctx.thread_quiet and ctx.thread_quiet(entry))
        out.append(Item("link", _("unmute_thread" if muted else "mute_thread"),
                        url=make("unmutethread" if muted else "mutethread", sid)))
    if ctx.subscribed is not None:
        out.append(SEP)
        on = ctx.subscribed(entry)
        out.append(Item("link", _("unsub_thread" if on else "sub_thread"),
                        url=make("unsub" if on else "sub", sid)))
    if sup("filter_status"):
        out.append(Item("link", _("hide_post"), url=make("hidepost", sid)))
    if ctx.cfg.get("lanes") is not None:  # which lanes take it, and by which rule
        out.append(Item("link", _("why_here"), url=make("why", sid)))
    if (ctx.cfg.get("debug") or {}).get("raw_json"):  # the post as the server gave it
        out.append(Item("link", _("raw_json"), url=make("raw", sid)))
    if (ctx.cfg.get("feed") or {}).get("around_post"):  # what came just before and after it
        out.append(Item("link", _("around_post"), url=make("around", sid)))
    if author.id != ctx.me_id:
        out.append(SEP)
        out.append(Item("link", _("mute_acct", acct=author.handle) + "…", url=make("mute", sid)))
        # its hashtags, each muted in one click (into the filter of muted hashtags)
        for tag in list(dict.fromkeys(t.lower() for t in p.tags or ()))[:MUTE_TAGS_SHOWN]:
            out.append(Item("link", _("tag_mute", tag=tag), url=make("mutetag", urlquote(tag))))
        out.append(Item("link", _("block_acct", acct=author.handle), url=make("block", sid)))
        domain = author.handle.partition("@")[2]
        if domain:
            out.append(Item("link", _("block_domain", domain=domain),
                            url=make("blockdomain", sid)))
        if not ctx.cfg["ui"]["arts_mode"]:
            out.append(Item("link", _("report"), url=make("report", sid)))
    mine = (entry.by if isinstance(entry, Share) else author).id == ctx.me_id
    if mine:
        out.append(SEP)
        out.append(Item("link", _("edit"), url=make("edit", sid)))
        if p.visibility in ("public", "unlisted"):
            out.append(Item("link", _("unpin") if p.mine.pinned else _("pin"),
                            url=make("unpin" if p.mine.pinned else "pin", p.id)))
        out.append(Item("link", _("delete"), url=make("delete", sid)))
        if ctx.cfg["post"].get("redraft", True):
            out.append(Item("link", _("redraft"), url=make("redraft", sid)))
    return out


__all__ = ["Button", "Ctx", "Item", "SEP", "VIS_KEY", "buttons", "can_translate", "menu",
           "vis_word"]
