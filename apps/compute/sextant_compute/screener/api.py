"""Screener & Calendar (P7) endpoints: fundamental screen and latest SEC filings.

The screen runs on calendar-aligned EDGAR frames (one value per company and
year, see ``data/cross_section.py``) mapped onto the unified line items. A
company missing an input of any criterion is excluded, and the response says
how many were excluded per criterion and why.

Price criteria (52-week change, distance from the 52-week high) are My data
only: they need ``price_source`` naming the user's own provider, which runs on
their key and caches in their own cache (``DataService``). Prices are fetched
only for the companies that pass the fundamental criteria, at most
``MAX_PRICED`` of them, since a personal key has a small request quota.
Market cap and P/E stay absent.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, BeforeValidator, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from sextant_compute.analytics.screener import METRICS, PRICE_METRICS, PRICE_WINDOW_DAYS, items_for
from sextant_compute.data.cross_section import CrossSection
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import Ctx, Data
from sextant_compute.data.sources import DEMO_SOURCE, PriceSource
from sextant_compute.envelope import DataSource, MetricError, MissingData, ResultEnvelope, envelope
from sextant_compute.errors import INPUT_ERROR, ApiError, check

router = APIRouter(tags=["screener"])

TOOL = "screener"
MAX_CRITERIA = 8
MAX_ROWS = 500
MAX_PRICED = 25  # companies priced per screen (each is one request on the user's key)
FIRST_YEAR = 2009  # XBRL frames start around 2009
# Test-only overrides (tests pin them to the recorded fixtures): the default
# year, and the day the 52-week price window ends (otherwise today).
DEFAULT_YEAR_ENV = "SCREENER_DEFAULT_YEAR"
PRICES_AS_OF_ENV = "SCREENER_PRICES_AS_OF"

FundamentalMetricId = Literal[
    "revenue",
    "revenue_growth",
    "gross_margin",
    "operating_margin",
    "net_margin",
    "roe",
    "debt_ratio",
    "current_ratio",
]
PriceMetricId = Literal["change_52w", "from_52w_high"]
MetricId = FundamentalMetricId | PriceMetricId
FilingForm = Literal["", "10-K", "10-Q", "8-K", "4", "S-1", "DEF 14A", "20-F", "6-K"]


def default_year(today: date | None = None) -> int:
    """The latest calendar year whose annual reports are (nearly) all filed:
    10-Ks for December year ends are due by the end of March."""
    pinned = os.environ.get(DEFAULT_YEAR_ENV)
    if pinned:
        return int(pinned)
    today = today or date.today()
    return today.year - 1 if (today.month, today.day) >= (4, 1) else today.year - 2


def prices_as_of() -> date:
    pinned = os.environ.get(PRICES_AS_OF_ENV)
    return date.fromisoformat(pinned) if pinned else date.today()


class Criterion(BaseModel):
    metric: MetricId
    op: Literal["min", "max"]
    # Decimal for percentages (0.1 = 10%), USD for revenue, a multiple for ratios.
    value: float


DEFAULT_CRITERIA = [
    Criterion(metric="revenue_growth", op="min", value=0.10),
    Criterion(metric="gross_margin", op="min", value=0.40),
    Criterion(metric="roe", op="min", value=0.15),
]

SortColumn = Literal["ticker", "name"] | MetricId


def _columns(criteria: list[Criterion]) -> list[str]:
    return list(dict.fromkeys(["revenue", *(c.metric for c in criteria)]))


class ScreenRequest(BaseModel):
    year: int | None = None
    criteria: Annotated[
        list[Criterion],
        check(lambda v: len(v) <= MAX_CRITERIA, f"Use at most {MAX_CRITERIA} criteria."),
    ] = DEFAULT_CRITERIA
    sort: SortColumn = "revenue"
    direction: Literal["asc", "desc"] = "desc"
    limit: Annotated[int, check(lambda v: 1 <= v <= MAX_ROWS, f"Show between 1 and {MAX_ROWS} rows.")] = 100
    source: Literal["sec_edgar"] = "sec_edgar"
    price_source: PriceSource | None = None
    """The user's own price provider (My data, e.g. ``"tiingo"``); needed by price criteria."""

    @field_validator("price_source")
    @classmethod
    def _price_source_is_my_data(cls, v: str | None) -> str | None:
        if v == DEMO_SOURCE:
            raise PydanticCustomError(INPUT_ERROR, "Price criteria use My data: real prices from your own provider.")
        return v

    @field_validator("year")
    @classmethod
    def _year_in_range(cls, v: int | None) -> int | None:
        if v is not None and not FIRST_YEAR <= v <= date.today().year:
            raise PydanticCustomError(INPUT_ERROR, f"Choose a year between {FIRST_YEAR} and {date.today().year}.")
        return v

    @field_validator("sort")
    @classmethod
    def _sort_is_a_column(cls, v: str, info: ValidationInfo) -> str:
        criteria = info.data.get("criteria")
        if v not in ("ticker", "name") and criteria is not None and v not in _columns(criteria):
            raise PydanticCustomError(INPUT_ERROR, "Sort by one of the columns shown.")
        return v


