"""The made-up world every screenshot shows — Qt's, GTK's, the terminal's, the web's,
the gallery's: Мира (@mira, me) and the people she talks to, a thread about a router,
mountains, a poll, a storm warning, likes and boosts — and its pictures (faces with a
letter, the mountains, the storm), drawn here: no network, no toolkit.

    from tools import showcase
    FakeApi.world = showcase.world()
    showcase.picture_png(url)   # the bytes of a face or a picture of that world
"""

from __future__ import annotations

import io
import struct
import zlib

from tests import fakes
from tests.fakes import ME, acct, status

KOT = acct("K", "kot@kot.example")
KOT["display_name"] = "Кот Учёный"
ARSEN = acct("A", "arsen@gts.example")
ARSEN["display_name"] = "Арсен"
OSTAP = acct("O", "ostap@vivaldi.example")
OSTAP["display_name"] = "Остап"
NEWS = acct("N", "weather_news", bot=True)
NEWS["display_name"] = "Погода на побережье"
AVATAR_COLORS = {"K": ("#d9c7a3", "К"), "A": ("#2f4f6f", "А"), "O": ("#5a3d5c", "О"),
                 "N": ("#7a3b2e", "Н"), "ME": ("#3b4a3f", "М")}
for a in (KOT, ARSEN, OSTAP, NEWS, ME):
    a["avatar_static"] = f"https://img.example/avatar/{a['id']}"


