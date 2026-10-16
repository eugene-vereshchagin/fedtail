"""The app icon, drawn from a theme's colours. No Qt: returns SVG text.

The picture: a speech bubble (talk) whose tail curls like a real tail — the
"tail" of the name — and inside it a thread: three lines stepping in, the way
fedtail shows a conversation, with an orange dot for "new". The terminal style
draws a green outline with a `>_` prompt instead.

Colours come from the theme's [icon] section; "auto" derives them from the
theme's accent, so a home-made theme gets a matching icon for free.
"""

_HEAD = 'xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256"'
DEFAULT = {"style": "bubble", "bg_top": "#3b8fd0", "bg_bottom": "#174a78",
           "bubble": "#ffffff", "ink": "#1d4f7a", "accent": "#e8702a"}


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    """a → b by t (0..1), as #rrggbb."""
    ra, rb = _hex(a), _hex(b)
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(ra, rb, strict=True))


def colors(icon_section, accent="#2a86c4", hot="#e8702a"):
    """Resolve "auto" values against the theme's accent and hot colours."""
    out = dict(DEFAULT)
    out.update({k: v for k, v in (icon_section or {}).items() if v})
    auto = {"bg_top": _mix(accent, "#ffffff", 0.18), "bg_bottom": _mix(accent, "#000000", 0.45),
            "bubble": "#ffffff", "ink": _mix(accent, "#000000", 0.35), "accent": hot}
    for k, v in auto.items():
        if str(out.get(k, "")).lower() == "auto":
            out[k] = v
    return out


def svg(c):
    """The icon as SVG text, 256×256."""
    if c.get("style") == "terminal":
        return _terminal(c)
    return f"""<svg {_HEAD}>
  <!-- fedtail: a talk bubble with a curled tail, a thread inside -->
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{c['bg_top']}"/>
      <stop offset="1" stop-color="{c['bg_bottom']}"/>
    </linearGradient>
  </defs>
  <rect x="8" y="8" width="240" height="240" rx="56" fill="url(#bg)"/>
  <!-- the tail: leaves the bubble's lower left and curls back on itself -->
  <path d="M86 176 C70 196 52 206 36 204 C22 202 18 188 28 182 C36 177 46 184 42 192
           C58 192 70 184 80 170 Z" fill="{c['bubble']}"/>
  <rect x="40" y="48" width="180" height="132" rx="34" fill="{c['bubble']}"/>
  <!-- a thread: a post, a reply, a reply to the reply -->
  <path d="M70 86 H186" stroke="{c['ink']}" stroke-width="13" stroke-linecap="round"/>
  <path d="M76 100 V122 H96" fill="none" stroke="{c['ink']}" stroke-width="6"
        stroke-linecap="round" stroke-linejoin="round" opacity="0.55"/>
  <path d="M106 122 H178" stroke="{c['ink']}" stroke-width="13" stroke-linecap="round"/>
  <path d="M112 136 V154 H130" fill="none" stroke="{c['ink']}" stroke-width="6"
        stroke-linecap="round" stroke-linejoin="round" opacity="0.55"/>
  <path d="M140 154 H164" stroke="{c['ink']}" stroke-width="13" stroke-linecap="round"/>
  <circle cx="190" cy="154" r="10" fill="{c['accent']}"/>
</svg>
"""


def _terminal(c):
    return f"""<svg {_HEAD}>
  <!-- fedtail, terminal: an outlined bubble with a prompt -->
  <rect x="8" y="8" width="240" height="240" rx="40" fill="{c['bg_bottom']}"
        stroke="{c['bg_top']}" stroke-width="4"/>
  <path d="M74 52 H182 A34 34 0 0 1 216 86 V142 A34 34 0 0 1 182 176 H96
           C84 192 66 204 46 202 C34 200 32 188 42 184 C50 181 58 188 54 194
           C64 192 72 186 78 176 H74 A34 34 0 0 1 40 142 V86 A34 34 0 0 1 74 52 Z"
        fill="none" stroke="{c['bubble']}" stroke-width="10" stroke-linejoin="round"/>
  <path d="M76 92 L110 114 L76 136" fill="none" stroke="{c['ink']}" stroke-width="14"
        stroke-linecap="square" stroke-linejoin="miter"/>
  <rect x="124" y="128" width="54" height="14" fill="{c['accent']}"/>
</svg>
"""
