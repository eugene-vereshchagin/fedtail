"""The standard (Unicode) emoji for the editor: the picker's "Standard" tab and the
`:name` suggestions as one types (post.emoji_standard). Built from Python's own
unicodedata — no table of our own to keep up — plus the short names people know from
GitHub, Slack and Discord (`:smile:`, `:+1:`), which Unicode's names don't have.

Each emoji is a dict: {"char", "code" (its short name, without colons), "name" (Unicode's,
lower case), "group" (a key: faces, people, nature, food, travel, things, symbols)}."""

from __future__ import annotations

import unicodedata
from functools import lru_cache

# (first, last, group): the blocks the emoji live in, in the picker's order
_BLOCKS = (
    (0x1F600, 0x1F64F, "faces"),
    (0x1F910, 0x1F92F, "faces"), (0x1F970, 0x1F97A, "faces"),
    (0x1F9D0, 0x1F9D0, "faces"), (0x1FAE0, 0x1FAE8, "faces"),
    (0x1F440, 0x1F487, "people"), (0x1F590, 0x1F596, "people"),
    (0x1F645, 0x1F64F, "people"), (0x1F930, 0x1F93E, "people"),
    (0x1F9B0, 0x1F9DF, "people"), (0x1FAF0, 0x1FAF8, "people"),
    (0x1F400, 0x1F43F, "nature"), (0x1F300, 0x1F321, "nature"),
    (0x1F324, 0x1F32C, "nature"), (0x1F330, 0x1F343, "nature"),
    (0x1F980, 0x1F9AE, "nature"), (0x1FAB0, 0x1FABF, "nature"),
    (0x1F344, 0x1F37F, "food"), (0x1F950, 0x1F96F, "food"), (0x1F9C0, 0x1F9CF, "food"),
    (0x1FAD0, 0x1FADB, "food"),
    (0x1F680, 0x1F6FF, "travel"), (0x1F3D4, 0x1F3F0, "travel"),
    (0x1F380, 0x1F3D3, "things"), (0x1F488, 0x1F4FF, "things"),
    (0x1F500, 0x1F58F, "things"), (0x1F597, 0x1F5FF, "things"),
    (0x1F93F, 0x1F94F, "things"), (0x1F9E0, 0x1F9FF, "things"),
    (0x1FA70, 0x1FAAF, "things"), (0x1FAC0, 0x1FACF, "things"),
)
GROUPS = ("faces", "people", "nature", "food", "travel", "things", "symbols")

# the older symbols that are emoji too (the rest of 2600–27BF are only symbols); ones
# drawn as text unless asked get VS16 (U+FE0F) after them
_SYMBOLS = "☀☁☂☃☄☎☑☔☕☘☝☠☢☣☦☪☮☯☸☹☺♀♂♈♉♊♋♌♍♎♏♐♑♒♓♟♠♣♥♦♨♻♾♿⚒⚓⚔⚕⚖⚗⚙⚛⚜⚠⚡" \
    "⚧⚪⚫⚰⚱⚽⚾⛄⛅⛈⛎⛏⛑⛓⛔⛩⛪⛰⛱⛲⛳⛴⛵⛷⛸⛹⛺⛽✂✅✈✉✊✋✌✍✏✒✔✖✝✡✨✳✴❄❇❌❎❓❔❕❗❣❤➕➖➗➡➰➿" \
    "⬅⬆⬇⬛⬜⭐⭕〰〽㊗㊙"
_WIDE = set("☔☕♈♉♊♋♌♍♎♏♐♑♒♓♿⚓⚡⚪⚫⚽⚾⛄⛅⛎⛔⛪⛲⛳⛵⛺⛽"
            "✅✊✋✨❌❎❓❔❕❗➕➖➗➰➿⬛⬜⭐⭕")


def _spans(text):
    """"1F322-1F323 1F398" → the set of code points."""
    out = set()
    for part in text.split():
        a, _s, b = part.partition("-")
        out.update(range(int(a, 16), int(b or a, 16) + 1))
    return out


# in the blocks above but only symbols, not emoji (Unicode's emoji-data.txt), and the skin
# tone modifiers (not emoji of their own)
_SKIP = _spans("""
    1F322-1F323 1F394-1F395 1F398 1F39C-1F39D 1F3F1-1F3F2 1F3F6 1F3FB-1F3FF 1F4FE
    1F53E-1F548 1F54F 1F568-1F56E 1F571-1F572 1F57B-1F586 1F588-1F589 1F58E-1F58F
    1F591-1F594 1F597-1F5A3 1F5A6-1F5A7 1F5A9-1F5B0 1F5B3-1F5BB 1F5BD-1F5C1 1F5C5-1F5D0
    1F5D4-1F5DB 1F5DF-1F5E0 1F5E2 1F5E4-1F5E7 1F5E9-1F5EE 1F5F0-1F5F2 1F5F4-1F5F9
    1F6C6-1F6CA 1F6D3-1F6D4 1F6E6-1F6E8 1F6EA 1F6F1-1F6F2""")
