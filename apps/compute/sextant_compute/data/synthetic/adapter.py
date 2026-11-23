"""The synthetic demo-data adapter: serves ``generate_universe`` through DataService."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from functools import cache

import pandas as pd

from sextant_compute.data.adapters import Scope
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.synthetic.generator import (
    DEFAULT_SEED,
    GENERATOR_VERSION,
    HISTORY_END,
    HISTORY_START,
    PERSONALITIES,
    generate_universe,
)
from sextant_compute.envelope import DataSource

SYNTHETIC = DataSource(id="synthetic", name="Sextant demo data (synthetic)", is_demo=True)

_KNOWN = ", ".join(sorted(PERSONALITIES))


@cache
def _universe(seed: int) -> dict[str, pd.DataFrame]:
    return generate_universe(seed)


class SyntheticAdapter:
    source = SYNTHETIC
    scope: Scope = "shared"
    # Deterministic data never goes stale; the TTL only bounds cache residency.
    ttl = {"daily_prices": 7 * 24 * 3600}

    def __init__(self, seed: int = DEFAULT_SEED) -> None:
        self.seed = seed
        self.version = f"g{GENERATOR_VERSION}-s{seed}"

    def daily_prices(
        self, ctx: RequestContext, tickers: Sequence[str], start: date, end: date
    ) -> dict[str, pd.DataFrame]:
        unknown = [t for t in tickers if t not in PERSONALITIES]
        if unknown:
            raise NoSuchData(
                self.source.id,
                f"Unknown ticker{'s' if len(unknown) > 1 else ''}: {', '.join(unknown)}. Demo data covers {_KNOWN}.",
                {t: f"Unknown ticker {t}. Demo tickers are {_KNOWN}." for t in unknown},
            )
        universe = _universe(self.seed)
        out = {t: universe[t].loc[pd.Timestamp(start) : pd.Timestamp(end)] for t in tickers}
        if any(frame.empty for frame in out.values()):
            message = f"No demo data between {start} and {end}. Demo data covers {HISTORY_START} to {HISTORY_END}."
            raise NoSuchData(self.source.id, message)
        return out
