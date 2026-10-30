"""Which language a post is in, when its author didn't say — or said wrong.

The aim is not to place every post to the letter but to keep a lane free of floods in
languages you don't read (`lanes.languages`). Two steps:

* the script, for free and on any length: Chinese, Japanese, Korean, Arabic, Hebrew,
  Georgian, Armenian, Thai, Greek, Devanagari… are unmistakable; Cyrillic is told apart
  by letters only Belarusian (ў) or Ukrainian (і ї є ґ) has, else it counts as Russian;
* `langdetect` (Debian: python3-langdetect; optional) for Latin and the rest of Cyrillic,
  only on posts of at least `lanes.detect_min_words` words — shorter ones it gets wrong.

What can't be told stays unknown, and an unknown language is never filtered out.
"""

import re
import unicodedata

from .model import html_to_text

# (first, last code point) → language, for scripts that give the language away
_SCRIPTS = [
    (0x0590, 0x05FF, "he"), (0x0600, 0x06FF, "ar"), (0x0750, 0x077F, "ar"),
    (0x0900, 0x097F, "hi"), (0x0980, 0x09FF, "bn"), (0x0B80, 0x0BFF, "ta"),
    (0x0E00, 0x0E7F, "th"), (0x10A0, 0x10FF, "ka"), (0x1C90, 0x1CBF, "ka"),
    (0x0530, 0x058F, "hy"), (0x0370, 0x03FF, "el"), (0x1F00, 0x1FFF, "el"),
    (0xAC00, 0xD7AF, "ko"), (0x1100, 0x11FF, "ko"), (0x3130, 0x318F, "ko"),
    (0x3040, 0x30FF, "ja"),  # kana: Japanese even among Chinese characters
    (0x4E00, 0x9FFF, "zh"), (0x3400, 0x4DBF, "zh"),
    (0x0A00, 0x0A7F, "pa"), (0x0A80, 0x0AFF, "gu"), (0x0C00, 0x0C7F, "te"),
    (0x0C80, 0x0CFF, "kn"), (0x0D00, 0x0D7F, "ml"),
]
_CYRILLIC = (0x0400, 0x04FF)
_UK, _BE = set("іїєґ"), set("ў")
# languages written in Cyrillic: a Cyrillic text tagged with another one is tagged wrong
CYRILLIC_LANGS = {"ru", "uk", "be", "bg", "sr", "mk", "kk", "ky", "mn", "tg", "tt", "ba",
                  "cv", "ce", "os", "sah", "udm", "kv", "ab"}
# …and those written in a script of their own: a Latin text tagged with one is tagged wrong
SCRIPT_LANGS = {lang for _lo, _hi, lang in _SCRIPTS}
MIN_SHARE = 0.6        # a script must hold this share of the letters to decide
MIN_PROBABILITY = 0.8  # what langdetect must be sure of
_cache = {}
_CACHE_MAX = 20000
_detector = None       # langdetect's detect_langs, or False when it isn't installed
# langdetect's profiles of languages its guess is never asked about: their script tells them
# above (Devanagari is "hi", Arabic letters "ar" — as before), so only Latin and Cyrillic
# texts reach it. Not loading these 20 of its 55 is two thirds of its memory (the CJK ones
# have the most n-grams) and changes no answer.
_BY_SCRIPT = {"ar", "fa", "ur", "he", "hi", "mr", "ne", "bn", "ta", "te", "kn", "ml", "gu",
              "pa", "th", "el", "ja", "ko", "zh-cn", "zh-tw"}
_among = "auto"        # lanes.detect_among: "auto" — those above left out; "all" — every one


def configure(among="auto"):
    """lanes.detect_among, before the first guess (Core does it as it starts); a change
    after one loads the profiles anew at the next."""
    global _among, _detector
    among = among if among in ("auto", "all") else "auto"
    if among != _among:
        _among = among
        if _detector:
            _detector = None
            _cache.clear()
            try:
                from langdetect import detector_factory
                detector_factory._factory = None
            except ImportError:
                pass


def base(code):
    """'en-US', 'zh-cn', 'RU' → 'en', 'zh', 'ru'; None and '' → None."""
    code = (code or "").strip().lower()
    return re.split(r"[-_]", code, maxsplit=1)[0] or None


def _letters(text):
    return [c for c in text if c.isalpha()]


def by_script(text):
    """The language its script gives away; "cyrillic" or "latin" when the script only
    narrows it; None (mixed, too little)."""
    letters = _letters(text)
    if not letters:
        return None
    counts = {}
    cyr = latin = 0
    for c in letters:
        o = ord(c)
        if _CYRILLIC[0] <= o <= _CYRILLIC[1]:
            cyr += 1
            continue
        if o < 0x0250:  # Basic Latin … Latin Extended-B
            latin += 1
            continue
        for lo, hi, lang in _SCRIPTS:
            if lo <= o <= hi:
                counts[lang] = counts.get(lang, 0) + 1
                break
    if counts.get("ja") and counts.get("zh"):  # kanji among kana: Japanese
        counts["ja"] += counts.pop("zh")
    best = max(counts, key=counts.get) if counts else None
    if best and counts[best] >= MIN_SHARE * len(letters):
        return best
    if cyr >= MIN_SHARE * len(letters):
        low = set(text.lower())
        if low & _BE:  # ў first: Belarusian has the і of Ukrainian too
            return "be"
        if low & _UK:
            return "uk"
        return "cyrillic"  # Russian, Bulgarian, Serbian…: the words decide, or Russian
    if latin >= MIN_SHARE * len(letters):
        return "latin"
    return None


