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


class YieldCurveAdapter(Adapter, Protocol):
    def yield_curves(self, ctx: RequestContext, year: int) -> YieldCurves:
        """Every curve published in calendar ``year``, ascending (empty for a year
        with no data yet). Raises ``SourceUnavailable`` when the provider is down
        or answers something unparseable."""
        ...
