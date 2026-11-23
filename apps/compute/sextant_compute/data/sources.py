"""The source ids a request model may name for daily prices (the Demo / My data toggle).

``"synthetic"`` is Demo data (shared, anyone). Every other id is a "My data"
provider: a user-scope adapter that runs on the visitor's own key, so a request
naming it without a key answers 403 ``key_required`` (``DataService``). Add a
provider here when its adapter lands (FMP), and register it in
``default_adapters()`` and ``keys.api.Provider``. The web mirror is
``apps/web/src/lib/myData.ts``.
"""

from __future__ import annotations

from typing import Literal

PriceSource = Literal["synthetic", "tiingo"]

DEMO_SOURCE = "synthetic"

DEMO_TICKER_PREFIX = "DEMO-"
"""Every Demo data ticker starts with this (``DEMO-MKT``, ``DEMO-A``...)."""


def is_demo_ticker(ticker: str) -> bool:
    """A made-up Demo data ticker, which no My data provider has."""
    return ticker.upper().startswith(DEMO_TICKER_PREFIX)
