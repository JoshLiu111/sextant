"""SQL for users' provider keys. Every function takes the owner's ``user_id`` and filters by it."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import psycopg

from sextant_compute.keys.cipher import Sealed


def upsert(conn: psycopg.Connection, user_id: UUID, provider: str, sealed: Sealed, hint: str) -> dict[str, Any]:
    """Save the user's key for ``provider``, replacing any earlier one."""
    row = conn.execute(
        "INSERT INTO provider_keys (user_id, provider, nonce, ciphertext, hint) VALUES (%s, %s, %s, %s, %s)"
        " ON CONFLICT (user_id, provider) DO UPDATE"
        " SET nonce = EXCLUDED.nonce, ciphertext = EXCLUDED.ciphertext, hint = EXCLUDED.hint, updated_at = now()"
        " RETURNING provider, hint, created_at, updated_at",
        (user_id, provider, sealed.nonce, sealed.ciphertext, hint),
    ).fetchone()
    assert row is not None
    return row


def list_for(conn: psycopg.Connection, user_id: UUID) -> list[dict[str, Any]]:
    """The user's saved keys, without the key material."""
    return conn.execute(
        "SELECT provider, hint, created_at, updated_at FROM provider_keys WHERE user_id = %s ORDER BY provider",
        (user_id,),
    ).fetchall()


def sealed_for(conn: psycopg.Connection, user_id: UUID) -> dict[str, Sealed]:
    """provider -> the user's encrypted key."""
    rows = conn.execute(
        "SELECT provider, nonce, ciphertext FROM provider_keys WHERE user_id = %s", (user_id,)
    ).fetchall()
    return {r["provider"]: Sealed(bytes(r["nonce"]), bytes(r["ciphertext"])) for r in rows}


def delete(conn: psycopg.Connection, user_id: UUID, provider: str) -> bool:
    """False if the user had no key for ``provider``."""
    cur = conn.execute("DELETE FROM provider_keys WHERE user_id = %s AND provider = %s", (user_id, provider))
    return cur.rowcount == 1