def _load():
    global _detector
    if _detector is None:
        try:
            from langdetect import DetectorFactory, detect_langs
            DetectorFactory.seed = 0  # the same answer for the same text, every time
            _detector = detect_langs
        except ImportError:
            _detector = False
        else:
            _load_profiles()
    return _detector


def _load_profiles():
    """langdetect's profiles read the way its DetectorFactory.load_profile reads them —
    but only the languages it is asked about (_BY_SCRIPT left out, unless "all"), and each
    n-gram's probabilities as an array of 4-byte floats, not a list of Python floats: 60 MB
    → 11 (30.10). Its internals unlike these (another version): its own loading, as is."""
    import json
    import os
    from array import array
    try:
        from langdetect import detector_factory as df
        from langdetect.utils.lang_profile import LangProfile
        if df._factory is not None:
            return
        files = [f for f in os.listdir(df.PROFILES_DIRECTORY) if not f.startswith(".")
                 and (_among == "all" or f not in _BY_SCRIPT)]
        factory = df.DetectorFactory()
        size, table = len(files), {}
        for name in files:
            with open(os.path.join(df.PROFILES_DIRECTORY, name), encoding="utf-8") as f:
                profile = LangProfile(**json.load(f))
            index = len(factory.langlist)
            factory.langlist.append(profile.name)
            for word, count in profile.freq.items():
                probs = table.get(word)
                if probs is None:
                    probs = table[word] = array("f", bytes(4 * size))
                if 1 <= len(word) <= 3:
                    probs[index] = count / profile.n_words[len(word) - 1]
        factory.word_lang_prob_map = table
        df._factory = factory
    except (ImportError, AttributeError, OSError, ValueError, TypeError):
        return


def available():
    """Is langdetect installed (the long-text half of the guess)?"""
    return bool(_load())


def by_words(text):
    """langdetect's guess, when it is sure enough; None otherwise or without it."""
    detect = _load()
    if not detect:
        return None
    try:
        found = detect(text)
    except Exception:  # its LangDetectException: no features in the text
        return None
    if found and found[0].prob >= MIN_PROBABILITY:
        return base(found[0].lang)
    return None


# what says nothing of a text's language: a link, @name@server, #tag, :shortcode:
_NOT_LANGUAGE = re.compile(r"https?://\S+|www\.\S+|@[\w.\-]+(?:@[\w.\-]+)?|#\w+|:[\w+\-]+:")


def words_only(text):
    """text without its links, @names, #tags and :emoji: — their letters are no language
    (a Japanese post with its link's Latin letters counted as Latin, its "ja" called a
    lie, and the language unknown: it passed a "ru only" filter, 30.10)."""
    return _NOT_LANGUAGE.sub(" ", text or "")


def guess(text, min_words=12):
    """The language of a plain text, or None."""
    text = words_only(unicodedata.normalize("NFC", text or ""))
    script = by_script(text)
    if script and script not in ("cyrillic", "latin"):
        return script
    words = len(re.findall(r"\w+", text))
    if words >= min_words:
        found = by_words(text)
        if found:
            return found
    return "ru" if script == "cyrillic" else None


def _contradicts(script, tagged):
    """Does the script say the tag can't be right?"""
    if script is None:
        return False
    if script == "cyrillic":
        return tagged not in CYRILLIC_LANGS
    if script == "latin":
        return tagged in CYRILLIC_LANGS or tagged in SCRIPT_LANGS
    return script != tagged


def post_language(status, mode="untagged", min_words=12):
    """The language a post is in, for filtering: the author's tag, or the guess.

    mode: "off" — the tag only; "untagged" — guess when there is no tag, or when the
    script says the tag can't be right (an "en" post in Chinese characters or in Cyrillic,
    a "ru" one in Latin letters); "always" — the guess beats the tag whenever there is one."""
    tagged = base(status.get("language"))
    if mode == "off":
        return tagged
    key = (status.get("id"), status.get("edited_at"), mode, min_words)
    if key[0] and key in _cache:
        return _cache[key]
    text = words_only("\n".join(x for x in (status.get("spoiler_text") or "",
                                            html_to_text(status.get("content") or "")) if x))
    script = by_script(text)
    if mode == "untagged" and tagged and not _contradicts(script, tagged):
        lang = tagged
    elif mode == "untagged" and tagged:
        lang = guess(text, min_words)  # the tag lies: what the text says, or unknown
    else:
        lang = guess(text, min_words) or tagged
    if key[0]:
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[key] = lang
    return lang


def wanted(status, languages, mode="untagged", min_words=12):
    """Does a post pass a languages filter? No filter, or an unknown language: it does."""
    if not languages:
        return True
    lang = post_language(status, mode, min_words)
    return lang is None or lang in languages
