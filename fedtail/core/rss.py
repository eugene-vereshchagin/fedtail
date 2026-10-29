"""RSS and Atom feeds as a source of a lane of rules (`source = "rss:<address>"`,
feeds.md §2.1): each item becomes a read-only post of the feed — its title and summary,
its link as the post's address and card. Such a post lives only here: no server knows
it, so it can be opened (in the browser), read, bookmarked locally — not liked, boosted
or answered (core/app.py says so instead of asking a server).

Fetched like other servers' things (core/remote.py): no token, public addresses only,
the size capped; at most every lanes.extra_minutes (as the wider lanes).
"""

from __future__ import annotations

import hashlib
import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

log = logging.getLogger(__name__)

PREFIX = "rss-"          # the id of a post that came from a feed
FEED_MAX = 4 * 1024 * 1024
ITEMS_MAX = 60
SUMMARY_MAX = 1200

_TAGS = re.compile(r"<[^>]+>")


def is_rss(status_or_id):
    sid = status_or_id.get("id") if isinstance(status_or_id, dict) else status_or_id
    return isinstance(sid, str) and sid.startswith(PREFIX)


def _local(tag):
    return tag.rsplit("}", 1)[-1].lower()


def _child(el, *names):
    for c in el:
        if _local(c.tag) in names:
            return c
    return None


def _text(el, *names):
    c = _child(el, *names)
    return (c.text or "").strip() if c is not None and c.text else ""


def _when(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        d = parsedate_to_datetime(text)  # RSS: RFC 822
    except (TypeError, ValueError, IndexError):
        try:
            d = datetime.fromisoformat(text.replace("Z", "+00:00"))  # Atom: RFC 3339
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=UTC)
    return d.astimezone(UTC)


def _iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _summary(raw):
    """A feed's HTML summary as safe short HTML: tags out, the text escaped, paragraphs
    kept as line breaks."""
    text = html.unescape(_TAGS.sub(" ", raw or ""))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text).strip()
    if len(text) > SUMMARY_MAX:
        text = text[:SUMMARY_MAX].rsplit(" ", 1)[0] + "…"
    return "<br>".join(html.escape(line) for line in text.split("\n") if line)


def parse(body, feed_url, now=None):
    """The feed's items as posts (Mastodon-shaped dicts), newest first; [] when it
    doesn't read as RSS or Atom."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        log.info("rss %s: not a feed (%s)", urlsplit(feed_url).hostname, e)
        return []
    kind = _local(root.tag)
    if kind == "rss":
        channel = _child(root, "channel")
        if channel is None:
            return []
        title, link = _text(channel, "title"), _text(channel, "link")
        items = [c for c in channel if _local(c.tag) == "item"]
    elif kind == "feed":  # Atom
        title = _text(root, "title")
        alt = next((c for c in root if _local(c.tag) == "link"
                    and c.get("rel", "alternate") == "alternate"), None)
        link = alt.get("href", "") if alt is not None else ""
        items = [c for c in root if _local(c.tag) == "entry"]
    elif kind == "rdf":  # RSS 1.0
        channel = _child(root, "channel")
        title = _text(channel, "title") if channel is not None else ""
        link = _text(channel, "link") if channel is not None else ""
        items = [c for c in root if _local(c.tag) == "item"]
    else:
        return []
    host = urlsplit(link or feed_url).hostname or urlsplit(feed_url).hostname or "feed"
    account = {"id": "rss:" + host, "acct": host, "username": host,
               "display_name": title or host, "url": link or feed_url, "avatar_static": "",
               "avatar": "", "bot": True, "note": "", "fields": []}
    now = now or datetime.now(UTC)
    out = []
    for it in items[:ITEMS_MAX]:
        if kind == "feed":
            ln = next((c for c in it if _local(c.tag) == "link"
                       and c.get("rel", "alternate") == "alternate"), None)
            url = ln.get("href", "") if ln is not None else ""
            when = _when(_text(it, "published", "updated"))
            body_html = _text(it, "summary", "content")
            guid = _text(it, "id") or url
        else:
            url = _text(it, "link")
            when = _when(_text(it, "pubdate", "date"))
            body_html = _text(it, "description", "encoded")
            guid = _text(it, "guid") or url
        head = _text(it, "title")
        if not (head or body_html or url):
            continue
        sid = PREFIX + hashlib.sha1((feed_url + "\n" + (guid or head)).encode()).hexdigest()[:16]
        content = (f"<p><b>{html.escape(head)}</b></p>" if head else "") + \
            (f"<p>{_summary(body_html)}</p>" if body_html else "")
        st = {"id": sid, "account": account, "in_reply_to_id": None,
              "in_reply_to_account_id": None,
              "created_at": _iso(min(when or now, now)), "visibility": "public",
              "content": content, "spoiler_text": "", "sensitive": False, "mentions": [],
              "tags": [], "media_attachments": [], "replies_count": 0,
              "favourites_count": 0, "reblogs_count": 0, "favourited": False,
              "reblogged": False, "url": url or link or feed_url,
              "uri": url or (feed_url + "#" + sid), "fedtail_rss": feed_url}
        if url:
            st["card"] = {"url": url, "title": head or url,
                          "provider_name": host, "description": "", "image": None}
        out.append(st)
    out.sort(key=lambda s: (s["created_at"], s["id"]), reverse=True)
    return out


def fetch(url, own_hosts=(), timeout=12):
    """The feed at url, its items as posts; [] when it can't be had."""
    import requests

    from ..version import USER_AGENT
    from . import remote
    host = urlsplit(url).hostname or "?"
    try:
        with remote.open_url(requests, url, timeout=timeout,
                             headers={"User-Agent": USER_AGENT,
                                      "Accept": "application/rss+xml, application/atom+xml, "
                                                "application/xml;q=0.9, */*;q=0.5"},
                             own_hosts=own_hosts) as r:
            if r.status_code != 200:
                log.info("rss %s: %s", host, r.status_code)
                return []
            body = remote.read(r, FEED_MAX)
    except (requests.RequestException, OSError) as e:
        log.info("rss %s: %s", host, e)
        return []
    return parse(body, url)
