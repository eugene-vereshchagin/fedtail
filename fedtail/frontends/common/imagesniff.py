"""What a picture is, by its first bytes, and whether it came whole — before any
toolkit's decoder sees it.

Left to itself, Qt's QImageReader asks every installed plugin "is this yours?" —
KDE's kimageformats among them (PSD, XCF, RAS, PIC, JXL, HEIF, EXR…), plugins made for
files opened by hand, not for whatever a network hands over. On a picture cut short by
a flaky connection, or simply not theirs, some of them seek far past the end
(QBuffer::seek: Invalid pos: 2418672158) and abort the whole process (28.10, on a
phone's mobile internet). So fedtail names the format itself and lets only that one
decoder read it; a file that isn't one of the formats a post's picture can be, or that
ended before its end, never reaches a decoder (and never the disk cache).
"""

from __future__ import annotations

import struct

# formats a fediverse picture can be; "risky": read by plugins outside Qt itself (and
# GdkPixbuf's extra loaders) — read one at a time, see DECODE_ALONE
COMMON = ("jpeg", "png", "gif", "webp", "bmp")
RISKY = ("avif", "heic", "jxl", "tiff", "ico", "svg")


def sniff(data):
    """The format name Qt and GdkPixbuf know it by, or None: not a picture we read."""
    head = bytes(data[:64])
    if head[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    if head[:2] == b"BM" and len(head) >= 26:
        return "bmp"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"avif", b"avis"):
            return "avif"
        if brand in (b"heic", b"heix", b"hevc", b"hevx", b"mif1", b"msf1"):
            return "heic"
        return None  # an MP4, a MOV: a video, not a picture
    if head[:2] == b"\xff\x0a" or head[:12] == b"\x00\x00\x00\x0cJXL \r\n\x87\n":
        return "jxl"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "tiff"
    if head[:4] == b"\x00\x00\x01\x00":
        return "ico"
    text = head.lstrip()[:5].lower()
    if text.startswith(b"<svg") or text.startswith(b"<?xml"):
        return "svg"
    return None


def whole(data, fmt):
    """Did the file come to its end? (a connection cut mid-picture leaves a head with no
    tail). Formats without a tail to look for: yes."""
    data = bytes(data)
    if fmt == "jpeg":
        # the end-of-image mark, allowing a little padding after it (some servers add)
        return b"\xff\xd9" in data[-64:]
    if fmt == "png":
        return b"IEND" in data[-32:]
    if fmt == "gif":
        return data.rstrip(b"\x00")[-1:] == b"\x3b"
    if fmt == "webp":
        if len(data) < 12:
            return False
        (size,) = struct.unpack("<I", data[4:8])
        return len(data) >= size + 8
    if fmt == "bmp":
        (size,) = struct.unpack("<I", data[2:6])
        return size == 0 or len(data) >= size
    if fmt in ("avif", "heic"):
        return _boxes_whole(data)
    return True


def _boxes_whole(data):
    """ISO BMFF (AVIF, HEIF): the boxes add up to the file, none runs past its end."""
    at, n = 0, len(data)
    while at < n:
        if n - at < 8:
            return False
        (size,) = struct.unpack(">I", data[at:at + 4])
        if size == 1:  # a 64-bit size follows the type
            if n - at < 16:
                return False
            (size,) = struct.unpack(">Q", data[at + 8:at + 16])
        elif size == 0:  # to the end of the file
            return True
        if size < 8 or at + size > n:
            return False
        at += size
    return True


def readable(data):
    """(format, why not) — format None when the bytes must not reach a decoder:
    "not a picture" or "cut short"."""
    fmt = sniff(data)
    if fmt is None:
        return None, "not a picture"
    if not whole(data, fmt):
        return None, "cut short"
    return fmt, ""
