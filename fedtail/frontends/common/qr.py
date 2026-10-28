"""A QR code of a short text, without a library: the sync key shown on one device and
scanned by another (≡ → Sync → "Show the key"). Byte mode, error correction M (15 % of
the code may be lost), versions 1–10 (up to 213 bytes) — the key is well under that.
Every interface draws the matrix itself: Qt and GTK as a picture, the web page as SVG,
the terminal in half blocks, the phone on a canvas.

    m = matrix("fedtail-sync:…")    # [[bool]] — True is dark, no quiet zone
    r = rows(m)                     # "1"/"0" strings with the quiet zone (what a Row holds)
    svg(r), blocks(r)               # the web page's picture, the terminal's lines

The algorithm is the standard's (ISO/IEC 18004), laid out the way Project Nayuki's
reference encoder does it.
"""

from __future__ import annotations

# version → (data codewords per block of group 1, blocks, of group 2, blocks, EC per block)
_BLOCKS_M = {
    1: (16, 1, 0, 0, 10), 2: (28, 1, 0, 0, 16), 3: (44, 1, 0, 0, 26), 4: (32, 2, 0, 0, 18),
    5: (43, 2, 0, 0, 24), 6: (27, 4, 0, 0, 16), 7: (31, 4, 0, 0, 18), 8: (38, 2, 39, 2, 22),
    9: (36, 3, 37, 2, 22), 10: (43, 4, 44, 1, 26),
}
_ALIGN = {1: (), 2: (6, 18), 3: (6, 22), 4: (6, 26), 5: (6, 30), 6: (6, 34),
          7: (6, 22, 38), 8: (6, 24, 42), 9: (6, 26, 46), 10: (6, 28, 50)}
_FORMAT_M = 0  # the two bits of level M in the format information


class TooLong(ValueError):
    """More than version 10 holds."""


def _capacity(version):
    a, na, b, nb, _ec = _BLOCKS_M[version]
    return a * na + b * nb


def _mul(x, y):
    """Multiplication in GF(256) modulo x^8 + x^4 + x^3 + x^2 + 1."""
    z = 0
    for i in reversed(range(8)):
        z = ((z << 1) ^ ((z >> 7) * 0x11D)) & 0xFF
        z ^= ((y >> i) & 1) * x
    return z


def _divisor(degree):
    out = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(degree):
            out[j] = _mul(out[j], root)
            if j + 1 < degree:
                out[j] ^= out[j + 1]
        root = _mul(root, 0x02)
    return out


def _remainder(data, divisor):
    out = [0] * len(divisor)
    for b in data:
        factor = b ^ out.pop(0)
        out.append(0)
        for i, c in enumerate(divisor):
            out[i] ^= _mul(c, factor)
    return out


def _codewords(data, version):
    """The data's bits (byte mode), padded, split into blocks, with their error
    correction, interleaved — the sequence of codewords to place."""
    bits = []

    def put(value, n):
        bits.extend((value >> i) & 1 for i in reversed(range(n)))

    put(0b0100, 4)
    put(len(data), 8 if version < 10 else 16)
    for b in data:
        put(b, 8)
    room = _capacity(version) * 8
    put(0, min(4, room - len(bits)))
    put(0, -len(bits) % 8)
    pad = 0xEC
    while len(bits) < room:
        put(pad, 8)
        pad ^= 0xEC ^ 0x11
    words = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
    a, na, b, nb, ec = _BLOCKS_M[version]
    blocks, at = [], 0
    for size, count in ((a, na), (b, nb)):
        for _ in range(count):
            blocks.append(words[at:at + size])
            at += size
    div = _divisor(ec)
    eccs = [_remainder(blk, div) for blk in blocks]
    out = []
    for i in range(max(len(blk) for blk in blocks)):
        out += [blk[i] for blk in blocks if i < len(blk)]
    for i in range(ec):
        out += [e[i] for e in eccs]
    return out


