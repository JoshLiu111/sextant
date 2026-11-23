"""Time-weighted and money-weighted (IRR) returns of a saved portfolio (P4, story 52).

``POST /portfolios/{id}/returns`` rebuilds the portfolio day by day over the date
range from its current holdings and its imported transactions (see
``analytics.flow_returns``), then answers with:

- ``twr:portfolio``: time-weighted return over the range (decimal), with details
  ``start_value``, ``end_value``, ``currency``.
- ``twr_annualized:portfolio``: the same per year.
- ``irr:portfolio``: money-weighted return (IRR) per year; ``missing_data`` when no
  single rate solves it.

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
from sextant_compute.portfolio.saved import Db, load

router = APIRouter(tags=["portfolios"])


class ReturnsSettings(BaseModel):
    start: date
    end: date
    source: PriceSource = DEMO_SOURCE

    @field_validator("end")
    @classmethod
    def _end_after_start(cls, end: date, info: ValidationInfo) -> date:
        start = info.data.get("start")
        if start is not None and end <= start:
            raise PydanticCustomError(INPUT_ERROR, "End date must be after the start date.")
        return end


class ReturnsParameters(ReturnsSettings):
    """What the returns were computed from; echoed as the envelope's ``meta.parameters``."""

    portfolio_id: UUID
    name: str
    transactions: int


def _trade(row: dict) -> flow_returns.Trade:
    gross = row["quantity"] * row["price"]
    if row["side"] == "buy":
        return flow_returns.Trade(row["date"], row["ticker"], row["quantity"], gross + row["fees"])
    return flow_returns.Trade(row["date"], row["ticker"], -row["quantity"], -(gross - row["fees"]))


@router.post("/{portfolio_id}/returns")
def portfolio_returns(
    portfolio_id: UUID, settings: ReturnsSettings, user: CurrentUser, db: Db, data: Data, ctx: Ctx
) -> ResultEnvelope:
    saved = load(db, user.id, portfolio_id)
    with db.connection() as conn:
        rows = store.list_transactions(conn, user.id, portfolio_id) or []
    currencies = sorted({h.currency for h in saved.holdings} | {r["currency"] for r in rows})
    if len(currencies) > 1:
        raise ApiError(
            422,
            "mixed_currencies",
            f"This portfolio holds or traded more than one currency ({', '.join(currencies)}). "
            "Converting between currencies is not available yet, so use one currency per portfolio for now.",
        )
    trades = [_trade(r) for r in rows]
    tickers = list(dict.fromkeys([*(h.ticker for h in saved.holdings), *(t.ticker for t in trades)]))
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

    def book() -> flow_returns.Book:
        return flow_returns.daily_book(frames, holdings, trades)

    def twr() -> Detailed:
        b = book()
        total, _ = flow_returns.time_weighted_return(b)
        details = {"start_value": float(b.value.iloc[0]), "end_value": float(b.value.iloc[-1]), "currency": currencies[0]}
        return Detailed(total, details)

    def twr_annualized() -> float:
        return flow_returns.annualize(*flow_returns.time_weighted_return(book()))

    def irr() -> Detailed:
        flows = flow_returns.cash_flows(book())
        return Detailed(flow_returns.irr(flows), {"cash_flows": len(flows)})

    req = ReturnsParameters(
        **settings.model_dump(), portfolio_id=saved.id, name=saved.name, transactions=len(trades)
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