# emoji drawn as text unless asked: VS16 (U+FE0F) after them
_TEXT = _spans("""
    1F321 1F324-1F32C 1F336 1F37D 1F396-1F397 1F399-1F39B 1F39E-1F39F 1F3CB-1F3CE
    1F3D4-1F3DF 1F3F3 1F3F5 1F3F7 1F43F 1F441 1F4FD 1F549-1F54A 1F56F-1F570 1F573-1F579
    1F587 1F58A-1F58D 1F590 1F5A5 1F5A8 1F5B1-1F5B2 1F5BC 1F5C2-1F5C4 1F5D1-1F5D3
    1F5DC-1F5DE 1F5E1 1F5E3 1F5E8 1F5EF 1F5F3 1F5FA 1F6CB 1F6CD-1F6CF 1F6E0-1F6E5 1F6E9
    1F6F0 1F6F3""")

# the short names people type (GitHub / Slack / Discord), where Unicode's differ
ALIASES = {
    "smile": "😄", "smiley": "😃", "grin": "😁", "grinning": "😀", "laughing": "😆",
    "satisfied": "😆", "joy": "😂", "rofl": "🤣", "sweat_smile": "😅", "wink": "😉",
    "blush": "😊", "innocent": "😇", "slightly_smiling_face": "🙂", "upside_down": "🙃",
    "relaxed": "☺️", "yum": "😋", "heart_eyes": "😍", "star_struck": "🤩",
    "kissing_heart": "😘", "kiss": "😘", "stuck_out_tongue": "😛",
    "stuck_out_tongue_winking_eye": "😜", "zany": "🤪", "money_mouth": "🤑", "hugs": "🤗",
    "hug": "🤗", "thinking": "🤔", "shushing": "🤫", "zipper_mouth": "🤐",
    "neutral_face": "😐", "expressionless": "😑", "no_mouth": "😶", "smirk": "😏",
    "unamused": "😒", "roll_eyes": "🙄", "rolling_eyes": "🙄", "grimacing": "😬",
    "relieved": "😌", "pensive": "😔", "sleepy": "😪", "sleeping": "😴", "mask": "😷",
    "nerd": "🤓", "nerd_face": "🤓", "sunglasses": "😎", "cool": "😎", "party": "🥳",
    "partying_face": "🥳", "cowboy": "🤠", "confused": "😕", "worried": "😟",
    "frowning": "😦", "slightly_frowning_face": "🙁", "open_mouth": "😮", "hushed": "😯",
    "astonished": "😲", "flushed": "😳", "pleading": "🥺", "cry": "😢", "sob": "😭",
    "scream": "😱", "fearful": "😨", "cold_sweat": "😰", "sweat": "😓", "weary": "😩",
    "tired_face": "😫", "yawning": "🥱", "triumph": "😤", "angry": "😠", "rage": "😡",
    "cursing": "🤬", "skull": "💀", "poop": "💩", "hankey": "💩", "clown": "🤡",
    "ghost": "👻", "alien": "👽", "robot": "🤖", "see_no_evil": "🙈", "hear_no_evil": "🙉",
    "speak_no_evil": "🙊", "facepalm": "🤦", "shrug": "🤷", "thumbsup": "👍", "+1": "👍",
    "thumbsdown": "👎", "-1": "👎", "ok_hand": "👌", "ok": "👌", "v": "✌️",
    "crossed_fingers": "🤞", "metal": "🤘", "call_me": "🤙", "point_up": "☝️",
    "point_down": "👇", "point_left": "👈", "point_right": "👉", "wave": "👋",
    "raised_hand": "✋", "hand": "✋", "clap": "👏", "raised_hands": "🙌", "pray": "🙏",
    "handshake": "🤝", "muscle": "💪", "fist": "✊", "punch": "👊", "writing_hand": "✍️",
    "eyes": "👀", "eye": "👁️", "brain": "🧠", "heart": "❤️", "red_heart": "❤️",
    "orange_heart": "🧡", "yellow_heart": "💛", "green_heart": "💚", "blue_heart": "💙",
    "purple_heart": "💜", "black_heart": "🖤", "white_heart": "🤍", "broken_heart": "💔",
    "two_hearts": "💕", "sparkling_heart": "💖", "100": "💯", "fire": "🔥", "star": "⭐",
    "star2": "🌟", "sparkles": "✨", "zap": "⚡", "boom": "💥", "tada": "🎉",
    "confetti_ball": "🎊", "gift": "🎁", "balloon": "🎈", "trophy": "🏆", "rocket": "🚀",
    "coffee": "☕", "tea": "🍵", "beer": "🍺", "beers": "🍻", "wine_glass": "🍷",
    "pizza": "🍕", "cake": "🍰", "cookie": "🍪", "apple": "🍎", "cat": "🐱", "dog": "🐶",
    "unicorn": "🦄", "bug": "🐛", "penguin": "🐧", "sun": "☀️", "sunny": "☀️",
    "cloud": "☁️", "rainbow": "🌈", "snowflake": "❄️", "umbrella": "☔", "moon": "🌙",
    "earth": "🌍", "seedling": "🌱", "rose": "🌹", "check": "✅",
    "white_check_mark": "✅", "heavy_check_mark": "✔️", "x": "❌", "warning": "⚠️",
    "question": "❓", "exclamation": "❗", "no_entry": "⛔", "bulb": "💡", "memo": "📝",
    "pencil": "✏️", "book": "📖", "books": "📚", "link": "🔗", "lock": "🔒", "key": "🔑",
    "bell": "🔔", "mute": "🔇", "computer": "💻", "phone": "📱", "camera": "📷",
    "mag": "🔍", "hourglass": "⌛", "clock": "🕒", "calendar": "📅", "pushpin": "📌",
    "paperclip": "📎", "wrench": "🔧", "hammer": "🔨", "gear": "⚙️", "moneybag": "💰",
    "house": "🏠", "car": "🚗", "airplane": "✈️", "musical_note": "🎵", "notes": "🎶",
    "zzz": "💤", "wave_dash": "〰️", "kissing": "😗", "dizzy_face": "😵", "exploding_head": "🤯",
    "hot": "🥵", "cold": "🥶", "woozy": "🥴", "smiling_imp": "😈", "imp": "👿",
}


