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

Holdings and lots are in today's share count (like prices), but a file's rows are
in the share count of their dates. So before a row is applied, its quantity is
multiplied by every split after its date and its price divided by the same factor;
cash, fees and realized P&L do not change. The stored rows keep the file's own
numbers (the returns convert them again, ``portfolio.returns``), and both answers
list the splits that were applied (``splits_applied``).

Splits come from the price source: Demo data for Demo tickers, otherwise the user's
first My data provider with a saved key. When there is no key, or the provider
cannot serve a ticker's splits, its rows import as written and ``warnings`` says so:
an import never fails for want of splits.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field as PydanticField

from sextant_compute.auth import CurrentUser
from sextant_compute.auth.deps import get_db
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData, SourceUnavailable
from sextant_compute.data.service import Ctx, Data, DataService
from sextant_compute.data.sources import DEMO_SOURCE, MY_DATA_SOURCES, is_demo_ticker
from sextant_compute.data.splits import Split, shares_today
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


class SplitOut(BaseModel):
    ticker: str
    ex_date: date
    ratio: float
    """New shares per old share."""


class SplitNotes(BaseModel):
    splits_applied: list[SplitOut] = []
    """Splits after some imported row's date, oldest first: those rows count in today's share count."""
    warnings: list[str] = []
    """Tickers whose splits could not be checked; their rows import as written."""


class Preview(SplitNotes):
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


class ImportResult(SplitNotes):
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


def _splits(
    data: DataService, ctx: RequestContext, transactions: list[Transaction]
) -> tuple[dict[str, list[Split]], list[str]]:
    """Each imported ticker's splits since its first row, and a warning per group of tickers whose splits are unknown."""
    since: dict[str, date] = {}
    for t in transactions:
        since[t.ticker] = min(t.date, since.get(t.ticker, t.date))
    provider = next((p for p in MY_DATA_SOURCES if ctx.key_for(p)), None)
    found: dict[str, list[Split]] = {}
    unchecked: list[str] = []
    failed: list[tuple[str, str]] = []
    for ticker, start in since.items():
        source = DEMO_SOURCE if is_demo_ticker(ticker) else provider
        if source is None:
            unchecked.append(ticker)
            continue
        try:
            found[ticker] = data.splits(ctx, ticker, start, source=source)
        except (NoSuchData, SourceUnavailable) as exc:
            failed.append((ticker, exc.message))
    after = "Their rows import as written; if one split after a trade, edit its holding afterwards."
    warnings = [
        f"Could not get the stock splits of {ticker}: {message} Its rows import as written; "
        "if it split after a trade, edit its holding afterwards."
        for ticker, message in failed
    ]
    if unchecked:
        names = " or ".join(s.name for s in MY_DATA_SOURCES.values())
        warnings.append(
            f"Stock splits were not checked for {', '.join(unchecked)}: that needs a {names} key in Settings. {after}"
        )
    return found, warnings


def _in_todays_shares(t: Transaction, splits: list[Split]) -> Transaction:
    factor = shares_today(splits, t.date)
    return t if factor == 1 else replace(t, quantity=t.quantity * factor, price=t.price / factor)


def _applied_splits(splits: dict[str, list[Split]], transactions: list[Transaction]) -> list[SplitOut]:
    first = {t.ticker: t.date for t in sorted(transactions, key=lambda t: t.date, reverse=True)}
    used = [
        SplitOut(ticker=ticker, ex_date=s.ex_date, ratio=s.ratio)
        for ticker, found in splits.items()
        for s in found
        if ticker in first and s.ex_date > first[ticker]
    ]
    return sorted(used, key=lambda s: (s.ex_date, s.ticker))


