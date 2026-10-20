"""Mastodon API JSON → fedtail.model.

The only place that knows what a status, an account or a notification looks like on
the wire. Servers differ: GoToSocial, Akkoma, Pleroma, glitch-soc and Mastodon of
various versions add, rename or leave out fields — every lookup here is forgiving, and
an odd value turns into an empty one, never an exception.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ...model import (
    Account,
    Activity,
    Card,
    Counts,
    Emoji,
    Field,
    Media,
    Mention,
    Mine,
    Policy,
    Poll,
    PollOption,
    Post,
    Quote,
    Reaction,
    Ref,
    Relationship,
    Share,
)
from . import PROTO

# Mastodon's visibility → ours; "local" is Akkoma/Pleroma's public-but-not-federated
VISIBILITY = {"public": "public", "unlisted": "unlisted", "private": "followers",
              "direct": "direct", "limited": "followers", "local": "public"}

MEDIA_KIND = {"image": "image", "gifv": "gifv", "video": "video", "audio": "audio"}

ACTIVITY_KIND = {
    "mention": "mention", "status": "post", "reblog": "share", "favourite": "like",
    "follow": "follow", "follow_request": "follow_request", "poll": "poll",
    "update": "update", "quote": "quote", "quoted_update": "update",
    "pleroma:emoji_reaction": "reaction", "reaction": "reaction",
    "admin.sign_up": "notice", "admin.report": "notice",
    "severed_relationships": "notice", "moderation_warning": "notice",
}

QUOTE_DEPTH = 2  # a quote inside a quote inside a post — no deeper


def sort_key(created_at, item_id):
    """Chronological text key that works across id formats (ULID, snowflake): the time,
    then the id left-padded. Same as Store.sort_key, which will move here (stage 3)."""
    return f"{created_at or ''}|{str(item_id).rjust(32, '0')}"


def when(value):
    """An ISO time (or date) from the server as an aware datetime in UTC; None when
    missing or unreadable."""
    if not value or not isinstance(value, str):
        return None
    try:
        t = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return t.replace(tzinfo=UTC) if t.tzinfo is None else t.astimezone(UTC)


def _str(v):
    return v if isinstance(v, str) else ""


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return 0


def _list(v):
    return v if isinstance(v, list) else []


def _dict(v):
    return v if isinstance(v, dict) else {}


def _ref(profile, oid):
    return Ref(PROTO, profile, str(oid or ""))


def emojis(raw):
    return tuple(Emoji(_str(e.get("shortcode")), _str(e.get("url")),
                       _str(e.get("static_url")))
                 for e in _list(raw) if isinstance(e, dict) and e.get("shortcode"))


def account(raw, profile=""):
    """An account (a Person, a Service, a Group)."""
    raw = _dict(raw)
    moved = raw.get("moved")
    return Account(
        ref=_ref(profile, raw.get("id")),
        handle=_str(raw.get("acct")),
        username=_str(raw.get("username")) or _str(raw.get("acct")).split("@")[0],
        name=_str(raw.get("display_name")),
        url=_str(raw.get("url")),
        uri=_str(raw.get("uri")),
        avatar=_str(raw.get("avatar")),
        avatar_static=_str(raw.get("avatar_static")) or _str(raw.get("avatar")),
        header=_str(raw.get("header")),
        header_static=_str(raw.get("header_static")) or _str(raw.get("header")),
        note=_str(raw.get("note")),
        fields=tuple(Field(_str(f.get("name")), _str(f.get("value")),
                           when(f.get("verified_at")))
                     for f in _list(raw.get("fields")) if isinstance(f, dict)),
        emojis=emojis(raw.get("emojis")),
        bot=bool(raw.get("bot")),
        group=bool(raw.get("group")),
        locked=bool(raw.get("locked")),
        discoverable=raw.get("discoverable") if isinstance(raw.get("discoverable"), bool)
        else None,
        created=when(raw.get("created_at")),
        last_post=when(raw.get("last_status_at")),
        posts=_int(raw.get("statuses_count")),
        followers=_int(raw.get("followers_count")),
        following=_int(raw.get("following_count")),
        moved=account(moved, profile) if isinstance(moved, dict) and moved.get("id")
        else None,
    )


def media(raw, profile=""):
    raw = _dict(raw)
    meta = _dict(raw.get("meta"))
    size = _dict(meta.get("original")) or _dict(meta.get("small"))
    focus = _dict(meta.get("focus"))
    try:
        point = (float(focus["x"]), float(focus["y"])) if focus else None
    except (KeyError, TypeError, ValueError):
        point = None
    try:
        duration = float(size.get("duration") or meta.get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.0
    return Media(
        ref=_ref(profile, raw.get("id")),
        kind=MEDIA_KIND.get(raw.get("type"), "unknown"),
        url=_str(raw.get("url")) or _str(raw.get("remote_url")),
        preview=_str(raw.get("preview_url")),
        remote_url=_str(raw.get("remote_url")),
        alt=_str(raw.get("description")),
        width=_int(size.get("width")),
        height=_int(size.get("height")),
        duration=duration,
        focus=point,
        blurhash=_str(raw.get("blurhash")),
    )


def poll(raw, profile=""):
    if not isinstance(raw, dict) or not isinstance(raw.get("options"), list) \
            or not raw["options"]:
        return None
    voters = raw.get("voters_count")
    return Poll(
        ref=_ref(profile, raw.get("id")),
        options=tuple(PollOption(_str(o.get("title")),
                                 o["votes_count"] if isinstance(o.get("votes_count"), int)
                                 else None,
                                 emojis(raw.get("emojis")))
                      for o in _list(raw.get("options")) if isinstance(o, dict)),
        multiple=bool(raw.get("multiple")),
        expires=when(raw.get("expires_at")),
        expired=bool(raw.get("expired")),
        votes=_int(raw.get("votes_count")),
        voters=voters if isinstance(voters, int) else None,
        voted=bool(raw.get("voted")),
        my_votes=tuple(v for v in _list(raw.get("own_votes")) if isinstance(v, int)),
    )


def card(raw):
    if not isinstance(raw, dict) or not raw.get("url"):
        return None
    return Card(url=_str(raw.get("url")), title=_str(raw.get("title")),
                description=_str(raw.get("description")), image=_str(raw.get("image")),
                provider=_str(raw.get("provider_name")), kind=_str(raw.get("type")) or "link",
                author=_str(raw.get("author_name")), width=_int(raw.get("width")),
                height=_int(raw.get("height")))


def quote(raw, profile="", depth=0):
    """The quoted post, in whichever shape the server gives it: Mastodon 4.5+
    {"state", "quoted_status" | "quoted_status_id"}; Akkoma, Fedibird — the whole status
    in "quote" (or pleroma.quote); older ones — just "quote_id"."""
    q = raw.get("quote") or _dict(raw.get("pleroma")).get("quote")
    if not isinstance(q, dict):
        qid = raw.get("quote_id") or _dict(raw.get("pleroma")).get("quote_id")
        return Quote("accepted", None, str(qid)) if qid else None
    if "account" in q and "content" in q:  # a whole status
        inner, state, qid = q, "accepted", q.get("id")
    else:
        inner = q.get("quoted_status")
        state = _str(q.get("state")) or "accepted"
        qid = _dict(inner).get("id") or q.get("quoted_status_id")
    got = post(inner, profile, depth + 1) if isinstance(inner, dict) and inner.get("id") \
        and depth < QUOTE_DEPTH else None
    if isinstance(got, Share):
        got = got.post
    return Quote(state, got, str(qid) if qid else None)


def reactions(raw):
    lst = raw.get("emoji_reactions")
    if not isinstance(lst, list):
        lst = _dict(raw.get("pleroma")).get("emoji_reactions")
    return tuple(Reaction(_str(r.get("name")), _int(r.get("count")), bool(r.get("me")),
                          _str(r.get("url")))
                 for r in _list(lst) if isinstance(r, dict) and r.get("name"))


def _audience(rule):
    rule = _dict(rule)
    return (tuple(str(x) for x in _list(rule.get("always")) or _list(rule.get("automatic"))),
            tuple(str(x) for x in _list(rule.get("with_approval")) or _list(rule.get("manual"))))


def policy(raw):
    """GoToSocial's interaction_policy and Mastodon's quote_approval, together."""
    ip, qa = raw.get("interaction_policy"), raw.get("quote_approval")
    if not isinstance(ip, dict) and not isinstance(qa, dict):
        return None
    ip = _dict(ip)
    reply, reply_a = _audience(ip.get("can_reply"))
    share, share_a = _audience(ip.get("can_reblog"))
    like, like_a = _audience(ip.get("can_favourite"))
    quote_, quote_a = _audience(qa)
    return Policy(reply=reply, reply_approval=reply_a, share=share, share_approval=share_a,
                  like=like, like_approval=like_a, quote=quote_, quote_approval=quote_a,
                  can_quote=_str(_dict(qa).get("current_user")))


def _filters(raw):
    warn, hide = [], False
    for f in _list(raw.get("filtered")):
        flt = _dict(_dict(f).get("filter"))
        if flt.get("filter_action") == "hide":
            hide = True
        elif flt.get("title"):
            warn.append(_str(flt.get("title")))
    return tuple(warn), hide


def post(raw, profile="", _depth=0):
    """A status: a Post, or a Share when it is a boost (the post inside)."""
    raw = _dict(raw)
    created_at = raw.get("created_at")
    sort = sort_key(created_at, raw.get("id"))
    vis_raw = _str(raw.get("visibility"))
    visibility = VISIBILITY.get(vis_raw, "public")
    if isinstance(raw.get("reblog"), dict) and raw["reblog"].get("id"):
        inner = post(raw["reblog"], profile, _depth)
        return Share(ref=_ref(profile, raw.get("id")), by=account(raw.get("account"), profile),
                     post=inner.post if isinstance(inner, Share) else inner,
                     created=when(created_at), sort=sort, visibility=visibility)
    pleroma = _dict(raw.get("pleroma"))
    warn, hide = _filters(raw)
    return Post(
        ref=_ref(profile, raw.get("id")),
        author=account(raw.get("account"), profile),
        created=when(created_at),
        sort=sort,
        text=_str(raw.get("content")),
        source=_str(raw.get("text")),
        source_type=_str(raw.get("content_type")),
        warning=_str(raw.get("spoiler_text")),
        sensitive=bool(raw.get("sensitive")),
        visibility=visibility,
        local_only=vis_raw == "local" or bool(raw.get("local_only"))
        or bool(pleroma.get("local")),
        lang=_str(raw.get("language")),
        url=_str(raw.get("url")) or _str(raw.get("uri")),
        uri=_str(raw.get("uri")),
        reply_to=str(raw["in_reply_to_id"]) if raw.get("in_reply_to_id") else None,
        reply_to_author=str(raw["in_reply_to_account_id"])
        if raw.get("in_reply_to_account_id") else None,
        edited=when(raw.get("edited_at")),
        media=tuple(media(m, profile) for m in _list(raw.get("media_attachments"))
                    if isinstance(m, dict)),
        poll=poll(raw.get("poll"), profile),
        card=card(raw.get("card")),
        quote=quote(raw, profile, _depth),
        mentions=tuple(Mention(_ref(profile, m.get("id")), _str(m.get("acct")),
                               _str(m.get("username")), _str(m.get("url")),
                               _str(m.get("uri")))
                       for m in _list(raw.get("mentions")) if isinstance(m, dict)),
        tags=tuple(_str(t.get("name")) for t in _list(raw.get("tags"))
                   if isinstance(t, dict) and t.get("name")),
        emojis=emojis(raw.get("emojis")),
        reactions=reactions(raw),
        counts=Counts(replies=_int(raw.get("replies_count")),
                      shares=_int(raw.get("reblogs_count")),
                      likes=_int(raw.get("favourites_count")),
                      quotes=_int(raw.get("quotes_count"))),
        mine=Mine(liked=bool(raw.get("favourited")), shared=bool(raw.get("reblogged")),
                  bookmarked=bool(raw.get("bookmarked")), muted=bool(raw.get("muted")),
                  pinned=bool(raw.get("pinned"))),
        policy=policy(raw),
        app=_str(_dict(raw.get("application")).get("name")),
        filtered=warn,
        hidden=hide,
    )


def _notice(raw):
    """What a server's own notice says, in a line."""
    if raw.get("moderation_warning"):
        w = _dict(raw["moderation_warning"])
        return " ".join(x for x in (_str(w.get("action")), _str(w.get("text"))) if x)
    ev = raw.get("event") or raw.get("relationship_severance_event")
    if isinstance(ev, dict):
        return " ".join(x for x in (_str(ev.get("type")), _str(ev.get("target_name"))) if x)
    if raw.get("report"):
        return _str(_dict(raw["report"]).get("comment"))
    return ""


