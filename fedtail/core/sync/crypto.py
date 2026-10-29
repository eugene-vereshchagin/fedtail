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


# ---- the pictures of drafts ---------------------------------------------------------
# A draft's picture travels on its own, beside the journal (the store keeps it under a
# name, PROTOCOL.md): sealed like a blob, its bytes in place of the JSON, and named by a
# keyed hash — the same picture has the same name (stored once), and the name tells the
# store nothing about it.
#
#     picture = b"FTM1" | key id (8) | nonce (12) | AES-GCM(the bytes) with the first 12 as AAD

MEDIA = b"FTM1"
MAX_MEDIA = 16 * 1024 * 1024  # a picture never opens bigger than this


def media_name(key, data):
    import hashlib
    import hmac
    return hmac.new(key, b"fedtail-media" + bytes(data), hashlib.sha256).hexdigest()[:48]


def seal_media(key, data):
    head = MEDIA + key_id(key)
    nonce = os.urandom(_NONCE)
    return head + nonce + _aes(key).encrypt(nonce, bytes(data), head)


def unseal_media(key, blob):
    """The picture's bytes; BadBlob: not one, another key's, damaged, or not the picture
    its name says (`media_name` is checked by the caller)."""
    blob = bytes(blob)
    if len(blob) < _HEAD + _NONCE + 16 or blob[:len(MEDIA)] != MEDIA:
        raise BadBlob("not a fedtail picture")
    if len(blob) > MAX_MEDIA + _HEAD + _NONCE + 16:
        raise BadBlob("too big")
    if blob[len(MEDIA):_HEAD] != key_id(key):
        raise BadBlob("sealed by another key")
    head, nonce, body = blob[:_HEAD], blob[_HEAD:_HEAD + _NONCE], blob[_HEAD + _NONCE:]
    try:
        from cryptography.exceptions import InvalidTag
    except ImportError as e:
        raise CryptoMissing("sync needs the 'cryptography' package") from e
    try:
        return _aes(key).decrypt(nonce, body, head)
    except InvalidTag as e:
        raise BadBlob("damaged or forged") from e


# ---- the key kept in the journal under a password ("escrow") ------------------------
# A device that knows the key may put it into the journal itself, sealed by a password:
# a new device with only the password (and the fediverse account it logs into) takes it
# from there — no other device needs to be at hand. The store sees one more opaque blob.
#
#     blob = b"FTK2" | salt (16) | nonce (12) | AES-GCM(the key) with the first 20 as AAD
#
# The password is stretched with scrypt (n = 2**17, r = 8: 128 MB, slow to guess
# offline). FTK1 (0.21, n = 2**15) is still opened — a folder's journal may hold one —
# but never made.

ESCROW = b"FTK2"
ESCROW_OLD = b"FTK1"
_SALT = 16
SCRYPT = {"n": 2 ** 17, "r": 8, "p": 1, "maxmem": 256 * 1024 * 1024}
_SCRYPT_OLD = {**SCRYPT, "n": 2 ** 15}
MIN_PASSWORD = 10


def _stretch(password, salt, params=None):
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, dklen=KEY_BYTES,
                          **(params or SCRYPT))


def is_escrow(blob):
    return isinstance(blob, (bytes, bytearray)) and bytes(blob[:len(ESCROW)]) in (
        ESCROW, ESCROW_OLD)


def escrow_seal(key, password):
    """The key sealed by a password, as a blob for the journal."""
    if len(password or "") < MIN_PASSWORD:
        raise ValueError("password too short")
    salt = os.urandom(_SALT)
    head = ESCROW + salt
    nonce = os.urandom(_NONCE)
    return head + nonce + _aes(_stretch(password, salt)).encrypt(nonce, key, head)


def escrow_open(blob, password):
    """The key back from such a blob. BadBlob: not one, or the password is wrong."""
    if not is_escrow(blob) or len(blob) < len(ESCROW) + _SALT + _NONCE + 16:
        raise BadBlob("not a key blob")
    head = blob[:len(ESCROW) + _SALT]
    nonce = blob[len(head):len(head) + _NONCE]
    body = blob[len(head) + _NONCE:]
    try:
        from cryptography.exceptions import InvalidTag
    except ImportError as e:
        raise CryptoMissing("sync needs the 'cryptography' package") from e
    try:
        params = _SCRYPT_OLD if head[:len(ESCROW)] == ESCROW_OLD else SCRYPT
        key = _aes(_stretch(password or "", head[len(ESCROW):], params)).decrypt(
            nonce, body, head)
    except InvalidTag as e:
        raise BadBlob("wrong password") from e
    if len(key) != KEY_BYTES:
        raise BadBlob("not a key")
    return key


# ---- whose journal on a sync server (protocol 2): the key's ------------------------
# The server files a journal under an id and checks a secret, both derived from the key
# (the key itself never goes there): whoever has the key has the journal.

def journal_id(key):
    """32 hex digits: the journal's name on a sync server."""
    import hmac
    return hmac.new(key, b"fedtail-journal-id", hashlib.sha256).hexdigest()[:32]


def journal_secret(key):
    """64 hex digits: what proves a device has the key."""
    import hmac
    return hmac.new(key, b"fedtail-journal-secret", hashlib.sha256).hexdigest()


def escrow_id(password, where, who):
    """Where the key under a password is kept on a sync server: an id from the password
    and the fediverse account (`who`, "user@host" — a new device has logged in to it),
    stretched as the password is, different for each server (`where`, its address). The
    account makes it one person's: a guessed password tests one account, not everyone
    on the server (PROTOCOL.md)."""
    who = str(who or "").strip().lstrip("@").lower()
    if "@" not in who:
        raise ValueError("the account, user@host, is needed")
    salt = b"fedtail-escrow-id:" + str(where).rstrip("/").lower().encode("utf-8") + \
        b"\n" + who.encode("utf-8")
    return _stretch(password or "", salt).hex()


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
