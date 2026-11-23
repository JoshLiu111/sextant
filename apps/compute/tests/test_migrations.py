import psycopg
from psycopg import sql

from sextant_compute.db import MIGRATIONS_DIR, migrate


def test_migrations_apply_to_an_empty_database_once_and_then_are_up_to_date(pg_server_url):
    name = "sextant_test_migrate_once"
    with psycopg.connect(pg_server_url, autocommit=True) as conn:
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(name)))
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = psycopg.conninfo.make_conninfo(pg_server_url, dbname=name)
    try:
        first = migrate(url)
        second = migrate(url)

        assert first == sorted(p.name for p in MIGRATIONS_DIR.glob("*.sql"))
        assert first[0] == "0001_users_and_sessions.sql"
        assert second == []
    finally:
        with psycopg.connect(pg_server_url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
