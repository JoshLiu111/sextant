"""Encryption at rest for users' provider keys: AES-256-GCM.

The 256-bit key is derived (HKDF-SHA256) from the ``PROVIDER_KEY_SECRET``
environment variable, a random string of at least 32 characters. Each stored
key gets a fresh 96-bit nonce, and the ciphertext is bound to its owner and
provider (associated data), so a row copied to another user or provider fails
to decrypt instead of leaking.

Rotating the secret makes existing keys undecryptable; they then read as
absent and users re-enter them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SECRET_ENV = "PROVIDER_KEY_SECRET"
MIN_SECRET_LENGTH = 32
_INFO = b"sextant provider keys v1"


class KeysNotConfigured(RuntimeError):
    """``PROVIDER_KEY_SECRET`` is missing or too short."""


class UndecryptableKey(ValueError):
    """The stored key was encrypted with another secret, or tampered with."""


@dataclass(frozen=True)
class Sealed:
    nonce: bytes
    ciphertext: bytes


class KeyCipher:
    def __init__(self, secret: str) -> None:
        if len(secret) < MIN_SECRET_LENGTH:
            raise KeysNotConfigured(f"{SECRET_ENV} must be at least {MIN_SECRET_LENGTH} characters.")
        derived = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(secret.encode())
        self._aead = AESGCM(derived)

    @classmethod
    def from_env(cls) -> KeyCipher:
        secret = os.environ.get(SECRET_ENV)
        if not secret:
            raise KeysNotConfigured(f"{SECRET_ENV} is not set.")
        return cls(secret)

    def seal(self, user_id: UUID, provider: str, key: str) -> Sealed:
        nonce = os.urandom(12)
        return Sealed(nonce, self._aead.encrypt(nonce, key.encode(), _associated(user_id, provider)))

    def open(self, user_id: UUID, provider: str, sealed: Sealed) -> str:
        try:
            return self._aead.decrypt(sealed.nonce, sealed.ciphertext, _associated(user_id, provider)).decode()
        except InvalidTag:
            raise UndecryptableKey(provider) from None


def _associated(user_id: UUID, provider: str) -> bytes:
    return f"{user_id}:{provider}".encode()
