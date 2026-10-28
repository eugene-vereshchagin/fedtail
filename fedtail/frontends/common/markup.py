"""The editor's formatting buttons (post.format_bar): bold, italic, strikethrough, code, a
link, a quote, a list — Markdown put around the selection (or taken off it, pressed again),
so nobody has to remember the marks. Every editor (Qt, GTK, the web page, the phone) draws
the buttons and asks here; this module knows only text and positions, no toolkit.

    e = apply("bold", "say hi", 4, 6)   # Edit(text="say **hi**", start=6, end=8)

Positions are in characters (Python str indices); an editor that counts otherwise (the
browser's UTF-16, Qt's) converts on its side — `utf16`/`from_utf16` here help.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Format:
    """One button: its name, the face on it, the i18n key of its tooltip, the shortcut
    (Qt's and GTK's spelling, "" — none)."""

    name: str
    face: str
    tip: str
    keys: str = ""


FORMATS = (
    Format("bold", "B", "fmt_bold", "Ctrl+B"),
    Format("italic", "I", "fmt_italic", "Ctrl+I"),
    Format("strike", "S", "fmt_strike", ""),
    Format("code", "</>", "fmt_code", ""),
    Format("link", "🔗", "fmt_link", "Ctrl+K"),
    Format("quote", "❝", "fmt_quote", ""),
    Format("list", "•", "fmt_list", ""),
)
BY_NAME = {f.name: f for f in FORMATS}
INLINE = {"bold": "**", "italic": "*", "strike": "~~", "code": "`"}
LINE = {"quote": "> ", "list": "- "}
URL_HINT = "https://"


@dataclass(frozen=True)
class Edit:
    """The text after a button, and the selection to leave (start == end: the cursor)."""

    text: str
    start: int
    end: int


def shown(cfg, markdown):
    """Are the buttons drawn? post.format_bar: "auto" — when the server understands
    Markdown (else the marks would come out as they are), "on", "off"."""
    mode = ((cfg or {}).get("post") or {}).get("format_bar", "auto")
    return mode == "on" or (mode == "auto" and bool(markdown))


def tip(fmt, words):
    """A button's tooltip: its words, and the shortcut when it has one."""
    return f"{words} ({fmt.keys})" if fmt.keys else words


def apply(name, text, start, end):
    """The text with format `name` put on [start, end) — or taken off, if it is there.

    Args:
        name: one of FORMATS' names.
        text: the editor's whole text.
        start, end: the selection (any order; equal — just the cursor).

    Returns:
        Edit: the new text and the selection to leave.
    """
    start, end = sorted((max(0, min(start, len(text))), max(0, min(end, len(text)))))
    if name in INLINE:
        mark = INLINE[name]
        if name == "code" and "\n" in text[start:end]:
            return _fence(text, start, end)
        return _inline(text, start, end, mark, name)
    if name in LINE:
        return _lines(text, start, end, LINE[name])
    if name == "link":
        return _link(text, start, end)
    raise KeyError(name)


# ---- around the selection: **…**, *…*, ~~…~~, `…` ----------------------------------------
def _run(text, i, step, ch):
    """How many `ch` in a row from i going by step (-1: to the left of i, 1: from i on)."""
    n = 0
    j = i - 1 if step < 0 else i
    while 0 <= j < len(text) and text[j] == ch:
        n += 1
        j += step
    return n


def _has(run, mark):
    """Does a run of marks around the text hold this one? "*" lives in runs of 1 and 3
    (***x*** is bold and italic), "**" in runs of 2 and 3; the others — at least theirs."""
    if mark == "*":
        return run in (1, 3)
    if mark == "**":
        return run >= 2
    return run >= len(mark)


