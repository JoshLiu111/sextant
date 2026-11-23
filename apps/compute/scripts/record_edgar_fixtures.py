"""Record trimmed SEC EDGAR responses as test fixtures (tests/fixtures/edgar/).

Run by hand when the fixtures need refreshing; tests never touch the network::

    SEC_USER_AGENT="Sextant dev admin@example.com" uv run python -m scripts.record_edgar_fixtures

Use a generic User-Agent; never commit a real contact. ``--raw-dir DIR`` trims
responses you already downloaded (``company_tickers.json``, ``CIK##########.json``)
instead of fetching.

Trimming keeps the files small but real (values are never edited):
- ``company_tickers.json``: only the rows for ``TICKERS``.
- companyfacts: ``cik``, ``entityName``, and for every tag named in
  ``line_items.toml`` only annual-report facts (10-K family) filed since
  ``SINCE``. ``description`` texts are dropped.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from sextant_compute.data.edgar.client import DATA_URL, WWW_URL, EdgarClient
from sextant_compute.data.edgar.mapping import line_items

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "edgar"
# AAPL/MSFT: different revenue tags. JPM: a bank (no COGS, no current assets).
# WMT: no GrossProfit or Liabilities tags (derived), custom EPS tags.
TICKERS = ["AAPL", "MSFT", "JPM", "WMT"]
EXTRA_TICKER_ROWS = ["GOOGL", "GOOG", "BRK-B"]  # ticker-map shapes only, no companyfacts
ANNUAL_FORMS = {"10-K", "10-K/A", "10-KT", "20-F", "40-F"}
SINCE = "2016-01-01"


def trim_tickers(raw: dict) -> dict:
    wanted = set(TICKERS) | set(EXTRA_TICKER_ROWS)
    rows = [row for row in raw.values() if row["ticker"] in wanted]
    return {str(i): row for i, row in enumerate(rows)}


def trim_companyfacts(raw: dict) -> dict:
    wanted: dict[str, set[str]] = {}
    for spec in line_items():
        for tag in spec.tags:
            wanted.setdefault(tag.taxonomy, set()).add(tag.name)
    facts: dict[str, dict] = {}
    for taxonomy, names in wanted.items():
        for name in sorted(names):
            concept = raw.get("facts", {}).get(taxonomy, {}).get(name)
            if concept is None:
                continue
            units = {}
            for unit, rows in concept["units"].items():
                kept = [r for r in rows if r.get("form") in ANNUAL_FORMS and r.get("filed", "") >= SINCE]
                if kept:
                    units[unit] = kept
            if units:
                facts.setdefault(taxonomy, {})[name] = {"label": concept.get("label"), "units": units}
    return {"cik": raw["cik"], "entityName": raw["entityName"], "facts": facts}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path)
    args = parser.parse_args()
    client = None if args.raw_dir else EdgarClient()

    def load(host: str, path: str) -> dict:
        if args.raw_dir:
            return json.loads((args.raw_dir / Path(path).name).read_text())
        assert client is not None
        return client.get_json(host, path)

    OUT.mkdir(parents=True, exist_ok=True)
    tickers = trim_tickers(load(WWW_URL, "/files/company_tickers.json"))
    (OUT / "company_tickers.json").write_text(json.dumps(tickers, indent=1) + "\n")
    for row in tickers.values():
        if row["ticker"] not in TICKERS:
            continue
        name = f"CIK{row['cik_str']:010d}.json"
        trimmed = trim_companyfacts(load(DATA_URL, f"/api/xbrl/companyfacts/{name}"))
        (OUT / name).write_text(json.dumps(trimmed, separators=(",", ":")) + "\n")
        print(f"{row['ticker']}: {name} ({(OUT / name).stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
