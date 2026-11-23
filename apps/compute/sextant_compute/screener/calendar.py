"""Screener & Calendar (P7) endpoints: earnings calendar and dividend history.

Earnings calendar: an earnings release is an 8-K (or 8-K/A) carrying Item 2.02
"Results of Operations and Financial Condition", read from each company's
submissions list. EDGAR has no market-wide item filter, so the calendar covers a
list of companies (``CALENDAR_TICKERS`` by default, or the visitor's own).
Upcoming dates are estimates: a company's release 52 weeks after last year's
same-quarter release, unless it has already reported within ``EARLY_WINDOW``
before that date. Each expected row links to the 8-K it was projected from.

Dividend history: declared per-share dividends by fiscal quarter and year from
the company's XBRL filings (``data/edgar/dividends.py``).
"""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, BeforeValidator, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.filings import FilingEntry, FilingList
from sextant_compute.data.service import Ctx, Data
from sextant_compute.envelope import ResultEnvelope, envelope
from sextant_compute.errors import INPUT_ERROR, ApiError, check

router = APIRouter(tags=["screener"])

TOOL = "screener"
# Large US companies across sectors; the recorded fixtures cover exactly these.
CALENDAR_TICKERS = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "JPM",
    "V", "WMT", "PG", "JNJ", "KO", "XOM", "NFLX",
)  # fmt: skip
MAX_TICKERS = 20
MAX_RANGE_DAYS = 366
DEFAULT_BACK = timedelta(days=30)
DEFAULT_AHEAD = timedelta(days=60)
EARNINGS_ITEM = "2.02"
YEAR_LATER = timedelta(weeks=52)  # keeps the weekday
EARLY_WINDOW = timedelta(days=30)
FETCH_WORKERS = 4  # the shared EDGAR rate limiter paces the requests
# Test-only override of "today" (the recorded submissions end in November 2026).
TODAY_ENV = "SCREENER_TODAY"


def today() -> date:
    pinned = os.environ.get(TODAY_ENV)
    return date.fromisoformat(pinned) if pinned else date.today()


def _tickers(value: object) -> object:
    """Accepts a list or a comma/space separated string; upper case, deduplicated."""
    if isinstance(value, str):
        value = value.replace(",", " ").split()
    if isinstance(value, list | tuple):
        return list(dict.fromkeys(str(t).strip().upper() for t in value if str(t).strip()))
    return value


class EarningsRequest(BaseModel):
    """``start``/``end`` default to 30 days back and 60 days ahead of today."""

    tickers: Annotated[
        list[str],
        BeforeValidator(_tickers),
        check(lambda v: 1 <= len(v) <= MAX_TICKERS, f"Enter between 1 and {MAX_TICKERS} tickers."),
    ] = list(CALENDAR_TICKERS)
    start: date | None = None
    end: date | None = None
    source: Literal["sec_edgar"] = "sec_edgar"

    @field_validator("end")
    @classmethod
    def _range(cls, end: date | None, info: ValidationInfo) -> date | None:
        start = info.data.get("start")
        if start and end:
            if start > end:
                raise PydanticCustomError(INPUT_ERROR, "The end date must be on or after the start date.")
            if (end - start).days > MAX_RANGE_DAYS:
                raise PydanticCustomError(INPUT_ERROR, f"Choose a range of at most {MAX_RANGE_DAYS} days.")
        return end


class EarningsEventOut(BaseModel):
    """``reported``: the 8-K filed on ``date``. ``expected``: an estimate; ``url``
    is last year's 8-K (filed ``based_on``) the date was projected from."""

    ticker: str
    company: str
    cik: int
    date: date
    status: Literal["reported", "expected"]
    form: str
    accession: str
    url: str
    based_on: date | None = None


class EarningsEnvelope(ResultEnvelope):
    start: date
    end: date
    as_of: date
    tickers: list[str]
    events: list[EarningsEventOut]


def _is_earnings(f: FilingEntry) -> bool:
    return f.form.split("/")[0] == "8-K" and EARNINGS_ITEM in f.items


def _events(ticker: str, filings: FilingList, start: date, end: date, as_of: date) -> list[EarningsEventOut]:
    releases = [f for f in filings.filings if _is_earnings(f)]
    company = filings.company or (releases[0].company if releases else ticker)
    out: list[EarningsEventOut] = []

    def event(f: FilingEntry, when: date, status: Literal["reported", "expected"]) -> EarningsEventOut:
        return EarningsEventOut(
            ticker=ticker,
            company=company,
            cik=f.cik,
            date=when,
            status=status,
            form=f.form,
            accession=f.accession,
            url=f.url,
            based_on=f.filed if status == "expected" else None,
        )

    for f in releases:
        if start <= f.filed <= end and f.filed <= as_of:
            out.append(event(f, f.filed, "reported"))
        projected = f.filed + YEAR_LATER
        if projected > as_of and start <= projected <= end:
            early = any(projected - EARLY_WINDOW <= r.filed <= as_of for r in releases)
            if not early:
                out.append(event(f, projected, "expected"))
    return out


