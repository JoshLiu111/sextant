"""Postgres access for the compute service.

The compute service is the only owner of the database (see
docs/adr/0001-accounts-sessions-and-user-owned-data.md). Migrations are plain
SQL files in ``migrations/``, applied in filename order by ``migrate``.

``DATABASE_URL`` is the (pooled) connection string Neon injects through the
Vercel Marketplace. ``DATABASE_URL_UNPOOLED`` is preferred for migrations,
because the advisory lock needs a real session.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

MIGRATIONS_DIR = Path(__file__).parent / "migrations"

# Arbitrary constant; serialises concurrent cold starts running migrations.
_MIGRATION_LOCK_ID = 7_351_224_105


class DatabaseNotConfigured(RuntimeError):
    """DATABASE_URL is not set. Anonymous tools keep working without it."""


def migrate(conninfo: str) -> list[str]:
    """Apply pending migrations; returns the names applied. Idempotent."""
    applied: list[str] = []
    with psycopg.connect(conninfo, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(%s)", (_MIGRATION_LOCK_ID,))
        try:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                " name text PRIMARY KEY,"
                " applied_at timestamptz NOT NULL DEFAULT now())"
            )
            done = {name for (name,) in conn.execute("SELECT name FROM schema_migrations")}
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if path.name in done:
                    continue
                with conn.transaction():
                    conn.execute(path.read_text())
                    conn.execute("INSERT INTO schema_migrations (name) VALUES (%s)", (path.name,))
                applied.append(path.name)
        finally:
            conn.execute("SELECT pg_advisory_unlock(%s)", (_MIGRATION_LOCK_ID,))
    return applied


class Database:
    """A lazily opened connection pool. One per app instance."""

    def __init__(self, url: str | None, migrate_url: str | None = None, auto_migrate: bool = True):
        self.url = url
        self.migrate_url = migrate_url or url
        self.auto_migrate = auto_migrate
        self._pool: ConnectionPool | None = None

    @classmethod
    def from_env(cls) -> Database:
        return cls(
            url=os.environ.get("DATABASE_URL") or None,
            migrate_url=os.environ.get("DATABASE_URL_UNPOOLED") or None,
            auto_migrate=os.environ.get("DB_AUTO_MIGRATE", "1") != "0",
        )

    @property
    def configured(self) -> bool:
        return bool(self.url)

    def _get_pool(self) -> ConnectionPool:
        if not self.url:
            raise DatabaseNotConfigured("DATABASE_URL is not set")
        if self._pool is None:
            if self.auto_migrate and self.migrate_url:
                migrate(self.migrate_url)
            # prepare_threshold=None: Neon's pooled endpoint is PgBouncer in
            # transaction mode, which does not support prepared statements.
            self._pool = ConnectionPool(
                self.url,
                min_size=0,
                max_size=4,
                kwargs={"row_factory": dict_row, "prepare_threshold": None},
                open=True,
            )
        return self._pool

    @contextmanager
    def connection(self) -> Iterator[psycopg.Connection]:
        """A pooled connection inside a transaction (committed on success)."""
        with self._get_pool().connection() as conn:
            yield conn

    def close(self) -> None:
        if self._pool is not None:
            self._pool.close()
            self._pool = None

