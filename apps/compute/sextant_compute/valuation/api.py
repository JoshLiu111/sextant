"""Valuation Calculator (P2): FCF-based DCF, WACC breakdown, sensitivity table.

Free cash flow = Operating Cash Flow − Capital Expenditure from the latest fiscal
year of the company's EDGAR statements. Equity value = enterprise value + cash +
short-term investments − total debt; a company that reports no short-term
investments counts them as 0 (``details.basis = "not_reported"``). Market-data inputs (risk-free rate, beta,
equity risk premium, share price) have no public source here, so they start from
the documented defaults below and the visitor can override them. Every WACC
component can also be overridden directly; ``null`` means "derive it".
"""

from __future__ import annotations

from collections.abc import Callable
from functools import cache
from typing import Annotated, Any, Literal

from fastapi import APIRouter
from pydantic import AfterValidator, BaseModel, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from sextant_compute.analytics import valuation as v
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.context import RequestContext
from sextant_compute.data.service import Ctx, Data, DataService
from sextant_compute.data.sources import DEMO_SOURCE, PriceSource
from sextant_compute.data.statements import FinancialStatements, Missing
from sextant_compute.envelope import (
    DataSource,
    Detailed,
    MetricError,
    MetricResult,
    MissingData,
    ResultEnvelope,
    SeriesResult,
    envelope,
    metric,
    series,
)
from sextant_compute.errors import INPUT_ERROR, ApiError, check
from sextant_compute.request_models import Ticker

router = APIRouter(tags=["valuation"])

TOOL = "valuation"
HISTORY_YEARS = 5
# Sensitivity grid: offsets from the base case, in decimals. The center cell is the base case.
GROWTH_STEPS = (-0.02, -0.01, 0.0, 0.01, 0.02)
DISCOUNT_STEPS = (-0.01, -0.005, 0.0, 0.005, 0.01)

# Documented defaults for inputs that need market data (see docs in en.ts / ticket notes).
DEFAULT_RISK_FREE_RATE = 0.045  # about the 10-year US Treasury yield in 2025-26 (FRED DGS10)
DEFAULT_BETA = 1.0  # the market average
DEFAULT_EQUITY_RISK_PREMIUM = 0.05  # Damodaran's implied US ERP has been about 4-6% since 2010

NO_PRICE_MESSAGE = "Enter a share price to compare the market value with the intrinsic value."


def _rate(low: float, high: float, name: str) -> AfterValidator:
    return check(lambda x: low <= x <= high, f"Enter {name} between {low:.0%} and {high:.0%}.")




class ValuationAssumptions(BaseModel):
    """Every DCF/WACC input the user chooses (what a saved assumption set stores)."""

    forecast_years: Annotated[int, check(lambda x: 1 <= x <= 20, "Choose between 1 and 20 years.")] = 5
    growth_rate: Annotated[float, _rate(-0.5, 1.0, "a growth rate")] = 0.05
    """Annual FCF growth during the forecast years (decimal)."""
    discount_rate: Annotated[float | None, _rate(0.0, 0.5, "a discount rate")] = None
    """Override for the discount rate; null = use the WACC."""
    terminal_growth: Annotated[float, _rate(-0.05, 0.1, "a terminal growth rate")] = 0.025
    risk_free_rate: Annotated[float, _rate(-0.05, 0.2, "a risk-free rate")] = DEFAULT_RISK_FREE_RATE
    beta: Annotated[float, check(lambda x: -1 <= x <= 5, "Enter a beta between -1 and 5.")] = DEFAULT_BETA
    equity_risk_premium: Annotated[float, _rate(0.0, 0.2, "an equity risk premium")] = DEFAULT_EQUITY_RISK_PREMIUM
    cost_of_equity: Annotated[float | None, _rate(0.0, 0.5, "a cost of equity")] = None
    """Override; null = CAPM from the risk-free rate, beta and equity risk premium."""
    cost_of_debt: Annotated[float | None, _rate(0.0, 0.5, "a cost of debt")] = None
    """Override (pre-tax); null = interest expense / total debt."""
    tax_rate: Annotated[float | None, _rate(0.0, 1.0, "a tax rate")] = None
    """Override; null = income tax / pre-tax income."""
    debt_weight: Annotated[
        float | None, check(lambda x: 0 <= x < 1, "Enter a debt weight from 0% up to (not including) 100%.")
    ] = None
    """Override for D / (D + E); null = from total debt and the value of equity."""
    share_price: Annotated[float | None, check(lambda x: x > 0, "Enter a share price greater than 0.")] = None
    """Optional. Market value of equity = price × shares outstanding (for the weights, market
    cap and margin of safety); null = the latest close on My data, else book equity and no comparison."""

    @field_validator("terminal_growth")
    @classmethod
    def _below_discount_rate(cls, g: float, info: ValidationInfo) -> float:
        r = info.data.get("discount_rate")
        if r is not None and g >= r:
            raise PydanticCustomError(INPUT_ERROR, "Terminal growth must be below the discount rate.")
        return g