def _inline(text, start, end, mark, name):
    ch = mark[0]
    k = len(mark)
    left, right = _run(text, start, -1, ch), _run(text, end, 1, ch)
    if _has(left, mark) and _has(right, mark) and (name != "code" or (left, right) == (1, 1)):
        # the marks stand just outside the selection: take them off
        text = text[:start - k] + text[start:end] + text[end + k:]
        return Edit(text, start - k, end - k)
    inner = text[start:end]
    if len(inner) >= 2 * k and inner.startswith(mark) and inner.endswith(mark):
        il, ir = _run(inner, 0, 1, ch), _run(inner, len(inner), -1, ch)
        if _has(il, mark) and _has(ir, mark) and il + ir <= len(inner):
            # selected with its marks: take them off, keep the words selected
            text = text[:start] + inner[k:len(inner) - k] + text[end:]
            return Edit(text, start, end - 2 * k)
    # a selection's spaces at its edges stay outside the marks: "**word** " not "**word **"
    lead = len(inner) - len(inner.lstrip())
    trail = len(inner) - len(inner.rstrip()) if inner.strip() else 0
    s, e = start + lead, end - trail
    text = text[:s] + mark + text[s:e] + mark + text[e:]
    return Edit(text, s + k, e + k)


def _fence(text, start, end):
    """Several lines as code: a ``` block on lines of its own (or taken off, if the
    selection is one already)."""
    inner = text[start:end]
    body = inner.strip("\n")
    if body.startswith("```") and body.endswith("```") and body.count("\n") >= 1:
        lines = body.split("\n")
        plain = "\n".join(lines[1:-1])
        text = text[:start] + plain + text[end:]
        return Edit(text, start, start + len(plain))
    before = "" if start == 0 or text[start - 1] == "\n" else "\n"
    after = "" if end == len(text) or text[end] == "\n" else "\n"
    block = f"{before}```\n{body}\n```{after}"
    text = text[:start] + block + text[end:]
    first = start + len(before) + 4
    return Edit(text, first, first + len(body))


# ---- at the start of each line: "> ", "- " ---------------------------------------------
def _lines(text, start, end, prefix):
    a = text.rfind("\n", 0, start) + 1
    stop = end - 1 if end > start and text[end - 1:end] == "\n" else end
    b = text.find("\n", stop)
    b = len(text) if b < 0 else b
    lines = text[a:b].split("\n")
    bare = prefix.rstrip()
    filled = [ln for ln in lines if ln.strip()]
    off = bool(filled) and all(ln.startswith(prefix) or ln == bare for ln in filled)
    if off:
        new = [ln[len(prefix):] if ln.startswith(prefix) else
               ("" if ln == bare else ln) for ln in lines]
    else:
        new = [prefix + ln if ln.strip() or len(lines) == 1 else ln for ln in lines]
    block = "\n".join(new)
    text = text[:a] + block + text[b:]
    if start == end:  # the cursor moves with its line's words
        shift = len(new[0]) - len(lines[0])
        pos = max(a, start + shift)
        return Edit(text, pos, pos)
    return Edit(text, a, a + len(block))


# ---- a link: [words](address) -----------------------------------------------------------
def _looks_like_url(s):
    return s.startswith(("http://", "https://")) and " " not in s


def _link(text, start, end):
    """The selection becomes the link's words and the address is left selected to type
    over; a selected address becomes the address, the cursor where the words go."""
    inner = text[start:end].strip()
    if _looks_like_url(inner):
        made = f"[]({inner})"
        text = text[:start] + made + text[end:]
        return Edit(text, start + 1, start + 1)
    words = text[start:end]
    made = f"[{words}]({URL_HINT})"
    text = text[:start] + made + text[end:]
    s = start + len(words) + 3
    return Edit(text, s, s + len(URL_HINT))


# ---- positions for editors that count in UTF-16 (the browser, Qt) -----------------------
def utf16(text, i):
    """A str index → the same place counted in UTF-16 code units."""
    return len(text[:i].encode("utf-16-le")) // 2


def from_utf16(text, u):
    """A UTF-16 position → a str index (inside a surrogate pair: after it)."""
    n = 0
    for i, ch in enumerate(text):
        if n >= u:
            return i
        n += 2 if ord(ch) > 0xFFFF else 1
    return len(text)
