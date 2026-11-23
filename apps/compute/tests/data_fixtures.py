"""Hand-built adapters for API tests: swap the DataService without touching the network."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date

import pandas as pd
from fastapi import FastAPI

from main import app
from sextant_compute.data.adapters import Adapter
from sextant_compute.data.errors import NoSuchData, SourceUnavailable
from sextant_compute.data.service import DataService, get_data_service
from sextant_compute.envelope import DataSource

FIXTURE = DataSource(id="fixture", name="Test fixture", is_demo=False)


def price_frame(start: str, closes: Sequence[float], dividends: dict[int, float] | None = None) -> pd.DataFrame:
    """Daily frame on consecutive business days from ``start``; ``dividends`` maps row -> cash amount."""
    index = pd.bdate_range(start, periods=len(closes), name="date")
    dividend = [0.0] * len(closes)
    for row, amount in (dividends or {}).items():
        dividend[row] = amount
    return pd.DataFrame(
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": 1000, "dividend": dividend},
        index=index,
    )


class FixtureAdapter:
    """Serves fixed frames; counts calls so tests can see whether the source was hit."""

    version = "1"

    def __init__(self, frames: dict[str, pd.DataFrame], source: DataSource = FIXTURE, scope: str = "shared") -> None:
        self.frames = frames
        self.source = source
        self.scope = scope
        self.ttl = {"daily_prices": 3600}
        self.calls = 0

    def daily_prices(self, ctx, tickers: Sequence[str], start: date, end: date) -> dict[str, pd.DataFrame]:
        self.calls += 1
        missing = {t: f"Unknown ticker {t}." for t in tickers if t not in self.frames}
        if missing:
            raise NoSuchData(self.source.id, "Unknown ticker.", missing)
        return {t: self.frames[t].loc[pd.Timestamp(start) : pd.Timestamp(end)] for t in tickers}


class DownAdapter:
    """A provider that is always down."""

    source = DataSource(id="down", name="Down provider", is_demo=False)
    scope = "shared"
    version = "1"

    def __init__(self) -> None:
        self.ttl = {"daily_prices": 3600}

    def daily_prices(self, ctx, tickers, start, end):
        raise SourceUnavailable(self.source.id, "connection refused")


@contextmanager
def serving(
    adapter: Adapter, source_id: str = "synthetic", *, on: FastAPI = app, **service_kwargs
) -> Iterator[DataService]:
    """Route ``source_id`` requests to ``adapter`` on app ``on`` for the duration of the block."""
    service = DataService({source_id: adapter}, **service_kwargs)
    on.dependency_overrides[get_data_service] = lambda: service
    try:
        yield service
    finally:
        on.dependency_overrides.pop(get_data_service, None)
