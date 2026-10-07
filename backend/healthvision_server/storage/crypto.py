"""Envelope encryption for biometric templates (docs/10 §4).

Each template gets its own random 256-bit data key (DEK). The template is encrypted with
AES-256-GCM under the DEK; the DEK is wrapped (AES-256-GCM) under the key-encryption key
(KEK). The KEK lives in the OS keystore (``keystore: os``) or, by explicit opt-in, in the
HEALTHVISION_KEK environment variable (``keystore: env``). It is never written to the DB or
to a plaintext file. Crypto-shredding = destroying the wrapped DEK, after which the
ciphertext can no longer be decrypted.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEYRING_SERVICE = "healthvision-ai"
KEYRING_USER = "template-kek-v1"
KEK_ID = "kek-v1"


class KeystoreUnavailable(Exception):
    pass


def load_kek(mode: str) -> bytes:
    if mode == "env":
        val = os.environ.get("HEALTHVISION_KEK")
        if not val:
            raise KeystoreUnavailable("HEALTHVISION_KEK not set")
        key = base64.b64decode(val)
        if len(key) != 32:
            raise KeystoreUnavailable("HEALTHVISION_KEK must be 32 bytes (base64)")
        return key
    try:
        import keyring

        stored = keyring.get_password(KEYRING_SERVICE, KEYRING_USER)
        if stored is None:
            stored = base64.b64encode(os.urandom(32)).decode()
            keyring.set_password(KEYRING_SERVICE, KEYRING_USER, stored)
            if keyring.get_password(KEYRING_SERVICE, KEYRING_USER) != stored:
                raise KeystoreUnavailable("keystore did not persist the key")
        return base64.b64decode(stored)
    except KeystoreUnavailable:
        raise
    except Exception as exc:  # no backend, locked keychain, …
        raise KeystoreUnavailable(f"OS keystore unavailable: {type(exc).__name__}") from exc


@dataclass
class Sealed:
    ciphertext: bytes
    nonce: bytes
    wrapped_dek: bytes
    kek_id: str


class EnvelopeCipher:
    def __init__(self, kek: bytes):
        self._kek = AESGCM(kek)

    def seal(self, plaintext: bytes, aad: bytes) -> Sealed:
        dek = AESGCM.generate_key(bit_length=256)
        nonce = os.urandom(12)
        ct = AESGCM(dek).encrypt(nonce, plaintext, aad)
        wn = os.urandom(12)
        wrapped = wn + self._kek.encrypt(wn, dek, aad)
        return Sealed(ct, nonce, wrapped, KEK_ID)

    def open(self, s: Sealed, aad: bytes) -> bytes:
        wn, wct = s.wrapped_dek[:12], s.wrapped_dek[12:]
        dek = self._kek.decrypt(wn, wct, aad)
        return AESGCM(dek).decrypt(s.nonce, s.ciphertext, aad)
