"""Saved portfolios (P4): signed-in users' manually entered holdings.

Every query is scoped by the current user's id, so one user can never read or
change another user's portfolios: someone else's portfolio id answers 404, the
same as an id that does not exist.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Annotated
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, BeforeValidator

from sextant_compute.analytics import portfolio as portfolio_analytics
from sextant_compute.analytics.errors import MissingData
from sextant_compute.auth import CurrentUser
from sextant_compute.auth.deps import get_db
from sextant_compute.data.service import Ctx, Data
from sextant_compute.db import Database
from sextant_compute.envelope import MetricResult, MetricStatus, ResultEnvelope, SeriesResult
from sextant_compute.errors import ApiError, check
from sextant_compute.portfolio import store
from sextant_compute.portfolio.fx import Converter
from sextant_compute.portfolio.api import MAX_HOLDINGS, AnalysisSettings, load_prices, score
from sextant_compute.portfolio.positions import position_metrics
from sextant_compute.request_models import Ticker

router = APIRouter(tags=["portfolios"])

Db = Annotated[Database, Depends(get_db)]
MAX_NAME = 100


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _upper(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


Currency = Annotated[
    str,
    BeforeValidator(_upper),
    check(lambda v: len(v) == 3 and v.isascii() and v.isalpha(), "Enter a 3-letter currency code, like USD."),
]
"""An ISO 4217-style code, upper-cased (``usd`` -> ``USD``)."""


def today() -> date:
    """The day a holding entered by hand is dated (its lot's open date). Tests pin it."""
    return datetime.now(UTC).date()


class SavedHolding(BaseModel):
    ticker: Ticker
    quantity: Annotated[float, check(lambda v: v > 0, "Enter a quantity greater than 0.")]
    cost_price: Annotated[float, check(lambda v: v >= 0, "Enter a cost price of 0 or more.")]
    """Average price paid per unit, in ``currency``."""
    currency: Currency = "USD"


class PortfolioIn(BaseModel):
    name: Annotated[
        str,
        BeforeValidator(_strip),
        check(lambda v: v != "", "Enter a name."),
        check(lambda v: len(v) <= MAX_NAME, f"Use at most {MAX_NAME} characters."),
    ]
    holdings: Annotated[
        list[SavedHolding],
        check(lambda v: len(v) >= 1, "Add at least one holding."),
        check(lambda v: len(v) <= MAX_HOLDINGS, f"Enter at most {MAX_HOLDINGS} holdings."),
        check(lambda v: len({h.ticker for h in v}) == len(v), "Each ticker can only be listed once."),
    ]


class PortfolioSummary(BaseModel):
    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime


class PortfolioOut(PortfolioSummary):
    holdings: list[SavedHolding]


def _not_found() -> ApiError:
    return ApiError(404, "not_found", "No such portfolio.")


def load(db: Database, user_id: UUID, portfolio_id: UUID) -> PortfolioOut:
    """The user's portfolio, or 404 if it does not exist or belongs to someone else."""
    with db.connection() as conn:
        row = store.get(conn, user_id, portfolio_id)
    if row is None:
        raise _not_found()
    return PortfolioOut.model_validate(row)


@router.get("")
def list_portfolios(user: CurrentUser, db: Db) -> list[PortfolioSummary]:
    with db.connection() as conn:
        rows = store.list_for(conn, user.id)
    return [PortfolioSummary.model_validate(row) for row in rows]


@router.post("", status_code=status.HTTP_201_CREATED)
def create_portfolio(body: PortfolioIn, user: CurrentUser, db: Db) -> PortfolioOut:
    with db.connection() as conn:
        portfolio_id = store.create(conn, user.id, body.name, [h.model_dump() for h in body.holdings], today())
    return load(db, user.id, portfolio_id)


@router.get("/{portfolio_id}")
def get_portfolio(portfolio_id: UUID, user: CurrentUser, db: Db) -> PortfolioOut:
    return load(db, user.id, portfolio_id)


@router.put("/{portfolio_id}")
def update_portfolio(portfolio_id: UUID, body: PortfolioIn, user: CurrentUser, db: Db) -> PortfolioOut:
    """Rename the portfolio and replace its holdings with ``body.holdings``."""
    with db.connection() as conn:
        found = store.replace(
            conn, user.id, portfolio_id, body.name, [h.model_dump() for h in body.holdings], today()
        )
    if not found:
        raise _not_found()
    return load(db, user.id, portfolio_id)


@router.delete("/{portfolio_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_portfolio(portfolio_id: UUID, user: CurrentUser, db: Db) -> Response:
    with db.connection() as conn:
        found = store.delete(conn, user.id, portfolio_id)
    if not found:
        raise _not_found()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


class SavedAnalysisSettings(AnalysisSettings):
    reporting_currency: Currency | None = None
    """Currency every amount is shown in; None: the first holding's currency."""


class ScoredPortfolio(SavedAnalysisSettings):
    """What a saved-portfolio result was computed from; echoed as the envelope's ``meta.parameters``."""

    reporting_currency: str
    portfolio_id: UUID
    name: str
    holdings: list[SavedHolding]


def _span(start: date, end: date, *dates: date) -> tuple[date, date]:
    return min(start, *dates), max(end, *dates)


def _without_portfolio_risk(env: ResultEnvelope, own: Mapping[str, MetricResult], reason: str) -> ResultEnvelope:
    """The envelope with the portfolio's risk metrics and chart ``missing_data`` (``own`` metrics kept)."""
    for key, result in env.metrics.items():
        if key.endswith(":portfolio") and key not in own:
            env.metrics[key] = MetricResult(value=None, status=MetricStatus.MISSING_DATA, reason=reason, unit=result.unit)
    for key, chart in env.series.items():
        if key.endswith(":portfolio"):
            env.series[key] = SeriesResult(
                status=MetricStatus.MISSING_DATA, reason=reason, x_unit=chart.x_unit, y_unit=chart.y_unit
            )
    return env


@router.post("/{portfolio_id}/metrics")
def saved_portfolio_metrics(
    portfolio_id: UUID, settings: SavedAnalysisSettings, user: CurrentUser, db: Db, data: Data, ctx: Ctx
) -> ResultEnvelope:
    """Performance and risk of the user's saved portfolio, held at its quantities (buy and hold),
    plus each position's value, weight and P&L (``portfolio.positions``), all in the reporting
    currency at each date's exchange rate (``portfolio.fx``).

    Prices come from ``settings.source``: Demo data or the user's own provider (My data).
    On My data a holding without prices marks only its own value, weight and P&L
    ``missing_data``, plus the portfolio-level metrics that need it (with the reason).
    """
    saved = load(db, user.id, portfolio_id)
    with db.connection() as conn:
        lots = store.holding_lots(conn, saved.id)
        trades = store.trade_history(conn, saved.id)
    reporting = settings.reporting_currency or saved.holdings[0].currency
    quantities = {h.ticker: h.quantity for h in saved.holdings}
    # On My data an unknown ticker marks only its own position missing, like Risk & Performance.
    prices, frames = load_prices(data, ctx, list(quantities), settings, allow_missing=True)
    undated_on = saved.created_at.date()
    lot_dates = [
        date.fromisoformat(lot["date"]) for held in lots.values() for lot in held or [] if lot.get("date")
    ]
    first, last = _span(
        frames[settings.benchmark].index[0].date(),
        frames[settings.benchmark].index[-1].date(),
        undated_on,
        *lot_dates,
        *(t["date"] for t in trades),
    )
    fx = Converter(data, ctx, reporting, [*(h.currency for h in saved.holdings), *(t["currency"] for t in trades)], first, last)

    converted: dict[str, pd.DataFrame] = {}
    problem: MissingData | None = None
    if prices.missing:
        problem = MissingData(f"needs prices for every holding. {' '.join(prices.missing.values())}")
    for h in saved.holdings:
        if h.ticker in prices.missing:
            continue
        try:
            converted[h.ticker] = fx.prices(frames[h.ticker], h.currency)
        except MissingData as exc:
            problem = problem or exc
    valued_on = frames[settings.benchmark].index[-1].date()
    last_close: dict[str, float | MissingData] = {
        t: MissingData(prices.missing[t]) if t in prices.missing else float(frames[t]["close"].iloc[-1])
        for t in quantities
    }
    extra = position_metrics(saved.holdings, lots, last_close, valued_on, trades, fx, undated_on)
    req = ScoredPortfolio(
        **settings.model_dump(exclude={"reporting_currency"}),
        reporting_currency=reporting,
        portfolio_id=saved.id,
        name=saved.name,
        holdings=saved.holdings,
    )
    if problem is not None:
        # The portfolio's value cannot be built; score the benchmark alone and mark the portfolio's risk missing.
        placeholder = frames[settings.benchmark]["close"] / frames[settings.benchmark]["close"].iloc[0]
        return _without_portfolio_risk(score(req, settings, prices, frames, placeholder, extra), extra, str(problem))
    value = portfolio_analytics.buy_and_hold_value({**frames, **converted}, quantities)
    return score(req, settings, prices, frames, value / value.iloc[0], extra)