class DcfRequest(ValuationAssumptions):
    ticker: Ticker = "MSFT"
    source: Literal["sec_edgar"] = "sec_edgar"
    price_source: PriceSource = DEMO_SOURCE
    """Where a missing ``share_price`` comes from: ``"synthetic"`` (Demo) looks nothing up;
    a My data provider (``"tiingo"``) uses its latest close, on the user's own key."""


class CompanyOut(BaseModel):
    ticker: str
    cik: int
    name: str


class BasePeriodOut(BaseModel):
    id: str
    label: str
    filed: str
    url: str


class SensitivityOut(BaseModel):
    """Cell metric ``"sensitivity:<i>:<j>"`` is the value per share at
    ``growth_rates[i]`` and ``discount_rates[j]``; the center cell is the base case."""

    growth_rates: list[float]
    discount_rates: list[float]


class ValuationEnvelope(ResultEnvelope):
    company: CompanyOut
    price_source: DataSource | None = None
    """The provider the share price came from (My data); null when it was typed in or there is none."""
    base_period: BasePeriodOut
    sensitivity: SensitivityOut


class _Result:
    """A value or the expected failure that prevented it (re-raised on ``get``)."""

    def __init__(self, compute: Callable[[], Any]) -> None:
        try:
            self.value, self.exc = compute(), None
        except (MissingData, MetricError) as exc:
            self.value, self.exc = None, exc

    def get(self) -> Any:
        if self.exc is not None:
            raise self.exc
        return self.value


def _basis(override: float | None) -> dict[str, str]:
    return {"basis": "override" if override is not None else "derived"}


