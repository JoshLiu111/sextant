"""The per-user cache backend: Postgres table ``user_data_cache`` (migration 0007).

``DataService`` puts responses fetched with a user's own key here (adapters
with ``scope = "user"``), never in the shared cache. Every entry is owned by a
user (``user_id`` cascades on account deletion), so ``set`` needs the
``user:<uuid>`` tag that ``DataService`` always attaches to user-scope entries,
and the ``source:<id>`` tag (to drop a provider's rows when its key is deleted).

Like ``RuntimeCache``, a database failure counts as a miss: the request is
served from the provider instead of failing.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import psycopg
from psycopg.types.json import Jsonb

from sextant_compute.db import Database, DatabaseNotConfigured

log = logging.getLogger(__name__)

_DB_ERRORS = (psycopg.Error, DatabaseNotConfigured)


def _tag(tags: Sequence[str], prefix: str) -> str | None:
    return next((t.removeprefix(prefix) for t in tags if t.startswith(prefix)), None)


class PostgresUserCache:
    def __init__(self, db: Database) -> None:
        self._db = db

    def get(self, key: str) -> Any | None:
        try:
            with self._db.connection() as conn:
                row = conn.execute(
                    "SELECT value FROM user_data_cache WHERE cache_key = %s AND expires_at > now()", (key,)
                ).fetchone()
        except _DB_ERRORS:
            log.warning("user_data_cache read failed; treating it as a miss", exc_info=True)
            return None
        return row["value"] if row else None

    def set(self, key: str, value: Any, *, ttl: int, tags: Sequence[str] = ()) -> None:
        user_id, source = _tag(tags, "user:"), _tag(tags, "source:")
        if user_id is None or source is None:
            raise ValueError("user_data_cache entries need a user:<id> and a source:<id> tag")
        expires = datetime.now(UTC) + timedelta(seconds=ttl)
        try:
            with self._db.connection() as conn:
                conn.execute(
                    "DELETE FROM user_data_cache WHERE user_id = %s AND expires_at <= now()", (UUID(user_id),)
                )
                conn.execute(
                    "INSERT INTO user_data_cache (cache_key, user_id, source, value, expires_at)"
                    " VALUES (%s, %s, %s, %s, %s)"
                    " ON CONFLICT (cache_key) DO UPDATE"
                    " SET value = EXCLUDED.value, expires_at = EXCLUDED.expires_at, created_at = now()",
                    (key, UUID(user_id), source, Jsonb(value), expires),
                )
        except _DB_ERRORS:
            log.warning("user_data_cache write failed; the response is served uncached", exc_info=True)

    def expire_tag(self, tag: str) -> None:
        with self._db.connection() as conn:
            if user_id := _tag([tag], "user:"):
                conn.execute("DELETE FROM user_data_cache WHERE user_id = %s", (UUID(user_id),))
            elif source := _tag([tag], "source:"):
                conn.execute("DELETE FROM user_data_cache WHERE source = %s", (source,))


def delete_for(conn: psycopg.Connection, user_id: UUID, source: str) -> None:
    """Drop everything cached for ``user_id`` from ``source`` (their key for it is gone)."""
    conn.execute("DELETE FROM user_data_cache WHERE user_id = %s AND source = %s", (user_id, source))
