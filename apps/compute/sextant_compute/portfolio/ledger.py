"""Applying transactions to a portfolio's holdings (pure).

Each holding is a list of open lots, oldest first (see docs/adr/0004). A
holding entered or edited by hand is one lot at its cost price. Transactions
apply in date order (file order within a day) on top of the current lots:

- A buy adds a lot at ``price + fees / quantity`` per unit. A new ticker is
  added at the end of the holdings.
- A sell closes lots first in, first out. It books realized P&L of
  ``quantity * price - fees - cost of the closed lots``. A holding sold down to
  zero is removed.

A holding's cost price is the average cost of its open lots.

A row that cannot apply (selling more than is held, or a currency that differs
from the holding's) becomes a row error and is skipped; later rows apply as if
it was not there.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sextant_compute.portfolio.transactions_csv import RowError, Transaction

# Quantities this close to zero count as nothing left (float dust).
_DUST = 1e-9


@dataclass
class Lot:
    quantity: float
    cost_price: float
    """Cost per unit, including buy fees."""
    date: date | None = None
    """When the lot was opened: the buy's trade date, or the day a holding was entered by hand.
    None for lots stored before lots were dated. Cost converts to another currency at this date's rate."""

    @classmethod
    def of(cls, lot: Lot | dict) -> Lot:
        if isinstance(lot, Lot):
            return Lot(lot.quantity, lot.cost_price, lot.date)
        when = lot.get("date")
        return cls(lot["quantity"], lot["cost_price"], date.fromisoformat(when) if isinstance(when, str) else when)

    def to_json(self) -> dict:
        out: dict = {"quantity": self.quantity, "cost_price": self.cost_price}
        if self.date is not None:
            out["date"] = self.date.isoformat()
        return out


@dataclass
class Position:
    ticker: str
    quantity: float
    cost_price: float
    currency: str
    lots: list[Lot] = field(default_factory=list)
    """Open lots, oldest first. Empty: one lot of ``quantity`` at ``cost_price``."""

    def __post_init__(self) -> None:
        self.lots = [Lot.of(lot) for lot in self.lots]
        if not self.lots or abs(sum(lot.quantity for lot in self.lots) - self.quantity) > _DUST * max(1.0, self.quantity):
            # No lots, or lots that no longer add up to the holding: the holding itself is the lot.
            self.lots = [Lot(self.quantity, self.cost_price)]

    def _sync(self) -> None:
        self.quantity = sum(lot.quantity for lot in self.lots)
        if self.quantity > _DUST:
            self.cost_price = sum(lot.quantity * lot.cost_price for lot in self.lots) / self.quantity

    def buy(self, quantity: float, price: float, fees: float, on: date | None = None) -> None:
        self.lots.append(Lot(quantity, price + fees / quantity, on))
        self._sync()

    def sell(self, quantity: float, price: float, fees: float) -> float:
        """Close lots first in, first out; returns the realized P&L."""
        cost, left = 0.0, quantity
        while left > _DUST and self.lots:
            lot = self.lots[0]
            take = min(lot.quantity, left)
            cost += take * lot.cost_price
            lot.quantity -= take
            left -= take
            if lot.quantity <= _DUST:
                self.lots.pop(0)
        self._sync()
        return quantity * price - fees - cost


@dataclass(frozen=True)
class Applied:
    transaction: Transaction
    realized_pnl: float | None
    """For a sell, the P&L it booked; None for a buy."""


def _fmt(x: float) -> str:
    return f"{x:,.6f}".rstrip("0").rstrip(".")


def apply_transactions(
    holdings: list[Position], transactions: list[Transaction]
) -> tuple[list[Position], list[Applied], list[RowError]]:
    """The holdings after ``transactions``, the transactions that applied, and the ones that could not."""
    book = {
        h.ticker: Position(h.ticker, h.quantity, h.cost_price, h.currency, [Lot.of(lot) for lot in h.lots])
        for h in holdings
    }
    order = [h.ticker for h in holdings]
    applied: list[Applied] = []
    errors: list[RowError] = []
    for t in sorted(transactions, key=lambda t: (t.date, t.line)):
        held = book.get(t.ticker)
        if held is not None and held.currency != t.currency:
            errors.append(RowError(t.line, "currency", f"{t.ticker} is held in {held.currency}, but this row is in {t.currency}."))
            continue
        if t.side == "buy":
            if held is None:
                cost = t.price + t.fees / t.quantity
                held = book[t.ticker] = Position(t.ticker, t.quantity, cost, t.currency, [Lot(t.quantity, cost, t.date)])
                order.append(t.ticker)
            else:
                held.buy(t.quantity, t.price, t.fees, t.date)
            applied.append(Applied(t, None))
            continue
        have = held.quantity if held is not None else 0.0
        if held is None or t.quantity > have + _DUST:
            errors.append(
                RowError(t.line, "quantity", f"Sells {_fmt(t.quantity)} {t.ticker}, but only {_fmt(have)} is held on {t.date.isoformat()}.")
            )
            continue
        applied.append(Applied(t, held.sell(t.quantity, t.price, t.fees)))
        if held.quantity <= _DUST:
            del book[t.ticker]
            order.remove(t.ticker)
    return [book[ticker] for ticker in order], applied, errors
