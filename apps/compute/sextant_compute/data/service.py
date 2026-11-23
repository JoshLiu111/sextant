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
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Annotated, Any, TypeVar, cast

import pandas as pd
from fastapi import Depends

from sextant_compute.auth import OptionalUser
from sextant_compute.data.adapters import (
    Adapter,
    DailyPricesAdapter,
    EconomicSeries,
    EconomicSeriesAdapter,
    SeriesMeta,
    YieldCurveAdapter,
    YieldCurves,
)
from sextant_compute.data.cache import CACHE_VERSION, CacheBackend, InMemoryCache, default_shared_cache
from sextant_compute.data.context import RequestContext
from sextant_compute.data.fred import FredAdapter
from sextant_compute.data.synthetic import SyntheticAdapter
from sextant_compute.data.treasury import TreasuryAdapter
from sextant_compute.envelope import DataSource

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
        value = fetch()
        cache.set(key, encode(value), ttl=ttl, tags=[*tags, f"source:{adapter.source.id}"])
        return value

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
    treasury = TreasuryAdapter.from_env()
    return {synthetic.source.id: synthetic, fred.source.id: fred, treasury.source.id: treasury}


_service: DataService | None = None


def get_data_service() -> DataService:
    """FastAPI dependency. Tests swap it with ``app.dependency_overrides``."""
    global _service
    if _service is None:
        _service = DataService(default_adapters(), shared_cache=default_shared_cache())
    return _service


def get_request_context(user: OptionalUser) -> RequestContext:
    """FastAPI dependency building ``ctx`` for the current request: the signed-in
    user's id (None when anonymous). The user's own provider keys get added here
    once bring-your-own-key lands."""
    return RequestContext(user_id=user.id) if user is not None else RequestContext.anonymous()


Data = Annotated[DataService, Depends(get_data_service)]
Ctx = Annotated[RequestContext, Depends(get_request_context)]
