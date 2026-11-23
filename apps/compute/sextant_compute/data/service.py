"""DataService: the one way tools get data.

Every method takes ``ctx`` (``RequestContext``) first and a ``source`` id naming
the adapter to use. Tool endpoints get the service with the ``Data`` dependency
and never import adapters directly::

    @router.post("/metrics")
    def handler(req: Req, data: Data, ctx: Ctx) -> ResultEnvelope:
        prices = data.daily_prices(ctx, ["DEMO-A"], start, end, source="synthetic")
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import threading
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future
from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType
from typing import Annotated, Any, TypeVar, cast

import pandas as pd
from fastapi import Depends, Request

from sextant_compute.auth import OptionalUser
from sextant_compute.auth.deps import get_db
from sextant_compute.data.adapters import (
    Adapter,
    CountryIndicator,
    CountryIndicatorAdapter,
    CountrySeries,
    CrossSectionsAdapter,
    DailyFactorsAdapter,
    DailyPricesAdapter,
    DividendsAdapter,
    EconomicSeries,
    EconomicSeriesAdapter,
    FilingsAdapter,
    FinancialStatementsAdapter,
    FxRates,
    FxRatesAdapter,
    LatestCloseAdapter,
    SeriesMeta,
    SeriesSearchAdapter,
    SeriesSummary,
    SplitsAdapter,
    YieldCurveAdapter,
    YieldCurves,
)
from sextant_compute.data.cache import CACHE_VERSION, CacheBackend, InMemoryCache, default_shared_cache
from sextant_compute.data.context import RequestContext
from sextant_compute.data.cross_section import CrossSection
from sextant_compute.data.dividends import DividendHistory
from sextant_compute.data.ecb import EcbAdapter
from sextant_compute.data.edgar import EdgarAdapter
from sextant_compute.data.errors import KeyRequired, NoSuchData
from sextant_compute.data.filings import FilingList
from sextant_compute.data.fmp import FmpAdapter
from sextant_compute.data.frankfurter import FrankfurterAdapter
from sextant_compute.data.fred import FredAdapter
from sextant_compute.data.statements import FinancialStatements, Frequency
from sextant_compute.data.synthetic import SyntheticAdapter
from sextant_compute.data.tiingo import TiingoAdapter
from sextant_compute.data.treasury import TreasuryAdapter
from sextant_compute.data.user_cache import PostgresUserCache
from sextant_compute.data.world_bank import WorldBankAdapter
from sextant_compute.db import Database
from sextant_compute.envelope import DataSource
from sextant_compute.keys.vault import user_keys

T = TypeVar("T")


@dataclass(frozen=True)
class PriceHistory:
    """Daily prices per ticker, plus the source they came from (put it in the envelope).

    ``missing`` (filled only with ``partial=True``): ticker -> why the source has
    no prices for it. Those tickers are not in ``frames``."""

    source: DataSource
    frames: dict[str, pd.DataFrame]
    missing: dict[str, str] = field(default_factory=dict)

    @property
    def last_date(self) -> date | None:
        ends = [f.index[-1].date() for f in self.frames.values() if not f.empty]
        return max(ends) if ends else None


@dataclass(frozen=True)
class LatestClose:
    """One ticker's most recent close and the source it came from."""

    source: DataSource
    ticker: str
    date: date
    close: float


@dataclass(frozen=True)
class FactorHistory:
    """Daily factor returns (``FACTOR_COLUMNS``, decimals) and the source they came from."""

    source: DataSource
    frame: pd.DataFrame


