"""Time-weighted and money-weighted (IRR) returns of a saved portfolio (P4, story 52).

``POST /portfolios/{id}/returns`` rebuilds the portfolio day by day over the date
range from its current holdings and its imported transactions (see
``analytics.flow_returns``), then answers with:

- ``twr:portfolio``: time-weighted return over the range (decimal), with details
  ``start_value``, ``end_value``, ``currency``.
- ``twr_annualized:portfolio``: the same per year.
- ``irr:portfolio``: money-weighted return (IRR) per year; ``missing_data`` when no
  single rate solves it.

Values and trades convert into the reporting currency (``reporting_currency``,
default the first holding's) at each date's Frankfurter rate (``portfolio.fx``):
each day's closes at that day's rate, each trade's cash at its trade date's rate.
A currency Frankfurter does not publish makes every metric ``missing_data``.

When the holdings were edited by hand so that undoing the transactions would leave
a negative quantity, every metric is ``missing_data`` with the ticker in the reason.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from sextant_compute.analytics import flow_returns
from sextant_compute.auth import CurrentUser
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import Ctx, Data
from sextant_compute.data.sources import DEMO_SOURCE, PriceSource
from sextant_compute.envelope import Detailed, ResultEnvelope, envelope, metric
from sextant_compute.errors import INPUT_ERROR, ApiError
from sextant_compute.portfolio import store
from sextant_compute.portfolio.api import TOOL, fetch_prices
from sextant_compute.portfolio.fx import Converter
from sextant_compute.portfolio.saved import Currency, Db, load

router = APIRouter(tags=["portfolios"])


class ReturnsSettings(BaseModel):
    start: date
    end: date
    source: PriceSource = DEMO_SOURCE
    reporting_currency: Currency | None = None
    """Currency the values and cash flows are measured in; None: the first holding's currency."""

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, end: date, info: ValidationInfo) -> date:
        start = info.data.get("start")
        if start is not None and end <= start:
            raise PydanticCustomError(INPUT_ERROR, "End date must be after the start date.")
        return end


class ReturnsParameters(ReturnsSettings):
    """What the returns were computed from; echoed as the envelope's ``meta.parameters``."""

    reporting_currency: str
    portfolio_id: UUID
    name: str
    transactions: int


def _trade(row: dict, rate: float) -> flow_returns.Trade:
    """The trade with its cash in the reporting currency (``rate`` per unit of the row's currency)."""
    gross = row["quantity"] * row["price"]
    if row["side"] == "buy":
        return flow_returns.Trade(row["date"], row["ticker"], row["quantity"], (gross + row["fees"]) * rate)
    return flow_returns.Trade(row["date"], row["ticker"], -row["quantity"], -(gross - row["fees"]) * rate)


@router.post("/{portfolio_id}/returns")
def portfolio_returns(
    portfolio_id: UUID, settings: ReturnsSettings, user: CurrentUser, db: Db, data: Data, ctx: Ctx
) -> ResultEnvelope:
    saved = load(db, user.id, portfolio_id)
    with db.connection() as conn:
        rows = store.list_transactions(conn, user.id, portfolio_id) or []
    reporting = settings.reporting_currency or saved.holdings[0].currency
    currency_of = {r["ticker"]: r["currency"] for r in rows} | {h.ticker: h.currency for h in saved.holdings}
    tickers = list(dict.fromkeys([*(h.ticker for h in saved.holdings), *(r["ticker"] for r in rows)]))
    try:
        prices = fetch_prices(data, ctx, tickers, settings.start, settings.end, settings.source)
    except NoSuchData as exc:
        raise ApiError(422, "no_such_data", exc.message, {"start": exc.message}) from exc
    common = prices.frames[tickers[0]].index
    for ticker in tickers[1:]:
        common = common.intersection(prices.frames[ticker].index)
    if len(common) < 2:
        message = "The portfolio's tickers share fewer than 2 trading days in this range."
        raise ApiError(422, "no_such_data", message, {"start": message})
    frames = {t: prices.frames[t].loc[common] for t in tickers}
    holdings = {h.ticker: h.quantity for h in saved.holdings}
    first, last = common[0].date(), common[-1].date()
    fx = Converter(data, ctx, reporting, currency_of.values(), first, last)

    def in_range(row: dict) -> bool:
        # Only trades inside the range move cash (see ``flow_returns.daily_book``); the rest need no rate.
        return first < row["date"] <= last

    def book() -> flow_returns.Book:
        converted = {t: fx.prices(frame, currency_of[t]) for t, frame in frames.items()}
        trades = [_trade(r, fx.rate(r["currency"], r["date"]) if in_range(r) else 1.0) for r in rows]
        return flow_returns.daily_book(converted, holdings, trades)

    def twr() -> Detailed:
        b = book()
        total, _ = flow_returns.time_weighted_return(b)
        details = {"start_value": float(b.value.iloc[0]), "end_value": float(b.value.iloc[-1]), "currency": reporting}
        return Detailed(total, details)

    def twr_annualized() -> float:
        return flow_returns.annualize(*flow_returns.time_weighted_return(book()))

    def irr() -> Detailed:
        flows = flow_returns.cash_flows(book())
        return Detailed(flow_returns.irr(flows), {"cash_flows": len(flows)})

    req = ReturnsParameters(
        **settings.model_dump(exclude={"reporting_currency"}),
        reporting_currency=reporting,
        portfolio_id=saved.id,
        name=saved.name,
        transactions=len(rows),
    )
    return envelope(
        tool=TOOL,
        request=req,
        metrics={
            "twr:portfolio": metric(twr, unit="decimal"),
            "twr_annualized:portfolio": metric(twr_annualized, unit="decimal"),
            "irr:portfolio": metric(irr, unit="decimal"),
        },
        source=prices.source,
        data_cutoff=prices.last_date,
    )