def activity(raw, profile=""):
    """A notification."""
    raw = _dict(raw)
    st = raw.get("status")
    p = post(st, profile) if isinstance(st, dict) and st.get("id") else None
    if isinstance(p, Share):
        p = p.post
    who = raw.get("account")
    return Activity(
        ref=_ref(profile, raw.get("id")),
        kind=ACTIVITY_KIND.get(raw.get("type"), "other"),
        who=account(who, profile) if isinstance(who, dict) and who.get("id") else None,
        created=when(raw.get("created_at")),
        sort=sort_key(raw.get("created_at"), raw.get("id")),
        post=p,
        emoji=_str(raw.get("emoji")),
        notice=_notice(raw),
        group_key=_str(raw.get("group_key")),
    )


def relationship(raw):
    raw = _dict(raw)
    return Relationship(
        following=bool(raw.get("following")), followed_by=bool(raw.get("followed_by")),
        requested=bool(raw.get("requested")), requested_by=bool(raw.get("requested_by")),
        muting=bool(raw.get("muting")), blocking=bool(raw.get("blocking")),
        blocked_by=bool(raw.get("blocked_by")), notifying=bool(raw.get("notifying")),
        showing_shares=raw.get("showing_reblogs") is not False,
        endorsed=bool(raw.get("endorsed")), note=_str(raw.get("note")))


# ours → the API's, for what fedtail sends
VISIBILITY_OUT = {"public": "public", "unlisted": "unlisted", "followers": "private",
                  "direct": "direct"}


def visibility_out(v):
    """Our visibility as the API names it; the API's own names pass as they are."""
    return VISIBILITY_OUT.get(v, v if v in VISIBILITY else "public")


def visibility_in(v):
    return VISIBILITY.get(v, v if v in VISIBILITY_OUT else "public")
