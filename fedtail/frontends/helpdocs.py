"""The in-app help and the "What's this?" hints, without any GUI.

The help is Markdown in ``fedtail/data/help/<lang>/``:

* ``index.md`` lists the pages in order (``- [Title](name.md) — what it's about``);
* each page is light reading with links to the deep dive;
* ``ref/`` holds the deep dive itself — copies of ``docs/<lang>/features.md``,
  ``config.md`` and ``comparison.md`` that ``tools/docs_build.py`` keeps there, so the
  help works offline and in every build;
* ``hints.toml`` — the longer hint for a button, keyed by the i18n key of its tooltip
  (see `hint_for`).

A frontend asks for `pages`, `page` (the Markdown ready to show), `resolve` (where a
clicked link goes) and `search`; the Qt help panel and the hint mode are the first
users, the TUI and the web interface may be next.
"""

import html
import posixpath
import re
import tomllib
from dataclasses import dataclass
from importlib import resources

from .. import i18n, version

LANGS = ("ru", "en")
REF = "ref"  # the deep dive's folder inside a language's help
_INCLUDE = re.compile(r"^<!-- /?include[^>]*-->\n?", re.M)
_INDEX_LINE = re.compile(r"^- \[(?P<title>[^\]]+)\]\((?P<name>[\w./-]+)\.md\)")
_HEADING = re.compile(r"^(#{1,6}) +(.+?)\s*$", re.M)


def _root(lang):
    return resources.files("fedtail").joinpath("data", "help", lang)


def language(lang=None):
    """The help's language: the interface's one, English when there's no such help."""
    lang = lang or i18n.current_language()
    return lang if lang in LANGS else "en"


def _read(lang, name):
    f = _root(lang).joinpath(*f"{name}.md".split("/"))
    return f.read_text("utf-8") if f.is_file() else None


def exists(lang, name):
    return _read(lang, name) is not None


def slug(title):
    """A heading's anchor, the way GitHub makes it: "Что нового и что дальше" →
    "что-нового-и-что-дальше" (markup and punctuation dropped)."""
    t = re.sub(r"[`*_\[\]()]", "", title).strip().lower()
    t = re.sub(r"[^\w\- ]", "", t)
    return t.replace(" ", "-")


@dataclass
class Page:
    name: str  # "reading", "ref/features"
    title: str
    about: str = ""
    deep: bool = False  # one of the deep-dive pages


def pages(lang=None):
    """[Page] in the order of index.md, then the deep dive (ref/)."""
    lang = language(lang)
    out = [Page("index", _title(lang, "index"))]
    for line in (_read(lang, "index") or "").splitlines():
        m = _INDEX_LINE.match(line)
        if m:
            about = line[m.end():].lstrip(" —-").strip()
            out.append(Page(m.group("name"), m.group("title"), about))
    ref = _root(lang).joinpath(REF)
    if ref.is_dir():
        order = {"features": 0, "config": 1, "comparison": 2}
        for f in sorted(ref.iterdir(), key=lambda f: (order.get(f.name[:-3], 9), f.name)):
            if f.name.endswith(".md"):
                name = f"{REF}/{f.name[:-3]}"
                out.append(Page(name, _title(lang, name), deep=True))
    return out


def _title(lang, name):
    m = _HEADING.search(_read(lang, name) or "")
    return re.sub(r"[`*]", "", m.group(2)) if m else name


def page(lang, name):
    """The page's Markdown as a viewer should get it: the include markers gone, the
    <details> folds opened (Qt's Markdown has no folding), <br> in tables made a dot."""
    text = _read(language(lang), name)
    if text is None:
        return None
    text = _INCLUDE.sub("", text)
    text = re.sub(r"^</?details>\s*$\n?", "", text, flags=re.M)
    text = re.sub(r"<details><summary>(.*?)</summary>", r"**\1**", text)
    text = text.replace("<br>", " · ")
    return text


def headings(lang, name):
    """[(level, title, anchor)] of a page — a table of contents, and the anchors links
    may point at."""
    out = []
    for m in _HEADING.finditer(page(lang, name) or ""):
        title = re.sub(r"[`*]", "", m.group(2))
        out.append((len(m.group(1)), title, slug(m.group(2))))
    return out


@dataclass
class Target:
    page: str = ""  # a help page to show…
    anchor: str = ""  # …and where on it
    url: str = ""  # or an address for the browser


def _github(path):
    return f"{version.HOMEPAGE}/blob/main/{path.lstrip('/')}"


