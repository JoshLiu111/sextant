"""Position P&L of a saved portfolio (P4, story 50), as envelope metrics.

Per position (metric ids ``<metric>:<TICKER>``, in holding order, then tickers
sold out by an import in the order they were first traded):

- ``quantity``, ``cost_basis`` (quantity x average cost of the open FIFO lots),
  ``market_value`` (quantity x last close in the analysis range), ``weight``
  (share of the portfolio's market value; 0 for a sold-out position),
  ``unrealized_pnl`` (market value - cost basis) and ``realized_pnl`` (the sum
  of the P&L each imported sell booked, FIFO; see docs/adr/0004).

Portfolio totals (``<metric>:portfolio``) are the sums of the positions, plus
``unrealized_return``. Realized P&L covers every imported sell to date, not just
the analysis range. Amounts are in the portfolio's currency (unit ``money``,
``details.currency``); a realized amount in another currency is shown on its
position but not added to the total until FX conversion exists.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from sextant_compute.analytics.errors import MissingData
from sextant_compute.envelope import Detailed, MetricResult, metric

if TYPE_CHECKING:
    from sextant_compute.portfolio.saved import SavedHolding


def _realized_by_ticker(rows: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, float | None]]:
    """``{ticker: {currency: realized P&L or None if a sell has none booked}}``, first-traded first."""
    out: dict[str, dict[str, float | None]] = {}
    for row in rows:
        out.setdefault(row["ticker"], {})[row["currency"]] = None if row["unbooked"] else row["realized_pnl"]
    return out


def _realized(amounts: Mapping[str, float | None], currency: str) -> Detailed:
    """One position's realized P&L: in a single currency, with every sell booked."""
    if not amounts:
        return Detailed(0.0, {"currency": currency})
    if len(amounts) > 1:
        raise MissingData(f"realized in more than one currency ({', '.join(sorted(amounts))})")
    (booked_in, amount), = amounts.items()
    if amount is None:
        raise MissingData("includes sells imported before realized P&L was recorded")
    return Detailed(amount, {"currency": booked_in})


def _weight(market_value: float, total: float) -> float:
    if total <= 0:
        raise MissingData("needs a portfolio market value above 0")
    return market_value / total


def position_metrics(
    holdings: Sequence[SavedHolding],
    last_close: Mapping[str, float],
    realized_rows: Sequence[Mapping[str, Any]],
    currency: str,
) -> dict[str, MetricResult]:
    """Per-position and portfolio value, weight and P&L metrics (see the module docstring)."""
    realized = _realized_by_ticker(realized_rows)
    money = {"currency": currency}
    rows: dict[str, dict[str, float]] = {}
    for h in holdings:
        market_value = h.quantity * last_close[h.ticker]
        cost_basis = h.quantity * h.cost_price
        rows[h.ticker] = {
            "quantity": h.quantity,
            "cost_basis": cost_basis,
            "market_value": market_value,
            "unrealized_pnl": market_value - cost_basis,
        }
    for ticker in realized:
        if ticker not in rows:
            rows[ticker] = {"quantity": 0.0, "cost_basis": 0.0, "market_value": 0.0, "unrealized_pnl": 0.0}
    total = {name: sum(r[name] for r in rows.values()) for name in ("cost_basis", "market_value", "unrealized_pnl")}

    currencies = {h.ticker: h.currency for h in holdings}
    metrics: dict[str, MetricResult] = {}
    for ticker, row in rows.items():
        amounts = realized.get(ticker, {})
        # A sold-out position is in the currency its trades were in.
        own = {"currency": currencies.get(ticker) or next(iter(amounts), currency)}
        mv = row["market_value"]
        metrics[f"quantity:{ticker}"] = metric(lambda q=row["quantity"]: q)
        metrics[f"cost_basis:{ticker}"] = metric(lambda v=row["cost_basis"], d=own: Detailed(v, d), unit="money")
        metrics[f"market_value:{ticker}"] = metric(lambda v=mv, d=own: Detailed(v, d), unit="money")
        metrics[f"weight:{ticker}"] = metric(lambda v=mv: _weight(v, total["market_value"]), unit="decimal")
        metrics[f"unrealized_pnl:{ticker}"] = metric(
            lambda v=row["unrealized_pnl"], d=own: Detailed(v, d), unit="money"
        )
        metrics[f"realized_pnl:{ticker}"] = metric(lambda a=amounts, c=own["currency"]: _realized(a, c), unit="money")

    def realized_total() -> Detailed:
        others = sorted({c for amounts in realized.values() for c in amounts} - {currency})
        if others:
            raise MissingData(
                f"some realized P&L is in {', '.join(others)}; converting currencies is not available yet"
            )
        if any(a is None for amounts in realized.values() for a in amounts.values()):
            raise MissingData("includes sells imported before realized P&L was recorded")
        return Detailed(sum(a or 0.0 for amounts in realized.values() for a in amounts.values()), money)

    def unrealized_return() -> float:
        if total["cost_basis"] == 0:
            raise MissingData("needs a cost basis above 0")
        return total["unrealized_pnl"] / total["cost_basis"]

    metrics.update({
        "market_value:portfolio": metric(lambda: Detailed(total["market_value"], money), unit="money"),
        "cost_basis:portfolio": metric(lambda: Detailed(total["cost_basis"], money), unit="money"),
        "unrealized_pnl:portfolio": metric(lambda: Detailed(total["unrealized_pnl"], money), unit="money"),
        "unrealized_return:portfolio": metric(unrealized_return, unit="decimal"),
        "realized_pnl:portfolio": metric(realized_total, unit="money"),
    })
    return metrics
