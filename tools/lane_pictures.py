"""Draws the library of lane pictures (fedtail/data/icons/lanes/*.svg): what one's own
lane may wear (`icon = "…"` in [[lanes.custom]], the lane editor's "Picture").

Drawn the way the fallback set is (data/icons/fallback): 16×16, the shape filled with
the theme's gradient ({l} → {c}), outlined with {d}, a shine on top — so each theme's
[pictures] style (gloss, flat, silhouette, qip…) colours them as its own pictures. The
main shape goes first: silhouette cuts the lines after it out of it — but
those marked as outside it ({o}), drawn in its colour.

    python3 tools/lane_pictures.py          # writes the files anew
"""

from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "fedtail" / "data" / "icons" / "lanes"
HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" width="16" height="16">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" '
        'stop-color="{l}"/><stop offset="1" stop-color="{c}"/></linearGradient></defs>')


def body(d):  # the shape: the gradient, an outline
    return (f'<path d="{d}" fill="url(#g)" stroke="{{d}}" stroke-width="1" '
            'stroke-linejoin="round"/>')


def ball(cx, cy, r):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#g)" stroke="{{d}}" '
            'stroke-width="1"/>')


def box(x, y, w, h, rx):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="url(#g)" '
            'stroke="{d}" stroke-width="1" stroke-linejoin="round"/>')


def line(d, w=1.7, out=False):
    """Lines in the outline's colour. out: they lie outside the main shape (a lamp's
    base, the sun's rays) — {o}, which silhouette draws in the shape's colour instead of
    cutting them out of it."""
    return (f'<path d="{d}" fill="none" stroke="{{{"o" if out else "d"}}}" '
            f'stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>')


def dot(cx, cy, r, out=False):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{{{"o" if out else "d"}}}"/>'


def ink(d, opacity=1.0):  # a filled shape in the outline's colour
    o = f' opacity="{opacity}"' if opacity < 1 else ""
    return f'<path d="{d}" fill="{{d}}"{o}/>'


def ring(cx, cy, r, w=1.3):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{{d}}" '
            f'stroke-width="{w}"/>')


def shine(cx, cy, rx, ry):
    return f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="#fff" opacity=".35"/>'