def _code(name):
    return name.lower().replace(" ", "_").replace("-", "_")


@lru_cache(maxsize=1)
def every():
    """Every standard emoji this Python knows, in the picker's order (groups, then code
    points), each once: [dict]."""
    out, seen = [], set()

    def add(char, group):
        base = char.rstrip("️")
        if base in seen:
            return
        try:
            name = unicodedata.name(base)
        except (ValueError, TypeError):
            return
        seen.add(base)
        out.append({"char": char, "code": _code(name), "name": name.lower(), "group": group})

    for group in GROUPS[:-1]:
        for first, last, g in _BLOCKS:
            if g == group:
                for cp in range(first, last + 1):
                    if cp not in _SKIP:
                        add(chr(cp) + ("\ufe0f" if cp in _TEXT else ""), group)
    for ch in _SYMBOLS:
        add(ch if ch in _WIDE else ch + "️", "symbols")
    for char in ALIASES.values():  # one the blocks missed
        add(char, "symbols")
    return out


@lru_cache(maxsize=1)
def _by_char():
    return {e["char"].rstrip("️"): e for e in every()}


def _names(e):
    """Every short name an emoji answers to: its aliases first, then Unicode's."""
    base = e["char"].rstrip("️")
    return [a for a, c in ALIASES.items() if c.rstrip("️") == base] + [e["code"]]


def code(e):
    """The short name to show beside an emoji (":smile:" rather than ":grinning_face_with_
    smiling_eyes:" where people have one)."""
    return _names(e)[0]


def search(words, limit=None):
    """The emoji whose short names or Unicode name match `words` (English; a leading or
    trailing ":" ignored): a short name starting with it first, then a word of the name
    starting with it ("smile" finds "smiling" too), then any part. [dict]."""
    q = str(words or "").strip().strip(":").casefold().replace(" ", "_")
    if not q:
        return list(every())[:limit] if limit else list(every())
    stem = q[:-1] if len(q) > 3 and q.endswith("e") else q
    exact, starts, word, within = [], [], [], []
    for e in every():
        names = _names(e)
        parts = [p for n in names for p in n.split("_")] + e["name"].split()
        if q in names:
            exact.append(e)
        elif any(n.startswith(q) for n in names):
            starts.append(e)
        elif any(p.startswith(stem) for p in parts):
            word.append(e)
        elif any(q in n for n in names):
            within.append(e)
    got = exact + starts + word + within
    return got[:limit] if limit else got


def suggestions(prefix, limit=8):
    """For `:smi` as one types: [(the emoji itself, ":short_name: <emoji>")]."""
    return [(e["char"], f"{e['char']} :{code(e)}:") for e in search(prefix, limit)]


def picker(words=""):
    """The picker's "Standard" tab: [{"char", "code", "name", "group"}], code being the
    short name people know; with `words`, only what they find (search), the best first."""
    return [dict(e, code=code(e)) for e in (search(words) if words.strip() else every())]
