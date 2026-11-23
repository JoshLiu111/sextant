"""What an adapter is: one per data provider, behind ``DataService``.

An adapter declares:

- ``source``: a ``DataSource`` whose ``id``/``name`` are the *real* provider
  (``"sec_edgar"``, ``"fred"``, ``"tiingo"``, ``"synthetic"``). Never label paid or
  user-keyed data as a public source.
- ``scope``: ``"shared"`` for public data (cached for everyone) or ``"user"`` for
  data fetched with the visitor's own key (cached per user, never shared).
- ``ttl``: dataset name -> cache TTL in seconds. A dataset missing here is not cached.
- ``version``: part of every cache key. Bump it when the adapter's output changes
  (new mapping, parser fix, new generator), because cached entries outlive deploys.

and implements the dataset methods it supports (see the protocols below). Each
method takes ``ctx`` first, does its own rate limiting / retries, and raises only
``SourceUnavailable`` or ``NoSuchData`` for provider problems.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

import pandas as pd

from sextant_compute.data.context import RequestContext
from sextant_compute.data.cross_section import CrossSection
from sextant_compute.data.dividends import DividendHistory
from sextant_compute.data.filings import FilingList
from sextant_compute.data.statements import FinancialStatements
from sextant_compute.envelope import DataSource

Scope = Literal["shared", "user"]

PRICE_COLUMNS = ["open", "high", "low", "close", "volume", "dividend"]


class Adapter(Protocol):
    source: DataSource
    scope: Scope
    ttl: Mapping[str, int]
    version: str


class DailyPricesAdapter(Adapter, Protocol):
    def daily_prices(
        self, ctx: RequestContext, tickers: Sequence[str], start: date, end: date
    ) -> dict[str, pd.DataFrame]:
        """One frame per requested ticker: DatetimeIndex ``date`` (trading days within
        [start, end], ascending) and ``PRICE_COLUMNS``. ``dividend`` is the cash
        dividend with that ex-date (0 otherwise); ``close`` is not dividend-adjusted.
        Raises ``NoSuchData`` (``missing`` keyed by ticker) for unknown tickers or an
        empty range."""
        ...


class LatestCloseAdapter(Adapter, Protocol):
    def latest_close(self, ctx: RequestContext, ticker: str) -> tuple[date, float]:
        """The most recent trading day's date and closing price, in today's share
        count (a later split has not happened yet, so the raw close is current).
        Raises ``NoSuchData`` (``missing`` keyed by ticker) for an unknown ticker or
        one without prices."""
        ...


FACTOR_COLUMNS = ["Mkt-RF", "SMB", "HML", "MOM", "RF"]


class DailyFactorsAdapter(Adapter, Protocol):
    def daily_factors(self, ctx: RequestContext, start: date, end: date) -> pd.DataFrame:
        """Daily factor returns in [start, end]: DatetimeIndex ``date`` and
        ``FACTOR_COLUMNS`` as decimals (Fama-French / Carhart layout). Raises
        ``NoSuchData`` for an empty range. Only the synthetic demo source serves
        factors (ADR 0003): Sextant fetches and caches no real factor data."""
        ...


class FinancialStatementsAdapter(Adapter, Protocol):
    def financial_statements(self, ctx: RequestContext, ticker: str) -> FinancialStatements:
        """Standardized annual statements, every fiscal period available, oldest
        first (see ``data/statements.py``). Raises ``NoSuchData`` (``missing`` keyed
        by the ticker as given) for an unknown ticker or a company without
        financial statements."""
        ...

    def quarterly_statements(self, ctx: RequestContext, ticker: str) -> FinancialStatements:
        """The same, by fiscal quarter (``FiscalPeriod.fiscal_quarter`` 1..4)."""
        ...


class CrossSectionsAdapter(Adapter, Protocol):
    def cross_sections(self, ctx: RequestContext, item_ids: Sequence[str], year: int) -> dict[str, CrossSection]:
        """One ``CrossSection`` per requested unified line item for ``year``
        (calendar-aligned, see ``data/cross_section.py``), covering every listed
        company that reported it."""
        ...


class FilingsAdapter(Adapter, Protocol):
    def latest_filings(self, ctx: RequestContext, form: str) -> FilingList:
        """The newest filings market-wide; ``form`` "" means every form type."""
        ...

    def company_filings(self, ctx: RequestContext, ticker: str) -> FilingList:
        """One company's recent filings, newest first. Raises ``NoSuchData``
        (``missing`` keyed by the ticker as given) for an unknown ticker."""
        ...


class DividendsAdapter(Adapter, Protocol):
    def dividends(self, ctx: RequestContext, ticker: str) -> DividendHistory:
        """Per-share dividends by fiscal quarter and year, newest first (see
        ``data/dividends.py``). A company that pays none gets an empty history,
        not an error. Raises ``NoSuchData`` (``missing`` keyed by the ticker as
        given) for an unknown ticker or a company without XBRL data."""
        ...


@dataclass(frozen=True)
class SeriesMeta:
    """What a page must show next to an economic series (spec: source, units,
    frequency, last updated).

    ``source`` is the agency that publishes the data (e.g. "U.S. Bureau of Labor
    Statistics"), not the API it came through. ``units`` describes the values as
    returned, so a transformed series (FRED ``units=pc1``) reports the
    transformation. ``last_updated`` is ISO 8601 with the provider's UTC offset.
    """

    id: str
    title: str
    source: str
    units: str
    frequency: str
    seasonal_adjustment: str
    last_updated: str


@dataclass(frozen=True)
class EconomicSeries:
    """One time series: metadata plus ``(date, value)`` observations, ascending.
    ``None`` is a period the provider has no value for."""

    source: DataSource
    meta: SeriesMeta
    observations: list[tuple[date, float | None]]

    @property
    def latest(self) -> tuple[date, float] | None:
        """The most recent observation that has a value."""
        for when, value in reversed(self.observations):
            if value is not None:
                return when, value
        return None


class EconomicSeriesAdapter(Adapter, Protocol):
    def economic_series(
        self, ctx: RequestContext, series_id: str, start: date, units: str = "lin"
    ) -> EconomicSeries:
        """Metadata and observations from ``start`` on. ``units`` is a provider
        transformation (FRED: ``lin`` as published, ``pc1`` percent change from a
        year ago, ...). Raises ``NoSuchData`` (``missing`` keyed by series id) for
        unknown series and for series we may not republish (copyright)."""
        ...


@dataclass(frozen=True)
class SeriesSummary:
    """One search hit: enough to pick a series before fetching it. ``last_updated``
    is ISO 8601 with the provider's UTC offset, ``observation_end`` an ISO date."""

    id: str
    title: str
    units: str
    frequency: str
    seasonal_adjustment: str
    last_updated: str
    observation_end: str


class SeriesSearchAdapter(Adapter, Protocol):
    def search_series(self, ctx: RequestContext, query: str, limit: int) -> list[SeriesSummary]:
        """Series matching ``query`` (name, keyword or id), best match first, at most
        ``limit``. Only series ``economic_series`` may serve are offered (FRED:
        public-domain, no copyright notice). No match is an empty list."""
        ...


Curve = dict[float, float]
"""One day's yield curve: maturity in months (1, 1.5, ..., 360) -> yield in percent.
Maturities not published that day are absent."""


@dataclass(frozen=True)
class YieldCurves:
    """Daily yield curves, ascending by date, with the metadata a page must show.
    ``meta.last_updated`` is when the data was fetched (the provider publishes no
    revision timestamp)."""

    source: DataSource
    meta: SeriesMeta
    curves: list[tuple[date, Curve]]


@dataclass(frozen=True)
class FxRates:
    """Daily exchange rates, ascending: one unit of ``base`` costs ``rate`` units of ``quote``.
    A day the provider has no rate for is absent (look up the last rate on or before it)."""

    source: DataSource
    base: str
    quote: str
    rates: list[tuple[date, float]]


class FxRatesAdapter(Adapter, Protocol):
    def fx_rates(self, ctx: RequestContext, base: str, quote: str, year: int) -> FxRates:
        """Every ``base`` -> ``quote`` rate in calendar ``year``, ascending (empty for a
        year with none). Raises ``NoSuchData`` (``missing`` keyed by the currency code)
        for a currency the provider does not publish."""
        ...


class YieldCurveAdapter(Adapter, Protocol):
    def yield_curves(self, ctx: RequestContext, year: int) -> YieldCurves:
        """Every curve published in calendar ``year``, ascending (empty for a year
        with no data yet). Raises ``SourceUnavailable`` when the provider is down
        or answers something unparseable."""
        ...


@dataclass(frozen=True)
class CountrySeries:
    """One economy's annual values of an indicator: ``(year, value)`` ascending.
    ``None`` is a year the provider has no value for."""

    country: str
    """ISO 3166-1 alpha-3 code, or the provider's aggregate code (``EMU`` = euro area)."""
    name: str
    observations: list[tuple[int, float | None]]

    @property
    def latest(self) -> tuple[int, float] | None:
        """The most recent year that has a value."""
        for year, value in reversed(self.observations):
            if value is not None:
                return year, value
        return None


@dataclass(frozen=True)
class CountryIndicator:
    """One indicator across several economies, with the metadata a page must show.
    ``meta.last_updated`` is the provider's last update date (``YYYY-MM-DD``)."""

    source: DataSource
    meta: SeriesMeta
    countries: dict[str, CountrySeries]


class CountryIndicatorAdapter(Adapter, Protocol):
    def country_indicator(
        self, ctx: RequestContext, indicator_id: str, countries: Sequence[str], start_year: int, end_year: int
    ) -> CountryIndicator:
        """Annual values in [start_year, end_year] for each requested economy the
        provider knows. Raises ``NoSuchData`` (``missing`` keyed by indicator id)
        for unknown indicators and for indicators we may not republish (license)."""
        ...
