"""Reading a transactions CSV: columns, a guessed column mapping, and row-level checks.

Pure: takes the file's text and a mapping, returns parsed transactions and the
rows that could not be read. Knows nothing about users, portfolios or the database.

Line numbers are the file's own (the header is line 1), so a user can find a
bad row in their spreadsheet.
"""

from __future__ import annotations

import csv
import io
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

Field = Literal["date", "ticker", "side", "quantity", "price", "fees", "currency"]
Side = Literal["buy", "sell"]

REQUIRED_FIELDS: tuple[Field, ...] = ("date", "ticker", "side", "quantity", "price")
OPTIONAL_FIELDS: tuple[Field, ...] = ("fees", "currency")
FIELDS: tuple[Field, ...] = REQUIRED_FIELDS + OPTIONAL_FIELDS

DEFAULT_CURRENCY = "USD"
SAMPLE_ROWS = 5
MAX_ROWS = 5000

# Header names used by common broker exports, in priority order per field.
# Compared case-insensitively after collapsing anything that is not a letter or digit.
_ALIASES: dict[Field, tuple[str, ...]] = {
    "date": ("date", "trade date", "tradedate", "transaction date", "run date", "activity date",
             "date/time", "execution date", "settlement date", "settle date"),
    "ticker": ("ticker", "symbol", "ticker symbol", "instrument", "security", "stock"),
    "side": ("side", "action", "buy/sell", "type", "transaction type", "trans code", "activity", "activity type"),
    "quantity": ("quantity", "qty", "shares", "units", "no. of shares", "amount of shares"),
    "price": ("price", "trade price", "t. price", "unit price", "price ($)", "price per share", "execution price"),
    "fees": ("fees", "fee", "commission", "commissions", "comm/fee", "commission & fees", "commissions & fees",
             "fees & comm", "comm in usd"),
    "currency": ("currency", "ccy", "currency code", "trade currency"),
}

_SIDES: dict[str, Side] = {
    "buy": "buy", "b": "buy", "bought": "buy", "purchase": "buy", "you bought": "buy", "buy to open": "buy",
    "sell": "sell", "s": "sell", "sold": "sell", "sale": "sell", "you sold": "sell", "sell to close": "sell",
}

_DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%m/%d/%y", "%d-%b-%Y", "%b %d, %Y", "%Y%m%d")


class CsvUnreadable(ValueError):
    """The file has no header row, no data rows, or too many rows."""


@dataclass(frozen=True)
class Table:
    columns: list[str]
    rows: list[tuple[int, list[str]]]
    """``(line number, cells)`` for each non-blank data row."""


@dataclass(frozen=True)
class Transaction:
    line: int
    date: date
    ticker: str
    side: Side
    quantity: float
    price: float
    fees: float
    currency: str


@dataclass(frozen=True)
class RowError:
    line: int
    field: Field | None
    message: str


def read_table(text: str) -> Table:
    text = text.lstrip("﻿")
    try:
        sample = text[:4096]
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t") if sample.strip() else csv.excel
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(io.StringIO(text), dialect)
    columns: list[str] | None = None
    rows: list[tuple[int, list[str]]] = []
    try:
        for cells in reader:
            if not any(c.strip() for c in cells):
                continue
            if columns is None:
                columns = [c.strip() for c in cells]
                continue
            rows.append((reader.line_num, [c.strip() for c in cells]))
            if len(rows) > MAX_ROWS:
                raise CsvUnreadable(f"The file has more than {MAX_ROWS} rows. Split it into smaller files.")
    except csv.Error as exc:
        raise CsvUnreadable(f"This file could not be read as CSV ({exc}).") from exc
    if columns is None:
        raise CsvUnreadable("The file is empty. Upload a CSV with a header row and at least one transaction.")
    if not rows:
        raise CsvUnreadable("The file has a header row but no transactions.")
    return Table(columns, rows)


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def guess_mapping(columns: list[str]) -> dict[Field, str | None]:
    """Each field's best-matching column, or None. A column is used for at most one field."""
    by_key: dict[str, str] = {}
    for column in columns:
        by_key.setdefault(_key(column), column)
    used: set[str] = set()
    mapping: dict[Field, str | None] = {}
    for field in FIELDS:
        mapping[field] = None
        for alias in _ALIASES[field]:
            column = by_key.get(_key(alias))
            if column is not None and column not in used:
                mapping[field] = column
                used.add(column)
                break
    return mapping


