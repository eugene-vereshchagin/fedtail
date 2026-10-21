"""Does your server push? Web Push from it to an ntfy topic, opened here.

Before fedtail on a phone relies on pushes (UnifiedPush through ntfy), this checks the
whole way with the server you have:

    python3 tools/push_probe.py                     # the main profile, ntfy.sh
    python3 tools/push_probe.py --profile work --ntfy https://ntfy.my.server

1. It asks your server what it is and whether it has a Web Push key (VAPID).
2. It makes a key pair here and subscribes your account to pushes
   (POST /api/v1/push/subscription) with an endpoint on a random ntfy topic — the way a
   UnifiedPush app would. The topic's name is printed: subscribe to it in the ntfy app on
   the phone to see the (encrypted) pushes arrive there too.
3. It waits for pushes on that topic (`--wait` seconds, 5 minutes by default). Get
   someone to mention you, favourite or boost a post of yours, follow you. Every push
   that comes is decrypted here (RFC 8291, aes128gcm) and shown: what it says, how long
   it took.
4. It removes the subscription (`--keep` leaves it).

Your token goes only to your own server, as fedtail's always does. ntfy sees the
encrypted pushes and nothing else; the private key never leaves this run. One push
subscription per token is the rule of the Mastodon API: this replaces whatever the same
token had (fedtail on the desktop has none). Needs `requests` and `cryptography`.
"""

import argparse
import base64
import json
import os
import secrets
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fedtail.core import auth, paths  # noqa: E402
from fedtail.version import USER_AGENT  # noqa: E402


def b64u(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def unb64(text):
    text = text.strip()
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Keys:
    """The receiving side of RFC 8291: an ECDH P-256 pair and a 16-byte auth secret."""

    def __init__(self):
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.public = self.private.public_key().public_bytes(
            Encoding.X962, PublicFormat.UncompressedPoint)
        self.auth = secrets.token_bytes(16)

    def decrypt(self, body):
        """An aes128gcm push body → its plain bytes (one record, as Web Push sends)."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
        salt, idlen = body[:16], body[20]
        server_pub = body[21:21 + idlen]
        ct = body[21 + idlen:]
        peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), server_pub)
        secret = self.private.exchange(ec.ECDH(), peer)

        def hkdf(salt_, ikm, info, n):
            return HKDF(hashes.SHA256(), n, salt_, info).derive(ikm)
        ikm = hkdf(self.auth, secret, b"WebPush: info\0" + self.public + server_pub, 32)
        cek = hkdf(salt, ikm, b"Content-Encoding: aes128gcm\0", 16)
        nonce = hkdf(salt, ikm, b"Content-Encoding: nonce\0", 12)
        plain = AESGCM(cek).decrypt(nonce, ct, None)
        return plain.rstrip(b"\0")[:-1]  # the padding: zeros after a delimiter byte (2)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--profile", help="the fedtail profile (default: the main one)")
    p.add_argument("--ntfy", default="https://ntfy.sh", help="the ntfy server")
    p.add_argument("--wait", type=int, default=300, help="seconds to wait for pushes")
    p.add_argument("--keep", action="store_true", help="leave the subscription in place")
    a = p.parse_args(argv)
    try:
        keys = Keys()
    except ImportError:
        raise SystemExit("needs the cryptography package "
                         "(Debian: python3-cryptography)") from None
    where = paths.resolve(a.profile)
    creds = auth.load(where.auth_file)
    if not creds:
        raise SystemExit(f"profile {where.profile}: not logged in (open fedtail first)")
    server = creds["server"].rstrip("/")
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT, "Authorization": f"Bearer {creds['token']}"})

    info = s.get(f"{server}/api/v1/instance", timeout=20).json()
    print(f"server: {server} — {info.get('version', '?')}")
    v2 = s.get(f"{server}/api/v2/instance", timeout=20)
    vapid = ((v2.json().get("configuration") or {}).get("vapid") or {}).get("public_key") \
        if v2.ok else None
    print(f"VAPID key in /api/v2/instance: {'yes' if vapid else 'no (may still push)'}")

    topic = "fedtailprobe" + secrets.token_hex(8)
    endpoint = f"{a.ntfy.rstrip('/')}/{topic}?up=1"
    form = {"subscription[endpoint]": endpoint,
            "subscription[keys][p256dh]": b64u(keys.public),
            "subscription[keys][auth]": b64u(keys.auth),
            "subscription[standard]": "true",  # Mastodon 4.4+: RFC 8291, not the old draft
            "data[policy]": "all"}
    for kind in ("mention", "status", "reblog", "follow", "follow_request", "favourite",
                 "poll", "update"):
        form[f"data[alerts][{kind}]"] = "true"
    r = s.post(f"{server}/api/v1/push/subscription", data=form, timeout=20)
    if not r.ok:
        raise SystemExit(f"subscribing refused: HTTP {r.status_code} {r.text[:300]}")
    sub = r.json()
    print(f"subscribed: id {sub.get('id')}, alerts "
          f"{sorted(k for k, v in (sub.get('alerts') or {}).items() if v)}")
    print(f"ntfy topic: {topic}  (subscribe to it in the ntfy app on the phone too)")
    print(f"waiting {a.wait} s — get someone to mention you, like or boost a post of yours…")

    t0, since, got = time.time(), "all", 0
    try:
        while time.time() - t0 < a.wait:
            try:
                resp = requests.get(f"{a.ntfy.rstrip('/')}/{topic}/json",
                                    params={"poll": "1", "since": since}, timeout=30,
                                    headers={"User-Agent": USER_AGENT})
            except requests.RequestException as e:
                print(f"  ntfy: {e.__class__.__name__}, again…")
                time.sleep(5)
                continue
            for line in resp.text.splitlines():
                ev = json.loads(line)
                if ev.get("event") != "message":
                    continue
                since = ev["id"]
                raw = ev.get("message", "")
                body = unb64(raw) if ev.get("encoding") == "base64" else raw.encode()
                took = time.time() - t0
                try:
                    shown = json.loads(keys.decrypt(body))
                except Exception as e:  # noqa: BLE001 — say what came, whatever it is
                    print(f"  [{took:5.0f} s] a push came, {len(body)} B, not opened: "
                          f"{e.__class__.__name__} (not aes128gcm? the server's own draft?)")
                    continue
                got += 1
                print(f"  [{took:5.0f} s] {shown.get('notification_type')}: "
                      f"{shown.get('title')} — {shown.get('body', '')[:100]}")
            time.sleep(3)
    except KeyboardInterrupt:
        print()
    finally:
        if not a.keep:
            d = s.delete(f"{server}/api/v1/push/subscription", timeout=20)
            print(f"subscription removed: HTTP {d.status_code}")
    print("works: the server pushes, ntfy carries, the device decrypts" if got
          else "no push opened in that time")
    return 0 if got else 1


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.exit(main())
