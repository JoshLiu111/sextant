"""Applying transactions to a portfolio's holdings (pure).

Transactions apply in date order (file order within a day) on top of the
current holdings:

- A buy adds to the holding. The cost price becomes the average cost including
  fees: ``(q * cost + qty * price + fees) / (q + qty)``. A new ticker is added
  at the end of the holdings.
- A sell reduces the quantity and leaves the average cost unchanged (realized
  P&L is a later ticket). A holding sold down to zero is removed.

A row that cannot apply (selling more than is held, or a currency that differs
from the holding's) becomes a row error and is skipped; later rows apply as if
it was not there.
"""

from __future__ import annotations

from dataclasses import dataclass

from sextant_compute.portfolio.transactions_csv import RowError, Transaction

# Quantities this close to zero after a sell count as fully sold (float dust).
_DUST = 1e-9


@dataclass
class Position:
    ticker: str
    quantity: float
    cost_price: float
    currency: str


def _fmt(x: float) -> str:
    return f"{x:,.6f}".rstrip("0").rstrip(".")


def apply_transactions(
    holdings: list[Position], transactions: list[Transaction]
) -> tuple[list[Position], list[Transaction], list[RowError]]:
    """The holdings after ``transactions``, the transactions that applied, and the ones that could not."""
    book = {h.ticker: Position(h.ticker, h.quantity, h.cost_price, h.currency) for h in holdings}
    order = [h.ticker for h in holdings]
    applied: list[Transaction] = []
    errors: list[RowError] = []
    for t in sorted(transactions, key=lambda t: (t.date, t.line)):
        held = book.get(t.ticker)
        if held is not None and held.currency != t.currency:
            errors.append(RowError(t.line, "currency", f"{t.ticker} is held in {held.currency}, but this row is in {t.currency}."))
            continue
        if t.side == "buy":
            if held is None:
                held = book[t.ticker] = Position(t.ticker, 0.0, 0.0, t.currency)
                order.append(t.ticker)
            total = held.quantity + t.quantity
            held.cost_price = (held.quantity * held.cost_price + t.quantity * t.price + t.fees) / total
            held.quantity = total
        else:
            have = held.quantity if held is not None else 0.0
            if held is None or t.quantity > have + _DUST:
                errors.append(
                    RowError(t.line, "quantity", f"Sells {_fmt(t.quantity)} {t.ticker}, but only {_fmt(have)} is held on {t.date.isoformat()}.")
                )
                continue
            held.quantity -= t.quantity
            if held.quantity <= _DUST:
                del book[t.ticker]
                order.remove(t.ticker)
        applied.append(t)
    return [book[ticker] for ticker in order], applied, errors
