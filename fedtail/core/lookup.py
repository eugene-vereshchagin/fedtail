"""Looking a post or a picture up elsewhere: a picture in the image searches
(media.image_search — Google Lens, Yandex, TinEye…), a post's claim in a fact-checker
(card.fact_check). Nothing is fetched here: each service is a link that opens in the
browser, its address a template the config gives ("Name|https://…{image}…").

The interfaces only show what these say — a picture's right click (a long press on the
phone; the terminal's picture screen) and a post's menu.

Placeholders, each URL-encoded: {image} — the picture's address; {query} — what the
post says, short (its link's title, else its first words); {link} — the link the post
shares ("" — none); {lang} — the interface's language.
"""

from __future__ import annotations

import re
from urllib.parse import quote

from ..i18n import current_language
from ..model import real
from ..model.text import html_to_text, without_quote_fallback

QUERY_CHARS = 120  # a fact-checker searches words: a whole post finds nothing


def services(lines):
    """The config's "Name|template" lines → [(name, template)]; a line without a name
    is named after its host, one without http(s):// is left out."""
    out = []
    for line in lines or ():
        name, bar, url = str(line).partition("|")
        if not bar:
            name, url = "", name
        name, url = name.strip(), url.strip()
        if not url.startswith(("https://", "http://")):
            continue
        out.append((name or url.split("/")[2], url))
    return out


def _fill(template, **values):
    return re.sub(r"\{(\w+)\}",
                  lambda m: quote(values.get(m.group(1), ""), safe="")
                  if m.group(1) in values else m.group(0), template)


def picture_url(m):
    """The address a search is given for a media: the picture itself, a video's still
    frame; "" — nothing to search by (audio without a cover)."""
    if m.kind == "image":
        return m.url or m.remote_url or m.preview
    return m.preview


def image_search(cfg, m):
    """[(name, url)]: where to look the picture up (media.image_search); [] — none."""
    pic = picture_url(m)
    if not pic.startswith(("https://", "http://")):
        return []
    lines = (cfg.get("ui") or {}).get("image_search") or ()
    return [(name, _fill(t, image=pic, lang=current_language()))
            for name, t in services(lines)]


def query(post):
    """What a fact-checker is asked about a post: the title of the link it shares, else
    its first sentence (mentions, tags and links left out), at most QUERY_CHARS."""
    p = real(post)
    if p.card and p.card.title.strip():
        words = p.card.title
    else:
        words = html_to_text(without_quote_fallback(p.text or ""))
        words = re.sub(r"https?://\S+|[@#][\w.@-]+", " ", words)
    words = " ".join(words.split())
    first = re.match(r"(.+?[.!?…])(\s|$)", words)
    if first and len(first.group(1)) >= 20:  # "Wow." alone says nothing
        words = first.group(1)
    if len(words) > QUERY_CHARS:
        words = words[:QUERY_CHARS].rsplit(" ", 1)[0]
    return words.strip()


def fact_check(cfg, post):
    """[(name, url)]: where to check what the post says (card.fact_check); [] — none:
    nothing to ask, or a followers' or direct post with card.fact_check_private off
    (its words would go to a stranger's service)."""
    feed = cfg.get("feed") or {}
    p = real(post)
    if p.visibility not in ("public", "unlisted") and not feed.get("fact_check_private"):
        return []
    words = query(p)
    if not words:
        return []
    link = p.card.url if p.card else ""
    return [(name, _fill(t, query=words, link=link, lang=current_language()))
            for name, t in services(feed.get("fact_check") or ())]