class ColumnOut(BaseModel):
    id: str
    label: str
    unit: str


class RowOut(BaseModel):
    ticker: str
    cik: int
    name: str
    period_end: date | None  # the company's fiscal year end behind the frame (from revenue)
    values: dict[str, float | None]


class ReasonCount(BaseModel):
    reason: str
    count: int


class ExclusionOut(BaseModel):
    metric: str
    label: str
    count: int
    reasons: list[ReasonCount]


class ExcludedOut(BaseModel):
    total: int
    by_criterion: list[ExclusionOut]


class ScreenEnvelope(ResultEnvelope):
    """The standard envelope (no metrics) plus the screen: ``universe`` companies
    screened, ``matched`` passing every criterion (``rows`` holds the first
    ``limit`` of them in sort order), ``excluded`` lacking an input."""

    year: int
    default_year: int  # the year a request without ``year`` screens
    frames: dict[str, str]
    criteria: list[Criterion]
    columns: list[ColumnOut]
    rows: list[RowOut]
    universe: int
    matched: int
    excluded: ExcludedOut
    price_source: DataSource | None  # set when the screen has price criteria
    prices_as_of: date | None  # the newest close behind the price columns


def _label(metric: str) -> str:
    return PRICE_METRICS[metric].label if metric in PRICE_METRICS else METRICS[metric].label


def _unit(metric: str) -> str:
    return PRICE_METRICS[metric].unit if metric in PRICE_METRICS else METRICS[metric].unit


def _passes(value: float, c: Criterion) -> bool:
    return value >= c.value if c.op == "min" else value <= c.value


