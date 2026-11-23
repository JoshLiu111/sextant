"""Company Health Check (P1) endpoints: standardized financial statements.

``frequency``: ``annual`` (default; the ``years`` most recent fiscal years) or
``quarterly`` (the ``quarters`` most recent fiscal quarters, labelled
"Q2 FY2026"; Q4 flows are the year minus the first three quarters)."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, BeforeValidator

from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import Ctx, Data
from sextant_compute.data.statements import FinancialStatements, Frequency, Missing
from sextant_compute.envelope import MetricResult, MetricStatus, ResultEnvelope, envelope
from sextant_compute.errors import ApiError, check

router = APIRouter(tags=["company"])

TOOL = "company"
MAX_YEARS = 10
MAX_QUARTERS = 20
# XBRL unit -> envelope unit.
UNITS = {"USD": "currency", "USD/shares": "per_share", "shares": "shares"}


def _normalize_ticker(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


class StatementsRequest(BaseModel):
    ticker: Annotated[str, BeforeValidator(_normalize_ticker), check(lambda v: v != "", "Enter a ticker.")] = "AAPL"
    years: Annotated[
        int, check(lambda v: 1 <= v <= MAX_YEARS, f"Choose between 1 and {MAX_YEARS} years.")
    ] = 5
    frequency: Frequency = "annual"
    quarters: Annotated[
        int, check(lambda v: 1 <= v <= MAX_QUARTERS, f"Choose between 1 and {MAX_QUARTERS} quarters.")
    ] = 8
    source: Literal["sec_edgar"] = "sec_edgar"

    def periods(self) -> int:
        """How many recent periods to show: ``years``, or ``quarters`` when quarterly."""
        return self.quarters if self.frequency == "quarterly" else self.years


class CompanyOut(BaseModel):
    ticker: str
    cik: int
    name: str


class PeriodOut(BaseModel):
    id: str
    label: str
    fiscal_year: int
    fiscal_quarter: int | None
    start: date | None
    end: date
    filed: date
    form: str
    accession: str
    url: str


class ItemOut(BaseModel):
    id: str
    label: str
    statement: Literal["income", "balance", "cash_flow"]
    unit: str
    display: bool


class StatementsEnvelope(ResultEnvelope):
    """The standard envelope plus the grid layout. Each cell is metric
    ``"<item id>:<period id>"``; ok cells carry their filing in ``details``
    (form, filed, accession, url, tag, derived_from), missing ones
    ``details.missing`` (``not_reported`` | ``not_reported_for_period``)."""

    company: CompanyOut
    periods: list[PeriodOut]
    items: list[ItemOut]


def statement_metrics(statements: FinancialStatements) -> dict[str, MetricResult]:
    out: dict[str, MetricResult] = {}
    for item in statements.items:
        unit = UNITS.get(item.unit, item.unit)
        for period in statements.periods:
            cell = statements.cell(item.id, period.id)
            key = f"{item.id}:{period.id}"
            if isinstance(cell, Missing):
                out[key] = MetricResult(
                    value=None,
                    status=MetricStatus.MISSING_DATA,
                    reason=cell.message,
                    unit=unit,
                    details={"missing": cell.reason},
                )
            else:
                out[key] = MetricResult(
                    value=cell.value,
                    status=MetricStatus.OK,
                    unit=unit,
                    details={
                        "form": cell.filing.form,
                        "filed": cell.filing.filed.isoformat(),
                        "accession": cell.filing.accession,
                        "url": cell.filing.url,
                        "tag": cell.tag,
                        "derived_from": cell.derived_from,
                    },
                )
    return out


@router.post("/statements")
def statements(req: StatementsRequest, data: Data, ctx: Ctx) -> StatementsEnvelope:
    try:
        full = data.statements(ctx, req.ticker, source=req.source, frequency=req.frequency)
    except NoSuchData as exc:
        message = exc.missing.get(req.ticker, exc.message)
        raise ApiError(422, "no_such_data", message, {"ticker": message}) from exc
    st = full.last(req.periods())
    base = envelope(
        tool=TOOL,
        request=req,
        metrics=statement_metrics(st),
        source=st.source,
        data_cutoff=max(p.filed for p in st.periods),
    )
    return StatementsEnvelope(
        **base.model_dump(),
        company=CompanyOut(ticker=st.company.ticker, cik=st.company.cik, name=st.company.name),
        periods=[
            PeriodOut(
                id=p.id,
                label=p.label,
                fiscal_year=p.fiscal_year,
                fiscal_quarter=p.fiscal_quarter,
                start=p.start,
                end=p.end,
                filed=p.filed,
                form=p.filing.form,
                accession=p.filing.accession,
                url=p.filing.url,
            )
            for p in st.periods
        ],
        items=[ItemOut(**i.__dict__) for i in st.items],
    )