def resolve(link, lang, current="index"):
    """Where a link on the page `current` goes. Pages of the help stay in the help; the
    repository's documents (links from its root, /docs/en/features.md) come from the
    deep dive when it has them and from GitHub otherwise; the web goes to the browser."""
    lang = language(lang)
    link = link.strip()
    if re.match(r"^[a-z][a-z0-9+.-]*:", link, re.I):  # https:, mailto:…
        return Target(url=link)
    path, _, anchor = link.partition("#")
    if not path:
        return Target(page=current, anchor=anchor)
    if path.startswith("/"):
        m = re.match(r"^/docs/(\w\w)/([\w-]+)\.md$", path)
        if m and exists(lang, f"{REF}/{m.group(2)}"):
            return Target(page=f"{REF}/{m.group(2)}", anchor=anchor)
        return Target(url=_github(path) + (f"#{anchor}" if anchor else ""))
    here = posixpath.dirname(current)
    name = posixpath.normpath(posixpath.join(here, path))
    if name.endswith(".md"):
        name = name[:-3]
    if not name.startswith("..") and exists(lang, name):
        return Target(page=name, anchor=anchor)
    # outside the help (../../docs/…): the repository on GitHub
    repo = posixpath.normpath(posixpath.join("fedtail/data/help", lang, here, path))
    return Target(url=_github(repo) + (f"#{anchor}" if anchor else ""))


def plain(markdown):
    """The text of a page without its markup — what search looks through."""
    t = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", markdown)
    t = re.sub(r"[`*_#>|]", " ", t)
    return re.sub(r"\s+", " ", t)


def _stem(word):
    """Enough of a word to find its other forms: "шторка" finds "шторку", "threads"
    finds "thread" — the ending goes, at least four letters stay."""
    return word if len(word) <= 4 else word[:max(4, len(word) - 2)]


def search(lang, query, limit=50):
    """[(Page, matches)] — the pages where every word of the query is (in any of its
    forms), the most matches first."""
    words = [_stem(w) for w in query.lower().split() if w]
    if not words:
        return []
    out = []
    for p in pages(lang):
        text = plain(page(lang, p.name) or "").lower()
        if all(w in text for w in words):
            out.append((p, sum(text.count(w) for w in words)))
    out.sort(key=lambda x: -x[1])
    return out[:limit]


# ---- "What's this?" ---------------------------------------------------------------

def hints(lang=None):
    """{i18n key: {"text", "config"?, "help"?}} from hints.toml of the language."""
    lang = language(lang)
    f = _root(lang).joinpath("hints.toml")
    return tomllib.loads(f.read_text("utf-8")) if f.is_file() else {}


def _norm(text):
    t = (text or "").strip().split("\n", 1)[0]
    t = re.sub(r"\s*\((?:[^()]*)\)\s*$", "", t)  # " (Ctrl+N)", " (Alt+3)"
    return t.rstrip(" .…:").strip().lower()


_index_cache = {}


def _index(lang):
    """{the shown text of a string: [its i18n keys]} for one language."""
    if lang not in _index_cache:
        idx = {}
        for key, value in i18n.strings(lang).items():
            if isinstance(value, str) and value:
                idx.setdefault(_norm(value), []).append(key)
        _index_cache[lang] = idx
    return _index_cache[lang]


def hint_for(tooltip, key=None, lang=None):
    """The hint for a widget: by its own `key` (a widget may name one) or by its
    tooltip — the text is looked up among the interface's strings, and the first of
    their keys that has a hint wins. None: nothing more to say than the tooltip."""
    lang = language(lang)
    table = hints(lang)
    if key and key in table:
        return key, table[key]
    for k in _index(i18n.current_language() or lang).get(_norm(tooltip), []):
        if k in table:
            return k, table[k]
    return None


def hint_html(tooltip, hint, lang=None):
    """The rich tooltip of "What's this?": the button's own words, the hint, the config
    key that changes it and where the help says more."""
    lang = language(lang)
    first = (tooltip or "").strip().split("\n", 1)[0]
    parts = []
    if first:
        parts.append(f"<b>{html.escape(first)}</b>")
    parts.append(html.escape(hint["text"].strip()).replace("\n", "<br>"))
    small = []
    if hint.get("config"):
        small.append(i18n._("hint_config", opt=html.escape(hint["config"])))
    if hint.get("help"):
        name, _sep, anchor = hint["help"].partition("#")
        name = name[:-3] if name.endswith(".md") else name
        title = next((p.title for p in pages(lang) if p.name == name), name)
        section = next((t for _lvl, t, a in headings(lang, name) if anchor and a == anchor), "")
        where = f"{title} → {section}" if section else title
        small.append(i18n._("hint_help", page=html.escape(where)))
    if small:
        parts.append("<small>" + "<br>".join(small) + "</small>")
    return "<p>" + "</p><p>".join(parts) + "</p>"
