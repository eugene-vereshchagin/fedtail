"""Spell checking for the editor, without a toolkit: which words of a text look wrong,
what to put instead, and a dictionary of my own.

The dictionaries are the system's, through Enchant (what GNOME and LibreOffice use; it
reads Hunspell's, Aspell's and others): pyenchant when it is installed (on Windows its
wheel brings Enchant and dictionaries along), else libenchant-2 straight through ctypes
(Debian and most Linux desktops have it). Neither there — no checking, and the editors
say so once (spell_unavailable); nothing else changes.

A word is fine when any of the languages takes it (a Russian post with English words in
it is the usual thing), or it is in my own dictionary (<config folder>/spelling.txt, one
word a line — "Add to dictionary" writes there, any editor may too). Links, @names,
#tags, :emoji:, `code` and words with digits are never checked.

A word is judged only by dictionaries of its own script: a Cyrillic word by ru / uk…,
a Latin one by en / de…. The languages asked for have none of its script (an English
interface, a Russian post — 28.10: every word underlined) — the installed dictionaries
of that script are taken; none installed — the word isn't judged at all."""

from __future__ import annotations

import ctypes
import ctypes.util
import logging
import re
import threading
import unicodedata
from pathlib import Path

log = logging.getLogger(__name__)

# what is not a word to check: a link, @name@server, #tag, :shortcode:, `code`, an
# address, anything with a digit in it
SKIP = re.compile(r"""
      https?://\S+ | www\.\S+
    | @[\w.\-]+(?:@[\w.\-]+)?
    | \#\w+
    | :[\w+\-]+:
    | `[^`]*`
    | \S+@\S+\.\w+
""", re.VERBOSE | re.UNICODE)
# a word: letters, inner apostrophes and hyphens (don't, кто-то); digits make it not one
WORD = re.compile(r"[^\W\d_](?:[^\W\d_]|['’\-](?=[^\W\d_]))*", re.UNICODE)

SUGGESTIONS = 8  # what a wrong word's menu offers, at most — every window's


def words(text):
    """[(start, end, word)] of the words to check in text (positions in characters)."""
    skip = [(m.start(), m.end()) for m in SKIP.finditer(text or "")]
    out, k = [], 0
    for m in WORD.finditer(text or ""):
        while k < len(skip) and skip[k][1] <= m.start():
            k += 1
        if k < len(skip) and skip[k][0] < m.end() and m.start() < skip[k][1]:
            continue
        end = m.end()
        if end < len(text) and text[end].isdigit() or m.start() and text[m.start() - 1].isdigit():
            continue  # a part of "4k", "mp3"
        out.append((m.start(), end, m.group()))
    return out


# ---- the backends -------------------------------------------------------------------------
class _PyEnchant:
    def __init__(self, enchant):
        self.enchant = enchant

    def languages(self):
        return list(self.enchant.list_languages())

    def open(self, tag):
        return self.enchant.Dict(tag) if self.enchant.dict_exists(tag) else None

    @staticmethod
    def check(d, word):
        return d.check(word)

    @staticmethod
    def suggest(d, word):
        return list(d.suggest(word))


class _LibEnchant:
    """libenchant-2 through ctypes: the few calls a spell checker needs."""

    def __init__(self, lib):
        self.lib = lib
        lib.enchant_broker_init.restype = ctypes.c_void_p
        lib.enchant_broker_request_dict.restype = ctypes.c_void_p
        lib.enchant_broker_request_dict.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.enchant_broker_dict_exists.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
        lib.enchant_dict_check.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_ssize_t]
        lib.enchant_dict_suggest.restype = ctypes.POINTER(ctypes.c_char_p)
        lib.enchant_dict_suggest.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                             ctypes.c_ssize_t,
                                             ctypes.POINTER(ctypes.c_size_t)]
        lib.enchant_dict_free_string_list.argtypes = [ctypes.c_void_p,
                                                      ctypes.POINTER(ctypes.c_char_p)]
        self.CALLBACK = ctypes.CFUNCTYPE(None, ctypes.c_char_p, ctypes.c_char_p,
                                         ctypes.c_char_p, ctypes.c_char_p, ctypes.c_void_p)
        lib.enchant_broker_list_dicts.argtypes = [ctypes.c_void_p, self.CALLBACK,
                                                  ctypes.c_void_p]
        self.broker = lib.enchant_broker_init()

    def languages(self):
        got = []

        def one(tag, _name, _desc, _file, _data):
            got.append(tag.decode("utf-8", "replace"))
        cb = self.CALLBACK(one)
        self.lib.enchant_broker_list_dicts(self.broker, cb, None)
        return sorted(set(got))

    def open(self, tag):
        t = tag.encode()
        if not self.lib.enchant_broker_dict_exists(self.broker, t):
            return None
        return self.lib.enchant_broker_request_dict(self.broker, t) or None

    def check(self, d, word):
        w = word.encode("utf-8")
        return self.lib.enchant_dict_check(d, w, len(w)) == 0

    def suggest(self, d, word):
        w = word.encode("utf-8")
        n = ctypes.c_size_t(0)
        arr = self.lib.enchant_dict_suggest(d, w, len(w), ctypes.byref(n))
        if not arr:
            return []
        try:
            return [arr[i].decode("utf-8", "replace") for i in range(n.value)]
        finally:
            self.lib.enchant_dict_free_string_list(d, arr)


