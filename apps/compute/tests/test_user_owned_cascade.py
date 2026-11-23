"""Account deletion removes every user-owned row, now and for future tables.

A table is *user-owned* if it references ``users`` directly, or references
another user-owned table (e.g. holdings -> portfolios -> users).

When you add a user-owned table, add an entry to ``USER_OWNED_ROWS`` that
inserts one row for the given user. ``test_every_user_owned_table_has_a_row_factory``
fails until you do, so the cascade test below always covers every table.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from psycopg import sql

from tests.auth_helpers import bearer, sign_in

RowFactory = Callable[[psycopg.Connection, object], None]


def _session_row(conn: psycopg.Connection, user_id) -> None:
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at)"
        " VALUES (%s, %s, %s)",
        (os.urandom(32), user_id, datetime.now(UTC) + timedelta(days=1)),
    )


def _portfolio_row(conn: psycopg.Connection, user_id) -> None:
    conn.execute("INSERT INTO portfolios (user_id, name) VALUES (%s, 'Cascade test')", (user_id,))


def _portfolio_holding_row(conn: psycopg.Connection, user_id) -> None:
    conn.execute(
        "INSERT INTO portfolio_holdings (portfolio_id, position, ticker, quantity, cost_price, currency)"
        " SELECT id, 0, 'DEMO-A', 10, 100, 'USD' FROM portfolios WHERE user_id = %s LIMIT 1",
        (user_id,),
    )


def _portfolio_transaction_row(conn: psycopg.Connection, user_id) -> None:
    conn.execute(
        "INSERT INTO portfolio_transactions"
        " (portfolio_id, import_id, line, trade_date, ticker, side, quantity, price, fees, currency)"
        " SELECT id, gen_random_uuid(), 2, '2024-01-05', 'DEMO-A', 'buy', 10, 100, 1, 'USD'"
        " FROM portfolios WHERE user_id = %s LIMIT 1",
        (user_id,),
    )


def _ai_usage_row(conn: psycopg.Connection, user_id) -> None:
    conn.execute(
        "INSERT INTO ai_usage (user_id, tool, input_tokens, output_tokens) VALUES (%s, 'options', 1000, 200)",
        (user_id,),
    )


def _provider_key_row(conn: psycopg.Connection, user_id) -> None:
    conn.execute(
        "INSERT INTO provider_keys (user_id, provider, nonce, ciphertext, hint)"
        " VALUES (%s, 'tiingo', %s, %s, 'abcd')",
        (user_id, os.urandom(12), os.urandom(56)),
    )


def _valuation_assumptions_row(conn: psycopg.Connection, user_id) -> None:
    conn.execute(
        "INSERT INTO valuation_assumptions (user_id, ticker, name, assumptions)"
        " VALUES (%s, 'MSFT', 'Cascade test', '{}'::jsonb)",
        (user_id,),
    )


def _user_data_cache_row(conn: psycopg.Connection, user_id) -> None:
    conn.execute(
        "INSERT INTO user_data_cache (cache_key, user_id, source, value, expires_at)"
        " VALUES (%s, %s, 'tiingo', '{}'::jsonb, now() + interval '1 hour')",
        (f"v1:user:{user_id}:tiingo@1:daily_prices:cascade", user_id),
    )


def _user_factor_file_row(conn: psycopg.Connection, user_id) -> None:
    conn.execute(
        "INSERT INTO user_factor_files (user_id, kind, filename, frequency, factors)"
        " VALUES (%s, 'three_factor', 'F-F_Research_Data_Factors.CSV', 'monthly',"
        " '{\"dates\": [], \"order\": [], \"columns\": {}}'::jsonb)",
        (user_id,),
    )


# table name -> inserts one row owned by user_id. Order matters: parents first.
USER_OWNED_ROWS: dict[str, RowFactory] = {
    "sessions": _session_row,
    "portfolios": _portfolio_row,
    "portfolio_holdings": _portfolio_holding_row,
    "portfolio_transactions": _portfolio_transaction_row,
    "ai_usage": _ai_usage_row,
    "provider_keys": _provider_key_row,
    "user_data_cache": _user_data_cache_row,
    "valuation_assumptions": _valuation_assumptions_row,
    "user_factor_files": _user_factor_file_row,
}


def _foreign_keys(conn: psycopg.Connection) -> list[dict]:
    """Every foreign key in the public schema: child table, parent table, delete rule."""
    return conn.execute(
        """
        SELECT c.conrelid::regclass::text  AS child,
               c.confrelid::regclass::text AS parent,
               c.confdeltype               AS on_delete,
               c.conname                   AS name
          FROM pg_constraint c
          JOIN pg_namespace n ON n.oid = c.connamespace
         WHERE c.contype = 'f' AND n.nspname = 'public'
        """
    ).fetchall()


def _user_owned_tables(conn: psycopg.Connection) -> set[str]:
    fks = _foreign_keys(conn)
    owned: set[str] = set()
    frontier = {"users"}
    while frontier:
        found = {fk["child"] for fk in fks if fk["parent"] in frontier} - owned - {"users"}
        owned |= found
        frontier = found
    return owned


@pytest.fixture
def conn(db_url):
    with psycopg.connect(db_url, autocommit=True, row_factory=psycopg.rows.dict_row) as c:
        yield c


def test_every_foreign_key_into_user_owned_data_cascades_on_delete(conn):
    owned_parents = _user_owned_tables(conn) | {"users"}
    offenders = [
        f"{fk['name']} ({fk['child']} -> {fk['parent']})"
        for fk in _foreign_keys(conn)
        if fk["parent"] in owned_parents and fk["on_delete"] != "c"
    ]

    assert offenders == [], "Use ON DELETE CASCADE for references to user-owned data"


def test_every_user_id_column_references_users(conn):
    columns = conn.execute(
        """
        SELECT table_name FROM information_schema.columns
         WHERE table_schema = 'public' AND column_name = 'user_id'
        """
    ).fetchall()
    tables_with_user_id = {c["table_name"] for c in columns}
    referencing_users = {fk["child"] for fk in _foreign_keys(conn) if fk["parent"] == "users"}

    assert tables_with_user_id <= referencing_users


def test_every_user_owned_table_has_a_row_factory(conn):
    assert _user_owned_tables(conn) == set(USER_OWNED_ROWS)


def _count_rows(conn: psycopg.Connection, table: str) -> int:
    return conn.execute(
        sql.SQL("SELECT count(*) AS n FROM {}").format(sql.Identifier(table))
    ).fetchone()["n"]


def test_deleting_an_account_removes_all_its_user_owned_rows_and_nobody_elses(client, conn):
    bob_token = sign_in(client, "sub-bob", email="bob@example.test")
    bob_id = client.get("/api/compute/me", headers=bearer(bob_token)).json()["id"]
    for make_row in USER_OWNED_ROWS.values():
        make_row(conn, bob_id)
    counts_without_alice = {table: _count_rows(conn, table) for table in USER_OWNED_ROWS}
    alice_token = sign_in(client, "sub-alice", email="alice@example.test")
    alice_id = client.get("/api/compute/me", headers=bearer(alice_token)).json()["id"]
    for make_row in USER_OWNED_ROWS.values():
        make_row(conn, alice_id)

    assert client.delete("/api/compute/me", headers=bearer(alice_token)).status_code == 204

    assert {table: _count_rows(conn, table) for table in USER_OWNED_ROWS} == counts_without_alice
    assert client.get("/api/compute/me", headers=bearer(bob_token)).status_code == 200


def test_cascade_also_covers_tables_added_later_that_follow_the_convention(client, conn):
    """Simulates a future ticket's table (e.g. portfolios) to prove the convention works."""
    conn.execute(
        "CREATE TABLE test_future_owned ("
        " id serial PRIMARY KEY,"
        " user_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE)"
    )
    conn.execute(
        "CREATE TABLE test_future_child ("
        " id serial PRIMARY KEY,"
        " parent_id int NOT NULL REFERENCES test_future_owned (id) ON DELETE CASCADE)"
    )
    try:
        token = sign_in(client)
        user_id = client.get("/api/compute/me", headers=bearer(token)).json()["id"]
        parent = conn.execute(
            "INSERT INTO test_future_owned (user_id) VALUES (%s) RETURNING id", (user_id,)
        ).fetchone()["id"]
        conn.execute("INSERT INTO test_future_child (parent_id) VALUES (%s)", (parent,))

        client.delete("/api/compute/me", headers=bearer(token))

        assert _count_rows(conn, "test_future_owned") == 0
        assert _count_rows(conn, "test_future_child") == 0
    finally:
        conn.execute("DROP TABLE test_future_child, test_future_owned")
