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

MUTE_TAGS_SHOWN = 3  # feed.mute_tags_shown's default: a post's hashtags offered for muting

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


def can_boost(p):
    """Can this post be boosted? Public and quiet public only: a followers' or a direct
    post the server refuses — every interface asks this (the phone offered it on every
    post, 31.10)."""
    return p.visibility in ("public", "unlisted")


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
    if can_boost(p):
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
    tool: str = ""    # its name among the tools over a post (TOOLS), "" — the menu's only
    on: bool = False  # a toggle's state (a thread followed, muted): the tool's look
    group: str = ""   # its submenu (GROUPS) with ui.menu_groups; "" — the menu's top


# the tools over a post (ui.hover_tools): seen while the mouse is on it, at its top
# right, each one of the ⋯ menu's items — out of the menu then, where they show (the
# windows); name → (the picture, iconpack's name; the glyph without pictures)
TOOLS = {"open": ("open", "↗"), "copy_link": ("copy", "⧉"), "translate": ("translate", "文"),
         "quote": ("quote", "❝"), "sub_thread": ("subs", "◉"), "mute_thread": ("mute", "🔇"),
         "read_upto": ("mark_read", "✓"), "edit": ("edit", "✎"), "delete": ("delete", "✕")}


SEP = Item("separator")


def hover_tools(cfg):
    """The tools over a post the config asks for (ui.hover_tools), in its order."""
    return [t for t in (cfg.get("ui") or {}).get("hover_tools") or () if t in TOOLS]


def tools(entry, ctx, short_id=None, unread=False):
    """The tools over a post (ui.hover_tools), in the config's order: [(item, picture,
    glyph)] — the menu's own items (what each does, when it's offered: the menu's
    rules), only those this post has now."""
    wanted = hover_tools(ctx.cfg)
    if not wanted:
        return []
    have = {it.tool: it for it in _menu(entry, ctx, short_id, unread) if it.tool}
    return [(have[t], *TOOLS[t]) for t in wanted if t in have]


# the submenus of a post's menu (ui.menu_groups), in this order, after its top items
GROUPS = ("author", "thread", "more")


def _group_label(group, entry):
    if group == "author":
        return _("menu_author", acct="@" + real(entry).author.handle)
    return _("menu_" + group)


def menu(entry, ctx, short_id=None, unread=False, without_tools=False, nested=False):
    """The ⋯ menu of a post, top to bottom. without_tools: the window shows the tools
    over the post (ui.hover_tools) — those items are there, not here (08.11: a menu of
    thirty lines). nested: the window draws submenus — with ui.menu_groups the items
    about the author, the thread and the rest go into "Author ▸", "Thread ▸", "More ▸"
    (Item kind "submenu", its items in data); a group of one stays in the top."""
    out = _menu(entry, ctx, short_id, unread)
    if without_tools:
        shown = set(hover_tools(ctx.cfg))
        out = [it for it in out if it.tool not in shown]
    if nested and (ctx.cfg.get("ui") or {}).get("menu_groups", True):
        groups = {g: [it for it in out if it.group == g] for g in GROUPS}
        top = [it for it in out if it.group not in groups or len(groups[it.group]) < 2]
        subs = [Item("submenu", _group_label(g, entry), data=_tidy(groups[g]))
                for g in GROUPS if len(groups[g]) >= 2]
        out = top + ([SEP] if subs else []) + subs
    return _tidy(out)


def _tidy(out):
    tidy = []  # no line first, last or twice
    for it in out:
        if it.kind == "separator" and (not tidy or tidy[-1].kind == "separator"):
            continue
        tidy.append(it)
    while tidy and tidy[-1].kind == "separator":
        tidy.pop()
    return tidy


