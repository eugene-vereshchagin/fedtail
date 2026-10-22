"""A theme's colours worked out without a toolkit: "auto" from a desktop palette, the
colours that follow or tint others, mixing and contrast.

frontends/qt/theme.py does the same with QColor today; this module is the shared
version the GTK frontend is built on (docs/GTK.md, stage 0), and a test checks the
two agree wherever PySide6 is installed. Colour arithmetic copies QColor's: lightness
is HSL's, lighter()/darker() scale HSV's value and take saturation off when the value
runs past the top, so a theme looks the same on both toolkits.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ..i18n import months


@dataclass(frozen=True)
class Color:
    """An sRGB colour, 0–255 a channel, alpha 255 = opaque."""
    r: int
    g: int
    b: int
    a: int = 255

    # ---- reading ----------------------------------------------------------------
    @classmethod
    def parse(cls, text):
        """'#rgb', '#rrggbb', '#rrggbbaa' (alpha last, as CSS) or 'rgba(r,g,b,a)' (alpha
        0–1, or 0–255 when above 1). ValueError for anything else."""
        s = (text or "").strip()
        if s.startswith("rgb"):
            nums = [float(x.strip().rstrip("%")) for x in s[s.index("(") + 1:s.rindex(")")]
                    .split(",")]
            a = 255
            if len(nums) > 3:
                a = round(nums[3] * 255) if nums[3] <= 1 else round(nums[3])
            return cls(int(nums[0]), int(nums[1]), int(nums[2]), a)
        if s.startswith("#"):
            h = s[1:]
            if len(h) == 3:
                h = "".join(c * 2 for c in h)
            if len(h) in (6, 8):
                v = [int(h[i:i + 2], 16) for i in range(0, len(h), 2)]
                return cls(*v)
        raise ValueError(f"not a colour: {text!r}")

    # ---- writing ----------------------------------------------------------------
    def name(self):
        """'#rrggbb' (alpha left out, as QColor.name())."""
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    def css(self):
        """For a stylesheet: '#rrggbb', or rgba() when not opaque."""
        if self.a < 255:
            return f"rgba({self.r},{self.g},{self.b},{self.a / 255:.3g})"
        return self.name()

    def with_alpha(self, a):
        return Color(self.r, self.g, self.b, max(0, min(255, round(a))))

    # ---- QColor's arithmetic ----------------------------------------------------
    def lightness(self):
        """HSL lightness, 0–255."""
        return (max(self.r, self.g, self.b) + min(self.r, self.g, self.b) + 1) // 2  # as Qt

    def _hsv(self):
        mx, mn = max(self.r, self.g, self.b), min(self.r, self.g, self.b)
        v = mx / 255
        s = 0.0 if mx == 0 else (mx - mn) / mx
        if mx == mn:
            h = 0.0
        elif mx == self.r:
            h = ((self.g - self.b) / (mx - mn)) % 6
        elif mx == self.g:
            h = (self.b - self.r) / (mx - mn) + 2
        else:
            h = (self.r - self.g) / (mx - mn) + 4
        return h * 60, s, v

    @classmethod
    def _from_hsv(cls, h, s, v, a=255):
        c = v * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = v - c
        i = int(h // 60) % 6
        r, g, b = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][i]
        return cls(round((r + m) * 255), round((g + m) * 255), round((b + m) * 255), a)

    def lighter(self, factor=150):
        if factor <= 0:
            return self
        if factor < 100:
            return self.darker(10000 / factor)
        h, s, v = self._hsv()
        v = v * factor / 100
        if v > 1:
            s = max(0.0, s - (v - 1))
            v = 1.0
        return Color._from_hsv(h, s, v, self.a)

    def darker(self, factor=200):
        if factor <= 0:
            return self
        if factor < 100:
            return self.lighter(10000 / factor)
        h, s, v = self._hsv()
        return Color._from_hsv(h, s, v * 100 / factor, self.a)


GREY = Color(0x88, 0x88, 0x88)


def mix(a, b, t):
    """a moved towards b by t (0 = a, 1 = b); opaque."""
    return Color(round(a.r * (1 - t) + b.r * t), round(a.g * (1 - t) + b.g * t),
                 round(a.b * (1 - t) + b.b * t))


def readable_on(bg):
    """Black or white, whichever reads better on bg."""
    lum = 0.2126 * bg.r / 255 + 0.7152 * bg.g / 255 + 0.0722 * bg.b / 255
    return Color(0x11, 0x11, 0x11) if lum > 0.45 else Color(0xff, 0xff, 0xff)


@dataclass(frozen=True)
class Desktop:
    """What a toolkit can say about the desktop's colours: Qt has the whole QPalette,
    GTK 4 has light/dark and maybe an accent (see gtk/theme.py)."""
    base: Color        # behind text you read (QPalette.Base)
    window: Color      # around it (QPalette.Window)
    text: Color
    highlight: Color   # the selection / accent
    link: Color


def auto_colors(d):
    """Every 'auto' colour, derived from the desktop palette (works light and dark)."""
    base, win, text, hl, link = d.base, d.window, d.text, d.highlight, d.link
    dark = base.lightness() < 128
    green = Color(0x3c, 0x9a, 0x3c)
    accent = hl.darker(135) if dark else hl.darker(145)
    sidebar = win.lighter(112) if dark else win.darker(104)
    return {
        "window": win,
        "sidebar": sidebar,
        "sidebar_border": mix(win, text, 0.15),
        # dark: a step towards the text from the sidebar — base.lighter() of a near-black
        # base came out the sidebar's own colour, and the chosen lane didn't show
        "selected": mix(sidebar, text, 0.14) if dark else base,
        "selected_text": text,
        "view": base,
        "header_border": mix(base, text, 0.12),
        "card": base.lighter(115) if dark else base,
        "card_border": mix(base, text, 0.13),
        "card_border_unread": mix(base, hl, 0.45),
        "text": text,
        "muted": mix(text, base, 0.36),
        "link": link,
        "accent": accent,
        "on_accent": readable_on(accent),
        "quiet": mix(base, text, 0.18),
        "on_quiet": text,
        "new_pill": mix(base, hl, 0.16),
        "on_new_pill": hl.lighter(150) if dark else hl.darker(170),
        "ctx": mix(base, text, 0.05),
        "ctx_bar": mix(base, text, 0.35),
        "focus": mix(base, hl, 0.12),
        "focus_border": mix(base, hl, 0.5),
        "myreply": mix(base, green, 0.12),
        "on_myreply": mix(text, green, 0.55) if not dark else green.lighter(150),
        "separator": accent,
        "rail": mix(base, text, 0.22),
        "button": base,
        "button_border": mix(base, text, 0.22),
        "dot": hl,
    }


# colours that, left at "auto", copy another one of the same theme (not the desktop):
# a theme with its own text colour gets it in the sidebar too
FOLLOWS = {"sidebar_text": "text", "sidebar_muted": "muted", "panel": "window",
           "primary": "accent", "on_primary": "on_accent", "name": "text",
           "header_bar": "accent", "chat_me": "link", "chat_them": "hot",
           "view_end": "view", "tab_mark": "accent", "window_end": "window",
           "button_end": "button", "header_end": "header"}
# "auto" mixed from two colours of the same theme: (from, towards, how far)
TINTS = {"header": ("view", "accent", 0.16)}


def resolve(colors, desktop):
    """A theme's [colors] table (key → "auto" | colour text) as {key: Color}."""
    auto = auto_colors(desktop)
    out, follow = {}, []
    for key, val in colors.items():
        val = val.strip()
        if val == "auto" and (key in FOLLOWS or key in TINTS):
            follow.append(key)
        elif val == "auto":
            out[key] = auto.get(key, GREY)
        else:
            out[key] = Color.parse(val)
    for key in follow:  # "auto" here means "the same as the colour it stands for"
        if key in FOLLOWS and FOLLOWS[key] in out:
            out[key] = out[FOLLOWS[key]]
    for key in follow:  # …or a mix of two of them, once the plain ones are known
        if key in TINTS:
            a, b, t = TINTS[key]
            out[key] = mix(out[a], out[b], t)
    for key in follow:  # following a mixed one (header_end → header): now it's known
        if key in FOLLOWS and key not in out:
            out[key] = out[FOLLOWS[key]]
    return out


def word(words, key, text, **kw):
    """A theme's [words] template filled in (Theme.word in qt/theme.py)."""
    if words.get("lowercase"):
        text = text.lower()
    return words[key].format(text=text, **kw)


def date(words, when, fmt=None):
    """A time as the theme writes it (words.date, or fmt): an aware datetime or ISO
    text. Placeholders: {day} {mon} {time} (the year, for another year) {dd} {mm} {yyyy}
    {yy} {clock} (HH:MM) {secs} (HH:MM:SS)."""
    if isinstance(when, datetime):
        dt = when.astimezone()
    else:
        try:
            dt = datetime.fromisoformat(when.replace("Z", "+00:00")).astimezone()
        except (ValueError, AttributeError):
            return ""
    now = datetime.now(UTC).astimezone()
    time = f"{dt:%H:%M}" if dt.year == now.year else str(dt.year)
    return (fmt or words["date"]).format(
        day=dt.day, mon=months()[dt.month - 1], dd=f"{dt.day:02d}", mm=f"{dt.month:02d}",
        yyyy=dt.year, yy=f"{dt:%y}", time=time, clock=f"{dt:%H:%M}", secs=f"{dt:%H:%M:%S}")
