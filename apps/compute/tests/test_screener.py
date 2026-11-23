"""Screener (P7) API: fundamental screens on recorded EDGAR frames.

Fixture universe: 37 large caps (``SCREEN_TICKERS`` in
``scripts/record_edgar_fixtures.py``), frames CY2024/CY2025. Expected values are
read off the recorded frames by hand (USD), not recomputed by the code path.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from main import app
from tests.data_fixtures import serving
from tests.edgar_fixtures import edgar_adapter, edgar_transport

client = TestClient(app)
PATH = "/api/compute/screener/screen"


def screen(body: dict | None = None, adapter=None):
    with serving(adapter or edgar_adapter(), "sec_edgar"):
        return client.post(PATH, json={"year": 2025, **(body or {})})


def tickers(body: dict) -> list[str]:
    return [row["ticker"] for row in body["rows"]]


def test_the_default_screen_returns_matching_companies() -> None:
    res = screen()

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tool"] == "screener"
    assert body["source"] == {"id": "sec_edgar", "name": "SEC EDGAR", "is_demo": False}
    assert body["year"] == 2025
    assert [c["metric"] for c in body["criteria"]] == ["revenue_growth", "gross_margin", "roe"]
    assert body["rows"], "the default screen should match some companies"
    nvda = next(r for r in body["rows"] if r["ticker"] == "NVDA")
    assert nvda["name"] == "NVIDIA CORP"
    assert nvda["cik"] == 1045810
    # Revenues CY2025 215,938M (FY ended 2026-01-25) vs CY2024 130,497M.
    assert abs(nvda["values"]["revenue_growth"] - (215_938 / 130_497 - 1)) < 1e-9
    # GrossProfit 153,463M / revenue 215,938M; NetIncomeLoss 120,067M / StockholdersEquity 157,293M.
    assert abs(nvda["values"]["gross_margin"] - 153_463 / 215_938) < 1e-9
    assert abs(nvda["values"]["roe"] - 120_067 / 157_293) < 1e-9
    assert nvda["values"]["revenue"] == 215_938_000_000
    assert nvda["period_end"] == "2026-01-25"


def test_only_companies_meeting_every_criterion_are_returned() -> None:
    body = screen({"criteria": [{"metric": "gross_margin", "op": "min", "value": 0.75}], "sort": "gross_margin"}).json()

    # GrossProfit (or Revenue - Cost of Revenue) over revenue, CY2025, from the frames by hand.
    assert tickers(body) == ["CAT", "ADBE", "UNH", "LLY", "META"]
    assert body["matched"] == 5
    assert all(r["values"]["gross_margin"] >= 0.75 for r in body["rows"])


def test_max_criteria_and_several_criteria_combine() -> None:
    body = screen(
        {
            "criteria": [
                {"metric": "debt_ratio", "op": "max", "value": 0.4},
                {"metric": "current_ratio", "op": "min", "value": 2},
            ],
            "sort": "ticker",
            "direction": "asc",
        }
    ).json()

    assert tickers(body) == ["AMD", "GOOGL", "NVDA", "TSLA"]
    nvda = body["rows"][2]
    # Liabilities 49,510M / Assets 206,803M; AssetsCurrent 125,605M / LiabilitiesCurrent 32,163M.
    assert abs(nvda["values"]["debt_ratio"] - 49_510 / 206_803) < 1e-9
    assert abs(nvda["values"]["current_ratio"] - 125_605 / 32_163) < 1e-9
    assert [c["id"] for c in body["columns"]] == ["revenue", "debt_ratio", "current_ratio"]
    assert {c["id"]: c["unit"] for c in body["columns"]} == {
        "revenue": "currency",
        "debt_ratio": "decimal",
        "current_ratio": "ratio",
    }


def test_values_map_onto_the_unified_line_items_with_fallback_tags_and_derivations() -> None:
    body = screen(
        {
            "criteria": [
                {"metric": "gross_margin", "op": "min", "value": -10},
                {"metric": "debt_ratio", "op": "max", "value": 10},
            ],
            "limit": 500,
        }
    ).json()
    rows = {r["ticker"]: r["values"] for r in body["rows"]}

    # WMT tags neither GrossProfit nor Liabilities: Revenues 713,163M - CostOfRevenue 535,395M;
    # LiabilitiesAndStockholdersEquity 284,668M - equity incl. NCI 105,887M.
    assert rows["WMT"]["revenue"] == 713_163_000_000
    assert abs(rows["WMT"]["gross_margin"] - (713_163 - 535_395) / 713_163) < 1e-9
    assert abs(rows["WMT"]["debt_ratio"] - (284_668 - 105_887) / 284_668) < 1e-9
    # AAPL reports revenue under RevenueFromContractWithCustomerExcludingAssessedTax.
    assert rows["AAPL"]["revenue"] == 416_161_000_000


def test_a_derived_item_works_without_its_preferred_tag() -> None:
    body = screen({"criteria": [{"metric": "debt_ratio", "op": "min", "value": 1}], "sort": "ticker"}).json()
    rows = {r["ticker"]: r["values"] for r in body["rows"]}

    # MCD tags no Liabilities and has negative equity: 59,515M - (-1,791M), over assets 59,515M.
    assert abs(rows["MCD"]["debt_ratio"] - (59_515 + 1_791) / 59_515) < 1e-9


def test_companies_missing_an_input_are_excluded_and_counted_with_the_reason() -> None:
    body = screen(
        {
            "criteria": [
                {"metric": "gross_margin", "op": "min", "value": 0},
                {"metric": "roe", "op": "min", "value": 0},
            ]
        }
    ).json()

    assert body["universe"] == 37
    found = set(tickers(body))
    # No GrossProfit and no cost of revenue: banks, card networks, telecoms, ...
    no_gross = {"DIS", "JPM", "MA", "MCD", "ORCL", "T", "V", "VZ", "XOM"}
    assert not found & no_gross
    gross = next(e for e in body["excluded"]["by_criterion"] if e["metric"] == "gross_margin")
    assert gross["count"] == 9
    assert gross["label"] == "Gross margin"
    assert {"reason": "Gross Profit is not reported for 2025.", "count": 9} in gross["reasons"]
    roe = next(e for e in body["excluded"]["by_criterion"] if e["metric"] == "roe")
    # MCD has negative equity; XOM has no net income in the CY2025 frame.
    assert roe["count"] == 2
    assert {r["reason"] for r in roe["reasons"]} == {
        "Equity is zero or negative, so the ratio is not meaningful.",
        "Net Income is not reported for 2025.",
    }
    assert body["excluded"]["total"] == 9  # MCD and XOM are in both groups
    assert body["matched"] + body["excluded"]["total"] <= body["universe"]


def test_results_sort_by_any_column_in_either_direction() -> None:
    criteria = [{"metric": "roe", "op": "min", "value": 0.3}]

    by_roe = screen({"criteria": criteria, "sort": "roe", "direction": "desc"}).json()["rows"]
    roes = [r["values"]["roe"] for r in by_roe]
    assert roes == sorted(roes, reverse=True) and len(roes) > 3

    by_revenue = screen({"criteria": criteria, "sort": "revenue", "direction": "asc"}).json()["rows"]
    revenues = [r["values"]["revenue"] for r in by_revenue]
    assert revenues == sorted(revenues)

    by_ticker = tickers(screen({"criteria": criteria, "sort": "ticker", "direction": "asc"}).json())
    assert by_ticker == sorted(by_ticker)
    by_name = [r["name"] for r in screen({"criteria": criteria, "sort": "name", "direction": "desc"}).json()["rows"]]
    assert by_name == sorted(by_name, key=str.casefold, reverse=True)
    assert set(by_ticker) == {r["ticker"] for r in by_roe}


def test_the_default_sort_is_revenue_descending_and_limit_caps_the_rows() -> None:
    body = screen({"limit": 3}).json()

    assert tickers(body) == ["AMZN", "GOOGL", "MSFT"]
    assert body["matched"] == 9


def test_no_criteria_lists_every_company_with_revenue() -> None:
    body = screen({"criteria": [], "limit": 500}).json()

    assert body["matched"] == 36  # XOM has no revenue in the CY2025 frames
    assert "XOM" not in tickers(body)
    assert body["excluded"] == {"total": 0, "by_criterion": []}


def test_rows_without_the_sort_value_go_last() -> None:
    # XOM has balance-sheet frames but no CY2025 revenue.
    body = screen({"criteria": [{"metric": "debt_ratio", "op": "max", "value": 10}], "limit": 500}).json()

    assert body["rows"][-1]["ticker"] == "XOM"
    assert body["rows"][-1]["values"]["revenue"] is None
    assert body["rows"][-1]["period_end"] is None


def test_sorting_by_a_column_not_shown_is_rejected_inline() -> None:
    res = screen({"criteria": [{"metric": "roe", "op": "min", "value": 0}], "sort": "debt_ratio"})

    assert res.status_code == 422
    assert res.json()["error"]["fields"] == {"sort": "Sort by one of the columns shown."}


def test_invalid_criteria_are_rejected_with_field_messages() -> None:
    res = screen({"criteria": [{"metric": "market_cap", "op": "min", "value": "x"}]})

    assert res.status_code == 422
    fields = res.json()["error"]["fields"]
    assert fields["criteria.0.metric"] == "Choose one of the listed options."
    assert fields["criteria.0.value"] == "Enter a number."


def test_too_many_criteria_and_years_out_of_range_are_rejected() -> None:
    many = [{"metric": "roe", "op": "min", "value": 0}] * 9
    res = screen({"criteria": many, "year": 1990})

    assert res.status_code == 422
    fields = res.json()["error"]["fields"]
    assert fields["criteria"] == "Use at most 8 criteria."
    assert fields["year"].startswith("Choose a year between 2009 and")


def test_the_default_year_can_be_pinned(monkeypatch) -> None:
    monkeypatch.setenv("SCREENER_DEFAULT_YEAR", "2025")
    with serving(edgar_adapter(), "sec_edgar"):
        body = client.post(PATH, json={}).json()

    assert body["year"] == 2025
    assert body["default_year"] == 2025
    assert body["frames"] == {"flow": "CY2025", "balance": "CY2025Q4I"}


def test_frames_are_fetched_with_the_user_agent_and_cached_per_line_item() -> None:
    transport = edgar_transport()
    with serving(edgar_adapter(transport), "sec_edgar"):
        client.post(PATH, json={"year": 2025})
        first = len(transport.requests)
        # Same screen, another sort: everything from cache.
        client.post(PATH, json={"year": 2025, "sort": "ticker"})
        assert len(transport.requests) == first
        # A new criterion fetches only its own items' frames.
        client.post(PATH, json={"year": 2025, "criteria": [{"metric": "current_ratio", "op": "min", "value": 1}]})

    frames = [r for r in transport.requests if "/frames/" in r.url.path]
    assert frames and all(r.headers["user-agent"] == "Sextant test admin@example.com" for r in frames)
    later = [r.url.path.split("/")[5] for r in transport.requests[first:] if "/frames/" in r.url.path]
    assert sorted(later) == ["AssetsCurrent", "LiabilitiesCurrent"]
    assert "/api/xbrl/frames/us-gaap/Revenues/USD/CY2024.json" in transport.paths()
    assert "/api/xbrl/frames/us-gaap/StockholdersEquity/USD/CY2025Q4I.json" in transport.paths()


def test_concurrent_screens_on_a_cold_cache_download_each_frame_once() -> None:
    transport = edgar_transport(on_request=lambda _r: time.sleep(0.01))
    with serving(edgar_adapter(transport), "sec_edgar"), ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.post(PATH, json={"year": 2025}), range(4)))

    assert all(r.status_code == 200 for r in results)
    assert len({tuple(tickers(r.json())) for r in results}) == 1
    frames = [p for p in transport.paths() if "/frames/" in p]
    assert len(frames) == len(set(frames))


def test_an_edgar_outage_is_a_503() -> None:
    res = screen(adapter=edgar_adapter(edgar_transport(status=503)))

    assert res.status_code == 503
    assert res.json()["error"]["code"] == "source_unavailable"
