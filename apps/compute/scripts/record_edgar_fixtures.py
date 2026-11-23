"""Record trimmed SEC EDGAR responses as test fixtures (tests/fixtures/edgar/).

Run by hand when the fixtures need refreshing; tests never touch the network::

    SEC_USER_AGENT="Sextant dev admin@example.com" uv run python -m scripts.record_edgar_fixtures

Use a generic User-Agent; never commit a real contact. ``--raw-dir DIR`` trims
responses you already downloaded instead of fetching; ``--screener-only`` leaves
the companyfacts files alone. Raw file names:
``company_tickers.json``, ``CIK##########.json`` (companyfacts),
``<taxonomy>_<Tag>_<unit>_<period>.json`` (frames), ``getcurrent_<form or all>.atom``
and ``submissions_CIK##########.json``.

Trimming keeps the files small but real (values are never edited):
- ``company_tickers.json``: only the rows for ``TICKERS``, ``EXTRA_TICKER_ROWS``
  and ``SCREEN_TICKERS``.
- companyfacts: ``cik``, ``entityName``, and for every tag named in
  ``line_items.toml`` only annual-report facts (10-K family) filed since
  ``SINCE``; for the per-share dividend tags (``DIVIDEND_TAGS``) the 10-Q
  family too. ``description`` texts are dropped.
- frames (screener): ``frames/<taxonomy>/<Tag>/<unit>/<period>.json``, one per tag
  the screener metrics need, for ``FRAME_YEARS``, keeping only the rows of
  ``SCREEN_TICKERS`` companies. A tag without a frame (404) gets no file.
- latest filings: ``getcurrent/<form or all>.atom`` for ``FEED_FORMS`` (kept
  whole), and ``submissions/CIK##########.json`` for ``SUBMISSION_TICKERS`` (the
  company header plus the newest ``SUBMISSIONS_KEEP`` filings and every
  earnings 8-K, Item 2.02, for the earnings calendar).
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from sextant_compute.analytics.screener import METRICS, items_for
from sextant_compute.data.edgar.client import DATA_URL, WWW_URL, EdgarClient, NotFound
from sextant_compute.data.edgar.dividends import DIVIDEND_TAGS
from sextant_compute.data.edgar.feeds import getcurrent_path
from sextant_compute.data.edgar.frames import FrameKey, frame_keys, frame_path, specs_needed
from sextant_compute.data.edgar.mapping import Tag, line_items
from sextant_compute.screener.calendar import CALENDAR_TICKERS, EARNINGS_ITEM

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "edgar"
# AAPL/MSFT: different revenue tags. JPM: a bank (no COGS, no current assets).
# WMT: no GrossProfit or Liabilities tags (derived), custom EPS tags.
# AMZN: pays no dividend (dividend history says so).
TICKERS = ["AAPL", "MSFT", "JPM", "WMT", "AMZN"]
EXTRA_TICKER_ROWS = ["GOOGL", "GOOG", "BRK-B"]  # ticker-map shapes only, no companyfacts
# The screener's fixture universe: large caps across sectors, incl. a bank (JPM)
# and companies with negative equity or no GrossProfit tag.
SCREEN_TICKERS = (
    "AAPL MSFT JPM WMT GOOGL NVDA AMZN META TSLA KO PEP XOM JNJ PG V MA HD COST NFLX INTC "
    "CSCO ORCL ADBE PFE MRK T VZ DIS NKE MCD BA CAT IBM UNH LLY AVGO AMD"
).split()
FRAME_YEARS = [2025, 2024]
FEED_FORMS = ["", "10-K"]
FEED_COUNT = 40
SUBMISSION_TICKERS = sorted({"AAPL", "MSFT", *CALENDAR_TICKERS})
SUBMISSIONS_KEEP = 60
ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "20-F", "40-F"}
QUARTERLY_FORMS = {"10-Q", "10-Q/A"}
SINCE = "2016-01-01"


def trim_tickers(raw: dict) -> dict:
    wanted = set(TICKERS) | set(EXTRA_TICKER_ROWS) | set(SCREEN_TICKERS)
    rows = [row for row in raw.values() if row["ticker"] in wanted]
    return {str(i): row for i, row in enumerate(rows)}


def trim_companyfacts(raw: dict) -> dict:
    wanted: dict[str, set[str]] = {}
    for spec in line_items():
        for tag in spec.tags:
            wanted.setdefault(tag.taxonomy, set()).add(tag.name)
    quarterly = {tuple(tag.split(":")) for tag, _ in DIVIDEND_TAGS}
    for taxonomy, name in quarterly:
        wanted.setdefault(taxonomy, set()).add(name)
    facts: dict[str, dict] = {}
    for taxonomy, names in wanted.items():
        for name in sorted(names):
            concept = raw.get("facts", {}).get(taxonomy, {}).get(name)
            if concept is None:
                continue
            forms = ANNUAL_FORMS | QUARTERLY_FORMS if (taxonomy, name) in quarterly else ANNUAL_FORMS
            units = {}
            for unit, rows in concept["units"].items():
                kept = [r for r in rows if r.get("form") in forms and r.get("filed", "") >= SINCE]
                if kept:
                    units[unit] = kept
            if units:
                facts.setdefault(taxonomy, {})[name] = {"label": concept.get("label"), "units": units}
    return {"cik": raw["cik"], "entityName": raw["entityName"], "facts": facts}


def trim_frame(raw: dict, ciks: set[int]) -> dict:
    rows = [r for r in raw["data"] if r["cik"] in ciks]
    head = {k: v for k, v in raw.items() if k not in ("data", "description", "pts")}
    return {**head, "pts": len(rows), "data": rows}


def trim_submissions(raw: dict) -> dict:
    columns = raw["filings"]["recent"]
    keep = [
        i
        for i, (form, items) in enumerate(zip(columns["form"], columns["items"], strict=True))
        if i < SUBMISSIONS_KEEP or (form.split("/")[0] == "8-K" and EARNINGS_ITEM in items.split(","))
    ]
    recent = {k: [v[i] for i in keep] for k, v in columns.items()}
    head = {k: raw[k] for k in ("cik", "name", "tickers", "exchanges", "sic", "sicDescription", "fiscalYearEnd")}
    return {**head, "filings": {"recent": recent}}


def screener_frame_keys() -> list[FrameKey]:
    item_ids = list(dict.fromkeys(i for bucket in items_for(list(METRICS)).values() for i in bucket))
    keys: list[FrameKey] = []
    for year in FRAME_YEARS:
        keys += frame_keys(specs_needed(item_ids, line_items()), year)
    return keys


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path)
    parser.add_argument("--screener-only", action="store_true", help="leave the companyfacts files as they are")
    args = parser.parse_args()
    client = None if args.raw_dir else EdgarClient()

    def load(host: str, path: str, raw_name: str | None = None) -> dict:
        if args.raw_dir:
            file = args.raw_dir / (raw_name or Path(path).name)
            if not file.exists():
                raise NotFound(str(file))
            return json.loads(file.read_text())
        assert client is not None
        return client.get_json(host, path)

    def load_text(host: str, path: str, raw_name: str) -> str:
        if args.raw_dir:
            return (args.raw_dir / raw_name).read_text(encoding="iso-8859-1")
        assert client is not None
        return client.get_text(host, path)

    OUT.mkdir(parents=True, exist_ok=True)
    tickers = trim_tickers(load(WWW_URL, "/files/company_tickers.json"))
    (OUT / "company_tickers.json").write_text(json.dumps(tickers, indent=1) + "\n")
    for row in tickers.values():
        if row["ticker"] not in TICKERS or args.screener_only:
            continue
        name = f"CIK{row['cik_str']:010d}.json"
        trimmed = trim_companyfacts(load(DATA_URL, f"/api/xbrl/companyfacts/{name}"))
        (OUT / name).write_text(json.dumps(trimmed, separators=(",", ":")) + "\n")
        print(f"{row['ticker']}: {name} ({(OUT / name).stat().st_size // 1024} KB)")

    screen_ciks = {row["cik_str"] for row in tickers.values() if row["ticker"] in SCREEN_TICKERS}
    for tag_id, unit, statement, year in screener_frame_keys():
        tag = Tag(*tag_id.split(":"))
        path = frame_path(tag, unit, statement, year)
        raw_name = "_".join([tag.taxonomy, tag.name, unit.replace("/", "-per-"), Path(path).stem]) + ".json"
        try:
            raw = load(DATA_URL, path, raw_name)
        except NotFound:
            print(f"{path}: no frame")
            continue
        file = OUT / path.removeprefix("/api/xbrl/")
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(json.dumps(trim_frame(raw, screen_ciks), separators=(",", ":")) + "\n")
        print(f"{path}: {file.stat().st_size // 1024} KB")

    (OUT / "getcurrent").mkdir(exist_ok=True)
    for form in FEED_FORMS:
        text = load_text(WWW_URL, getcurrent_path(form, FEED_COUNT), f"getcurrent_{form or 'all'}.atom")
        # The feed's <author> is a contact email; the repo carries none.
        text = re.sub(r"<author>.*?</author>\n?", "", text, flags=re.S)
        (OUT / "getcurrent" / f"{form or 'all'}.atom").write_text(text, encoding="iso-8859-1")
    (OUT / "submissions").mkdir(exist_ok=True)
    for row in tickers.values():
        if row["ticker"] in SUBMISSION_TICKERS:
            name = f"CIK{row['cik_str']:010d}.json"
            raw = load(DATA_URL, f"/submissions/{name}", f"submissions_{name}")
            (OUT / "submissions" / name).write_text(json.dumps(trim_submissions(raw), separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
