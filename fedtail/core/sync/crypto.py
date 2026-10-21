"""What devices tell each other, sealed so that only they can read it.

A batch of operations (JSON) is compressed and encrypted with AES-256-GCM under the
account's sync key — 32 random bytes made on the first device and carried to the
others by hand (`fedtail sync key` / `fedtail sync join`). Whatever stores the
batches (a sync server, a folder, a WebDAV share) sees opaque bytes: not what was read,
not which threads. A blob says only which key sealed it (8 bytes of a hash of the key),
so a device with another key knows at once that it is not its own journal.

    blob = b"FTS1" | key id (8) | nonce (12) | AES-GCM(zlib(json)) with the first 12 as AAD

The `cryptography` package does the AES; it is optional for fedtail as a whole
(Debian: python3-cryptography), and only sync needs it: `CryptoMissing` says so.
"""

import base64
import hashlib
import json
import os
import zlib

MAGIC = b"FTS1"
KEY_BYTES = 32
_HEAD = len(MAGIC) + 8
_NONCE = 12
MAX_PLAIN = 8 * 1024 * 1024  # a batch never opens bigger than this


class CryptoMissing(RuntimeError):
    """The `cryptography` package isn't installed."""


class BadBlob(ValueError):
    """Not a blob of ours, or not sealed by this key, or damaged."""


def _aes(key):
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:
        raise CryptoMissing("sync needs the 'cryptography' package "
                            "(Debian: python3-cryptography)") from e
    return AESGCM(key)


def available():
    try:
        _aes(bytes(KEY_BYTES))
    except CryptoMissing:
        return False
    return True


def new_key():
    return os.urandom(KEY_BYTES)


def key_id(key):
    return hashlib.sha256(b"fedtail sync key id\0" + key).digest()[:8]


def key_text(key):
    """The key as a person copies it: base32 in groups of four, like a licence key."""
    text = base64.b32encode(key).decode().rstrip("=")
    return "-".join(text[i:i + 4] for i in range(0, len(text), 4))


def key_from_text(text):
    """The key back from key_text() — spaces, dashes, case and a missing '=' forgiven."""
    clean = "".join(c for c in (text or "").upper() if c.isalnum())
    clean += "=" * (-len(clean) % 8)
    try:
        key = base64.b32decode(clean)
    except ValueError as e:  # binascii.Error is one
        raise ValueError("not a sync key") from e
    if len(key) != KEY_BYTES:
        raise ValueError("not a sync key")
    return key


def seal(key, obj):
    plain = zlib.compress(json.dumps(obj, separators=(",", ":")).encode(), 6)
    head = MAGIC + key_id(key)
    nonce = os.urandom(_NONCE)
    return head + nonce + _aes(key).encrypt(nonce, plain, head)


def blob_key_id(blob):
    if len(blob) < _HEAD + _NONCE + 16 or blob[:len(MAGIC)] != MAGIC:
        raise BadBlob("not a fedtail sync blob")
    return blob[len(MAGIC):_HEAD]


def unseal(key, blob):
    if blob_key_id(blob) != key_id(key):
        raise BadBlob("sealed by another key")
    head, nonce, body = blob[:_HEAD], blob[_HEAD:_HEAD + _NONCE], blob[_HEAD + _NONCE:]
    try:
        from cryptography.exceptions import InvalidTag
    except ImportError as e:
        raise CryptoMissing("sync needs the 'cryptography' package") from e
    try:
        plain = _aes(key).decrypt(nonce, body, head)
    except InvalidTag as e:
        raise BadBlob("damaged or forged") from e
    d = zlib.decompressobj()
    data = d.decompress(plain, MAX_PLAIN)
    if d.unconsumed_tail:
        raise BadBlob("too big")
    return json.loads(data)


# ---- the key file: data dir / sync.key, the owner's only, never in a bug report ------

def load_key(path):
    try:
        data = json.loads(path.read_text("utf-8"))
        return key_from_text(data["key"])
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def save_key(path, key):
    from .. import auth
    auth.save(path, {"key": key_text(key)})