def _plan(
    holdings: list[dict], parsed: list[Transaction], splits: dict[str, list[Split]]
) -> tuple[list[Position], list[Applied], list[RowError]]:
    positions = [
        Position(h["ticker"], h["quantity"], h["cost_price"], h["currency"], h.get("lots") or []) for h in holdings
    ]
    as_written = {t.line: t for t in parsed}
    today = [_in_todays_shares(t, splits.get(t.ticker, [])) for t in parsed]
    after, applied, errors = apply_transactions(positions, today)
    # The ledger works in today's share count; the rows answered and stored keep the file's numbers.
    applied = sorted(
        (replace(a, transaction=as_written[a.transaction.line]) for a in applied), key=lambda a: a.transaction.line
    )
    return after, applied, errors


def _parse(table: Table, mapping: dict[Field, str | None]) -> tuple[list[Transaction], list[RowError]]:
    return parse_rows(table, mapping, datetime.now(UTC).date())


def _holding(p: Position) -> SavedHolding:
    return SavedHolding(ticker=p.ticker, quantity=p.quantity, cost_price=p.cost_price, currency=p.currency)


def _stored_holding(p: Position) -> dict:
    lots = [lot.to_json() for lot in p.lots]
    return {**_holding(p).model_dump(), "lots": lots}


def _transaction(t: Transaction) -> TransactionOut:
    return TransactionOut(**{k: getattr(t, k) for k in TransactionOut.model_fields})


def _error(e: RowError) -> RowErrorOut:
    return RowErrorOut(line=e.line, field=e.field, message=e.message)


@router.post("/{portfolio_id}/transactions/preview")
def preview_import(portfolio_id: UUID, body: ImportIn, user: CurrentUser, db: Db, data: Data, ctx: Ctx) -> Preview:
    saved = load(db, user.id, portfolio_id)
    table = _table(body)
    mapping = _mapping(body, table)
    missing = missing_fields(mapping)
    sample = [SampleRow(line=line, cells=cells) for line, cells in table.rows[:SAMPLE_ROWS]]
    base = {"columns": table.columns, "sample": sample, "row_count": len(table.rows), "mapping": mapping}
    if missing:
        return Preview(**base, missing_fields=missing, transactions=[], errors=[], holdings_after=None)
    parsed, parse_errors = _parse(table, mapping)
    splits, warnings = _splits(data, ctx, parsed)
    after, applied, ledger_errors = _plan([h.model_dump() for h in saved.holdings], parsed, splits)
    return Preview(
        **base,
        missing_fields=[],
        transactions=[_transaction(a.transaction) for a in applied],
        errors=[_error(e) for e in sorted(parse_errors + ledger_errors, key=lambda e: e.line)],
        holdings_after=[_holding(p) for p in after],
        splits_applied=_applied_splits(splits, [a.transaction for a in applied]),
        warnings=warnings,
    )


@router.post("/{portfolio_id}/transactions", status_code=status.HTTP_201_CREATED)
def import_transactions(
    portfolio_id: UUID, body: ImportIn, user: CurrentUser, db: Db, data: Data, ctx: Ctx
) -> ImportResult:
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
    parsed, parse_errors = _parse(table, mapping)
    # Splits come from the provider, so fetch them before the holdings are locked.
    splits, warnings = _splits(data, ctx, parsed)
    with db.connection() as conn:
        holdings = store.lock_holdings(conn, user.id, portfolio_id)
        if holdings is None:
            raise _not_found()
        after, applied, ledger_errors = _plan(holdings, parsed, splits)
        errors = sorted(parse_errors + ledger_errors, key=lambda e: e.line)
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
        splits_applied=_applied_splits(splits, [a.transaction for a in applied]),
        warnings=warnings,
    )


@router.get("/{portfolio_id}/transactions")
def list_transactions(portfolio_id: UUID, user: CurrentUser, db: Db) -> list[StoredTransaction]:
    with db.connection() as conn:
        rows = store.list_transactions(conn, user.id, portfolio_id)
    if rows is None:
        raise _not_found()
    return [StoredTransaction.model_validate(r) for r in rows]
