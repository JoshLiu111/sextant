"""SQL for saved portfolios. Every function takes the owner's ``user_id`` and filters by it."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.types.json import Jsonb

Holding = dict[str, Any]
"""``{"ticker", "quantity", "cost_price", "currency"}``, plus ``"lots"`` (open FIFO lots,
``[{"quantity", "cost_price"}]`` oldest first) when read with ``lock_holdings`` or written
by an import. Missing or None: one lot of the whole holding (docs/adr/0004)."""

_HOLDING_COLUMNS = "ticker, quantity::float8 AS quantity, cost_price::float8 AS cost_price, currency"


def _lots(h: Holding) -> Jsonb | None:
    lots = h.get("lots")
    return Jsonb(lots) if lots and len(lots) > 1 else None


def _insert_holdings(conn: psycopg.Connection, portfolio_id: UUID, holdings: Sequence[Holding]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO portfolio_holdings (portfolio_id, position, ticker, quantity, cost_price, currency, lots)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s)",
            [
                (portfolio_id, i, h["ticker"], h["quantity"], h["cost_price"], h["currency"], _lots(h))
                for i, h in enumerate(holdings)
            ],
        )


def _same(a: Holding, b: Holding) -> bool:
    def close(x: float, y: float) -> bool:
        return abs(x - y) <= 1e-9 * max(1.0, abs(x), abs(y))

    return (
        a["currency"] == b["currency"]
        and close(a["quantity"], b["quantity"])
        and close(a["cost_price"], b["cost_price"])
    )


def _holdings_with_lots(conn: psycopg.Connection, portfolio_id: UUID) -> list[Holding]:
    return conn.execute(
        f"SELECT {_HOLDING_COLUMNS}, lots FROM portfolio_holdings WHERE portfolio_id = %s ORDER BY position",
        (portfolio_id,),
    ).fetchall()


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
    """Rename the portfolio and replace its holdings. False if the user has no such portfolio.

    A holding sent back unchanged (same ticker, quantity, cost price and currency)
    keeps its FIFO lots; any other holding becomes one lot at its cost price.
    """
    row = conn.execute(
        "UPDATE portfolios SET name = %s, updated_at = now() WHERE id = %s AND user_id = %s RETURNING id",
        (name, portfolio_id, user_id),
    ).fetchone()
    if row is None:
        return False
    before = {h["ticker"]: h for h in _holdings_with_lots(conn, portfolio_id)}
    kept = [
        {**h, "lots": before[h["ticker"]]["lots"] if h["ticker"] in before and _same(h, before[h["ticker"]]) else None}
        for h in holdings
    ]
    conn.execute("DELETE FROM portfolio_holdings WHERE portfolio_id = %s", (portfolio_id,))
    _insert_holdings(conn, portfolio_id, kept)
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
        f"SELECT {_HOLDING_COLUMNS} FROM portfolio_holdings WHERE portfolio_id = %s ORDER BY position",
        (portfolio_id,),
    ).fetchall()
    return {**portfolio, "holdings": holdings}


def lock_holdings(conn: psycopg.Connection, user_id: UUID, portfolio_id: UUID) -> list[Holding] | None:
    """The portfolio's holdings with their lots, row-locked until the transaction ends.
    None if the user has no such portfolio."""
    row = conn.execute(
        "SELECT id FROM portfolios WHERE id = %s AND user_id = %s FOR UPDATE", (portfolio_id, user_id)
    ).fetchone()
    if row is None:
        return None
    return _holdings_with_lots(conn, portfolio_id)


def record_import(
    conn: psycopg.Connection,
    portfolio_id: UUID,
    holdings: Sequence[Holding],
    transactions: Sequence[dict[str, Any]],
) -> UUID:
    """Store an import's transactions (each with ``realized_pnl``) and the holdings they produced
    (each with ``lots``). Call after ``lock_holdings``."""
    import_id = uuid4()
    conn.execute("UPDATE portfolios SET updated_at = now() WHERE id = %s", (portfolio_id,))
    conn.execute("DELETE FROM portfolio_holdings WHERE portfolio_id = %s", (portfolio_id,))
    _insert_holdings(conn, portfolio_id, holdings)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO portfolio_transactions"
            " (portfolio_id, import_id, line, trade_date, ticker, side, quantity, price, fees, currency, realized_pnl)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (portfolio_id, import_id, t["line"], t["date"], t["ticker"], t["side"],
                 t["quantity"], t["price"], t["fees"], t["currency"], t["realized_pnl"])
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
        " price::float8 AS price, fees::float8 AS fees, currency, realized_pnl::float8 AS realized_pnl"
        " FROM portfolio_transactions WHERE portfolio_id = %s ORDER BY trade_date, id",
        (portfolio_id,),
    ).fetchall()


def realized_by_ticker(conn: psycopg.Connection, portfolio_id: UUID) -> list[dict[str, Any]]:
    """Realized P&L booked per ticker and currency, first-traded ticker first.

    ``{"ticker", "currency", "realized_pnl", "unbooked"}``; ``unbooked`` counts sells
    stored before realized P&L was booked (their P&L is unknown).
    """
    return conn.execute(
        "SELECT ticker, currency, COALESCE(sum(realized_pnl), 0)::float8 AS realized_pnl,"
        " count(*) FILTER (WHERE side = 'sell' AND realized_pnl IS NULL) AS unbooked"
        " FROM portfolio_transactions WHERE portfolio_id = %s"
        " GROUP BY ticker, currency ORDER BY min(trade_date), min(id)",
        (portfolio_id,),
    ).fetchall()
