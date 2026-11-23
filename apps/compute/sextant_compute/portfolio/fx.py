"""Converting a saved portfolio's amounts into its reporting currency (P4, story 51).

``Converter`` loads, once per request, the Frankfurter rates from each currency
the portfolio holds or traded into the reporting currency, over the dates the
request needs. Every amount converts at the rate of its own date (a price at
that day's close, a lot at its buy date, a realized P&L at its sell date), never
at today's rate. A currency Frankfurter does not publish is not an error for the
whole request: whatever needs it raises ``MissingData`` with the reason, so only
those metrics are ``missing_data``. A Frankfurter outage still raises
``SourceUnavailable`` (503).

A result built with a ``Converter`` is a ``ConvertedEnvelope``: its ``fx_source``
names Frankfurter only when some amount was converted with one of its rates, so
the page credits Frankfurter only then.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date, timedelta

import pandas as pd

from sextant_compute.analytics import fx
from sextant_compute.analytics.errors import MissingData
from sextant_compute.data.context import RequestContext
from sextant_compute.data.errors import NoSuchData
from sextant_compute.data.service import DataService
from sextant_compute.envelope import DataSource, ResultEnvelope

SOURCE = "frankfurter"
LOOKBACK = timedelta(days=14)
"""Rates are fetched from this long before the first date, so a date on a holiday still finds an earlier rate."""


class ConvertedEnvelope(ResultEnvelope):
    """A result whose amounts are in a reporting currency."""

    fx_source: DataSource | None = None
    """Where the exchange rates came from; None when no amount needed converting."""


class Converter:
    def __init__(
        self,
        data: DataService,
        ctx: RequestContext,
        reporting: str,
        currencies: Iterable[str],
        start: date,
        end: date,
    ) -> None:
        self.reporting = reporting
        self._rates: dict[str, pd.Series] = {}
        self._missing: dict[str, str] = {}
        self._source: DataSource | None = None
        for currency in sorted(set(currencies) - {reporting}):
            try:
                loaded = data.fx_rates(ctx, currency, reporting, start=start - LOOKBACK, end=end, source=SOURCE)
            except NoSuchData as exc:
                self._missing[currency] = " ".join(exc.missing.values()) or exc.message
                continue
            self._source = loaded.source
            self._rates[currency] = pd.Series(
                [rate for _, rate in loaded.rates],
                index=pd.DatetimeIndex([pd.Timestamp(when) for when, _ in loaded.rates]),
                dtype=float,
            )

    def envelope(self, env: ResultEnvelope) -> ConvertedEnvelope:
        """``env`` naming the exchange-rate source, when any rate was loaded for converting."""
        return ConvertedEnvelope(**env.model_dump(), fx_source=self._source)

    def _series(self, currency: str) -> pd.Series:
        if currency in self._missing:
            raise MissingData(self._missing[currency])
        return self._rates[currency]

    def rate(self, currency: str, day: date) -> float:
        """Units of the reporting currency per unit of ``currency`` on ``day``."""
        if currency == self.reporting:
            return 1.0
        try:
            return fx.rate_on(self._series(currency), day)
        except MissingData as exc:
            if currency in self._missing:
                raise
            raise MissingData(f"{exc} for {currency} to {self.reporting} (Frankfurter)") from None

    def amount(self, value: float, currency: str, day: date) -> float:
        return value * self.rate(currency, day)

    def prices(self, frame: pd.DataFrame, currency: str) -> pd.DataFrame:
        """A daily price frame with its money columns converted at each day's rate."""
        if currency == self.reporting:
            return frame
        try:
            return fx.convert_prices(frame, self._series(currency))
        except MissingData as exc:
            if currency in self._missing:
                raise
            raise MissingData(f"{exc} for {currency} to {self.reporting} (Frankfurter)") from None
