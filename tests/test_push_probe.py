"""tools/push_probe.py opens what a server's Web Push (RFC 8291, aes128gcm) sends."""

import importlib.util
import os
import unittest
from pathlib import Path

try:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    HAVE = True
except ImportError:
    HAVE = False

TOOL = Path(__file__).resolve().parent.parent / "tools" / "push_probe.py"


def load_tool():
    spec = importlib.util.spec_from_file_location("push_probe", TOOL)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def server_encrypts(ua_public, auth_secret, plain):
    """What a server does (RFC 8291 §3, RFC 8188 with one record)."""
    me = ec.generate_private_key(ec.SECP256R1())
    me_pub = me.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    peer = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    secret = me.exchange(ec.ECDH(), peer)
    salt = os.urandom(16)

    def hkdf(s, ikm, info, n):
        return HKDF(hashes.SHA256(), n, s, info).derive(ikm)
    ikm = hkdf(auth_secret, secret, b"WebPush: info\0" + ua_public + me_pub, 32)
    cek = hkdf(salt, ikm, b"Content-Encoding: aes128gcm\0", 16)
    nonce = hkdf(salt, ikm, b"Content-Encoding: nonce\0", 12)
    ct = AESGCM(cek).encrypt(nonce, plain + b"\x02", None)
    return salt + (4096).to_bytes(4, "big") + bytes([len(me_pub)]) + me_pub + ct


@unittest.skipUnless(HAVE, "needs the cryptography package")
class PushProbeTest(unittest.TestCase):
    def test_opens_a_standard_push(self):
        tool = load_tool()
        keys = tool.Keys()
        body = server_encrypts(keys.public, keys.auth, b'{"title":"hi"}')
        self.assertEqual(keys.decrypt(body), b'{"title":"hi"}')
        self.assertEqual(tool.unb64(tool.b64u(b"\xff\x00x")), b"\xff\x00x")


if __name__ == "__main__":
    unittest.main()