@router.post("/screen")
def screen(req: ScreenRequest, data: Data, ctx: Ctx) -> ScreenEnvelope:
    year = req.year if req.year is not None else default_year()
    columns = _columns(req.criteria)
    fundamental_columns = [c for c in columns if c in METRICS]
    price_criteria = [c for c in req.criteria if c.metric in PRICE_METRICS]
    if price_criteria:
        if req.price_source is None:
            fields = {
                f"criteria.{i}.metric": PRICE_CRITERIA_NEED_MY_DATA
                for i, c in enumerate(req.criteria)
                if c.metric in PRICE_METRICS
            }
            raise ApiError(422, "validation_error", PRICE_CRITERIA_NEED_MY_DATA, fields)
        data.require_key(ctx, req.price_source)  # before any work, so the answer never depends on the data

    needed = items_for(fundamental_columns)
    sections: dict[tuple[str, int], CrossSection] = {}
    for offset, item_ids in sorted(needed.items(), reverse=True):
        for item_id, section in data.cross_sections(ctx, item_ids, year + offset, source=req.source).items():
            sections[(item_id, offset)] = section

    # Universe: every listed company with any current-year input.
    names: dict[int, tuple[str, str]] = {}
    for (_, offset), section in sections.items():
        if offset == 0:
            for cik, v in section.values.items():
                names.setdefault(cik, (v.ticker, v.name))

    excluded_by: dict[str, dict[str, int]] = {c: {} for c in dict.fromkeys(c.metric for c in req.criteria)}
    excluded: set[int] = set()

    def exclude(cik: int, reasons: dict[str, str]) -> None:
        excluded.add(cik)
        for m, reason in reasons.items():
            excluded_by[m][reason] = excluded_by[m].get(reason, 0) + 1

    # Fundamentals first: only companies passing them are priced.
    candidates: list[RowOut] = []
    for cik, (ticker, name) in names.items():

        def get(item_id: str, offset: int, cik: int = cik) -> float:
            section = sections[(item_id, offset)]
            hit = section.values.get(cik)
            if hit is None:
                raise MissingData(f"{section.label} is not reported for {year + offset}.")
            return hit.value

        values: dict[str, float | None] = {}
        reasons: dict[str, str] = {}
        for col in fundamental_columns:
            try:
                values[col] = METRICS[col].compute(get)
            except (MissingData, MetricError) as exc:
                values[col] = None
                reasons[col] = str(exc)
        missing = {m: reasons[m] for m in excluded_by if m in reasons}
        if missing:
            exclude(cik, missing)
            continue
        if all(_passes(values[c.metric], c) for c in req.criteria if c.metric in METRICS):  # type: ignore[arg-type]
            revenue = sections[("revenue", 0)].values.get(cik)
            candidates.append(
                RowOut(ticker=ticker, cik=cik, name=name, period_end=revenue.end if revenue else None, values=values)
            )

    rows = candidates
    price_source: DataSource | None = None
    last_close: date | None = None
    if price_criteria:
        assert req.price_source is not None
        rows, price_source, last_close = _apply_price_criteria(req, data, ctx, columns, candidates, exclude)

    _sort(rows, req.sort, req.direction)
    ends = [v.end for s in sections.values() for v in s.values.values()]
    base = envelope(tool=TOOL, request=req, metrics={}, source=data.source_info(req.source), data_cutoff=max(ends, default=None))
    return ScreenEnvelope(
        **base.model_dump(),
        year=year,
        default_year=default_year(),
        frames={"flow": f"CY{year}", "balance": f"CY{year}Q4I"},
        criteria=req.criteria,
        columns=[ColumnOut(id=c, label=_label(c), unit=_unit(c)) for c in columns],
        rows=rows[: req.limit],
        universe=len(names),
        matched=len(rows),
        excluded=ExcludedOut(
            total=len(excluded),
            by_criterion=[
                ExclusionOut(
                    metric=m,
                    label=_label(m),
                    count=sum(counts.values()),
                    reasons=[ReasonCount(reason=r, count=n) for r, n in sorted(counts.items(), key=lambda kv: -kv[1])],
                )
                for m, counts in excluded_by.items()
            ],
        ),
        price_source=price_source,
        prices_as_of=last_close,
    )


PRICE_CRITERIA_NEED_MY_DATA = "Price criteria need My data: sign in and add a price data key in Settings."