@router.post("/dcf")
def dcf(req: DcfRequest, data: Data, ctx: Ctx) -> ValuationEnvelope:
    try:
        st = data.financial_statements(ctx, req.ticker, source=req.source)
    except NoSuchData as exc:
        message = exc.missing.get(req.ticker, exc.message)
        raise ApiError(422, "no_such_data", message, {"ticker": message}) from exc
    if not st.periods:
        message = f"{req.ticker} has no annual reports with financial data."
        raise ApiError(422, "no_such_data", message, {"ticker": message})
    period = st.periods[-1]
    pid = period.id

    def item(item_id: str) -> Detailed:
        cell = st.cell(item_id, pid)
        if isinstance(cell, Missing):
            raise MissingData(cell.message)
        return Detailed(cell.value, {"period": period.label, "filed": cell.filing.filed.isoformat(), "url": cell.filing.url})

    @cache
    def fcf() -> float:
        return st.value("operating_cash_flow", pid) - st.value("capital_expenditure", pid)

    def short_term_investments() -> Detailed:
        if isinstance(st.cell("short_term_investments", pid), Missing):
            return Detailed(0.0, {"basis": "not_reported"})
        return item("short_term_investments")

    @cache
    def cash_and_investments() -> float:
        return st.value("cash", pid) + short_term_investments().value

    @cache
    def total_debt() -> float:
        return st.value("current_debt", pid) + st.value("long_term_debt", pid)

    def positive_fcf() -> float:
        if fcf() <= 0:
            raise MetricError(
                f"Free cash flow was negative in {period.label}, so an FCF-based DCF isn't meaningful for this company."
            )
        return fcf()

    price, price_source = _share_price(req, data, ctx)

    def share_price() -> Detailed:
        if isinstance(price, MissingData):
            raise price
        return price

    def equity_for_weights() -> float:
        if not isinstance(price, MissingData):
            return price.value * st.value("shares_outstanding", pid)
        return st.value("total_equity", pid)

    re_ = _Result(
        lambda: req.cost_of_equity
        if req.cost_of_equity is not None
        else v.cost_of_equity(
            risk_free_rate=req.risk_free_rate, beta=req.beta, equity_risk_premium=req.equity_risk_premium
        )
    )
    rd = _Result(
        lambda: req.cost_of_debt
        if req.cost_of_debt is not None
        else v.cost_of_debt(interest_expense=st.value("interest_expense", pid), total_debt=total_debt())
    )
    tax = _Result(
        lambda: req.tax_rate
        if req.tax_rate is not None
        else v.tax_rate(income_tax=st.value("income_tax", pid), pretax_income=st.value("pretax_income", pid))
    )
    wd = _Result(
        lambda: req.debt_weight
        if req.debt_weight is not None
        else v.debt_weight(equity=equity_for_weights(), debt=total_debt())
    )
    w = _Result(
        lambda: v.wacc(cost_of_equity=re_.get(), cost_of_debt=rd.get(), tax_rate=tax.get(), debt_weight=wd.get())
    )
    r = _Result(lambda: req.discount_rate if req.discount_rate is not None else w.get())

    def value_per_share(growth: float, discount_rate: float) -> float:
        model = v.dcf(
            positive_fcf(),
            growth=growth,
            terminal_growth=req.terminal_growth,
            discount_rate=discount_rate,
            years=req.forecast_years,
        )
        equity = v.equity_value(model.enterprise_value, cash=cash_and_investments(), total_debt=total_debt())
        return v.per_share(equity, st.value("shares_outstanding", pid))

    base = _Result(
        lambda: v.dcf(
            positive_fcf(),
            growth=req.growth_rate,
            terminal_growth=req.terminal_growth,
            discount_rate=r.get(),
            years=req.forecast_years,
        )
    )
    equity = _Result(
        lambda: v.equity_value(base.get().enterprise_value, cash=cash_and_investments(), total_debt=total_debt())
    )
    intrinsic = _Result(lambda: v.per_share(equity.get(), st.value("shares_outstanding", pid)))

    def sourced(compute: Callable[[], float]) -> Callable[[], Detailed]:
        """Statement-derived value with the base period's 10-K as its source."""
        return lambda: Detailed(
            compute(), {"period": period.label, "filed": period.filed.isoformat(), "url": period.filing.url}
        )

    metrics: dict[str, MetricResult] = {
        # Statement inputs
        "free_cash_flow": metric(sourced(fcf), unit="currency"),
        "operating_cash_flow": metric(lambda: item("operating_cash_flow"), unit="currency"),
        "capital_expenditure": metric(lambda: item("capital_expenditure"), unit="currency"),
        "cash": metric(lambda: item("cash"), unit="currency"),
        "short_term_investments": metric(short_term_investments, unit="currency"),
        "total_debt": metric(sourced(total_debt), unit="currency"),
        "shares_outstanding": metric(lambda: item("shares_outstanding"), unit="shares"),
        # WACC breakdown
        "cost_of_equity": metric(lambda: Detailed(re_.get(), _basis(req.cost_of_equity)), unit="decimal"),
        "cost_of_debt": metric(lambda: Detailed(rd.get(), _basis(req.cost_of_debt)), unit="decimal"),
        "tax_rate": metric(lambda: Detailed(tax.get(), _basis(req.tax_rate)), unit="decimal"),
        "after_tax_cost_of_debt": metric(lambda: rd.get() * (1 - tax.get()), unit="decimal"),
        "debt_weight": metric(lambda: Detailed(wd.get(), _basis(req.debt_weight)), unit="decimal"),
        "equity_weight": metric(lambda: Detailed(1 - wd.get(), _basis(req.debt_weight)), unit="decimal"),
        "wacc": metric(w.get, unit="decimal"),
        "discount_rate": metric(lambda: Detailed(r.get(), _basis(req.discount_rate)), unit="decimal"),
        # DCF
        "pv_forecast_fcf": metric(lambda: base.get().pv_forecast, unit="currency"),
        "terminal_value": metric(lambda: base.get().terminal_value, unit="currency"),
        "pv_terminal_value": metric(lambda: base.get().pv_terminal, unit="currency"),
        "enterprise_value": metric(lambda: base.get().enterprise_value, unit="currency"),
        "equity_value": metric(equity.get, unit="currency"),
        "intrinsic_value_per_share": metric(intrinsic.get, unit="per_share"),
        # Market comparison (needs a share price)
        "share_price": metric(share_price, unit="per_share"),
        "market_cap": metric(lambda: share_price().value * st.value("shares_outstanding", pid), unit="currency"),
        "margin_of_safety": metric(
            lambda: v.margin_of_safety(intrinsic_value=intrinsic.get(), price=share_price().value), unit="decimal"
        ),
    }

    growth_rates = [round(req.growth_rate + d, 10) for d in GROWTH_STEPS]
    discount_rates = [round(r.value + d, 10) for d in DISCOUNT_STEPS] if r.exc is None else []
    for i, g in enumerate(growth_rates):
        for j, _ in enumerate(DISCOUNT_STEPS):
            metrics[f"sensitivity:{i}:{j}"] = metric(
                lambda g=g, j=j: value_per_share(g, r.get() + DISCOUNT_STEPS[j]), unit="per_share"
            )

    out_series: dict[str, SeriesResult] = {
        "projected_fcf": series(
            lambda: [(t, cf) for t, cf in enumerate(base.get().projected, start=1)], x_unit="year", y_unit="currency"
        ),
        "historical_fcf": series(lambda: _fcf_history(st), x_unit="date", y_unit="currency"),
    }

    env = envelope(
        tool=TOOL, request=req, metrics=metrics, series=out_series, source=st.source, data_cutoff=period.filed
    )
    return ValuationEnvelope(
        **env.model_dump(),
        price_source=price_source,
        company=CompanyOut(ticker=st.company.ticker, cik=st.company.cik, name=st.company.name),
        base_period=BasePeriodOut(id=pid, label=period.label, filed=period.filed.isoformat(), url=period.filing.url),
        sensitivity=SensitivityOut(growth_rates=growth_rates, discount_rates=discount_rates),
    )


def _share_price(
    req: DcfRequest, data: DataService, ctx: RequestContext
) -> tuple[Detailed | MissingData, DataSource | None]:
    """The share price to compare with (and to weight equity at), and the provider it came from.

    A typed-in price wins (and spends none of the user's provider quota); otherwise
    My data looks up the latest close. ``KeyRequired`` propagates (403)."""
    if req.share_price is not None:
        return Detailed(req.share_price, {"basis": "entered"}), None
    if req.price_source == DEMO_SOURCE:
        return MissingData(NO_PRICE_MESSAGE), None
    try:
        close = data.latest_close(ctx, req.ticker, source=req.price_source)
    except NoSuchData as exc:
        return MissingData(exc.missing.get(req.ticker, exc.message)), data.source_info(req.price_source)
    return Detailed(close.close, {"basis": "latest_close", "date": close.date.isoformat()}), close.source


def _fcf_history(st: FinancialStatements) -> list[tuple[str, float | None]]:
    points: list[tuple[str, float | None]] = []
    for p in st.last(HISTORY_YEARS).periods:
        try:
            points.append((p.id, st.value("operating_cash_flow", p.id) - st.value("capital_expenditure", p.id)))
        except MissingData:
            points.append((p.id, None))
    return points
