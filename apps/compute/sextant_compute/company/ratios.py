"""Company Health Check (P1): ratio analytics and Altman Z for one or more companies.

``POST /api/compute/company/ratios`` with
``{"companies": [{"ticker": "AAPL", "price": 250.0 | null}, ...], "years": 5}``.
Each metric is ``"<ratio id>:<TICKER>:<period id>"`` (the period id is the
fiscal year end, as in ``/company/statements``). ``ratios`` lists the ratio ids
with their category and unit, in display order; ``companies`` lists each
company's displayed fiscal periods. Altman Z is metric ``altman_z`` with
``details.zone`` (safe / grey / distress) and its five inputs ``x1``..``x5``.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, BeforeValidator, Field

from sextant_compute.analytics.ratios import ALTMAN_Z, RATIOS, Ratio, Year
from sextant_compute.company.api import MAX_YEARS
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import Ctx, Data
from sextant_compute.data.statements import FinancialStatements
from sextant_compute.envelope import MetricResult, ResultEnvelope, envelope, metric
from sextant_compute.errors import ApiError, check

router = APIRouter(tags=["company"])

TOOL = "company"
MAX_COMPANIES = 5


def _normalize_ticker(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


class CompanyInput(BaseModel):
    ticker: Annotated[str, BeforeValidator(_normalize_ticker), check(lambda v: v != "", "Enter a ticker.")]
    price: Annotated[float | None, check(lambda v: v > 0, "Price must be greater than 0.")] = None


class RatiosRequest(BaseModel):
    companies: Annotated[
        list[CompanyInput],
        check(lambda v: len(v) >= 1, "Enter at least one ticker."),
        check(lambda v: len(v) <= MAX_COMPANIES, f"Compare at most {MAX_COMPANIES} companies."),
    ] = Field(default_factory=lambda: [CompanyInput(ticker="AAPL")])
    years: Annotated[
        int, check(lambda v: 1 <= v <= MAX_YEARS, f"Choose between 1 and {MAX_YEARS} years.")
    ] = 5
    source: Literal["sec_edgar"] = "sec_edgar"


class RatioOut(BaseModel):
    id: str
    category: str
    unit: str


class PeriodOut(BaseModel):
    id: str
    label: str
    fiscal_year: int
    end: date
    filed: date
    url: str


class CompanyRatiosOut(BaseModel):
    ticker: str
    cik: int
    name: str
    price: float | None
    periods: list[PeriodOut]


class RatiosEnvelope(ResultEnvelope):
    companies: list[CompanyRatiosOut]
    ratios: list[RatioOut]


def ratio_metrics(
    statements: FinancialStatements, years: int, price: float | None, ratios: tuple[Ratio, ...]
) -> dict[str, MetricResult]:
    """Every ratio for the ``years`` most recent periods, keyed ``"<ratio>:<period id>"``.

    Ratios are computed on the full history so the earliest displayed year can
    still average with the year before it."""
    out: dict[str, MetricResult] = {}
    n = len(statements.periods)
    for index in range(max(n - years, 0), n):
        year = Year(statements, index, price=price)
        for r in ratios:
            out[f"{r.id}:{year.period.id}"] = metric(lambda r=r, year=year: r.compute(year), unit=r.unit)
    return out


def _duplicates(req: RatiosRequest) -> dict[str, str]:
    seen: set[str] = set()
    fields: dict[str, str] = {}
    for i, c in enumerate(req.companies):
        if c.ticker in seen:
            fields[f"companies.{i}.ticker"] = f"{c.ticker} is already in the list."
        seen.add(c.ticker)
    return fields


@router.post("/ratios")
def ratios(req: RatiosRequest, data: Data, ctx: Ctx) -> RatiosEnvelope:
    if dupes := _duplicates(req):
        raise ApiError(422, "validation_error", "Each company can appear only once.", dupes)

    fetched: list[FinancialStatements] = []
    missing: dict[str, str] = {}
    for i, c in enumerate(req.companies):
        try:
            fetched.append(data.financial_statements(ctx, c.ticker, source=req.source))
        except NoSuchData as exc:
            missing[f"companies.{i}.ticker"] = exc.missing.get(c.ticker, exc.message)
    if missing:
        raise ApiError(422, "no_such_data", " ".join(missing.values()), missing)

    metrics: dict[str, MetricResult] = {}
    companies: list[CompanyRatiosOut] = []
    for c, full in zip(req.companies, fetched, strict=True):
        ticker = full.company.ticker
        for key, result in ratio_metrics(full, req.years, c.price, (*RATIOS, ALTMAN_Z)).items():
            ratio_id, period_id = key.split(":", 1)
            metrics[f"{ratio_id}:{ticker}:{period_id}"] = result
        shown = full.last(req.years)
        companies.append(
            CompanyRatiosOut(
                ticker=ticker,
                cik=full.company.cik,
                name=full.company.name,
                price=c.price,
                periods=[
                    PeriodOut(id=p.id, label=p.label, fiscal_year=p.fiscal_year, end=p.end, filed=p.filed, url=p.filing.url)
                    for p in shown.periods
                ],
            )
        )

    base = envelope(
        tool=TOOL,
        request=req,
        metrics=metrics,
        source=fetched[0].source,
        data_cutoff=max(p.filed for st in fetched for p in st.periods),
    )
    return RatiosEnvelope(
        **base.model_dump(),
        companies=companies,
        ratios=[RatioOut(id=r.id, category=r.category, unit=r.unit) for r in RATIOS],
    )