class _Grid:
    def __init__(self, version):
        self.version = version
        self.size = version * 4 + 17
        self.dark = [[False] * self.size for _ in range(self.size)]
        self.fixed = [[False] * self.size for _ in range(self.size)]

    def set(self, x, y, dark):
        self.dark[y][x] = dark
        self.fixed[y][x] = True

    def functions(self):
        n = self.size
        for i in range(n):  # timing
            self.set(6, i, i % 2 == 0)
            self.set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):  # finders with their separators
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        self.set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = _ALIGN[self.version]
        last = len(pos) - 1
        for i, cy in enumerate(pos):
            for j, cx in enumerate(pos):
                if (i, j) in ((0, 0), (0, last), (last, 0)):
                    continue  # where the finders are
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self.set(cx + dx, cy + dy, max(abs(dx), abs(dy)) != 1)
        self.format(0)  # reserved now, written with the mask chosen
        if self.version >= 7:
            rem = self.version
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.version << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self.set(a, b, bit)
                self.set(b, a, bit)

    def format(self, mask):
        n = self.size
        data = _FORMAT_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412

        def bit(i):
            return (bits >> i) & 1 == 1
        for i in range(6):
            self.set(8, i, bit(i))
        self.set(8, 7, bit(6))
        self.set(8, 8, bit(7))
        self.set(7, 8, bit(8))
        for i in range(9, 15):
            self.set(14 - i, 8, bit(i))
        for i in range(8):
            self.set(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self.set(8, n - 15 + i, bit(i))
        self.set(8, n - 8, True)

    def place(self, words):
        n, i, total = self.size, 0, len(words) * 8
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    up = ((right + 1) & 2) == 0
                    y = n - 1 - vert if up else vert
                    if not self.fixed[y][x] and i < total:
                        self.dark[y][x] = (words[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def masked(self, mask):
        test = _MASKS[mask]
        return [[d ^ (not f and test(y, x)) for x, (d, f) in enumerate(zip(row, frow, strict=True))]
                for y, (row, frow) in enumerate(zip(self.dark, self.fixed, strict=True))]


_MASKS = (
    lambda i, j: (i + j) % 2 == 0,
    lambda i, j: i % 2 == 0,
    lambda i, j: j % 3 == 0,
    lambda i, j: (i + j) % 3 == 0,
    lambda i, j: (i // 2 + j // 3) % 2 == 0,
    lambda i, j: (i * j) % 2 + (i * j) % 3 == 0,
    lambda i, j: ((i * j) % 2 + (i * j) % 3) % 2 == 0,
    lambda i, j: ((i + j) % 2 + (i * j) % 3) % 2 == 0,
)
_FINDERISH = ([True, False, True, True, True, False, True, False, False, False, False],
              [False, False, False, False, True, False, True, True, True, False, True])


def _penalty(m):
    """The standard's four penalties: long runs, 2×2 blocks, finder look-alikes, balance."""
    n, score = len(m), 0
    lines = m + [list(col) for col in zip(*m, strict=True)]
    for line in lines:
        run, prev = 0, None
        for d in line:
            if d == prev:
                run += 1
            else:
                if run >= 5:
                    score += 3 + run - 5
                run, prev = 1, d
        if run >= 5:
            score += 3 + run - 5
        for k in range(n - 10):
            if line[k:k + 11] in _FINDERISH:
                score += 40
    for y in range(n - 1):
        for x in range(n - 1):
            if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                score += 3
    dark = sum(map(sum, m))
    total = n * n
    score += ((abs(dark * 20 - total * 10) + total - 1) // total - 1) * 10
    return score


def matrix(text, mask=None):
    """The QR code of `text` (UTF-8): rows of modules, True dark; no quiet zone (draw
    four light modules around it). mask: 0–7 to force one (tests); the best by default.
    TooLong past version 10."""
    data = text.encode("utf-8") if isinstance(text, str) else bytes(text)
    version = next((v for v in _BLOCKS_M
                    if 4 + (8 if v < 10 else 16) + 8 * len(data) <= 8 * _capacity(v)), None)
    if version is None:
        raise TooLong(len(data))
    grid = _Grid(version)
    grid.functions()
    grid.place(_codewords(data, version))
    best = None
    for k in (range(8) if mask is None else (mask,)):
        grid.format(k)
        m = grid.masked(k)
        score = _penalty(m) if mask is None else 0
        if best is None or score < best[0]:
            best = (score, k, m)
    grid.format(best[1])
    return grid.masked(best[1])


QUIET = 4  # light modules around the code, as the standard asks


def rows(m):
    """The matrix as strings of "1" and "0", the quiet zone included (the phone draws it)."""
    n = len(m) + 2 * QUIET
    blank = "0" * n
    pad = "0" * QUIET
    return [blank] * QUIET + [pad + "".join("1" if d else "0" for d in r) + pad
                              for r in m] + [blank] * QUIET


def svg(rows_, module=6, dark="#000", light="#fff"):
    """The code (rows(), quiet zone included) as an SVG picture (the web page): dark on
    light whatever the theme — a scanner wants it so."""
    n = len(rows_)
    path = "".join(f"M{x},{y}h1v1h-1z" for y, r in enumerate(rows_)
                   for x, c in enumerate(r) if c == "1")
    size = n * module
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
            f'viewBox="0 0 {n} {n}" shape-rendering="crispEdges">'
            f'<rect width="{n}" height="{n}" fill="{light}"/>'
            f'<path d="{path}" fill="{dark}"/></svg>')


def blocks(rows_):
    """The code (rows(), quiet zone included) in half blocks, two rows of modules a line
    (the terminal): light modules are "█", dark ones spaces — light ink on a dark ground."""
    r = list(rows_)
    if len(r) % 2:
        r.append("0" * len(r[0]))
    cell = {("0", "0"): "█", ("1", "1"): " ", ("1", "0"): "▄", ("0", "1"): "▀"}
    return ["".join(cell[(a, b)] for a, b in zip(top, bottom, strict=True))
            for top, bottom in zip(r[0::2], r[1::2], strict=True)]


__all__ = ["QUIET", "TooLong", "blocks", "matrix", "rows", "svg"]