def _apply_price_criteria(
    req: ScreenRequest,
    data: Data,
    ctx: Ctx,
    columns: list[str],
    candidates: list[RowOut],
    exclude: Callable[[int, dict[str, str]], None],
) -> tuple[list[RowOut], DataSource, date | None]:
    """Price the fundamental matches on the user's own provider and keep those
    passing every price criterion. A company the provider can't price (or whose
    history is shorter than 52 weeks) is excluded with the reason."""
    assert req.price_source is not None
    if len(candidates) > MAX_PRICED:
        message = (
            f"Price criteria check at most {MAX_PRICED} companies, and {len(candidates)} pass the "
            "fundamental criteria. Tighten them first."
        )
        raise ApiError(422, "validation_error", message, {"criteria": message})
    as_of = prices_as_of()
    window_start = as_of - timedelta(days=PRICE_WINDOW_DAYS)
    # A week of lookback, so the close on (or last before) the window's first day is in range.
    prices = data.daily_prices(
        ctx,
        [r.ticker for r in candidates],
        window_start - timedelta(days=7),
        as_of,
        source=req.price_source,
        partial=True,
    )
    price_columns = [c for c in columns if c in PRICE_METRICS]
    price_criteria = [c for c in req.criteria if c.metric in PRICE_METRICS]
    rows: list[RowOut] = []
    for row in candidates:
        reasons: dict[str, str] = {}
        if row.ticker in prices.missing:
            reasons = {c.metric: prices.missing[row.ticker] for c in price_criteria}
        else:
            closes = prices.frames[row.ticker]["close"]
            for col in price_columns:
                try:
                    row.values[col] = PRICE_METRICS[col].compute(closes, window_start)
                except (MissingData, MetricError) as exc:
                    row.values[col] = None
                    reasons[col] = str(exc)
            reasons = {c.metric: reasons[c.metric] for c in price_criteria if c.metric in reasons}
        if reasons:
            exclude(row.cik, reasons)
        elif all(_passes(row.values[c.metric], c) for c in price_criteria):  # type: ignore[arg-type]
            rows.append(row)
    return rows, prices.source, prices.last_date


def _sort(rows: list[RowOut], column: str, direction: str) -> None:
    """In place; ties by ticker; rows without a value for ``column`` go last."""
    rows.sort(key=lambda r: r.ticker)
    if column in ("ticker", "name"):
        rows.sort(key=lambda r: getattr(r, column).casefold(), reverse=direction == "desc")
        return
    present = [r for r in rows if r.values.get(column) is not None]
    absent = [r for r in rows if r.values.get(column) is None]
    present.sort(key=lambda r: r.values[column], reverse=direction == "desc")  # type: ignore[arg-type,return-value]
    rows[:] = present + absent


# --- Latest SEC filings -------------------------------------------------------


def _normalize_ticker(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


class FilingsRequest(BaseModel):
    """``ticker`` "" lists the newest filings market-wide."""

    ticker: Annotated[str, BeforeValidator(_normalize_ticker)] = ""
    form: FilingForm = ""
    limit: Annotated[int, check(lambda v: 1 <= v <= 100, "Show between 1 and 100 filings.")] = 40
    source: Literal["sec_edgar"] = "sec_edgar"


class FilingOut(BaseModel):
    form: str
    title: str
    company: str
    cik: int
    filed: date
    accession: str
    url: str


class FilingsEnvelope(ResultEnvelope):
    scope: Literal["market", "company"]
    company: str | None
    filings: list[FilingOut]


def _form_matches(form: str, wanted: str) -> bool:
    return not wanted or form == wanted or form.startswith(f"{wanted}/")


@router.post("/filings")
def filings(req: FilingsRequest, data: Data, ctx: Ctx) -> FilingsEnvelope:
    if req.ticker:
        try:
            found = data.company_filings(ctx, req.ticker, source=req.source)
        except NoSuchData as exc:
            message = exc.missing.get(req.ticker, exc.message)
            raise ApiError(422, "no_such_data", message, {"ticker": message}) from exc
    else:
        found = data.latest_filings(ctx, req.form, source=req.source)
    rows = [f for f in found.filings if _form_matches(f.form, req.form)][: req.limit]
    base = envelope(
        tool=TOOL,
        request=req,
        metrics={},
        source=data.source_info(req.source),
        data_cutoff=max((f.filed for f in rows), default=None),
    )
    return FilingsEnvelope(
        **base.model_dump(),
        scope="company" if req.ticker else "market",
        company=found.company,
        filings=[FilingOut(**f.__dict__) for f in rows],
    )