PICTURES = {
    # the lanes of fedtail's set that had none of their own
    "commented": [
        body("M1.4 5.4a1.6 1.6 0 0 1 1.6-1.6h7.2a1.6 1.6 0 0 1 1.6 1.6v4.4a1.6 1.6 0 0 1"
             "-1.6 1.6H6.2l-2.8 2.6v-2.6H3a1.6 1.6 0 0 1-1.6-1.6z"),
        line("M5 3.6V3.2a1.4 1.4 0 0 1 1.4-1.4h7a1.4 1.4 0 0 1 1.4 1.4v4.4a1.4 1.4 0 0 1"
             "-1.4 1.4h-1", 1, True),
        dot(4.3, 7.6, .8), dot(6.6, 7.6, .8), dot(8.9, 7.6, .8)],
    "important": [
        body("M8 1.6c-2.6 0-4.2 2-4.2 4.6v3L2.4 11.6h11.2L12.2 9.2v-3C12.2 3.6 10.6 1.6 8"
             " 1.6z"),
        dot(8, 13.4, 1.3, True), shine(6.8, 4.8, 1.6, .9)],
    # the library
    "person": [ball(8, 5, 3), body("M2.4 15c0-3.4 2.5-5.6 5.6-5.6s5.6 2.2 5.6 5.6z"),
               shine(7, 3.8, 1.3, .7)],
    "people": [ball(10.8, 4.6, 2), body("M7.4 13.4c0-2.6 1.5-4.4 3.4-4.4s3.6 1.8 3.6 4.4z"),
               ball(5.6, 5.8, 2.3), body("M1.4 14.6c0-3 1.9-5 4.2-5s4.2 2 4.2 5z")],
    "heart": [body("M8 14.2S1.6 10.2 1.6 5.6A3.3 3.3 0 0 1 8 4.2a3.3 3.3 0 0 1 6.4 1.4C14.4"
                   " 10.2 8 14.2 8 14.2z"), shine(5, 5.2, 1.5, .9)],
    "fire": [body("M8 14.6c-3 0-5-2.1-5-4.8 0-2.6 1.8-4 2.6-6 .4 1.4 1.2 2.2 2 2.4C7.4 4"
                  " 8.4 2.4 10 1.4c-.2 2.4 3 3.9 3 7.6 0 3.3-2 5.6-5 5.6z"),
             ink("M8 13.4c-1.3 0-2.1-.9-2.1-2 0-1.2 1-1.9 1.4-3 .9.8 2.8 1.6 2.8 3.1 0 1.1"
                 "-.8 1.9-2.1 1.9z", .55)],
    "sparkle": [body("M8 1l1.6 4.4L14 7 9.6 8.6 8 13 6.4 8.6 2 7l4.4-1.6z"),
                body("M13 10.6l.6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6z")],
    "bolt": [body("M9.4 1.2L2.8 9.2h4.4L6.2 14.8l7-8.4H8.8z")],
    "news": [body("M1.6 3h10.4v10.6H3a1.4 1.4 0 0 1-1.4-1.4z"),
             body("M12 5.4h2.4v6.8a1.4 1.4 0 0 1-1.4 1.4h-1z"),
             line("M3.8 5.6h6M3.8 8h6M3.8 10.4h3.8", 1.2)],
    "megaphone": [body("M2 6h2.8l6.6-3.6v11.2L4.8 10H2z"),
                  line("M13.4 6.2v3.6", 1.6, True), line("M4.8 10l1 3.8h1.6l-.6-3.6", 1.2, True)],
    "rss": [box(1.6, 1.6, 12.8, 12.8, 2.4), dot(5, 11, 1.3),
            line("M4 7.4a4.6 4.6 0 0 1 4.6 4.6M4 4.2a7.8 7.8 0 0 1 7.8 7.8", 1.6)],
    "search": [ball(6.6, 6.6, 4.6), line("M10.2 10.2l4 4", 2.4, True), shine(5.4, 5, 2, 1.1)],
    "link": [line("M7.2 4.6l1.4-1.4a2.8 2.8 0 0 1 4 4l-1.4 1.4M8.8 11.4l-1.4 1.4a2.8 2.8 0"
                  " 0 1-4-4l1.4-1.4M6 10l4-4", 1.8)],
    "quote": [body("M2 8.6C2 5.4 3.6 3.4 6.4 3v1.8C5 5.2 4.4 6.2 4.4 7.4h2.2v5H2zM9 8.6C9"
                   " 5.4 10.6 3.4 13.4 3v1.8c-1.4.4-2 1.4-2 2.6h2.2v5H9z")],
    "inbox": [body("M1.6 9l2-6.2a1.2 1.2 0 0 1 1.1-.8h6.6a1.2 1.2 0 0 1 1.1.8l2 6.2v4a1.2"
                   " 1.2 0 0 1-1.2 1.2H2.8A1.2 1.2 0 0 1 1.6 13z"),
              line("M1.6 9h3.6l1 1.8h3.6l1-1.8h3.6", 1.2)],
    "image": [box(1.6, 2.6, 12.8, 10.8, 1.4),
              ink("M3 12l3.4-4.2 2.4 2.8 1.6-1.8L13 12z", .7), dot(10.8, 5.6, 1.3)],
    "camera": [body("M1.6 5.6a1.2 1.2 0 0 1 1.2-1.2h2.2l1-1.6h4l1 1.6h2.2a1.2 1.2 0 0 1"
                    " 1.2 1.2v6.8a1.2 1.2 0 0 1-1.2 1.2H2.8a1.2 1.2 0 0 1-1.2-1.2z"),
               ring(8, 8.8, 2.6, 1.4), dot(8, 8.8, 1)],
    "film": [box(1.6, 3.2, 12.8, 9.6, 1.2), line("M1.6 6h12.8M1.6 10h12.8", 1),
             line("M4 4.6h.1M8 4.6h.1M12 4.6h.1M4 11.4h.1M8 11.4h.1M12 11.4h.1", 1.5)],
    "music": [ball(4.6, 12.4, 2), ball(11.6, 11, 2), line("M6.6 12.4V3.6l7-1.6v9", 1.5, True)],
    "palette": [body("M8 1.6a6.4 6.4 0 0 0 0 12.8c1.2 0 1.6-.8 1.2-1.6-.5-1 .2-1.8 1.2-1.8"
                     "h1.6a2.4 2.4 0 0 0 2.4-2.4C14.4 4.4 11.6 1.6 8 1.6z"),
                dot(4.6, 7.6, 1), dot(6.2, 4.6, 1), dot(9.8, 4.6, 1), dot(11.6, 7.4, 1)],
    "book": [body("M8 4C6.4 2.8 4 2.6 1.6 3v10c2.4-.4 4.8-.2 6.4 1 1.6-1.2 4-1.4 6.4-1V3C12"
                  " 2.6 9.6 2.8 8 4z"), line("M8 4v10", 1)],
    "code": [line("M5 4.4L1.6 8 5 11.6M11 4.4L14.4 8 11 11.6M9.4 3L6.6 13")],
    "game": [body("M4.4 4.6h7.2a3 3 0 0 1 2.9 2.3l.8 3.6a1.9 1.9 0 0 1-3.2 1.7l-1.3-1.4H5.2"
                  "l-1.3 1.4A1.9 1.9 0 0 1 .7 10.5l.8-3.6a3 3 0 0 1 2.9-2.3z"),
             line("M4.6 6.4v2.8M3.2 7.8H6", 1.3), dot(10.8, 7, .8), dot(12.2, 8.6, .8)],
    "bulb": [body("M8 1.4a4.6 4.6 0 0 0-2.8 8.3c.6.5.9 1 .9 1.7v.6h3.8v-.6c0-.7.3-1.2.9"
                  "-1.7A4.6 4.6 0 0 0 8 1.4z"),
             line("M6.2 13.4h3.6M6.8 15h2.4", 1.3, True), shine(6.8, 4.2, 1.5, .9)],
    "flask": [body("M6.4 2h3.2v4.2l4.2 6.9a1 1 0 0 1-.9 1.5H3.1a1 1 0 0 1-.9-1.5l4.2-6.9z"),
              ink("M4.2 10.6h7.6l1.6 2.6a.6.6 0 0 1-.5.9H3.1a.6.6 0 0 1-.5-.9z", .55),
              line("M5.4 2h5.2", 1.4, True)],
    "wrench": [body("M13.8 4.2l-2.2 2.2-2-.6-.6-2 2.2-2.2A3.8 3.8 0 0 0 6.4 6.4L1.8 11a1.7"
                    " 1.7 0 0 0 2.4 2.4l4.6-4.6a3.8 3.8 0 0 0 5-4.6z")],
    "chart": [body("M2 9h3v5H2zM6.5 5.5h3V14h-3zM11 2h3v12h-3z"),
              line("M1.2 14.6h13.6", 1.2, True)],
    "shield": [body("M8 1.2l5.6 2v4.4c0 3.4-2.4 6-5.6 7.2-3.2-1.2-5.6-3.8-5.6-7.2V3.2z"),
               line("M5.4 8l1.8 1.8 3.4-3.6", 1.6)],
    "clock": [ball(8, 8, 6.4), line("M8 4.4V8l2.6 1.8", 1.6), shine(6, 4.4, 2.4, 1.1)],
    "calendar": [box(1.8, 2.8, 12.4, 11.4, 1.4), line("M1.8 6.2h12.4", 1),
                 line("M5 1.4v2.8M11 1.4v2.8", 1.6, True),
                 line("M4.6 8.8h.1M8 8.8h.1M11.4 8.8h.1M4.6 11.6h.1M8 11.6h.1", 1.6)],
    "flag": [body("M3.4 2.4c3-1.4 4.6 1.4 9.6 0v6.4c-5 1.4-6.6-1.4-9.6 0z"),
             line("M3 14.6V1.8", 1.7, True)],
    "pin": [body("M8 14.8S3 9.6 3 6.2a5 5 0 0 1 10 0c0 3.4-5 8.6-5 8.6z"), dot(8, 6.2, 1.8),
            shine(6.4, 3.8, 1.5, .8)],
    "globe": [ball(8, 8, 6.4),
              line("M1.6 8h12.8M8 1.6c-2.4 2-2.4 10.8 0 12.8M8 1.6c2.4 2 2.4 10.8 0 12.8"
                   "M2.6 4.8h10.8M2.6 11.2h10.8", 1)],
    "mountain": [body("M.8 14L5.8 5l2.6 4.4 1.8-2.8L15.2 14z"),
                 '<path d="M5.8 5l1.5 2.6-1-.6-.6.8-.6-.8-.9.6z" fill="#fff" opacity=".7"/>'],
    "sun": [ball(8, 8, 3.2),
            line("M8 1.2v1.8M8 13v1.8M1.2 8H3M13 8h1.8M3.2 3.2l1.3 1.3M11.5 11.5l1.3 1.3"
                 "M3.2 12.8l1.3-1.3M11.5 4.5l1.3-1.3", 1.5, True)],
    "moon": [body("M10.6 1.8a6.4 6.4 0 1 0 3.6 10.4A5.2 5.2 0 0 1 10.6 1.8z")],
    "cloud": [body("M4.4 13a3 3 0 0 1-.4-6 4.4 4.4 0 0 1 8.4-1 3.5 3.5 0 0 1 .2 7z"),
              shine(7.6, 6.4, 2.2, 1)],
    "leaf": [body("M2.4 13.6C2 7 5.6 2.4 13.8 2.2c.2 8.2-4.6 11.8-11.4 11.4z"),
             line("M2.4 13.6L10 6", 1)],
    "paw": [body("M8 8.4c-2.4 0-4.4 2.4-4.4 4.2 0 1.4 1.4 1.8 2.4 1.5.8-.2 1.3-.5 2-.5s1.2"
                 ".3 2 .5c1 .3 2.4-.1 2.4-1.5 0-1.8-2-4.2-4.4-4.2z"),
            ball(3, 6.4, 1.4), ball(6, 3.6, 1.5), ball(10, 3.6, 1.5), ball(13, 6.4, 1.4)],
    "fish": [body("M1.6 8c1.8-3 4.4-4.4 7.2-4.4 2.4 0 4 1.4 5 2.6l1.4-1.6v6.8l-1.4-1.6c-1"
                  " 1.2-2.6 2.6-5 2.6C6 12.4 3.4 11 1.6 8z"), dot(4.6, 7.4, .8)],
    "car": [body("M2.4 7.2l1.6-3.6a1.6 1.6 0 0 1 1.5-1h5a1.6 1.6 0 0 1 1.5 1l1.6 3.6a1.6"
                 " 1.6 0 0 1 1 1.5v3.1H1.4V8.7a1.6 1.6 0 0 1 1-1.5z"),
            line("M3.8 7h8.4", 1), dot(4.4, 12, 1.6, True), dot(11.6, 12, 1.6, True)],
    "plane": [body("M8 1c.8 0 1.2.8 1.2 1.8v3.6l5.4 3.2v1.6L9.2 9.6v2.8l1.8 1.4v1.4L8"
                   " 14.4l-3 .8v-1.4l1.8-1.4V9.6l-5.4 1.6V9.6l5.4-3.2V2.8C6.8 1.8 7.2 1 8"
                   " 1z")],
    "cup": [body("M2.4 5h9.2v5.2a3.4 3.4 0 0 1-3.4 3.4H5.8a3.4 3.4 0 0 1-3.4-3.4z"),
            line("M11.6 6.4h1a1.8 1.8 0 0 1 0 3.6h-1", 1.4, True),
            line("M5 1.6v1.6M7 1.2v2M9 1.6v1.6", 1.2, True)],
    "food": [line("M4 1.6v4.6a1.6 1.6 0 0 0 3.2 0V1.6M5.6 1.6v12.8M11.4 14.4V1.6c-1.8 1-2.4"
                  " 3-2.4 5.4 0 1.2.8 1.8 2.4 1.8", 1.6)],
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name, parts in PICTURES.items():
        (OUT / f"{name}.svg").write_text(HEAD + "".join(parts) + "</svg>\n", "utf-8")
    print(f"{len(PICTURES)} pictures → {OUT}")


if __name__ == "__main__":
    main()