def _recent(w):
    """Give the made-up posts today's dates, so cards show times, not years."""
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC).replace(second=0, microsecond=0)
    for st in w.statuses.values():
        minute = int(st["created_at"][14:16])
        st["created_at"] = (now - timedelta(minutes=60 - minute)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z")
    for n in w.notifications:
        n["created_at"] = n["status"]["created_at"]


def world():
    """The made-up server: posts, a thread, pictures, a poll, activity, lists."""
    w = fakes.World()
    t = lambda m: m  # minutes since 10:00 keep the order readable
    router = w.add(status("100", ME, minute=t(1), text="Роутер второй раз за неделю отвалился, "
                          "похоже, пора его менять. Кто что посоветует под OpenWrt, "
                          "чтобы без танцев?"), home=True)
    w.add(status("101", KOT, "100", "ME", minute=t(3), text="@mira перед тем как менять — "
                 "протри контакты и поставь умную розетку на мониторинг. У меня ровно так же "
                 "было: дело оказалось в блоке питания."), home=True, mention=True)
    mine = w.add(status("102", ME, "101", "K", minute=t(5), text="@kot а розетку какую взял? "
                        "Чтобы без облака, только по локальной сети."), home=True)
    w.add(status("103", KOT, mine["id"], "ME", minute=t(8), text="@mira обычную на Zigbee, "
                 "прошитую. Облака там нет вообще."), home=True, mention=True)
    pic = status("104", ARSEN, minute=t(12), vis="public",
                 text="Есть в горах точки, откуда видно сразу три страны и весь хребет. "
                      "Высота 2600 метров, дорога — только на полном приводе.")
    pic["media_attachments"] = [{"type": "image", "url": "https://img.example/full/mountains",
                                 "preview_url": "https://img.example/small/mountains",
                                 "description": "Горный хребет на закате",
                                 "meta": {"original": {"width": 1600, "height": 900}}}]
    pic["favourites_count"], pic["favourited"], pic["reblogs_count"] = 5, True, 1
    w.add(pic, home=True)
    w.add(status("105", ME, "104", "A", minute=t(14), text="@arsen с перевала в ясную погоду "
                 "видно, да. Но дорогу размыло."), home=True)
    w.add(status("106", OSTAP, minute=t(18), vis="unlisted", text="Десять лет на Point, а "
                 "потом раз — и все разбежались кто куда. Хорошо, что хоть треды теперь снова "
                 "деревом."), home=True)
    w.add(status("107", NEWS, minute=t(20), vis="public", text="Сильный порывистый ветер "
                 "уже второй день на побережье. #погода"), home=True)
    w.add(status("108", OSTAP, "100", "ME", minute=t(25), text="@mira а я свой просто "
                 "перевернул вверх ногами — перестал греться. Десять лет работает."),
          home=True, mention=True)
    w.statuses["106"]["poll"] = {
        "id": "P1", "expired": False, "multiple": False, "voted": True, "own_votes": [0],
        "votes_count": 23, "voters_count": 23, "expires_at": "2099-01-01T12:00:00Z",
        "options": [{"title": "GoToSocial", "votes_count": 12},
                    {"title": "Mastodon", "votes_count": 7},
                    {"title": "обратно на Point", "votes_count": 4}]}
    w.statuses["107"]["card"] = {
        "url": "https://weather.example/black-sea-storm", "provider_name": "weather.example",
        "title": "Шторм на побережье: ветер до 25 м/с",
        "description": "Порывы до 25 метров в секунду ожидаются во всех портах до конца "
                       "недели, паромы задерживаются.",
        "image": "https://img.example/small/storm"}
    w.requests = [OSTAP]
    router = w.statuses.get("100")
    for i, (kind, who) in enumerate((("favourite", KOT), ("favourite", ARSEN),
                                     ("favourite", OSTAP), ("reblog", ARSEN),
                                     ("follow", OSTAP)), 1):
        w.act(f"act{i}", kind, who, router if kind != "follow" else None, minute=i)
    w.lists = {"L1": {"title": "Новости", "exclusive": True, "members": {NEWS["id"]}},
               "L2": {"title": "Мемасики", "exclusive": True, "members": set()}}
    del router
    _recent(w)
    return w



def _png_plain(w, h, rgb):
    raw = b"".join(b"\x00" + bytes(rgb) * w for _ in range(h))

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + \
            struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _hex(c):
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(x * 2 for x in c)
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def picture_png(url):
    """A face (its colour and letter) or a picture (mountains at dusk, a stormy sea) of
    the made-up world, as PNG bytes. With Pillow: drawn; without: one colour."""
    url = url or ""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        Image = None  # noqa: N806
    if "/avatar/" in url:
        color, letter = AVATAR_COLORS.get(url.rsplit("/", 1)[1], ("#777777", "?"))
        if Image is None:
            return _png_plain(88, 88, _hex(color))
        im = Image.new("RGB", (88, 88), color)
        d = ImageDraw.Draw(im)
        try:
            font = ImageFont.truetype("DejaVuSans-Bold.ttf", 44)
        except OSError:
            try:
                font = ImageFont.load_default(size=44)
            except TypeError:
                font = ImageFont.load_default()
        d.text((44, 46), letter, fill="#ffffff", font=font, anchor="mm")
        return _save(im)
    storm = "storm" in url
    w, h = (800, 450)
    if Image is None:
        return _png_plain(w // 4, h // 4, (0x5f, 0x74, 0x86))
    stops = ((0, "#46586b"), (0.5, "#6f8496"), (1, "#22303b")) if storm else \
        ((0, "#cfd9e2"), (0.45, "#9fb2c3"), (0.7, "#5f7486"), (1, "#3d4c59"))
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / (h - 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:], strict=False):
            if t0 <= t <= t1:
                k = (t - t0) / (t1 - t0) if t1 > t0 else 0
                a, b = _hex(c0), _hex(c1)
                d.line([(0, y), (w, y)], fill=tuple(round(a[i] + (b[i] - a[i]) * k)
                                                    for i in range(3)))
                break
    if storm:  # waves
        for i in range(7):
            y0 = 250 + i * 30
            d.line([(x, y0 + (12 if (x // 40) % 2 else 0)) for x in range(0, w + 40, 40)],
                   fill="#c9d6df", width=3)
    else:  # the ridge
        d.polygon([(x / 2, y / 2) for x, y in
                   ((0, 900), (0, 620), (300, 420), (520, 560), (820, 300), (1100, 520),
                    (1350, 380), (1600, 560), (1600, 900))], fill="#2c3843")
    return _save(im)


def _save(im):
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()