_backend = None
_backend_lock = threading.Lock()


def backend():
    """The way to the system's dictionaries, or None (no Enchant here)."""
    global _backend
    with _backend_lock:
        if _backend is None:
            _backend = _find() or False
        return _backend or None


def _find():
    try:
        import enchant  # pyenchant
        return _PyEnchant(enchant)
    except Exception:  # noqa: BLE001 — not installed, or its library missing
        pass
    for name in ("enchant-2", "libenchant-2.so.2", "enchant"):
        path = ctypes.util.find_library(name) if "/" not in name and ".so" not in name \
            else name
        if not path:
            continue
        try:
            return _LibEnchant(ctypes.CDLL(path))
        except (OSError, AttributeError) as e:
            log.debug("enchant %s: %s", path, e)
    return None


def available():
    return backend() is not None


def languages():
    """The dictionaries installed: ["en_US", "ru_RU", …] ([] — none, or no Enchant)."""
    b = backend()
    try:
        return b.languages() if b else []
    except Exception as e:  # noqa: BLE001
        log.debug("spell languages: %s", e)
        return []


# the script a language is written in, where it isn't Latin
SCRIPTS = {**dict.fromkeys(("ru", "uk", "be", "bg", "sr", "mk", "kk", "ky", "tg", "mn", "tt",
                            "ba", "cv"), "CYRILLIC"),
           "el": "GREEK", "hy": "ARMENIAN", "ka": "GEORGIAN",
           **dict.fromkeys(("he", "yi"), "HEBREW"),
           **dict.fromkeys(("ar", "fa", "ur", "ps"), "ARABIC"),
           **dict.fromkeys(("hi", "mr", "ne"), "DEVANAGARI"), "th": "THAI"}


def script_of_tag(tag):
    """"ru_RU" → "CYRILLIC", "en_US" → "LATIN"."""
    return SCRIPTS.get((tag or "").replace("-", "_").split("_")[0].lower(), "LATIN")


def script_of_word(word):
    """The script of a word's first letter: "LATIN", "CYRILLIC", "GREEK"…"""
    for ch in word:
        if ch.isalpha():
            try:
                return unicodedata.name(ch).split()[0]
            except ValueError:
                return ""
    return ""


def pick(wanted, installed):
    """The installed dictionaries for the wanted languages: "ru" finds ru_RU, "en"
    en_US (or another en_*); an exact tag wins."""
    out = []
    for w in wanted:
        w = (w or "").replace("-", "_")
        if not w:
            continue
        if w in installed:
            got = w
        else:
            base = w.split("_")[0].lower()
            same = sorted(t for t in installed if t.split("_")[0].lower() == base)
            pref = [t for t in same if t.lower() in (f"{base}_{base}", "en_us")]
            got = (pref or same or [None])[0]
        if got and got not in out:
            out.append(got)
    return out


