"""Options Calculator (P6) endpoints."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from sextant_compute.analytics import options as bs
from sextant_compute.analytics import strategies as st
from sextant_compute.envelope import ResultEnvelope, envelope, metric, series
from sextant_compute.errors import INPUT_ERROR, check

router = APIRouter(tags=["options"])

TOOL = "options"


class MarketInputs(BaseModel):
    """Inputs in API units: rates, yields and volatility are decimals; time is in years."""

    spot: Annotated[float, check(lambda v: v > 0, "Spot price must be greater than 0.")]
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


Strike = Annotated[float, check(lambda v: v > 0, "Strike price must be greater than 0.")]


class OptionsRequest(MarketInputs):
    strike: Strike
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


MAX_LEGS = 8


class StrategyLeg(BaseModel):
    instrument: st.Instrument
    position: Literal["long", "short"] = "long"
    quantity: Annotated[
        float,
        check(lambda v: v > 0, "Quantity must be greater than 0."),
        check(lambda v: v <= 1_000_000, "Quantity must be at most 1,000,000."),
    ] = 1.0
    strike: Strike | None = Field(default=None, validate_default=True)

    @field_validator("strike")
    @classmethod
    def _options_need_a_strike(cls, v: float | None, info: ValidationInfo) -> float | None:
        if v is None and info.data.get("instrument") in ("call", "put"):
            raise PydanticCustomError(INPUT_ERROR, "Enter a strike price for this option.")
        return v

    def to_leg(self) -> st.Leg:
        sign = 1.0 if self.position == "long" else -1.0
        strike = None if self.instrument == "underlying" else self.strike
        return st.Leg(self.instrument, sign * self.quantity, strike)


class StrategyRequest(MarketInputs):
    legs: Annotated[
        list[StrategyLeg],
        check(lambda v: len(v) >= 1, "Add at least one leg."),
        check(lambda v: len(v) <= MAX_LEGS, f"Enter at most {MAX_LEGS} legs."),
    ]


GREEK_UNITS: dict[st.Greek, str] = {
    "delta": "per_dollar",
    "gamma": "per_dollar",
    "vega": "per_vol_point",
    "theta": "per_day",
    "rho": "per_rate_point",
}


@router.post("/strategy")
def strategy(req: StrategyRequest) -> ResultEnvelope:
    legs = [leg.to_leg() for leg in req.legs]
    market = st.Market(req.spot, req.time_to_expiry, req.volatility, req.risk_free_rate, req.dividend_yield)
    metrics = {
        "net_cost": metric(lambda: st.value(legs, market), unit="currency"),
        "max_profit": metric(lambda: st.max_profit(legs, market), unit="currency"),
        "max_loss": metric(lambda: st.max_loss(legs, market), unit="currency"),
    }
    curves = {
        "profit_at_expiry": series(
            lambda: st.profit_at_expiry_curve(legs, market), x_unit="currency", y_unit="currency"
        ),
        "profit_today": series(lambda: st.profit_today_curve(legs, market), x_unit="currency", y_unit="currency"),
    }
    for g, unit in GREEK_UNITS.items():
        metrics[g] = metric(lambda g=g: st.greek(g, legs, market), unit=unit)
        curves[f"{g}_vs_spot"] = series(lambda g=g: st.greek_vs_spot(g, legs, market), x_unit="currency", y_unit=unit)
        curves[f"{g}_vs_time"] = series(lambda g=g: st.greek_vs_time(g, legs, market), x_unit="years", y_unit=unit)
    return envelope(tool=TOOL, request=req, metrics=metrics, series=curves)