class DataService:
    """Routes each request to the adapter for ``source`` and caches whole responses.

    Cache key: (scope, source, dataset, normalized params), see ``cache_key``.
    Shared-scope adapters (public data) use ``shared_cache``. User-scope adapters
    (data fetched with the visitor's own key) use ``user_cache`` under a key that
    includes ``ctx.user_id``; they never touch the shared cache, and without a
    ``user_cache`` (or without a signed-in user) they are not cached at all.
    An adapter opts a dataset into caching by listing its TTL in ``adapter.ttl``.
    Errors are never cached.

    User-scope sources need the visitor's own key: without
    ``ctx.key_for(source.id)`` a call raises ``KeyRequired`` before the cache is
    consulted, so a deleted key also stops cached data from being served.

    Single flight: concurrent misses on the same key share one fetch (the others
    wait for it and get its result, or its error), so a burst of identical
    requests on a cold cache doesn't queue duplicate calls behind a rate limit.
    """

    def __init__(
        self,
        adapters: Mapping[str, Adapter],
        *,
        shared_cache: CacheBackend | None = None,
        user_cache: CacheBackend | None = None,
    ) -> None:
        self._adapters = dict(adapters)
        self.shared_cache = shared_cache if shared_cache is not None else InMemoryCache()
        self.user_cache = user_cache
        self._lock = threading.Lock()
        self._in_flight: dict[str, Future[Any]] = {}

    def _adapter(self, source: str) -> Adapter:
        try:
            return self._adapters[source]
        except KeyError:
            raise ValueError(f"No adapter registered for source {source!r}") from None

    def source_info(self, source: str) -> DataSource:
        """The ``DataSource`` behind a source id (for the envelope when no data came back)."""
        return self._adapter(source).source

    def require_key(self, ctx: RequestContext, source: str) -> None:
        """Raise ``KeyRequired`` if ``source`` runs on the visitor's own key and
        they have none. Every fetch checks this; call it up front when a request
        might end without fetching (so the answer doesn't depend on the data)."""
        self._require_key(ctx, self._adapter(source))

    @staticmethod
    def _require_key(ctx: RequestContext, adapter: Adapter) -> None:
        if adapter.scope == "user" and not ctx.key_for(adapter.source.id):
            raise KeyRequired(
                adapter.source.id, f"My data needs your own {adapter.source.name} key. Add one in Settings."
            )

    def _cached(
        self,
        ctx: RequestContext,
        adapter: Adapter,
        dataset: str,
        params: dict[str, Any],
        fetch: Callable[[], T],
        encode: Callable[[T], Any],
        decode: Callable[[Any], T],
    ) -> T:
        ttl = adapter.ttl.get(dataset)
        if adapter.scope == "user":
            self._require_key(ctx, adapter)
            cache = self.user_cache if ctx.user_id is not None else None
            tags = [f"user:{ctx.user_id}"]
        else:
            cache = self.shared_cache
            tags = []
        if cache is None or ttl is None:
            return fetch()
        key = cache_key(adapter, dataset, params, user_id=ctx.user_id if adapter.scope == "user" else None)
        hit = cache.get(key)
        if hit is not None:
            return decode(hit)
        with self._lock:
            pending = self._in_flight.get(key)
            owner = pending is None
            if pending is None:
                pending = self._in_flight[key] = Future()
        if not owner:
            # Followers decode their own copy, so callers never share mutable values.
            return decode(pending.result())
        try:
            # A flight that just finished may have filled the cache since the first look.
            hit = cache.get(key)
            if hit is not None:
                pending.set_result(hit)
                return decode(hit)
            value = fetch()
            encoded = encode(value)
            cache.set(key, encoded, ttl=ttl, tags=[*tags, f"source:{adapter.source.id}"])
            pending.set_result(encoded)
            return value
        except BaseException as exc:
            pending.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._in_flight.pop(key, None)

    def daily_prices(
        self,
        ctx: RequestContext,
        tickers: Sequence[str],
        start: date,
        end: date,
        *,
        source: str,
        partial: bool = False,
    ) -> PriceHistory:
        """Daily OHLCV + dividends per ticker in [start, end]; see ``DailyPricesAdapter``.

        By default one unknown ticker fails the whole call with ``NoSuchData``.
        With ``partial=True`` each ticker is fetched and cached on its own, and
        tickers the source has no prices for land in ``PriceHistory.missing``
        instead (for real tickers: a typo shouldn't cost the rest, nor the user's
        provider quota be spent refetching them). ``SourceUnavailable`` and
        ``KeyRequired`` still fail the call."""
        adapter = cast(DailyPricesAdapter, self._adapter(source))
        wanted = list(dict.fromkeys(tickers))
        if partial:
            found: dict[str, pd.DataFrame] = {}
            missing: dict[str, str] = {}
            for ticker in wanted:
                try:
                    found[ticker] = self._prices(ctx, adapter, [ticker], start, end)[ticker]
                except NoSuchData as exc:
                    missing[ticker] = exc.missing.get(ticker, exc.message)
            return PriceHistory(source=adapter.source, frames=found, missing=missing)
        frames = self._prices(ctx, adapter, wanted, start, end)
        return PriceHistory(source=adapter.source, frames={t: frames[t] for t in wanted})

    def _prices(
        self, ctx: RequestContext, adapter: DailyPricesAdapter, wanted: list[str], start: date, end: date
    ) -> dict[str, pd.DataFrame]:
        return self._cached(
            ctx,
            adapter,
            "daily_prices",
            {"tickers": sorted(wanted), "start": start.isoformat(), "end": end.isoformat()},
            lambda: adapter.daily_prices(ctx, wanted, start, end),
            _encode_frames,
            _decode_frames,
        )

    def splits(self, ctx: RequestContext, ticker: str, start: date, *, source: str) -> list[tuple[date, float]]:
        """One ticker's stock splits from ``start`` up to today; see ``SplitsAdapter``.
        A source without split data (the synthetic demo) has no splits."""
        adapter = self._adapter(source)
        if not hasattr(adapter, "splits"):
            return []
        splits = cast(SplitsAdapter, adapter)
        return self._cached(
            ctx,
            splits,
            "splits",
            {"ticker": ticker, "start": start.isoformat()},
            lambda: splits.splits(ctx, ticker, start),
            lambda found: [[d.isoformat(), ratio] for d, ratio in found],
            lambda raw: [(date.fromisoformat(d), float(ratio)) for d, ratio in raw],
        )

    def latest_close(self, ctx: RequestContext, ticker: str, *, source: str) -> LatestClose:
        """The most recent close for one ticker; see ``LatestCloseAdapter``."""
        adapter = cast(LatestCloseAdapter, self._adapter(source))
        symbol = ticker.strip().upper()
        when, close = self._cached(
            ctx,
            adapter,
            "latest_close",
            {"ticker": symbol},
            lambda: adapter.latest_close(ctx, symbol),
            lambda v: {"date": v[0].isoformat(), "close": v[1]},
            lambda raw: (date.fromisoformat(raw["date"]), float(raw["close"])),
        )
        return LatestClose(source=adapter.source, ticker=symbol, date=when, close=close)

    def daily_factors(self, ctx: RequestContext, start: date, end: date, *, source: str) -> FactorHistory:
        """Daily factor returns in [start, end]; see ``DailyFactorsAdapter``. Raises
        ``NoSuchData`` when ``source`` serves no factors (every source but the
        synthetic demo one, ADR 0003)."""
        adapter = self._adapter(source)
        if not hasattr(adapter, "daily_factors"):
            raise NoSuchData(adapter.source.id, f"There is no factor data for {adapter.source.name}.")
        factors = cast(DailyFactorsAdapter, adapter)
        frames = self._cached(
            ctx,
            factors,
            "daily_factors",
            {"start": start.isoformat(), "end": end.isoformat()},
            lambda: {"factors": factors.daily_factors(ctx, start, end)},
            _encode_frames,
            _decode_frames,
        )
        return FactorHistory(source=adapter.source, frame=frames["factors"])

    def financial_statements(self, ctx: RequestContext, ticker: str, *, source: str) -> FinancialStatements:
        """Standardized annual statements for one company; see ``FinancialStatementsAdapter``.
        Use ``.last(n)`` for the n most recent fiscal years."""
        adapter = cast(FinancialStatementsAdapter, self._adapter(source))
        return self._cached(
            ctx,
            adapter,
            "financial_statements",
            {"ticker": ticker.strip().upper()},
            lambda: adapter.financial_statements(ctx, ticker),
            FinancialStatements.to_json,
            FinancialStatements.from_json,
        )

    def quarterly_statements(self, ctx: RequestContext, ticker: str, *, source: str) -> FinancialStatements:
        """Standardized statements by fiscal quarter; see ``FinancialStatementsAdapter``."""
        adapter = cast(FinancialStatementsAdapter, self._adapter(source))
        return self._cached(
            ctx,
            adapter,
            "quarterly_statements",
            {"ticker": ticker.strip().upper()},
            lambda: adapter.quarterly_statements(ctx, ticker),
            FinancialStatements.to_json,
            FinancialStatements.from_json,
        )

    def statements(
        self, ctx: RequestContext, ticker: str, *, source: str, frequency: Frequency
    ) -> FinancialStatements:
        """Annual or quarterly statements."""
        if frequency == "quarterly":
            return self.quarterly_statements(ctx, ticker, source=source)
        return self.financial_statements(ctx, ticker, source=source)

    def cross_sections(
        self, ctx: RequestContext, item_ids: Sequence[str], year: int, *, source: str
    ) -> dict[str, CrossSection]:
        """Unified line items across every company for one year; see
        ``CrossSectionsAdapter``. Cached per (item, year), so screens with
        different criteria share entries; only missing items are fetched."""
        adapter = cast(CrossSectionsAdapter, self._adapter(source))
        wanted = list(dict.fromkeys(item_ids))
        ttl = adapter.ttl.get("cross_sections")
        cache = self.shared_cache if adapter.scope == "shared" and ttl is not None else None

        def key(item_id: str) -> str:
            return cache_key(adapter, "cross_sections", {"item": item_id, "year": year})

        out: dict[str, CrossSection] = {}
        if cache is not None:
            for item_id in wanted:
                hit = cache.get(key(item_id))
                if hit is not None:
                    out[item_id] = CrossSection.from_json(hit)
        misses = [i for i in wanted if i not in out]
        # Single flight per (item, year): a concurrent screen waits for the items
        # another request is already fetching instead of downloading them again.
        owned: list[str] = []
        waiting: dict[str, Future[Any]] = {}
        with self._lock:
            for item_id in misses:
                pending = self._in_flight.get(key(item_id))
                if pending is None:
                    self._in_flight[key(item_id)] = Future()
                    owned.append(item_id)
                else:
                    waiting[item_id] = pending
        try:
            if cache is not None:  # a flight that just finished may have filled the cache
                for item_id in owned:
                    hit = cache.get(key(item_id))
                    if hit is not None:
                        out[item_id] = CrossSection.from_json(hit)
            to_fetch = [i for i in owned if i not in out]
            fetched = adapter.cross_sections(ctx, to_fetch, year) if to_fetch else {}
            for item_id in to_fetch:
                out[item_id] = fetched[item_id]
                if cache is not None and ttl is not None:
                    cache.set(key(item_id), fetched[item_id].to_json(), ttl=ttl, tags=[f"source:{adapter.source.id}"])
            for item_id in owned:
                self._in_flight[key(item_id)].set_result(out[item_id].to_json())
        except BaseException as exc:
            for item_id in owned:
                future = self._in_flight[key(item_id)]
                if not future.done():
                    future.set_exception(exc)
            raise
        finally:
            with self._lock:
                for item_id in owned:
                    self._in_flight.pop(key(item_id), None)
        for item_id, pending in waiting.items():
            out[item_id] = CrossSection.from_json(pending.result())
        return {i: out[i] for i in wanted}

    def latest_filings(self, ctx: RequestContext, form: str, *, source: str) -> FilingList:
        """The newest filings market-wide (``form`` "" = all); see ``FilingsAdapter``."""
        adapter = cast(FilingsAdapter, self._adapter(source))
        return self._cached(
            ctx,
            adapter,
            "latest_filings",
            {"form": form},
            lambda: adapter.latest_filings(ctx, form),
            FilingList.to_json,
            FilingList.from_json,
        )

    def company_filings(self, ctx: RequestContext, ticker: str, *, source: str) -> FilingList:
        """One company's recent filings, newest first; see ``FilingsAdapter``."""
        adapter = cast(FilingsAdapter, self._adapter(source))
        return self._cached(
            ctx,
            adapter,
            "company_filings",
            {"ticker": ticker.strip().upper()},
            lambda: adapter.company_filings(ctx, ticker),
            FilingList.to_json,
            FilingList.from_json,
        )

    def dividends(self, ctx: RequestContext, ticker: str, *, source: str) -> DividendHistory:
        """One company's per-share dividends by period, newest first; see ``DividendsAdapter``."""
        adapter = cast(DividendsAdapter, self._adapter(source))
        return self._cached(
            ctx,
            adapter,
            "dividends",
            {"ticker": ticker.strip().upper()},
            lambda: adapter.dividends(ctx, ticker),
            DividendHistory.to_json,
            DividendHistory.from_json,
        )

    def economic_series(
        self, ctx: RequestContext, series_id: str, *, start: date, units: str = "lin", source: str
    ) -> EconomicSeries:
        """One economic time series with its metadata; see ``EconomicSeriesAdapter``."""
        adapter = cast(EconomicSeriesAdapter, self._adapter(source))
        return self._cached(
            ctx,
            adapter,
            "economic_series",
            {"series_id": series_id, "start": start.isoformat(), "units": units},
            lambda: adapter.economic_series(ctx, series_id, start, units),
            _encode_series,
            _decode_series,
        )

    def search_series(self, ctx: RequestContext, query: str, *, limit: int, source: str) -> list[SeriesSummary]:
        """Series matching a name, keyword or id; see ``SeriesSearchAdapter``.
        Cached per (query lowercased and trimmed, limit)."""
        adapter = cast(SeriesSearchAdapter, self._adapter(source))
        text = " ".join(query.split())
        return self._cached(
            ctx,
            adapter,
            "series_search",
            {"query": text.lower(), "limit": limit},
            lambda: adapter.search_series(ctx, text, limit),
            lambda hits: [dataclasses.asdict(h) for h in hits],
            lambda raw: [SeriesSummary(**h) for h in raw],
        )

    def yield_curves(self, ctx: RequestContext, *, start: date, end: date, source: str) -> YieldCurves:
        """Daily yield curves dated within [start, end], ascending; see ``YieldCurveAdapter``.
        Fetched and cached one calendar year at a time, so a wider range reuses the
        years already cached. ``meta`` is the newest year's."""
        adapter = cast(YieldCurveAdapter, self._adapter(source))
        years = [
            self._cached(
                ctx,
                adapter,
                "yield_curves",
                {"year": year},
                lambda year=year: adapter.yield_curves(ctx, year),
                _encode_curves,
                _decode_curves,
            )
            for year in range(start.year, end.year + 1)
        ]
        return YieldCurves(
            source=adapter.source,
            meta=years[-1].meta,
            curves=[(when, curve) for y in years for when, curve in y.curves if start <= when <= end],
        )

    def fx_rates(self, ctx: RequestContext, base: str, quote: str, *, start: date, end: date, source: str) -> FxRates:
        """Daily ``base`` -> ``quote`` rates dated within [start, end], ascending; see
        ``FxRatesAdapter``. Fetched and cached one calendar year at a time."""
        adapter = cast(FxRatesAdapter, self._adapter(source))
        years = [
            self._cached(
                ctx,
                adapter,
                "fx_rates",
                {"base": base, "quote": quote, "year": year},
                lambda year=year: adapter.fx_rates(ctx, base, quote, year),
                _encode_fx,
                _decode_fx,
            )
            for year in range(start.year, end.year + 1)
        ]
        return FxRates(
            source=adapter.source,
            base=base,
            quote=quote,
            rates=[(when, rate) for y in years for when, rate in y.rates if start <= when <= end],
        )

    def country_indicator(
        self,
        ctx: RequestContext,
        indicator_id: str,
        countries: Sequence[str],
        *,
        start_year: int,
        end_year: int,
        source: str,
    ) -> CountryIndicator:
        """One indicator's annual values for several economies; see ``CountryIndicatorAdapter``.
        Cached per (indicator, country set, years): ask for a fixed country set and
        filter, so every selection shares one entry."""
        adapter = cast(CountryIndicatorAdapter, self._adapter(source))
        wanted = sorted({c.strip().upper() for c in countries})
        return self._cached(
            ctx,
            adapter,
            "country_indicator",
            {"indicator": indicator_id, "countries": wanted, "start_year": start_year, "end_year": end_year},
            lambda: adapter.country_indicator(ctx, indicator_id, wanted, start_year, end_year),
            _encode_country_indicator,
            _decode_country_indicator,
        )