def missing_fields(mapping: dict[Field, str | None]) -> list[Field]:
    return [f for f in REQUIRED_FIELDS if not mapping.get(f)]


class _Bad(ValueError):
    def __init__(self, field: Field, message: str) -> None:
        super().__init__(message)
        self.field, self.message = field, message


def _number(raw: str, field: Field, label: str) -> float:
    text = raw.strip().replace(",", "").replace(" ", "")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").lstrip("$€£¥")
    if text.startswith("-"):
        negative, text = not negative, text[1:]
    text = text.lstrip("$€£¥")
    try:
        value = float(text)
    except ValueError:
        raise _Bad(field, f"{label} is not a number: \"{raw}\".") from None
    if not math.isfinite(value):
        raise _Bad(field, f"{label} is not a number: \"{raw}\".")
    return -value if negative else value


def _date(raw: str, today: date) -> date:
    text = raw.strip()
    # Datetimes such as "2024-01-05 15:30:00" or "2024-01-05T15:30": keep the date part.
    head = re.split(r"[T ]\d{1,2}:", text, maxsplit=1)[0].strip().rstrip(",;")
    for fmt in _DATE_FORMATS:
        try:
            parsed = datetime.strptime(head, fmt).date()
        except ValueError:
            continue
        if parsed > today:
            raise _Bad("date", f"Date {raw} is in the future.")
        return parsed
    raise _Bad("date", f"Date is not a date: \"{raw}\". Use YYYY-MM-DD or MM/DD/YYYY.")


def _row(line: int, cell: dict[Field, str], today: date) -> Transaction:
    if not cell["date"]:
        raise _Bad("date", "Date is empty.")
    trade_date = _date(cell["date"], today)
    ticker = cell["ticker"].strip().upper()
    if not ticker:
        raise _Bad("ticker", "Ticker is empty.")
    side = _SIDES.get(re.sub(r"\s+", " ", cell["side"].strip().lower()))
    if side is None:
        raise _Bad("side", f"Side is not buy or sell: \"{cell['side']}\".")
    quantity = _number(cell["quantity"], "quantity", "Quantity")
    if quantity < 0 and side == "sell":
        quantity = -quantity  # Several brokers export sells as negative quantities.
    if quantity <= 0:
        raise _Bad("quantity", f"Quantity must be greater than 0 (got {cell['quantity']}).")
    price = _number(cell["price"], "price", "Price")
    if price < 0:
        raise _Bad("price", f"Price must be 0 or more (got {cell['price']}).")
    # Commissions are often exported as negative amounts; a fee is a cost either way.
    fees = abs(_number(cell["fees"], "fees", "Fees")) if cell["fees"] else 0.0
    currency = (cell["currency"] or DEFAULT_CURRENCY).strip().upper()
    if not (len(currency) == 3 and currency.isascii() and currency.isalpha()):
        raise _Bad("currency", f"Currency is not a 3-letter code: \"{cell['currency']}\".")
    return Transaction(line, trade_date, ticker, side, quantity, price, fees, currency)


def parse_rows(
    table: Table, mapping: dict[Field, str | None], today: date
) -> tuple[list[Transaction], list[RowError]]:
    """Read every data row with ``mapping`` (field -> column name). Needs every required field mapped."""
    index = {c: i for i, c in reversed(list(enumerate(table.columns)))}
    transactions: list[Transaction] = []
    errors: list[RowError] = []
    for line, cells in table.rows:
        cell: dict[Field, str] = {}
        for field in FIELDS:
            column = mapping.get(field)
            i = index.get(column) if column else None
            cell[field] = cells[i] if i is not None and i < len(cells) else ""
        try:
            transactions.append(_row(line, cell, today))
        except _Bad as bad:
            errors.append(RowError(line, bad.field, bad.message))
    return transactions, errors
