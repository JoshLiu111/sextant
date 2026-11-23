"""Position P&L of a saved portfolio (P4, stories 50 and 51), as envelope metrics.

Per position (metric ids ``<metric>:<TICKER>``, in holding order, then tickers
sold out by an import in the order they were first traded):

- ``quantity``, ``cost_basis`` (the open FIFO lots' cost), ``market_value``
  (quantity x last close in the analysis range), ``weight`` (share of the
  portfolio's market value; 0 for a sold-out position), ``unrealized_pnl``
  (market value - cost basis) and ``realized_pnl`` (the sum of the P&L each
  imported sell booked, FIFO; see docs/adr/0004).

Portfolio totals (``<metric>:portfolio``) are the sums of the positions, plus
``unrealized_return``. Realized P&L covers every imported sell to date, not just
the analysis range.

Every amount is in the reporting currency (unit ``money``, ``details.currency``),
converted at the rate of its own date (``portfolio.fx``): market value at the
last close's date, each lot's cost at the date the lot was opened (its buy, or
the day a holding was entered by hand), each sell's realized P&L at the sell
date. An amount that cannot be converted (a currency Frankfurter does not
publish) is ``missing_data`` with the reason, and so is every total and weight
that needs it.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date
from typing import TYPE_CHECKING, Any

from sextant_compute.analytics.errors import MissingData
from sextant_compute.envelope import Detailed, MetricResult, metric
from sextant_compute.portfolio.fx import Converter
from sextant_compute.portfolio.ledger import Position

if TYPE_CHECKING:
    from sextant_compute.portfolio.saved import SavedHolding

Amount = float | MissingData
"""An amount in the reporting currency, or why it could not be worked out."""

UNBOOKED = "includes sells imported before realized P&L was recorded"


def _try(compute: Callable[[], float]) -> Amount:
    try:
        return compute()
    except MissingData as exc:
        return exc


def _ok(amount: Amount) -> float:
    if isinstance(amount, MissingData):
        raise MissingData(str(amount))
    return amount


def _sum(amounts: Iterable[Amount]) -> Amount:
    return _try(lambda: sum(_ok(a) for a in amounts))


def _weight(market_value: Amount, total: Amount) -> float:
    value, whole = _ok(market_value), _ok(total)
    if whole <= 0:
        raise MissingData("needs a portfolio market value above 0")
    return value / whole


def _realized(trades: Sequence[Mapping[str, Any]], fx: Converter) -> dict[str, list[Amount]]:
    """``{ticker: [each sell's realized P&L, converted at its sell date]}``, first-traded ticker first."""
    out: dict[str, list[Amount]] = {}
    for t in trades:
        sells = out.setdefault(t["ticker"], [])
        if t["side"] != "sell":
            continue
        if t["realized_pnl"] is None:
            sells.append(MissingData(UNBOOKED))
        else:
            sells.append(_try(lambda t=t: fx.amount(t["realized_pnl"], t["currency"], t["date"])))
    return out


def position_metrics(
    holdings: Sequence[SavedHolding],
    lots: Mapping[str, Sequence[Mapping[str, Any]] | None],
    last_close: Mapping[str, float],
    valued_on: date,
    trades: Sequence[Mapping[str, Any]],
    fx: Converter,
    undated_on: date,
) -> dict[str, MetricResult]:
    """Per-position and portfolio value, weight and P&L metrics (see the module docstring).

    ``last_close`` is in each holding's own currency, on ``valued_on``. ``lots`` are the
    stored open lots by ticker; a lot without a date (stored before lots were dated)
    converts at ``undated_on``. ``trades`` are ``store.trade_history`` rows.
    """
    money = {"currency": fx.reporting}
    rows: dict[str, dict[str, Amount]] = {}
    for h in holdings:
        position = Position(h.ticker, h.quantity, h.cost_price, h.currency, list(lots.get(h.ticker) or []))
        cost = _try(
            lambda p=position: sum(
                fx.amount(lot.quantity * lot.cost_price, p.currency, lot.date or undated_on) for lot in p.lots
            )
        )
        value = _try(lambda h=h: fx.amount(h.quantity * last_close[h.ticker], h.currency, valued_on))
        rows[h.ticker] = {
            "quantity": h.quantity,
            "cost_basis": cost,
            "market_value": value,
            "unrealized_pnl": _try(lambda v=value, c=cost: _ok(v) - _ok(c)),
        }
    realized = _realized(trades, fx)
    for ticker in realized:
        if ticker not in rows:
            rows[ticker] = {"quantity": 0.0, "cost_basis": 0.0, "market_value": 0.0, "unrealized_pnl": 0.0}
    total = {
        name: _sum(r[name] for r in rows.values()) for name in ("cost_basis", "market_value", "unrealized_pnl")
    }
    realized_total = _sum(a for sells in realized.values() for a in sells)

    def amount(a: Amount) -> Callable[[], Detailed]:
        return lambda: Detailed(_ok(a), money)

    metrics: dict[str, MetricResult] = {}
    for ticker, row in rows.items():
        metrics[f"quantity:{ticker}"] = metric(lambda q=row["quantity"]: _ok(q))
        metrics[f"cost_basis:{ticker}"] = metric(amount(row["cost_basis"]), unit="money")
        metrics[f"market_value:{ticker}"] = metric(amount(row["market_value"]), unit="money")
        metrics[f"weight:{ticker}"] = metric(
            lambda v=row["market_value"]: _weight(v, total["market_value"]), unit="decimal"
        )
        metrics[f"unrealized_pnl:{ticker}"] = metric(amount(row["unrealized_pnl"]), unit="money")
        metrics[f"realized_pnl:{ticker}"] = metric(amount(_sum(realized.get(ticker, []))), unit="money")

    def unrealized_return() -> float:
        cost = _ok(total["cost_basis"])
        if cost == 0:
            raise MissingData("needs a cost basis above 0")
        return _ok(total["unrealized_pnl"]) / cost

    metrics.update({
        "market_value:portfolio": metric(amount(total["market_value"]), unit="money"),
        "cost_basis:portfolio": metric(amount(total["cost_basis"]), unit="money"),
        "unrealized_pnl:portfolio": metric(amount(total["unrealized_pnl"]), unit="money"),
        "unrealized_return:portfolio": metric(unrealized_return, unit="decimal"),
        "realized_pnl:portfolio": metric(amount(realized_total), unit="money"),
    })
    return metrics
