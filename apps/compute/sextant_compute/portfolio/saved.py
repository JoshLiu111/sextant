"""Saved portfolios (P4): signed-in users' manually entered holdings.

Every query is scoped by the current user's id, so one user can never read or
change another user's portfolios: someone else's portfolio id answers 404, the
same as an id that does not exist.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, BeforeValidator

from sextant_compute.analytics import portfolio as portfolio_analytics
from sextant_compute.analytics.errors import MissingData
from sextant_compute.auth import CurrentUser
from sextant_compute.auth.deps import get_db
from sextant_compute.data.service import Ctx, Data
from sextant_compute.db import Database
from sextant_compute.envelope import Detailed, MetricResult, ResultEnvelope, metric
from sextant_compute.errors import ApiError, check
from sextant_compute.portfolio import store
from sextant_compute.portfolio.api import MAX_HOLDINGS, AnalysisSettings, load_prices, score
from sextant_compute.risk.api import Ticker

router = APIRouter(tags=["portfolios"])

Db = Annotated[Database, Depends(get_db)]
MAX_NAME = 100


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


def _upper(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


class SavedHolding(BaseModel):
    ticker: Ticker
    quantity: Annotated[float, check(lambda v: v > 0, "Enter a quantity greater than 0.")]
    cost_price: Annotated[float, check(lambda v: v >= 0, "Enter a cost price of 0 or more.")]
    """Average price paid per unit, in ``currency``."""
    currency: Annotated[
        str,
        BeforeValidator(_upper),
        check(lambda v: len(v) == 3 and v.isascii() and v.isalpha(), "Enter a 3-letter currency code, like USD."),
    ] = "USD"


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
        portfolio_id = store.create(conn, user.id, body.name, [h.model_dump() for h in body.holdings])
    return load(db, user.id, portfolio_id)


@router.get("/{portfolio_id}")
def get_portfolio(portfolio_id: UUID, user: CurrentUser, db: Db) -> PortfolioOut:
    return load(db, user.id, portfolio_id)


@router.put("/{portfolio_id}")
def update_portfolio(portfolio_id: UUID, body: PortfolioIn, user: CurrentUser, db: Db) -> PortfolioOut:
    """Rename the portfolio and replace its holdings with ``body.holdings``."""
    with db.connection() as conn:
        found = store.replace(conn, user.id, portfolio_id, body.name, [h.model_dump() for h in body.holdings])
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


class ScoredPortfolio(AnalysisSettings):
    """What a saved-portfolio result was computed from; echoed as the envelope's ``meta.parameters``."""

    portfolio_id: UUID
    name: str
    holdings: list[SavedHolding]


def _value_metrics(holdings: list[SavedHolding], last_close: dict[str, float], currency: str) -> dict[str, MetricResult]:
    """Today's value and unrealized P&L versus cost, in the holdings' currency (unit ``money``)."""
    details: dict[str, str | float | None] = {"currency": currency}
    market_value = sum(h.quantity * last_close[h.ticker] for h in holdings)
    cost_basis = sum(h.quantity * h.cost_price for h in holdings)

    def unrealized_return() -> float:
        if cost_basis == 0:
            raise MissingData("needs a cost basis above 0")
        return (market_value - cost_basis) / cost_basis

    return {
        "market_value:portfolio": metric(lambda: Detailed(market_value, details), unit="money"),
        "cost_basis:portfolio": metric(lambda: Detailed(cost_basis, details), unit="money"),
        "unrealized_pnl:portfolio": metric(lambda: Detailed(market_value - cost_basis, details), unit="money"),
        "unrealized_return:portfolio": metric(unrealized_return, unit="decimal"),
    }


@router.post("/{portfolio_id}/metrics")
def saved_portfolio_metrics(
    portfolio_id: UUID, settings: AnalysisSettings, user: CurrentUser, db: Db, data: Data, ctx: Ctx
) -> ResultEnvelope:
    """Performance and risk of the user's saved portfolio, held at its quantities (buy and hold).

    Prices come from ``settings.source`` (demo data until bring-your-own-key lands).
    """
    saved = load(db, user.id, portfolio_id)
    currencies = sorted({h.currency for h in saved.holdings})
    if len(currencies) > 1:
        raise ApiError(
            422,
            "mixed_currencies",
            f"This portfolio holds more than one currency ({', '.join(currencies)}). "
            "Converting between currencies is not available yet, so use one currency per portfolio for now.",
        )
    quantities = {h.ticker: h.quantity for h in saved.holdings}
    prices, frames = load_prices(data, ctx, list(quantities), settings)
    value = portfolio_analytics.buy_and_hold_value(frames, quantities)
    last_close = {t: float(frames[t]["close"].iloc[-1]) for t in quantities}
    req = ScoredPortfolio(**settings.model_dump(), portfolio_id=saved.id, name=saved.name, holdings=saved.holdings)
    return score(
        req, settings, prices, frames, value / value.iloc[0], _value_metrics(saved.holdings, last_close, currencies[0])
    )
