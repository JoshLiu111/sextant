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
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import Annotated, Any, TypeVar, cast

import pandas as pd
from fastapi import Depends

from sextant_compute.auth import OptionalUser
from sextant_compute.auth.deps import get_db
from sextant_compute.data.adapters import (
    Adapter,
    CrossSectionsAdapter,
    DailyPricesAdapter,
    EconomicSeries,
    EconomicSeriesAdapter,
    FilingsAdapter,
    FinancialStatementsAdapter,
    SeriesMeta,
    YieldCurveAdapter,
    YieldCurves,
)
from sextant_compute.data.cache import CACHE_VERSION, CacheBackend, InMemoryCache, default_shared_cache
from sextant_compute.data.context import RequestContext
from sextant_compute.data.cross_section import CrossSection
from sextant_compute.data.edgar import EdgarAdapter
from sextant_compute.data.filings import FilingList
from sextant_compute.data.fred import FredAdapter
from sextant_compute.data.statements import FinancialStatements
from sextant_compute.data.synthetic import SyntheticAdapter
from sextant_compute.data.treasury import TreasuryAdapter
from sextant_compute.db import Database
from sextant_compute.envelope import DataSource
from sextant_compute.keys.vault import user_keys

T = TypeVar("T")


@dataclass(frozen=True)
class PriceHistory:
    """Daily prices per ticker, plus the source they came from (put it in the envelope)."""

    source: DataSource
    frames: dict[str, pd.DataFrame]

    @property
    def last_date(self) -> date | None:
        ends = [f.index[-1].date() for f in self.frames.values() if not f.empty]
        return max(ends) if ends else None


class DataService:
    """Routes each request to the adapter for ``source`` and caches whole responses.

    Cache key: (scope, source, dataset, normalized params), see ``cache_key``.
    Shared-scope adapters (public data) use ``shared_cache``. User-scope adapters
    (data fetched with the visitor's own key) use ``user_cache`` under a key that
    includes ``ctx.user_id``; they never touch the shared cache, and without a
    ``user_cache`` (or without a signed-in user) they are not cached at all.
    An adapter opts a dataset into caching by listing its TTL in ``adapter.ttl``.
    Errors are never cached.

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
        self, ctx: RequestContext, tickers: Sequence[str], start: date, end: date, *, source: str
    ) -> PriceHistory:
        """Daily OHLCV + dividends per ticker in [start, end]; see ``DailyPricesAdapter``."""
        adapter = cast(DailyPricesAdapter, self._adapter(source))
        wanted = list(dict.fromkeys(tickers))
        frames = self._cached(
            ctx,
            adapter,
            "daily_prices",
            {"tickers": sorted(wanted), "start": start.isoformat(), "end": end.isoformat()},
            lambda: adapter.daily_prices(ctx, wanted, start, end),
            _encode_frames,
            _decode_frames,
        )
        return PriceHistory(source=adapter.source, frames={t: frames[t] for t in wanted})

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
        if misses:
            fetched = adapter.cross_sections(ctx, misses, year)
            for item_id in misses:
                out[item_id] = fetched[item_id]
                if cache is not None and ttl is not None:
                    cache.set(key(item_id), fetched[item_id].to_json(), ttl=ttl, tags=[f"source:{adapter.source.id}"])
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


def default_adapters() -> dict[str, Adapter]:
    synthetic = SyntheticAdapter()
    fred = FredAdapter.from_env()
    edgar = EdgarAdapter()
    treasury = TreasuryAdapter.from_env()
    return {
        synthetic.source.id: synthetic,
        fred.source.id: fred,
        edgar.source.id: edgar,
        treasury.source.id: treasury,
    }


_service: DataService | None = None


def get_data_service() -> DataService:
    """FastAPI dependency. Tests swap it with ``app.dependency_overrides``."""
    global _service
    if _service is None:
        _service = DataService(default_adapters(), shared_cache=default_shared_cache())
    return _service


def get_request_context(user: OptionalUser, db: Annotated[Database, Depends(get_db)]) -> RequestContext:
    """FastAPI dependency building ``ctx`` for the current request: the signed-in
    user's id (None when anonymous) and their own provider keys, decrypted fresh
    on every request so a replaced or deleted key takes effect at once."""
    if user is None:
        return RequestContext.anonymous()
    return RequestContext(user_id=user.id, keys=MappingProxyType(user_keys(db, user.id)))


Data = Annotated[DataService, Depends(get_data_service)]
Ctx = Annotated[RequestContext, Depends(get_request_context)]
