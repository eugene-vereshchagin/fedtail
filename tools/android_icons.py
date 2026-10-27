"""The Android app's launcher icons, made from the desktop's (fedtail/data/icons/fedtail.png):
an adaptive icon — the picture on a plain ground, inside the safe zone every launcher's
mask keeps — a monochrome layer for Android 13's themed icons, the legacy round
and square ones for launchers without adaptive icons, and the notifications' small icon.
Run it again when the icon changes:

    python3 tools/android_icons.py      # needs Pillow (python3-pil)
"""

from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "fedtail" / "data" / "icons" / "fedtail.png"
RES = ROOT / "android" / "app" / "src" / "main" / "res"
GROUND = "#F4EDE6"  # warm paper under the grey and pink
DENSITIES = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
# an adaptive layer is 108 dp; launchers show at least the middle 66 dp, the picture
# stays well inside that (its own empty margins add to it)
LAYER_DP, PICTURE_DP, LEGACY_DP = 108, 62, 48
STATUS_DP = 24  # a notification's small icon


def trimmed(im):
    return im.crop(im.getbbox())


def placed(picture, side, inner):
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    p = picture.copy()
    p.thumbnail((inner, inner), Image.LANCZOS)
    out.paste(p, ((side - p.width) // 2, (side - p.height) // 2), p)
    return out


def monochrome(layer):
    """Android tints it with the wallpaper's colour: only the shape (alpha) counts. The
    whole silhouette would be a shapeless blob — the drawing's dark lines are kept (the
    outline, the eyes), so the possum stays recognisable in one colour."""
    gray = layer.convert("L")
    alpha = layer.getchannel("A")
    lines = gray.point(lambda v: 255 if v < 110 else 0)
    shape = Image.composite(lines, Image.new("L", layer.size, 0), alpha.point(
        lambda a: 255 if a > 128 else 0))
    out = Image.new("RGBA", layer.size, (255, 255, 255, 0))
    out.putalpha(shape)
    return out


def status(picture, side):
    """The notification's small icon (the shade, the status bar): Android paints only
    its shape, in one colour. The possum filled, its pale face and belly cut out, so the
    eyes and the snout show (a plain silhouette is a blob; the drawing's lines alone
    vanish at 24 dp) — drawn large, then brought down to the size."""
    big = 480
    p = picture.copy()
    p.thumbnail((big, big), Image.LANCZOS)
    shape = ImageChops.subtract(p.getchannel("A").point(lambda a: 255 if a > 100 else 0),
                                p.convert("L").point(lambda v: 255 if v > 230 else 0))
    full = Image.new("L", (big, big), 0)
    full.paste(shape, ((big - p.width) // 2, (big - p.height) // 2))
    out = Image.new("RGBA", (side, side), (255, 255, 255, 0))
    out.putalpha(full.resize((side, side), Image.LANCZOS).point(lambda v: 255 if v > 110 else 0))
    return out


def legacy(picture, side, round_):
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    mask = Image.new("L", (side, side), 0)
    d = ImageDraw.Draw(mask)
    if round_:
        d.ellipse((0, 0, side - 1, side - 1), fill=255)
    else:
        d.rounded_rectangle((0, 0, side - 1, side - 1), radius=side // 5, fill=255)
    ground = Image.new("RGBA", (side, side), GROUND)
    out.paste(ground, (0, 0), mask)
    pic = placed(picture, side, int(side * 0.78))
    out.alpha_composite(pic)
    return out


def main():
    picture = trimmed(Image.open(SOURCE).convert("RGBA"))
    for name, k in DENSITIES.items():
        folder = RES / f"mipmap-{name}"
        folder.mkdir(parents=True, exist_ok=True)
        side = round(LAYER_DP * k)
        fg = placed(picture, side, round(PICTURE_DP * k))
        fg.save(folder / "ic_launcher_foreground.png", optimize=True)
        monochrome(fg).save(folder / "ic_launcher_monochrome.png", optimize=True)
        small = round(LEGACY_DP * k)
        legacy(picture, small, False).save(folder / "ic_launcher.png", optimize=True)
        legacy(picture, small, True).save(folder / "ic_launcher_round.png", optimize=True)
        drawable = RES / f"drawable-{name}"
        drawable.mkdir(parents=True, exist_ok=True)
        status(picture, round(STATUS_DP * k)).save(drawable / "ic_stat_fedtail.png",
                                                   optimize=True)
    any_dpi = RES / "mipmap-anydpi-v26"
    any_dpi.mkdir(parents=True, exist_ok=True)
    xml = ('<?xml version="1.0" encoding="utf-8"?>\n'
           '<!-- made by tools/android_icons.py from fedtail/data/icons/fedtail.png -->\n'
           '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
           '    <background android:drawable="@color/ic_launcher_background" />\n'
           '    <foreground android:drawable="@mipmap/ic_launcher_foreground" />\n'
           '    <monochrome android:drawable="@mipmap/ic_launcher_monochrome" />\n'
           '</adaptive-icon>\n')
    for name in ("ic_launcher.xml", "ic_launcher_round.xml"):
        (any_dpi / name).write_text(xml, "utf-8")
    (RES / "values" / "ic_launcher.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n<resources>\n'
        f'    <color name="ic_launcher_background">{GROUND}</color>\n</resources>\n', "utf-8")
    # the empty lane's swinging opossum (Possum.kt): the desktop's GIF as it is
    raw = RES / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    (raw / "possum_swing.gif").write_bytes((SOURCE.parent / "fedtail-swing.gif").read_bytes())
    print("icons written under", RES)


if __name__ == "__main__":
    main()
