"""What Ctrl+F looks through in a post, and how it matches. No Qt: testable."""

from ..core.model import html_to_text, real


def fold(s):
    """Case- and ё-insensitive, so «ежик» finds «Ёжик»."""
    return (s or "").casefold().replace("ё", "е")


def haystack(status, short_id=None):
    """Everything a reader would recognise a post by: text, warning, picture
    descriptions, author (name and @address), who boosted it, its #id."""
    st = real(status)
    parts = [html_to_text(st.get("content", "")), st.get("spoiler_text", "")]
    parts += [m.get("description") or "" for m in st.get("media_attachments", [])]
    for acc in (st.get("account", {}), status.get("account", {}) if status is not st else {}):
        parts += [acc.get("display_name", ""), "@" + acc.get("acct", "")]
    if short_id:
        parts.append("#" + short_id)
    return fold("\n".join(p for p in parts if p))


def matches(query, hay):
    """Every word of the query is somewhere in the post, in any order."""
    words = fold(query).split()
    return bool(words) and all(w in hay for w in words)
