"""Importing transactions from CSV into a saved portfolio (P4, story 49).

Two steps, both scoped to the signed-in user's portfolio (someone else's id is 404):

- ``POST /{id}/transactions/preview`` reads the file and answers with its columns,
  the first rows, a column mapping (guessed from common broker exports unless
  one is sent), the rows that will import and the rows that cannot (with their
  line numbers), and the holdings the import would produce. Nothing is stored.
- ``POST /{id}/transactions`` does the same with a complete mapping and stores
  the result: every importable row and the new holdings, in one database
  transaction (all or nothing). Rows with errors are skipped and listed.

``GET /{id}/transactions`` lists what earlier imports stored.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field as PydanticField

from sextant_compute.auth import CurrentUser
from sextant_compute.auth.deps import get_db
from sextant_compute.db import Database
from sextant_compute.errors import ApiError
from sextant_compute.portfolio import store
from sextant_compute.portfolio.api import MAX_HOLDINGS
from sextant_compute.portfolio.ledger import Applied, Position, apply_transactions
from sextant_compute.portfolio.saved import PortfolioOut, SavedHolding, load
from sextant_compute.portfolio.transactions_csv import (
    FIELDS,
    SAMPLE_ROWS,
    CsvUnreadable,
    Field,
    RowError,
    Side,
    Table,
    Transaction,
    guess_mapping,
    missing_fields,
    parse_rows,
    read_table,
)

router = APIRouter(tags=["portfolio transactions"])

Db = Annotated[Database, Depends(get_db)]
MAX_CSV_CHARS = 2_000_000

FIELD_LABELS: dict[Field, str] = {
    "date": "Date",
    "ticker": "Ticker",
    "side": "Buy/sell",
    "quantity": "Quantity",
    "price": "Price",
    "fees": "Fees",
    "currency": "Currency",
}


class ImportIn(BaseModel):
    csv: Annotated[str, PydanticField(max_length=MAX_CSV_CHARS)]
    """The file's text."""
    mapping: dict[Field, str | None] | None = None
    """Field -> column name. Omitted: guessed from the header row."""


class TransactionOut(BaseModel):
    line: int
    date: date
    ticker: str
    side: Side
    quantity: float
    price: float
    fees: float
    currency: str


class RowErrorOut(BaseModel):
    line: int
    field: Field | None
    message: str


class SampleRow(BaseModel):
    line: int
    cells: list[str]


class Preview(BaseModel):
    columns: list[str]
    sample: list[SampleRow]
    row_count: int
    mapping: dict[Field, str | None]
    missing_fields: list[Field]
    transactions: list[TransactionOut]
    """Rows that will import, in file order."""
    errors: list[RowErrorOut]
    """Rows that will not import, in file order."""
    holdings_after: list[SavedHolding] | None
    """The portfolio's holdings after the import; None until every required field is mapped."""


class ImportResult(BaseModel):
    import_id: UUID
    imported: int
    errors: list[RowErrorOut]
    """Rows that were skipped."""
    portfolio: PortfolioOut


class StoredTransaction(TransactionOut):
    import_id: UUID
    realized_pnl: float | None
    """For a sell, the P&L booked when it was imported (FIFO, docs/adr/0004), in ``currency``. None for buys."""


def _not_found() -> ApiError:
    return ApiError(404, "not_found", "No such portfolio.")


def _table(body: ImportIn) -> Table:
    try:
        return read_table(body.csv)
    except CsvUnreadable as exc:
        raise ApiError(422, "unreadable_csv", str(exc), {"csv": str(exc)}) from exc


def _mapping(body: ImportIn, table: Table) -> dict[Field, str | None]:
    if body.mapping is None:
        return guess_mapping(table.columns)
    mapping: dict[Field, str | None] = {f: (body.mapping.get(f) or None) for f in FIELDS}
    unknown = {
        f"mapping.{f}": f"The file has no column named \"{c}\"."
        for f, c in mapping.items()
        if c is not None and c not in table.columns
    }
    if unknown:
        raise ApiError(422, "validation_error", "Some columns in the mapping are not in the file.", unknown)
    return mapping