def _menu(entry, ctx, short_id=None, unread=False):
    p = real(entry)
    sid = entry.id
    url = p.url or p.uri
    out = [Item("open", _("open_browser"), url=url, tool="open"),
           Item("copy", _("copy_link"), text=url, tool="copy_link")]
    if short_id:
        out.append(Item("copy", _("copy_id", id="#" + short_id), text="#" + short_id))
    author = p.author
    booster = entry.by if isinstance(entry, Share) and entry.by.id != author.id else None
    # @user@server of who wrote it (and who boosted it): to call them anywhere
    for acc in [author] + ([booster] if booster else []):
        out.append(Item("link", _("copy_handle_of", acct="@" + acc.handle),
                        url="fedtail:copyhandle/" + urlquote(acc.handle, safe=""),
                        group="author"))
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
                            else _("add_to_list"), data=acc, group="author"))
    approval = p.policy.can_quote if p.policy else ""
    if ctx.cfg["post"].get("quote_action", True) and approval in ("automatic", "manual"):
        out.append(Item("link", _("quote") if approval == "automatic" else _("quote_ask"),
                        url=make("quote", p.id), tool="quote"))
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
        out.append(Item("translate", _("translate"), tool="translate"))
    if ctx.quote_reply and ctx.me_id:
        out.append(Item("quote_reply", _("reply_quote")))
    if ctx.cfg["post"].get("invite", True):
        out.append(Item("link", _("invite"), url=make("invite", sid), group="thread"))
    out.append(Item("link", _("unbookmark") if p.mine.bookmarked else _("bookmark"),
                    url=make("bookmark", sid)))
    if unread:  # by hand, whatever read.mark_read says
        out.append(Item("link", _("mark_one_read"), url=make("readone", sid)))
        out.append(Item("link", _("mark_read_upto"), url=make("readupto", sid),
                        tool="read_upto", group="thread"))
    # who liked, who boosted; quotes of my post; my post out of someone's quote
    sup = ctx.supports
    if sup("reactions") or p.reactions:  # an emoji of mine on it (Akkoma, Misskey…)
        out.append(Item("link", _("react_menu") + "…", url=make("react", sid)))
    for kind, count in (("favourited_by", p.counts.likes), ("reblogged_by", p.counts.shares)):
        if sup(kind) and count:
            out.append(Item("link", _("who_" + kind + "_n", n=count), url=make(kind, sid),
                            group="more"))
    if p.card and p.card.url.startswith("https://") and sup("link_timeline"):
        out.append(Item("link", _("link_posts"), url=make("linkposts", sid), group="more"))
    if author.id == ctx.me_id and sup("quotes") and p.visibility in ("public", "unlisted"):
        out.append(Item("link", _("quotes_of"), url=make("quotes", sid), group="more"))
    quoted_post = p.quote.post if p.quote else None
    if quoted_post is not None and quoted_post.author.id == ctx.me_id and \
            sup("quotes") and author.id != ctx.me_id:
        out.append(Item("link", _("revoke_quote"), url=make("revokequote", sid),
                        group="more"))
    # always offered: a server that can't mute a thread (GoToSocial) gets it done here
    if ctx.thread_quiet is not None or sup("mute_thread"):
        muted = bool(p.mine.muted) or bool(ctx.thread_quiet and ctx.thread_quiet(entry))
        out.append(Item("link", _("unmute_thread" if muted else "mute_thread"),
                        url=make("unmutethread" if muted else "mutethread", sid),
                        tool="mute_thread", on=muted, group="thread"))
    if ctx.subscribed is not None:
        out.append(SEP)
        on = ctx.subscribed(entry)
        out.append(Item("link", _("unsub_thread" if on else "sub_thread"),
                        url=make("unsub" if on else "sub", sid), tool="sub_thread", on=on,
                        group="thread"))
    if sup("filter_status"):
        out.append(Item("link", _("hide_post"), url=make("hidepost", sid), group="more"))
    if ctx.cfg.get("lanes") is not None:  # which lanes take it, and by which rule
        out.append(Item("link", _("why_here"), url=make("why", sid), group="more"))
    if (ctx.cfg.get("debug") or {}).get("raw_json"):  # the post as the server gave it
        out.append(Item("link", _("raw_json"), url=make("raw", sid), group="more"))
    if (ctx.cfg.get("feed") or {}).get("around_post"):  # what came just before and after it
        out.append(Item("link", _("around_post"), url=make("around", sid), group="more"))
    if author.id != ctx.me_id:
        out.append(SEP)
        out.append(Item("link", _("mute_acct", acct=author.handle) + "…", url=make("mute", sid),
                        group="author"))
        # its hashtags, each muted in one click (into the filter of muted hashtags)
        most = int((ctx.cfg.get("feed") or {}).get("mute_tags_shown", MUTE_TAGS_SHOWN))
        for tag in list(dict.fromkeys(t.lower() for t in p.tags or ()))[:most]:
            out.append(Item("link", _("tag_mute", tag=tag), url=make("mutetag", urlquote(tag)),
                            group="author"))
        out.append(Item("link", _("block_acct", acct=author.handle), url=make("block", sid),
                        group="author"))
        domain = author.handle.partition("@")[2]
        if domain:
            out.append(Item("link", _("block_domain", domain=domain),
                            url=make("blockdomain", sid), group="author"))
        if not ctx.cfg["ui"]["arts_mode"]:
            out.append(Item("link", _("report"), url=make("report", sid), group="author"))
    mine = (entry.by if isinstance(entry, Share) else author).id == ctx.me_id
    if mine:
        out.append(SEP)
        out.append(Item("link", _("edit"), url=make("edit", sid), tool="edit"))
        if p.visibility in ("public", "unlisted"):
            out.append(Item("link", _("unpin") if p.mine.pinned else _("pin"),
                            url=make("unpin" if p.mine.pinned else "pin", p.id)))
        out.append(Item("link", _("delete"), url=make("delete", sid), tool="delete"))
        if ctx.cfg["post"].get("redraft", True):
            out.append(Item("link", _("redraft"), url=make("redraft", sid)))
    return out


__all__ = ["Button", "Ctx", "Item", "SEP", "VIS_KEY", "buttons", "can_translate", "menu",
           "vis_word"]
