"""Shared fixtures: an ephemeral Postgres database and an app wired to it.

Postgres comes from one of (in order):
1. ``TEST_DATABASE_URL``: a server you already run (CI uses a postgres service
   container). Each test session creates and drops its own database on it.
2. Postgres binaries on PATH or in Homebrew (``initdb``/``pg_ctl``, e.g.
   ``postgresql@16``): a throwaway cluster in a temp dir on a free port.
Otherwise DB tests are skipped locally and fail in CI. Never touches Neon.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from scripts.ephemeral_postgres import ephemeral_cluster, find_pg_bin
from sextant_compute.app import create_app
from sextant_compute.db import migrate
from tests.auth_helpers import TEST_SESSION_SECRET


@pytest.fixture(scope="session")
def pg_server_url() -> Iterator[str]:
    """URL of a Postgres server's maintenance database (``postgres``)."""
    if url := os.environ.get("TEST_DATABASE_URL"):
        yield url
        return
    if not (find_pg_bin("initdb") and find_pg_bin("pg_ctl")):
        message = "No TEST_DATABASE_URL and no Postgres binaries on PATH"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)
    with ephemeral_cluster() as url:
        yield url


@pytest.fixture(scope="session")
def migrated_db_url(pg_server_url: str) -> Iterator[str]:
    """A fresh database with every migration applied, dropped afterwards."""
    name = f"sextant_test_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(pg_server_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = psycopg.conninfo.make_conninfo(pg_server_url, dbname=name)
    migrate(url)
    try:
        yield url
    finally:
        with psycopg.connect(pg_server_url, autocommit=True) as conn:
            conn.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name))
            )


@pytest.fixture
def db_url(migrated_db_url: str) -> Iterator[str]:
    """The migrated test database, emptied before each test."""
    with psycopg.connect(migrated_db_url, autocommit=True) as conn:
        tables = conn.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename <> 'schema_migrations'"
        ).fetchall()
        if tables:
            conn.execute(
                sql.SQL("TRUNCATE {} CASCADE").format(
                    sql.SQL(", ").join(sql.Identifier(t) for (t,) in tables)
                )
            )
    yield migrated_db_url


@pytest.fixture
def client(db_url: str, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("SESSION_SECRET", TEST_SESSION_SECRET)
    with TestClient(create_app()) as c:
        yield c
