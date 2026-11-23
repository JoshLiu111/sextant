"""The SEC EDGAR adapter: ticker -> CIK, companyfacts -> standardized statements."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from sextant_compute.data.adapters import Scope
from sextant_compute.data.context import RequestContext
from sextant_compute.data.cross_section import CrossSection
from sextant_compute.data.edgar.client import DATA_URL, SOURCE_ID, WWW_URL, EdgarClient, NotFound
from sextant_compute.data.dividends import DividendHistory
from sextant_compute.data.edgar.dividends import dividend_history
from sextant_compute.data.edgar.feeds import getcurrent_path, parse_getcurrent, parse_submissions
from sextant_compute.data.edgar.frames import FrameKey, frame_keys, frame_path, parse_frame, specs_needed, unify
from sextant_compute.data.edgar.mapping import LineItemSpec, Tag, line_items
from sextant_compute.data.edgar.standardize import standardize
from sextant_compute.data.errors import NoSuchData, SourceUnavailable
from sextant_compute.data.filings import FilingList
from sextant_compute.data.statements import Company, FinancialStatements
from sextant_compute.envelope import DataSource

SEC_EDGAR = DataSource(id=SOURCE_ID, name="SEC EDGAR", is_demo=False)
TICKER_MAP_TTL = 24 * 3600
FRAME_WORKERS = 4
FEED_COUNT = 40  # getcurrent accepts 10/20/40/80/100


def normalize_ticker(ticker: str) -> str:
    """Upper case; SEC writes share classes with a dash (``BRK.B`` -> ``BRK-B``)."""
    return ticker.strip().upper().replace(".", "-")


class EdgarAdapter:
    """Public SEC data: shared cache. Datasets: ``financial_statements``,
    ``cross_sections`` (frames), ``latest_filings``, ``company_filings``,
    ``dividends``.

    The ticker map (``company_tickers.json``, about 10k rows, changes daily) is
    kept in process for ``TICKER_MAP_TTL``; statements are cached by DataService.
    """

    source = SEC_EDGAR
    scope: Scope = "shared"
    # Filings arrive a few times a year; a day keeps a new 10-K from waiting long.
    # Frames change as filings arrive, slowly; feeds are "latest", so minutes.
    ttl = {
        "financial_statements": 24 * 3600,
        "cross_sections": 24 * 3600,
        "latest_filings": 5 * 60,
        "company_filings": 10 * 60,
        "dividends": 24 * 3600,
    }
    # Bump when the mapping file, the standardizer or the output shape changes.
    version = "3"

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
        self._frames_in_flight: dict[FrameKey, Future[dict]] = {}

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

    def _company_by_cik(self) -> Callable[[int], tuple[str, str] | None]:
        """CIK -> (primary ticker, SEC name). The first ticker in SEC's map wins
        (it lists a company's main share class first, e.g. GOOGL before GOOG)."""
        by_cik: dict[int, tuple[str, str]] = {}
        for ticker, (cik, name) in self._ticker_map().items():
            by_cik.setdefault(cik, (ticker, name))
        return by_cik.get

    def cross_sections(self, ctx: RequestContext, item_ids: Sequence[str], year: int) -> dict[str, CrossSection]:
        """Each item's values for every listed company, from the calendar-aligned
        frames for ``year`` (flows ``CY<year>``, balance sheet ``CY<year>Q4I``).
        A tag without a frame (404) simply contributes nothing."""
        specs = specs_needed(item_ids, self._mapping)
        company = self._company_by_cik()  # also opens the HTTP client before the threads start

        def download(key: FrameKey) -> dict:
            tag_id, unit, statement, frame_year = key
            path = frame_path(Tag(*tag_id.split(":")), unit, statement, frame_year)
            try:
                return parse_frame(self._client.get_json(DATA_URL, path))
            except NotFound:
                return {}

        def fetch(key: FrameKey) -> tuple[FrameKey, dict]:
            # Single flight: concurrent screens on a cold cache share each download
            # instead of queueing duplicates behind the rate limiter.
            with self._lock:
                pending = self._frames_in_flight.get(key)
                owner = pending is None
                if owner:
                    pending = self._frames_in_flight[key] = Future()
            assert pending is not None
            if not owner:
                return key, pending.result()
            try:
                pending.set_result(download(key))
            except BaseException as exc:
                pending.set_exception(exc)
            finally:
                with self._lock:
                    self._frames_in_flight.pop(key, None)
            return key, pending.result()

        keys = frame_keys(specs, year)
        # The shared rate limiter paces these; the pool only overlaps downloads.
        with ThreadPoolExecutor(max_workers=FRAME_WORKERS) as pool:
            frames = dict(pool.map(fetch, keys))
        return unify(item_ids, self._mapping, year, frames, company)

    def latest_filings(self, ctx: RequestContext, form: str) -> FilingList:
        """The market-wide getcurrent feed (newest first); ``form`` "" = all forms."""
        try:
            text = self._client.get_text(WWW_URL, getcurrent_path(form, FEED_COUNT))
            return FilingList(filings=tuple(parse_getcurrent(text)))
        except NotFound as exc:
            raise SourceUnavailable(self.source.id, "latest-filings feed not found") from exc
        except ValueError as exc:
            raise SourceUnavailable(self.source.id, f"unexpected latest-filings feed: {exc}") from exc

    def company_filings(self, ctx: RequestContext, ticker: str) -> FilingList:
        """One company's recent filings from the submissions API, newest first."""
        company = self.resolve(ctx, ticker)
        try:
            body = self._client.get_json(DATA_URL, f"/submissions/CIK{company.cik:010d}.json")
            _, filings = parse_submissions(body)
        except NotFound as exc:
            message = f"SEC EDGAR has no filings for {company.ticker}."
            raise NoSuchData(self.source.id, message, {ticker: message}) from exc
        except ValueError as exc:
            raise SourceUnavailable(self.source.id, f"unexpected submissions shape: {exc}") from exc
        return FilingList(filings=tuple(filings), company=company.name)

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

    def _companyfacts(self, company: Company) -> dict[str, Any] | None:
        """The company's XBRL facts, or None if SEC has none for it."""
        try:
            body: Any = self._client.get_json(DATA_URL, f"/api/xbrl/companyfacts/CIK{company.cik:010d}.json")
        except NotFound:
            return None
        return body if isinstance(body, dict) and "facts" in body else None

    def dividends(self, ctx: RequestContext, ticker: str) -> DividendHistory:
        """Per-share dividends by fiscal quarter and year from the XBRL filings,
        newest first; empty (``basis`` None) for a company that reports none."""
        company = self.resolve(ctx, ticker)
        body = self._companyfacts(company)
        if body is None:
            message = f"SEC EDGAR has no XBRL financial data for {company.ticker}."
            raise NoSuchData(self.source.id, message, {ticker: message})
        return dividend_history(body, company)

    def financial_statements(self, ctx: RequestContext, ticker: str) -> FinancialStatements:
        """Every annual fiscal period in the company's XBRL data, oldest first."""
        company = self.resolve(ctx, ticker)
        body = self._companyfacts(company)
        statements = (
            standardize(body, self._mapping, ticker=company.ticker, source=self.source) if body else None
        )
        if statements is None or not statements.periods:
            message = f"SEC EDGAR has no annual US-GAAP financial statements for {company.ticker}."
            raise NoSuchData(self.source.id, message, {ticker: message})
        return statements
