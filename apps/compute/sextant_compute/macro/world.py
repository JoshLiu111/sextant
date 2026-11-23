"""Macro Dashboard (P5) beyond the US: the cross-country comparison (World Bank)
and the euro area (ECB)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter
from pydantic import BaseModel, BeforeValidator, field_validator

from sextant_compute.analytics import macro
from sextant_compute.data.adapters import CountryIndicator, EconomicSeries
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import Ctx, Data
from sextant_compute.envelope import (
    Detail,
    Detailed,
    MetricResult,
    MissingData,
    ResultEnvelope,
    SeriesResult,
    envelope,
    metric,
    series,
)
from sextant_compute.errors import check
from sextant_compute.request_models import EndOnOrAfterStart

router = APIRouter(tags=["macro"])

TOOL = "macro"

# --- Cross-country comparison: World Bank WDI --------------------------------

# Economies a visitor can pick (ISO 3166-1 alpha-3; EMU is the World Bank's euro
# area aggregate). Every request fetches all of them, so any selection is a cache hit.
# The web picker (apps/web/src/app/macro/countries.ts) lists the same codes.
COUNTRIES = (
    "ARG", "AUS", "BRA", "CAN", "CHN", "DEU", "EMU", "ESP", "FRA",
    "GBR", "IND", "ITA", "JPN", "KOR", "MEX", "USA", "ZAF",
)  # fmt: skip
DEFAULT_COUNTRIES = ["USA", "DEU", "JPN", "GBR"]
MAX_COUNTRIES = 6
FIRST_YEAR = 1960  # WDI's first year


@dataclass(frozen=True)
class CountryIndicatorSpec:
    key: str
    indicator_id: str


# Annual, all in percent.
COMPARISON = [
    CountryIndicatorSpec("gdp_growth", "NY.GDP.MKTP.KD.ZG"),
    CountryIndicatorSpec("inflation", "FP.CPI.TOTL.ZG"),
    CountryIndicatorSpec("unemployment_rate", "SL.UEM.TOTL.ZS"),
]


def _country_code(value: object) -> object:
    return value.strip().upper() if isinstance(value, str) else value


CountryCode = Annotated[
    str,
    BeforeValidator(_country_code),
    check(lambda v: v in COUNTRIES, "Choose one of the listed countries."),
]


class CountriesRequest(BaseModel):
    countries: Annotated[
        list[CountryCode],
        check(lambda v: 1 <= len(v) <= MAX_COUNTRIES, f"Choose between 1 and {MAX_COUNTRIES} countries."),
    ] = DEFAULT_COUNTRIES
    start_year: Annotated[
        int, check(lambda v: FIRST_YEAR <= v <= datetime.now(UTC).year, f"World Bank data starts in {FIRST_YEAR}.")
    ] = 2000
    source: Literal["world_bank"] = "world_bank"

    @field_validator("countries", mode="after")
    @classmethod
    def _dedupe(cls, countries: list[str]) -> list[str]:
        return list(dict.fromkeys(countries))


def _country_values(found: CountryIndicator | NoSuchData, country: str):
    if isinstance(found, NoSuchData):
        raise MissingData(found.message)
    values = found.countries.get(country)
    if values is None or values.latest is None:
        name = values.name if values else country
        raise MissingData(f"The World Bank has no {found.meta.title} data for {name} in the range.")
    return found.meta, values


def _country_latest(found: CountryIndicator | NoSuchData, country: str) -> Detailed:
    meta, values = _country_values(found, country)
    year, value = values.latest  # type: ignore[misc]
    details: dict[str, Detail] = {
        "year": year,
        "country": country,
        "country_name": values.name,
        "indicator_id": meta.id,
        "title": meta.title,
        "source": meta.source,
        "units": meta.units,
        "frequency": meta.frequency,
        "last_updated": meta.last_updated,
    }
    return Detailed(value, details)


def _country_history(found: CountryIndicator | NoSuchData, country: str) -> list[tuple[float | str, float | None]]:
    _, values = _country_values(found, country)
    return [(year, value) for year, value in values.observations]


@router.post("/countries")
def compare_countries(req: CountriesRequest, data: Data, ctx: Ctx) -> ResultEnvelope:
    """GDP growth, inflation and unemployment for the selected economies, from the
    World Bank's World Development Indicators (annual, percent).
    Metrics ``latest:<indicator>:<ISO3>`` (details: year, country name, series
    metadata); series ``history:<indicator>:<ISO3>`` (x = calendar year).
    A World Bank outage (``SourceUnavailable``) fails the request with 503."""
    end_year = datetime.now(UTC).year
    metrics: dict[str, MetricResult] = {}
    charts: dict[str, SeriesResult] = {}
    latest_years: list[int] = []
    for spec in COMPARISON:
        found: CountryIndicator | NoSuchData
        try:
            found = data.country_indicator(
                ctx, spec.indicator_id, COUNTRIES, start_year=req.start_year, end_year=end_year, source=req.source
            )
        except NoSuchData as exc:
            found = exc
        for country in req.countries:
            if isinstance(found, CountryIndicator) and (c := found.countries.get(country)) and c.latest:
                latest_years.append(c.latest[0])
            metrics[f"latest:{spec.key}:{country}"] = metric(
                lambda found=found, country=country: _country_latest(found, country), unit="percent"
            )
            charts[f"history:{spec.key}:{country}"] = series(
                lambda found=found, country=country: _country_history(found, country), x_unit="year", y_unit="percent"
            )
    return envelope(
        tool=TOOL,
        request=req,
        metrics=metrics,
        series=charts,
        source=data.source_info(req.source),
        data_cutoff=date(max(latest_years), 12, 31) if latest_years else None,
    )


# --- Euro area: ECB key interest rates and HICP -------------------------------

EURO_START = date(2015, 1, 1)
ECB_FIRST = date(1999, 1, 1)  # the euro and the ECB's key rates start here


@dataclass(frozen=True)
class EuroSeries:
    key: str
    series_id: str
    is_rate: bool
    """A key ECB rate (a list of changes) rather than a monthly series."""


EURO_AREA = [
    EuroSeries("deposit_facility_rate", "FM/B.U2.EUR.4F.KR.DFR.LEV", is_rate=True),
    EuroSeries("main_refinancing_rate", "FM/B.U2.EUR.4F.KR.MRR_FR.LEV", is_rate=True),
    EuroSeries("marginal_lending_rate", "FM/B.U2.EUR.4F.KR.MLFR.LEV", is_rate=True),
    EuroSeries("hicp_inflation", "HICP/M.U2.N.000000.4D0.ANR", is_rate=False),
]


class EuroAreaRequest(EndOnOrAfterStart):
    start: Annotated[date, check(lambda v: v >= ECB_FIRST, "ECB data starts on 1999-01-01.")] = EURO_START
    """First day of the histories."""
    end: date | None = None
    """Last day considered (default: today, UTC)."""
    source: Literal["ecb"] = "ecb"


def _series_details(found: EconomicSeries) -> dict[str, Detail]:
    m = found.meta
    return {
        "series_id": m.id,
        "title": m.title,
        "source": m.source,
        "units": m.units,
        "frequency": m.frequency,
        "seasonal_adjustment": m.seasonal_adjustment,
        "last_updated": m.last_updated,
    }


def _ecb_series(found: EconomicSeries | NoSuchData) -> EconomicSeries:
    if isinstance(found, NoSuchData):
        raise MissingData(found.message)
    return found


def _in_range(s: EconomicSeries, start: date, end: date) -> Sequence[tuple[date, float | None]]:
    return [(when, value) for when, value in s.observations if start <= when <= end]


def _rate_latest(found: EconomicSeries | NoSuchData, end: date) -> Detailed:
    s = _ecb_series(found)
    current = macro.in_force(s.observations, end)
    if current is None:
        raise MissingData(f"No {s.meta.title} on or before {end.isoformat()}.")
    when, value = current
    return Detailed(value, {"date": when.isoformat(), **_series_details(s)})


def _rate_history(found: EconomicSeries | NoSuchData, start: date, end: date) -> list[tuple[float | str, float | None]]:
    steps = macro.step_path(_ecb_series(found).observations, start, end)
    if not steps:
        raise MissingData(f"No ECB rate in force between {start.isoformat()} and {end.isoformat()}.")
    return [(when.isoformat(), value) for when, value in steps]


def _monthly_latest(found: EconomicSeries | NoSuchData, end: date) -> Detailed:
    s = _ecb_series(found)
    observed = [(when, value) for when, value in s.observations if when <= end and value is not None]
    if not observed:
        raise MissingData(f"No {s.meta.title} on or before {end.isoformat()}.")
    when, value = observed[-1]
    return Detailed(value, {"date": when.isoformat()[:7], **_series_details(s)})


def _monthly_history(
    found: EconomicSeries | NoSuchData, start: date, end: date
) -> list[tuple[float | str, float | None]]:
    points = _in_range(_ecb_series(found), start, end)
    if not points:
        raise MissingData(f"No observations between {start.isoformat()} and {end.isoformat()}.")
    return [(when.isoformat(), value) for when, value in points]


def _month_end(d: date) -> date:
    return date(d.year + d.month // 12, d.month % 12 + 1, 1) - timedelta(days=1)


@router.post("/euro-area")
def euro_area(req: EuroAreaRequest, data: Data, ctx: Ctx) -> ResultEnvelope:
    """The key ECB interest rates (deposit facility, main refinancing operations,
    marginal lending facility) and euro area HICP inflation, from the ECB Data Portal.
    Metrics ``latest:<key>`` (percent; rates: details.date = when the rate took
    effect; HICP: details.date = the month, ``YYYY-MM``). Series ``history:<key>``
    (x = date; rates as step lines). An ECB outage fails the request with 503."""
    end = req.end or datetime.now(UTC).date()
    metrics: dict[str, MetricResult] = {}
    charts: dict[str, SeriesResult] = {}
    cutoffs: list[date] = []
    for spec in EURO_AREA:
        found: EconomicSeries | NoSuchData
        try:
            # Rates: the whole change history (cached once), to know the rate in force at ``start``.
            fetch_from = ECB_FIRST if spec.is_rate else req.start
            found = data.economic_series(ctx, spec.series_id, start=fetch_from, source=req.source)
        except NoSuchData as exc:
            found = exc
        latest, history = (_rate_latest, _rate_history) if spec.is_rate else (_monthly_latest, _monthly_history)
        metrics[f"latest:{spec.key}"] = metric(lambda f=found, latest=latest: latest(f, end), unit="percent")
        charts[f"history:{spec.key}"] = series(
            lambda f=found, history=history: history(f, req.start, end), x_unit="date", y_unit="percent"
        )
        if not spec.is_rate and isinstance(found, EconomicSeries) and (observed := _in_range(found, req.start, end)):
            cutoffs.append(_month_end(observed[-1][0]))
    return envelope(
        tool=TOOL,
        request=req,
        metrics=metrics,
        series=charts,
        source=data.source_info(req.source),
        data_cutoff=max(cutoffs) if cutoffs else None,
    )
