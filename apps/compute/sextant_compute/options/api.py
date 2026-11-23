"""Options Calculator (P6) endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel

from sextant_compute.analytics import options as bs
from sextant_compute.envelope import ResultEnvelope, envelope, metric, series
from sextant_compute.errors import check

router = APIRouter(tags=["options"])

TOOL = "options"


class OptionsRequest(BaseModel):
    """Inputs in API units: rates, yields and volatility are decimals; time is in years."""

    spot: Annotated[float, check(lambda v: v > 0, "Spot price must be greater than 0.")]
    strike: Annotated[float, check(lambda v: v > 0, "Strike price must be greater than 0.")]
    time_to_expiry: Annotated[
        float,
        check(lambda v: v > 0, "Time to expiry must be greater than 0: the option has already expired."),
        check(lambda v: v <= 50, "Time to expiry must be at most 50 years."),
    ]
    volatility: Annotated[
        float, check(lambda v: 0 < v <= 5, "Volatility must be greater than 0% and at most 500%.")
    ]
    risk_free_rate: Annotated[
        float, check(lambda v: -1 < v < 1, "Risk-free rate must be between -100% and 100%.")
    ]
    dividend_yield: Annotated[
        float, check(lambda v: -1 < v < 1, "Dividend yield must be between -100% and 100%.")
    ] = 0.0
    option_type: bs.OptionType = "call"
    market_price: Annotated[
        float | None, check(lambda v: v > 0, "Market price must be greater than 0.")
    ] = None


@router.post("/price")
def price(req: OptionsRequest) -> ResultEnvelope:
    args = (req.spot, req.strike, req.time_to_expiry, req.volatility, req.risk_free_rate, req.dividend_yield)
    kind, grid = req.option_type, bs.spot_grid(req.spot, req.strike)
    return envelope(
        tool=TOOL,
        request=req,
        metrics={
            "call_price": metric(lambda: bs.bs_price("call", *args), unit="currency"),
            "put_price": metric(lambda: bs.bs_price("put", *args), unit="currency"),
            "call_delta": metric(lambda: bs.delta("call", *args), unit="per_dollar"),
            "put_delta": metric(lambda: bs.delta("put", *args), unit="per_dollar"),
            "gamma": metric(lambda: bs.gamma(*args), unit="per_dollar"),
            "vega": metric(lambda: bs.vega(*args), unit="per_vol_point"),
            "call_theta": metric(lambda: bs.theta("call", *args), unit="per_day"),
            "put_theta": metric(lambda: bs.theta("put", *args), unit="per_day"),
            "call_rho": metric(lambda: bs.rho("call", *args), unit="per_rate_point"),
            "put_rho": metric(lambda: bs.rho("put", *args), unit="per_rate_point"),
            "implied_volatility": metric(
                lambda: bs.implied_volatility(
                    req.option_type,
                    req.market_price,
                    req.spot,
                    req.strike,
                    req.time_to_expiry,
                    req.risk_free_rate,
                    req.dividend_yield,
                ),
                unit="decimal",
            ),
        },
        series={
            "payoff_at_expiry": series(
                lambda: [(x, bs.payoff_at_expiry(kind, x, req.strike)) for x in grid],
                x_unit="currency",
                y_unit="currency",
            ),
            "theoretical_value": series(
                lambda: [(x, bs.bs_price(kind, x, *args[1:])) for x in grid],
                x_unit="currency",
                y_unit="currency",
            ),
        },
    )
