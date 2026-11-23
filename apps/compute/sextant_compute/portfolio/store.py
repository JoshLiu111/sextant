"""SQL for saved portfolios. Every function takes the owner's ``user_id`` and filters by it."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

import psycopg

Holding = dict[str, Any]
"""``{"ticker", "quantity", "cost_price", "currency"}``."""


def _insert_holdings(conn: psycopg.Connection, portfolio_id: UUID, holdings: Sequence[Holding]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO portfolio_holdings (portfolio_id, position, ticker, quantity, cost_price, currency)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            [
                (portfolio_id, i, h["ticker"], h["quantity"], h["cost_price"], h["currency"])
                for i, h in enumerate(holdings)
            ],
        )


def create(conn: psycopg.Connection, user_id: UUID, name: str, holdings: Sequence[Holding]) -> UUID:
    row = conn.execute(
        "INSERT INTO portfolios (user_id, name) VALUES (%s, %s) RETURNING id", (user_id, name)
    ).fetchone()
    assert row is not None
    _insert_holdings(conn, row["id"], holdings)
    return row["id"]


def list_for(conn: psycopg.Connection, user_id: UUID) -> list[dict[str, Any]]:
    return conn.execute(
        "SELECT id, name, created_at, updated_at FROM portfolios WHERE user_id = %s ORDER BY created_at, id",
        (user_id,),
    ).fetchall()


def replace(
    conn: psycopg.Connection, user_id: UUID, portfolio_id: UUID, name: str, holdings: Sequence[Holding]
) -> bool:
    """Rename the portfolio and replace its holdings. False if the user has no such portfolio."""
    row = conn.execute(
        "UPDATE portfolios SET name = %s, updated_at = now() WHERE id = %s AND user_id = %s RETURNING id",
        (name, portfolio_id, user_id),
    ).fetchone()
    if row is None:
        return False
    conn.execute("DELETE FROM portfolio_holdings WHERE portfolio_id = %s", (portfolio_id,))
    _insert_holdings(conn, portfolio_id, holdings)
    return True


def delete(conn: psycopg.Connection, user_id: UUID, portfolio_id: UUID) -> bool:
    """Delete the portfolio (its holdings cascade). False if the user has no such portfolio."""
    cur = conn.execute("DELETE FROM portfolios WHERE id = %s AND user_id = %s", (portfolio_id, user_id))
    return cur.rowcount == 1


def get(conn: psycopg.Connection, user_id: UUID, portfolio_id: UUID) -> dict[str, Any] | None:
    portfolio = conn.execute(
        "SELECT id, name, created_at, updated_at FROM portfolios WHERE id = %s AND user_id = %s",
        (portfolio_id, user_id),
    ).fetchone()
    if portfolio is None:
        return None
    holdings = conn.execute(
        "SELECT ticker, quantity::float8 AS quantity, cost_price::float8 AS cost_price, currency"
        " FROM portfolio_holdings WHERE portfolio_id = %s ORDER BY position",
        (portfolio_id,),
    ).fetchall()
    return {**portfolio, "holdings": holdings}


def lock_holdings(conn: psycopg.Connection, user_id: UUID, portfolio_id: UUID) -> list[Holding] | None:
    """The portfolio's holdings, row-locked until the transaction ends. None if the user has no such portfolio."""
    row = conn.execute(
        "SELECT id FROM portfolios WHERE id = %s AND user_id = %s FOR UPDATE", (portfolio_id, user_id)
    ).fetchone()
    if row is None:
        return None
    return conn.execute(
        "SELECT ticker, quantity::float8 AS quantity, cost_price::float8 AS cost_price, currency"
        " FROM portfolio_holdings WHERE portfolio_id = %s ORDER BY position",
        (portfolio_id,),
    ).fetchall()


def record_import(
    conn: psycopg.Connection,
    portfolio_id: UUID,
    holdings: Sequence[Holding],
    transactions: Sequence[dict[str, Any]],
) -> UUID:
    """Store an import's transactions and the holdings they produced. Call after ``lock_holdings``."""
    import_id = uuid4()
    conn.execute("UPDATE portfolios SET updated_at = now() WHERE id = %s", (portfolio_id,))
    conn.execute("DELETE FROM portfolio_holdings WHERE portfolio_id = %s", (portfolio_id,))
    _insert_holdings(conn, portfolio_id, holdings)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO portfolio_transactions"
            " (portfolio_id, import_id, line, trade_date, ticker, side, quantity, price, fees, currency)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (portfolio_id, import_id, t["line"], t["date"], t["ticker"], t["side"],
                 t["quantity"], t["price"], t["fees"], t["currency"])
                for t in transactions
            ],
        )
    return import_id


def list_transactions(conn: psycopg.Connection, user_id: UUID, portfolio_id: UUID) -> list[dict[str, Any]] | None:
    """The portfolio's imported transactions, oldest trade first. None if the user has no such portfolio."""
    owned = conn.execute("SELECT 1 FROM portfolios WHERE id = %s AND user_id = %s", (portfolio_id, user_id))
    if owned.fetchone() is None:
        return None
    return conn.execute(
        "SELECT import_id, line, trade_date AS date, ticker, side, quantity::float8 AS quantity,"
        " price::float8 AS price, fees::float8 AS fees, currency"
        " FROM portfolio_transactions WHERE portfolio_id = %s ORDER BY trade_date, id",
        (portfolio_id,),
    ).fetchall()