@router.post("/earnings")
def earnings(req: EarningsRequest, data: Data, ctx: Ctx) -> EarningsEnvelope:
    as_of = today()
    start = req.start or as_of - DEFAULT_BACK
    end = req.end or as_of + DEFAULT_AHEAD
    if start > end:  # one bound given, the other defaulted
        message = "The end date must be on or after the start date."
        raise ApiError(422, "validation_error", message, {"end": message})

    def fetch(ticker: str) -> FilingList | NoSuchData:
        try:
            return data.company_filings(ctx, ticker, source=req.source)
        except NoSuchData as exc:
            return exc

    with ThreadPoolExecutor(max_workers=FETCH_WORKERS) as pool:
        found = dict(zip(req.tickers, pool.map(fetch, req.tickers), strict=True))
    unknown = {t: r.missing.get(t, r.message) for t, r in found.items() if isinstance(r, NoSuchData)}
    if unknown:
        message = " ".join(unknown.values())
        raise ApiError(422, "no_such_data", message, {"tickers": message})

    events = [
        e for t, filings in found.items() if isinstance(filings, FilingList) for e in _events(t, filings, start, end, as_of)
    ]
    events.sort(key=lambda e: (e.date, e.ticker))
    reported = [e.date for e in events if e.status == "reported"]
    base = envelope(
        tool=TOOL,
        request=req,
        metrics={},
        source=data.source_info(req.source),
        data_cutoff=max(reported, default=None),
    )
    return EarningsEnvelope(**base.model_dump(), start=start, end=end, as_of=as_of, tickers=req.tickers, events=events)


# --- Dividend history ---------------------------------------------------------


def _ticker(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


class DividendsRequest(BaseModel):
    ticker: Annotated[str, BeforeValidator(_ticker), check(lambda v: bool(v), "Enter a ticker, e.g. AAPL.")]
    source: Literal["sec_edgar"] = "sec_edgar"


class DividendFilingOut(BaseModel):
    form: str
    filed: date
    accession: str
    url: str


class DividendPeriodOut(BaseModel):
    kind: Literal["quarter", "year"]
    label: str
    fiscal_year: int
    start: date
    end: date
    value: float  # USD per share
    derived: bool  # Q4 = the year less the first nine months
    tag: str
    filing: DividendFilingOut


class CompanyOut(BaseModel):
    ticker: str
    cik: int
    name: str


class DividendsEnvelope(ResultEnvelope):
    """``pays_dividends`` False (no periods) when the filings report no per-share
    dividend; ``note`` then says so."""

    company: CompanyOut
    pays_dividends: bool
    basis: Literal["declared", "paid"] | None
    note: str | None
    periods: list[DividendPeriodOut]


@router.post("/dividends")
def dividends(req: DividendsRequest, data: Data, ctx: Ctx) -> DividendsEnvelope:
    try:
        history = data.dividends(ctx, req.ticker, source=req.source)
    except NoSuchData as exc:
        message = exc.missing.get(req.ticker, exc.message)
        raise ApiError(422, "no_such_data", message, {"ticker": message}) from exc
    company = history.company
    note = (
        None
        if history.periods
        else f"{company.name} ({company.ticker}) has reported no per-share dividends in its XBRL filings."
    )
    base = envelope(
        tool=TOOL,
        request=req,
        metrics={},
        source=data.source_info(req.source),
        data_cutoff=max((p.end for p in history.periods), default=None),
    )
    return DividendsEnvelope(
        **base.model_dump(),
        company=CompanyOut(ticker=company.ticker, cik=company.cik, name=company.name),
        pays_dividends=bool(history.periods),
        basis=history.basis,
        note=note,
        periods=[
            DividendPeriodOut(
                kind=p.kind,
                label=p.label,
                fiscal_year=p.fiscal_year,
                start=p.start,
                end=p.end,
                value=p.value,
                derived=p.derived,
                tag=p.tag,
                filing=DividendFilingOut(
                    form=p.filing.form, filed=p.filing.filed, accession=p.filing.accession, url=p.filing.url
                ),
            )
            for p in history.periods
        ],
    )
