"""The SEC EDGAR adapter: ticker -> CIK, companyfacts -> standardized statements."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from sextant_compute.data.adapters import Scope
from sextant_compute.data.context import RequestContext
from sextant_compute.data.edgar.client import DATA_URL, SOURCE_ID, WWW_URL, EdgarClient, NotFound
from sextant_compute.data.edgar.mapping import LineItemSpec, line_items
from sextant_compute.data.edgar.standardize import standardize
from sextant_compute.data.errors import NoSuchData, SourceUnavailable
from sextant_compute.data.statements import Company, FinancialStatements
from sextant_compute.envelope import DataSource

SEC_EDGAR = DataSource(id=SOURCE_ID, name="SEC EDGAR", is_demo=False)
TICKER_MAP_TTL = 24 * 3600


def normalize_ticker(ticker: str) -> str:
    """Upper case; SEC writes share classes with a dash (``BRK.B`` -> ``BRK-B``)."""
    return ticker.strip().upper().replace(".", "-")


class EdgarAdapter:
    """Public SEC data: shared cache. Datasets: ``financial_statements``.

    The ticker map (``company_tickers.json``, about 10k rows, changes daily) is
    kept in process for ``TICKER_MAP_TTL``; statements are cached by DataService.
    """

    source = SEC_EDGAR
    scope: Scope = "shared"
    # Filings arrive a few times a year; a day keeps a new 10-K from waiting long.
    ttl = {"financial_statements": 24 * 3600}
    # Bump when the mapping file, the standardizer or the output shape changes.
    version = "1"

    def __init__(
        self,
        client: EdgarClient | None = None,
        *,
        mapping: Sequence[LineItemSpec] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client or EdgarClient()
        self._mapping = tuple(mapping) if mapping is not None else line_items()
        self._clock = clock
        self._tickers: tuple[float, dict[str, tuple[int, str]]] | None = None
        self._lock = threading.Lock()

    def _ticker_map(self) -> Mapping[str, tuple[int, str]]:
        with self._lock:
            if self._tickers and self._clock() - self._tickers[0] < TICKER_MAP_TTL:
                return self._tickers[1]
        try:
            raw = self._client.get_json(WWW_URL, "/files/company_tickers.json")
        except NotFound as exc:
            raise SourceUnavailable(self.source.id, "ticker map not found") from exc
        try:
            rows = raw.values() if isinstance(raw, dict) else raw
            parsed = {normalize_ticker(str(r["ticker"])): (int(r["cik_str"]), str(r["title"])) for r in rows}
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise SourceUnavailable(self.source.id, "unexpected ticker map shape") from exc
        with self._lock:
            self._tickers = (self._clock(), parsed)
        return parsed

    def resolve(self, ctx: RequestContext, ticker: str) -> Company:
        """Ticker -> company (CIK, SEC name). ``NoSuchData`` keyed by the ticker if unknown."""
        symbol = normalize_ticker(ticker)
        hit = self._ticker_map().get(symbol)
        if hit is None:
            raise NoSuchData(
                self.source.id,
                f"Unknown ticker {symbol}.",
                {ticker: f"Unknown ticker {symbol}. Enter the ticker of a company that files with the SEC, e.g. AAPL."},
            )
        return Company(ticker=symbol, cik=hit[0], name=hit[1])

    def financial_statements(self, ctx: RequestContext, ticker: str) -> FinancialStatements:
        """Every annual fiscal period in the company's XBRL data, oldest first."""
        company = self.resolve(ctx, ticker)
        try:
            body: Any = self._client.get_json(DATA_URL, f"/api/xbrl/companyfacts/CIK{company.cik:010d}.json")
        except NotFound:
            body = None
        if not isinstance(body, dict) or "facts" not in body:
            body = None
        statements = (
            standardize(body, self._mapping, ticker=company.ticker, source=self.source) if body else None
        )
        if statements is None or not statements.periods:
            message = f"SEC EDGAR has no annual US-GAAP financial statements for {company.ticker}."
            raise NoSuchData(self.source.id, message, {ticker: message})
        return statements
