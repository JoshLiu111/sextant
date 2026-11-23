"""Reading a user's provider keys back for ``ctx.keys``."""

from __future__ import annotations

import logging
from uuid import UUID

from sextant_compute.db import Database
from sextant_compute.keys import store
from sextant_compute.keys.cipher import KeyCipher, KeysNotConfigured, UndecryptableKey

log = logging.getLogger(__name__)


def user_keys(db: Database, user_id: UUID) -> dict[str, str]:
    """provider -> the user's decrypted key.

    A key that can't be decrypted (the secret was rotated, or is unset) reads
    as absent: the user falls back to demo data and can save the key again.
    """
    with db.connection() as conn:
        sealed = store.sealed_for(conn, user_id)
    if not sealed:
        return {}
    try:
        cipher = KeyCipher.from_env()
    except KeysNotConfigured:
        log.warning("PROVIDER_KEY_SECRET is not set; ignoring stored provider keys")
        return {}
    keys: dict[str, str] = {}
    for provider, value in sealed.items():
        try:
            keys[provider] = cipher.open(user_id, provider, value)
        except UndecryptableKey:
            log.warning("A stored %s key could not be decrypted; ignoring it", provider)
    return keys