def cache_key(adapter: Adapter, dataset: str, params: Mapping[str, Any], *, user_id: object | None = None) -> str:
    """``v<CACHE_VERSION>:<shared|user:<id>>:<source>@<adapter version>:<dataset>:<params hash>``."""
    scope = f"user:{user_id}" if user_id is not None else "shared"
    digest = hashlib.sha256(json.dumps(params, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:32]
    return f"v{CACHE_VERSION}:{scope}:{adapter.source.id}@{adapter.version}:{dataset}:{digest}"


def _encode_frames(frames: Mapping[str, pd.DataFrame]) -> dict[str, Any]:
    return {
        ticker: {
            "index": [ts.date().isoformat() for ts in frame.index],
            "columns": {col: frame[col].tolist() for col in frame.columns},
        }
        for ticker, frame in frames.items()
    }


def _decode_frames(raw: Mapping[str, Any]) -> dict[str, pd.DataFrame]:
    return {
        ticker: pd.DataFrame(
            payload["columns"], index=pd.DatetimeIndex(pd.to_datetime(payload["index"]), name="date")
        )
        for ticker, payload in raw.items()
    }


def _encode_series(series: EconomicSeries) -> dict[str, Any]:
    return {
        "source": series.source.model_dump(),
        "meta": dataclasses.asdict(series.meta),
        "observations": [[when.isoformat(), value] for when, value in series.observations],
    }


def _decode_series(raw: Mapping[str, Any]) -> EconomicSeries:
    return EconomicSeries(
        source=DataSource(**raw["source"]),
        meta=SeriesMeta(**raw["meta"]),
        observations=[(date.fromisoformat(when), value) for when, value in raw["observations"]],
    )


def _encode_curves(curves: YieldCurves) -> dict[str, Any]:
    return {
        "source": curves.source.model_dump(),
        "meta": dataclasses.asdict(curves.meta),
        "curves": [[when.isoformat(), [[m, v] for m, v in curve.items()]] for when, curve in curves.curves],
    }


def _decode_curves(raw: Mapping[str, Any]) -> YieldCurves:
    return YieldCurves(
        source=DataSource(**raw["source"]),
        meta=SeriesMeta(**raw["meta"]),
        curves=[(date.fromisoformat(when), {float(m): v for m, v in pairs}) for when, pairs in raw["curves"]],
    )


def _encode_fx(rates: FxRates) -> dict[str, Any]:
    return {
        "source": rates.source.model_dump(),
        "base": rates.base,
        "quote": rates.quote,
        "rates": [[when.isoformat(), rate] for when, rate in rates.rates],
    }


def _decode_fx(raw: Mapping[str, Any]) -> FxRates:
    return FxRates(
        source=DataSource(**raw["source"]),
        base=raw["base"],
        quote=raw["quote"],
        rates=[(date.fromisoformat(when), rate) for when, rate in raw["rates"]],
    )


def _encode_country_indicator(found: CountryIndicator) -> dict[str, Any]:
    return {
        "source": found.source.model_dump(),
        "meta": dataclasses.asdict(found.meta),
        "countries": [
            [c.country, c.name, [[year, value] for year, value in c.observations]] for c in found.countries.values()
        ],
    }


def _decode_country_indicator(raw: Mapping[str, Any]) -> CountryIndicator:
    return CountryIndicator(
        source=DataSource(**raw["source"]),
        meta=SeriesMeta(**raw["meta"]),
        countries={
            code: CountrySeries(code, name, [(int(year), value) for year, value in observations])
            for code, name, observations in raw["countries"]
        },
    )


def default_adapters() -> dict[str, Adapter]:
    synthetic = SyntheticAdapter()
    fred = FredAdapter.from_env()
    edgar = EdgarAdapter()
    treasury = TreasuryAdapter.from_env()
    frankfurter = FrankfurterAdapter.from_env()
    tiingo = TiingoAdapter.from_env()
    fmp = FmpAdapter.from_env()
    world_bank = WorldBankAdapter.from_env()
    ecb = EcbAdapter.from_env()
    return {
        tiingo.source.id: tiingo,
        frankfurter.source.id: frankfurter,
        fmp.source.id: fmp,
        synthetic.source.id: synthetic,
        fred.source.id: fred,
        edgar.source.id: edgar,
        treasury.source.id: treasury,
        world_bank.source.id: world_bank,
        ecb.source.id: ecb,
    }


def make_data_service(db: Database, adapters: Mapping[str, Adapter] | None = None) -> DataService:
    """The production wiring: the shared cache (Runtime Cache on Vercel) plus the
    per-user Postgres cache in ``db``. Tests pass their own ``adapters``."""
    return DataService(
        adapters if adapters is not None else default_adapters(),
        shared_cache=default_shared_cache(),
        user_cache=PostgresUserCache(db),
    )


_service_lock = threading.Lock()


def get_data_service(request: Request) -> DataService:
    """FastAPI dependency: one service per app, built on first use. Tests swap it
    with ``app.dependency_overrides`` (``serving``) or set ``app.state.data_service``.
    Built under a lock: concurrent first requests must share one service (one
    cache, one single-flight map), or a cold burst fetches everything N times."""
    service = getattr(request.app.state, "data_service", None)
    if service is None:
        with _service_lock:
            service = getattr(request.app.state, "data_service", None)
            if service is None:
                service = request.app.state.data_service = make_data_service(request.app.state.db)
    return service


def get_request_context(user: OptionalUser, db: Annotated[Database, Depends(get_db)]) -> RequestContext:
    """FastAPI dependency building ``ctx`` for the current request: the signed-in
    user's id (None when anonymous) and their own provider keys, decrypted fresh
    on every request so a replaced or deleted key takes effect at once."""
    if user is None:
        return RequestContext.anonymous()
    return RequestContext(user_id=user.id, keys=MappingProxyType(user_keys(db, user.id)))


Data = Annotated[DataService, Depends(get_data_service)]
Ctx = Annotated[RequestContext, Depends(get_request_context)]
