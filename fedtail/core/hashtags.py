"""Hashtags written in one case: a screen reader reads #georgianews as one long
mumble, #GeorgiaNews as two words. The composer gently points those out."""

import re

_TAG = re.compile(r"(?:^|(?<=\s))#(\w+)", re.UNICODE)
FLAT_MIN = 8  # shorter tags are usually one word anyway


def flat_tags(text):
    """Tags of letters only, at least FLAT_MIN long, without a capital inside."""
    out = []
    for tag in _TAG.findall(text or ""):
        if len(tag) >= FLAT_MIN and tag.isalpha() and tag[1:] == tag[1:].lower():
            if tag not in out:
                out.append(tag)
    return out
