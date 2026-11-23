"""Company Health Check (P1): ratio analytics and Altman Z for one or more companies.

``POST /api/compute/company/ratios`` with
``{"companies": [{"ticker": "AAPL", "price": 250.0 | null}, ...], "years": 5}``.
Each metric is ``"<ratio id>:<TICKER>:<period id>"`` (the period id is the
fiscal year end, as in ``/company/statements``). ``ratios`` lists the ratio ids
with their category and unit, in display order; ``companies`` lists each
company's displayed fiscal periods. ``models`` lists, the same way, the
scores (category ``scores``), the nine Piotroski signals (``piotroski``, unit
``signal``, value 1 = pass) and the DuPont burdens (``dupont``); see
``analytics.scores``. Altman Z (``altman_z``) has ``details.zone`` (safe / grey
/ distress) and ``x1``..``x5``; Piotroski F (``piotroski_f``) has ``zone``
(strong / neutral / weak) and each signal's 0/1; Beneish M (``beneish_m``) has
``zone`` (likely / unlikely) and its eight indices.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, BeforeValidator, Field

from sextant_compute.analytics.ratios import RATIOS, Ratio, Trace, WithDetails, Year
from sextant_compute.analytics.scores import MODELS
from sextant_compute.company.api import MAX_QUARTERS, MAX_YEARS, UNITS
from sextant_compute.company.periods import Periods, Source
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import Ctx, Data
from sextant_compute.data.statements import FinancialStatements, FiscalPeriod, Frequency, Missing
from sextant_compute.envelope import Detailed, MetricResult, ResultEnvelope, envelope, metric
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
    frequency: Frequency = "annual"
    quarters: Annotated[
        int, check(lambda v: 1 <= v <= MAX_QUARTERS, f"Choose between 1 and {MAX_QUARTERS} quarters.")
    ] = 8
    source: Literal["sec_edgar"] = "sec_edgar"

    def periods(self) -> int:
        return self.quarters if self.frequency == "quarterly" else self.years


Basis = Literal["fiscal_year", "ttm", "quarter_end"]


class RatioOut(BaseModel):
    id: str
    category: str
    unit: str
    basis: Basis


class PeriodOut(BaseModel):
    id: str
    label: str
    fiscal_year: int
    fiscal_quarter: int | None
    end: date
    filed: date
    url: str


def _period_out(p: FiscalPeriod) -> PeriodOut:
    return PeriodOut(
        id=p.id,
        label=p.label,
        fiscal_year=p.fiscal_year,
        fiscal_quarter=p.fiscal_quarter,
        end=p.end,
        filed=p.filed,
        url=p.filing.url,
    )


class CompanyRatiosOut(BaseModel):
    ticker: str
    cik: int
    name: str
    price: float | None
    periods: list[PeriodOut]


class RatiosEnvelope(ResultEnvelope):
    companies: list[CompanyRatiosOut]
    ratios: list[RatioOut]
    models: list[RatioOut]


def _basis(periods: Periods, trace: Trace) -> Basis:
    if periods.frequency == "annual":
        return "fiscal_year"
    return "ttm" if any(item in periods.flows for _, item in trace.reads) else "quarter_end"


def _compute(r: Ratio, year: Year, periods: Periods, trace: Trace) -> tuple[MetricResult, Basis]:
    """One ratio on one period; quarterly values carry ``details.basis``."""
    trace.clear()

    def compute() -> float | Detailed:
        out = r.compute(year)
        value, details = (out.value, dict(out.details)) if isinstance(out, WithDetails) else (out, {})
        if periods.frequency == "quarterly":
            details["basis"] = _basis(periods, trace)
        return Detailed(value, details) if details else value

    result = metric(compute, unit=r.unit)
    return result, _basis(periods, trace)


def ratio_metrics(
    statements: FinancialStatements,
    shown: int,
    price: float | None,
    ratios: tuple[Ratio, ...],
    frequency: Frequency = "annual",
) -> tuple[dict[str, MetricResult], dict[str, set[Basis]]]:
    """Every ratio for the ``shown`` most recent periods, keyed ``"<ratio>:<period id>"``,
    and the bases each ratio was computed on.

    Ratios are computed on the full history so the earliest displayed period can
    still average with the one before it."""
    trace = Trace()
    periods = Periods(statements, frequency, price, trace)
    out: dict[str, MetricResult] = {}
    bases: dict[str, set[Basis]] = {}
    n = len(statements.periods)
    for index in range(max(n - shown, 0), n):
        for r in ratios:
            result, basis = _compute(r, periods.years[index], periods, trace)
            out[f"{r.id}:{statements.periods[index].id}"] = result
            bases.setdefault(r.id, set()).add(basis)
    return out, bases


def _ratio_out(r: Ratio, bases: dict[str, set[Basis]], frequency: Frequency) -> RatioOut:
    seen = bases.get(r.id, set())
    basis: Basis = "fiscal_year" if frequency == "annual" else "ttm" if "ttm" in seen else "quarter_end"
    return RatioOut(id=r.id, category=r.category, unit=r.unit, basis=basis)


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
            fetched.append(data.statements(ctx, c.ticker, source=req.source, frequency=req.frequency))
        except NoSuchData as exc:
            missing[f"companies.{i}.ticker"] = exc.missing.get(c.ticker, exc.message)
    if missing:
        raise ApiError(422, "no_such_data", " ".join(missing.values()), missing)

    metrics: dict[str, MetricResult] = {}
    companies: list[CompanyRatiosOut] = []
    bases: dict[str, set[Basis]] = {}
    for c, full in zip(req.companies, fetched, strict=True):
        ticker = full.company.ticker
        results, company_bases = ratio_metrics(full, req.periods(), c.price, (*RATIOS, *MODELS), req.frequency)
        for key, result in results.items():
            ratio_id, period_id = key.split(":", 1)
            metrics[f"{ratio_id}:{ticker}:{period_id}"] = result
        for ratio_id, seen in company_bases.items():
            bases.setdefault(ratio_id, set()).update(seen)
        shown = full.last(req.periods())
        companies.append(
            CompanyRatiosOut(
                ticker=ticker,
                cik=full.company.cik,
                name=full.company.name,
                price=c.price,
                periods=[_period_out(p) for p in shown.periods],
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
        ratios=[_ratio_out(r, bases, req.frequency) for r in RATIOS],
        models=[_ratio_out(r, bases, req.frequency) for r in MODELS],
    )


# --- Drill-down -------------------------------------------------------------------

RATIOS_BY_ID = {r.id: r for r in (*RATIOS, *MODELS)}


class InputsRequest(BaseModel):
    ticker: Annotated[str, BeforeValidator(_normalize_ticker), check(lambda v: v != "", "Enter a ticker.")]
    ratio: Annotated[str, check(lambda v: v in RATIOS_BY_ID, "Unknown ratio.")]
    period: str  # the period id (its end date), as in the ratio's metric id
    frequency: Frequency = "annual"
    price: Annotated[float | None, check(lambda v: v > 0, "Price must be greater than 0.")] = None
    source: Literal["sec_edgar"] = "sec_edgar"


class SourceOut(BaseModel):
    """One statement cell: its value and the filing it came from (None when missing)."""

    period_id: str
    period_label: str
    value: float | None
    reason: str | None
    form: str | None
    filed: date | None
    accession: str | None
    url: str | None
    tag: str | None
    derived_from: str | None


class InputOut(BaseModel):
    item: str
    label: str
    unit: str  # envelope unit: currency, per_share, shares
    period_id: str
    period_label: str
    value: float | None
    reason: str | None
    basis: Literal["reported", "ttm"]  # ttm: the sum of the four quarters in ``sources``
    sources: list[SourceOut]


class InputsEnvelope(ResultEnvelope):
    """The ratio's metric (``"<ratio>:<TICKER>:<period>"``) and every statement
    value it read, in reading order, each with the filings it came from."""

    company: CompanyRatiosOut
    ratio: RatioOut
    period: PeriodOut
    inputs: list[InputOut]


def _source_out(s: Source) -> SourceOut:
    cell = s.cell
    if isinstance(cell, Missing):
        return SourceOut(
            period_id=s.period.id,
            period_label=s.period.label,
            value=None,
            reason=cell.message,
            form=None,
            filed=None,
            accession=None,
            url=None,
            tag=None,
            derived_from=None,
        )
    f = cell.filing
    return SourceOut(
        period_id=s.period.id,
        period_label=s.period.label,
        value=cell.value,
        reason=None,
        form=f.form,
        filed=f.filed,
        accession=f.accession,
        url=f.url,
        tag=cell.tag,
        derived_from=cell.derived_from,
    )


@router.post("/ratios/inputs")
def ratio_inputs(req: InputsRequest, data: Data, ctx: Ctx) -> InputsEnvelope:
    """The drill-down behind one ratio value: its inputs and their filings."""
    try:
        full = data.statements(ctx, req.ticker, source=req.source, frequency=req.frequency)
    except NoSuchData as exc:
        message = exc.missing.get(req.ticker, exc.message)
        raise ApiError(422, "no_such_data", message, {"ticker": message}) from exc
    index = next((i for i, p in enumerate(full.periods) if p.id == req.period), None)
    if index is None:
        message = f"{full.company.ticker} has no {req.frequency} period ending {req.period}."
        raise ApiError(422, "validation_error", message, {"period": message})

    r = RATIOS_BY_ID[req.ratio]
    trace = Trace()
    periods = Periods(full, req.frequency, req.price, trace)
    result, basis = _compute(r, periods.years[index], periods, trace)
    period = full.periods[index]
    ticker = full.company.ticker
    base = envelope(
        tool=TOOL,
        request=req,
        metrics={f"{r.id}:{ticker}:{period.id}": result},
        source=full.source,
        data_cutoff=max(p.filed for p in full.periods),
    )
    return InputsEnvelope(
        **base.model_dump(),
        company=CompanyRatiosOut(
            ticker=ticker, cik=full.company.cik, name=full.company.name, price=req.price, periods=[_period_out(period)]
        ),
        ratio=RatioOut(id=r.id, category=r.category, unit=r.unit, basis=basis),
        period=_period_out(period),
        inputs=[
            InputOut(
                item=i.item_id,
                label=i.label,
                unit=UNITS.get(full.item(i.item_id).unit, full.item(i.item_id).unit),
                period_id=i.period.id,
                period_label=i.period.label,
                value=i.value,
                reason=i.reason,
                basis="ttm" if i.ttm else "reported",
                sources=[_source_out(s) for s in i.sources],
            )
            for i in periods.inputs(trace)
        ],
    )