class Checker:
    """Spell checking in some languages, with my own words. Thread-safe."""

    def __init__(self, langs, own_file=None):
        self.own_file = Path(own_file) if own_file else None
        self._lock = threading.Lock()
        self.own = set()
        self._load_own()
        b = backend()
        self.dicts = []
        self.tags = []
        for tag in pick(langs, languages()) if b else []:
            self._open(tag)
        self._scripts = {script_of_tag(t) for t in self.tags}  # those looked for already

    def _open(self, tag):
        b = backend()
        try:
            d = b.open(tag)
        except Exception as e:  # noqa: BLE001
            log.debug("spell %s: %s", tag, e)
            d = None
        if d is not None:
            self.dicts.append(d)
            self.tags.append(tag)

    def _of_script(self, script):
        """The dictionaries for words of this script: the languages asked for, or else
        every installed one of that script (opened once); [] — none here."""
        if script not in self._scripts:
            self._scripts.add(script)
            for tag in languages():
                if script_of_tag(tag) == script and tag not in self.tags:
                    self._open(tag)
            if any(script_of_tag(t) == script for t in self.tags):
                log.info("spell: words in %s checked by %s too", script.lower(),
                         ", ".join(t for t in self.tags if script_of_tag(t) == script))
        return [d for d, t in zip(self.dicts, self.tags, strict=True)
                if script_of_tag(t) == script]

    @property
    def working(self):
        return bool(self.dicts)

    def _load_own(self):
        if self.own_file is None:
            return
        try:
            self.own = {w.strip() for w in self.own_file.read_text("utf-8").splitlines()
                        if w.strip() and not w.startswith("#")}
        except FileNotFoundError:
            self.own = set()
        except OSError as e:
            log.info("my dictionary: %s", e)

    def ok(self, word):
        if not self.dicts or word in self.own or word.lower() in self.own:
            return True
        if len(word) < 2 or word.isupper():  # "I", acronyms: NASA, ГИБДД
            return True
        b = backend()
        with self._lock:
            dicts = self._of_script(script_of_word(word))
            if not dicts:  # no dictionary of its script here: not ours to judge
                return True
            for d in dicts:
                try:
                    if b.check(d, word):
                        return True
                except Exception:  # noqa: BLE001 — a word a dictionary chokes on: fine
                    return True
        return False

    def wrong(self, text):
        """[(start, end, word)] that look misspelled."""
        if not self.dicts:
            return []
        return [w for w in words(text) if not self.ok(w[2])]

    def suggest(self, word, limit=8):
        b = backend()
        out = []
        with self._lock:
            for d in self._of_script(script_of_word(word)):
                try:
                    for s in b.suggest(d, word):
                        if s not in out:
                            out.append(s)
                except Exception:  # noqa: BLE001
                    pass
        return out[:limit]

    def add(self, word):
        """Into my own dictionary (the file too): never marked again."""
        word = word.strip()
        if not word or word in self.own:
            return
        self.own.add(word)
        if self.own_file is None:
            return
        try:
            self.own_file.parent.mkdir(parents=True, exist_ok=True)
            with self.own_file.open("a", encoding="utf-8") as f:
                f.write(word + "\n")
        except OSError as e:
            log.warning("my dictionary: %s", e)


def wanted_languages(cfg, post_language="", ui_language="en"):
    """Which languages to check in: post.spell_languages, or else the post's own
    language, the interface's and English."""
    set_ = list((cfg.get("post") or {}).get("spell_languages") or ())
    if set_:
        return set_
    out = []
    for x in (post_language, ui_language, "en"):
        x = (x or "").split("-")[0]
        if x and x not in out:
            out.append(x)
    return out


_checkers = {}
_checkers_lock = threading.Lock()


def for_post(cfg, config_dir, post_language="", ui_language="en"):
    """The Checker for a post in this language (made once, then kept: opening a
    dictionary takes a moment), or None when post.spellcheck is off or there are no
    dictionaries. My own words live next to the config: <config folder>/spelling.txt."""
    if not (cfg.get("post") or {}).get("spellcheck", True) or not available():
        return None
    langs = tuple(wanted_languages(cfg, post_language, ui_language))
    own = Path(config_dir) / "spelling.txt" if config_dir else None
    key = (langs, str(own))
    with _checkers_lock:
        got = _checkers.get(key)
        if got is None:
            got = _checkers[key] = Checker(langs, own)
        else:
            got._load_own()  # another window may have added a word
    return got if got.working else None


__all__ = ["Checker", "for_post", "available", "backend", "languages", "pick", "wanted_languages",
           "words"]
