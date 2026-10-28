"""Read marks and thread states of one account, the same on all its devices.

The server keeps no such thing (Mastodon's markers are one position per timeline), so
the devices keep a journal each and exchange it through a dumb store, sealed with a key
only they have:

    engine.py    Sync: what is recorded, the round (send, fetch, apply), the key's birth
    crypto.py    AES-GCM sealing, the key and its text form, the key file
    backends.py  where the blobs meet: a fedtail-sync server (sync.url), a folder

The server side is fedtail-sync, a project of its own
(https://github.com/eugene-vereshchagin/fedtail-syncserver). docs/en/sync.md says how to
set it all up.
"""

from .engine import Sync, load_auth, login_finish, login_start  # noqa: F401
