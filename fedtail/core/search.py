"""What Ctrl+F looks through in a post, and how it matches. No Qt: testable."""

from ..model.text import fold, matches  # noqa: F401 — one definition, with the model
from .model import html_to_text, real
from .proto import raw


def haystack(status, short_id=None):
    """Everything a reader would recognise a post by: text, warning, picture
    descriptions, author (name and @address), who boosted it, its #id."""
    st = real(status)
    parts = [html_to_text(st.get("content", "")), raw.warning(st)]
    parts += [m.get("description") or "" for m in raw.media(st)]
    for acc in (st.get("account", {}), status.get("account", {}) if status is not st else {}):
        parts += [raw.name(acc), "@" + raw.handle(acc)]
    if short_id:
        parts.append("#" + short_id)
    return fold("\n".join(p for p in parts if p))