def _plan(
    holdings: list[dict], table: Table, mapping: dict[Field, str | None]
) -> tuple[list[Position], list[Applied], list[RowError]]:
    parsed, parse_errors = parse_rows(table, mapping, datetime.now(UTC).date())
    positions = [
        Position(h["ticker"], h["quantity"], h["cost_price"], h["currency"], h.get("lots") or []) for h in holdings
    ]
    after, applied, ledger_errors = apply_transactions(positions, parsed)
    applied.sort(key=lambda a: a.transaction.line)
    return after, applied, sorted(parse_errors + ledger_errors, key=lambda e: e.line)


def _holding(p: Position) -> SavedHolding:
    return SavedHolding(ticker=p.ticker, quantity=p.quantity, cost_price=p.cost_price, currency=p.currency)


def _stored_holding(p: Position) -> dict:
    lots = [{"quantity": lot.quantity, "cost_price": lot.cost_price} for lot in p.lots]
    return {**_holding(p).model_dump(), "lots": lots}


def _transaction(t: Transaction) -> TransactionOut:
    return TransactionOut(**{k: getattr(t, k) for k in TransactionOut.model_fields})


def _error(e: RowError) -> RowErrorOut:
    return RowErrorOut(line=e.line, field=e.field, message=e.message)


@router.post("/{portfolio_id}/transactions/preview")
def preview_import(portfolio_id: UUID, body: ImportIn, user: CurrentUser, db: Db) -> Preview:
    saved = load(db, user.id, portfolio_id)
    table = _table(body)
    mapping = _mapping(body, table)
    missing = missing_fields(mapping)
    sample = [SampleRow(line=line, cells=cells) for line, cells in table.rows[:SAMPLE_ROWS]]
    base = {"columns": table.columns, "sample": sample, "row_count": len(table.rows), "mapping": mapping}
    if missing:
        return Preview(**base, missing_fields=missing, transactions=[], errors=[], holdings_after=None)
    after, applied, errors = _plan([h.model_dump() for h in saved.holdings], table, mapping)
    return Preview(
        **base,
        missing_fields=[],
        transactions=[_transaction(a.transaction) for a in applied],
        errors=[_error(e) for e in errors],
        holdings_after=[_holding(p) for p in after],
    )


@router.post("/{portfolio_id}/transactions", status_code=status.HTTP_201_CREATED)
def import_transactions(portfolio_id: UUID, body: ImportIn, user: CurrentUser, db: Db) -> ImportResult:
    table = _table(body)
    mapping = _mapping(body, table)
    missing = missing_fields(mapping)
    if missing:
        raise ApiError(
            422,
            "validation_error",
            "Choose a column for every required field.",
            {f"mapping.{f}": f"Choose the column that holds {FIELD_LABELS[f].lower()}." for f in missing},
        )
    with db.connection() as conn:
        holdings = store.lock_holdings(conn, user.id, portfolio_id)
        if holdings is None:
            raise _not_found()
        after, applied, errors = _plan(holdings, table, mapping)
        if not applied:
            message = "No rows can be imported. Fix the rows listed below and try again."
            raise ApiError(422, "nothing_to_import", message, {"csv": message})
        if len(after) > MAX_HOLDINGS:
            message = f"This import would leave {len(after)} holdings; a portfolio holds at most {MAX_HOLDINGS}."
            raise ApiError(422, "too_many_holdings", message, {"csv": message})
        if not after:
            message = "This import would sell every holding; a portfolio needs at least one."
            raise ApiError(422, "no_holdings_left", message, {"csv": message})
        import_id = store.record_import(
            conn,
            portfolio_id,
            [_stored_holding(p) for p in after],
            [{**_transaction(a.transaction).model_dump(), "realized_pnl": a.realized_pnl} for a in applied],
        )
    return ImportResult(
        import_id=import_id,
        imported=len(applied),
        errors=[_error(e) for e in errors],
        portfolio=load(db, user.id, portfolio_id),
    )


@router.get("/{portfolio_id}/transactions")
def list_transactions(portfolio_id: UUID, user: CurrentUser, db: Db) -> list[StoredTransaction]:
    with db.connection() as conn:
        rows = store.list_transactions(conn, user.id, portfolio_id)
    if rows is None:
        raise _not_found()
    return [StoredTransaction.model_validate(r) for r in rows]
