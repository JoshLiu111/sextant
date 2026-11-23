"""Company Health Check (P1) ratios and Altman Z on recorded EDGAR fixtures.

Expected values are hand-computed from the 10-K figures (USD millions), e.g.
AAPL FY2026 (ended 2026-09-26): current assets 173,857, current liabilities
169,915, total assets 404,548 (FY2025: 359,241), revenue 478,834.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from pytest import approx

from main import app
from sextant_compute.analytics.ratios import RATIOS, Year
from sextant_compute.data.context import RequestContext
from sextant_compute.envelope import metric
from tests.data_fixtures import serving
from tests.edgar_fixtures import edgar_adapter, edgar_transport, load_facts, without_tags

client = TestClient(app)
PATH = "/api/compute/company/ratios"
AAPL_FY26 = "2026-09-26"
AAPL_FY25 = "2025-09-27"
RATIOS_BY_ID = {r.id: r for r in RATIOS}


def post(body: dict | None = None, adapter=None):
    with serving(adapter or edgar_adapter(), "sec_edgar"):
        return client.post(PATH, json=body if body is not None else {})


def m(body: dict, ratio: str, ticker: str, period: str) -> dict:
    return body["metrics"][f"{ratio}:{ticker}:{period}"]


def test_the_default_ticker_gets_five_years_of_every_category() -> None:
    res = post()

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tool"] == "company"
    assert body["source"]["id"] == "sec_edgar"
    [company] = body["companies"]
    assert company["ticker"] == "AAPL"
    assert company["name"] == "Apple Inc."
    assert [p["label"] for p in company["periods"]] == ["FY2022", "FY2023", "FY2024", "FY2025", "FY2026"]
    assert {r["category"] for r in body["ratios"]} == {
        "efficiency",
        "liquidity",
        "profitability",
        "solvency",
        "valuation",
    }
    for category in ("efficiency", "liquidity", "profitability", "solvency", "valuation"):
        count = len([r for r in body["ratios"] if r["category"] == category])
        assert 5 <= count <= 10, category
    # Every ratio has a value (or a reason) for every displayed year.
    for r in body["ratios"]:
        for p in company["periods"]:
            assert f"{r['id']}:AAPL:{p['id']}" in body["metrics"]


def test_key_ratios_match_hand_computed_values() -> None:
    body = post({"companies": [{"ticker": "AAPL"}]}).json()

    current = m(body, "current_ratio", "AAPL", AAPL_FY26)
    assert current["status"] == "ok"
    assert current["value"] == approx(173_857 / 169_915)  # 1.0232
    assert current["unit"] == "ratio"
    # Balance-sheet denominators are averaged with the prior year.
    assert m(body, "asset_turnover", "AAPL", AAPL_FY26)["value"] == approx(1.253838, rel=1e-6)
    assert m(body, "return_on_equity", "AAPL", AAPL_FY26)["value"] == approx(1.422567, rel=1e-6)
    assert m(body, "return_on_equity", "AAPL", AAPL_FY26)["unit"] == "decimal"
    assert m(body, "operating_margin", "AAPL", AAPL_FY26)["value"] == approx(0.330100, rel=1e-5)
    assert m(body, "days_sales_outstanding", "AAPL", AAPL_FY26)["value"] == approx(31.8605, rel=1e-5)
    assert m(body, "days_sales_outstanding", "AAPL", AAPL_FY26)["unit"] == "days"
    assert m(body, "days_inventory_outstanding", "AAPL", AAPL_FY26)["value"] == approx(15.0766, rel=1e-5)
    assert m(body, "days_payables_outstanding", "AAPL", AAPL_FY26)["value"] == approx(113.2007, rel=1e-5)
    assert m(body, "cash_conversion_cycle", "AAPL", AAPL_FY26)["value"] == approx(
        31.8605 + 15.0766 - 113.2007, abs=1e-3
    )
    # Total debt = current debt 9,906 + long-term debt 68,208; equity 112,093.
    assert m(body, "debt_to_equity", "AAPL", AAPL_FY26)["value"] == approx(0.696868, rel=1e-6)
    assert m(body, "book_value_per_share", "AAPL", AAPL_FY26)["value"] == approx(112_093e6 / 14_532_259_000)
    assert m(body, "book_value_per_share", "AAPL", AAPL_FY26)["unit"] == "per_share"


def test_altman_z_matches_a_hand_computation_and_names_its_zone() -> None:
    body = post().json()

    z = m(body, "altman_z", "AAPL", AAPL_FY26)
    # Z' = 0.717·WC/TA + 0.847·RE/TA + 3.107·EBIT/TA + 0.420·Equity/TL + 0.998·Sales/TA
    assert z["status"] == "ok"
    assert z["value"] == approx(2.591861, rel=1e-6)
    assert z["details"]["zone"] == "grey"


def test_several_companies_are_compared_on_the_same_ratios() -> None:
    body = post({"companies": [{"ticker": "AAPL"}, {"ticker": "msft"}, {"ticker": "JPM"}], "years": 3}).json()

    assert [c["ticker"] for c in body["companies"]] == ["AAPL", "MSFT", "JPM"]
    assert [p["label"] for p in body["companies"][1]["periods"]] == ["FY2024", "FY2025", "FY2026"]
    for c in body["companies"]:
        last = c["periods"][-1]["id"]
        assert m(body, "net_margin", c["ticker"], last)["status"] == "ok"


def test_a_bank_without_current_items_gets_missing_data_naming_them() -> None:
    body = post({"companies": [{"ticker": "JPM"}]}).json()

    current = m(body, "current_ratio", "JPM", "2025-12-31")
    assert current["status"] == "missing_data"
    assert "Current Assets" in current["reason"]
    z = m(body, "altman_z", "JPM", "2025-12-31")
    assert z["status"] == "missing_data"
    assert "Current Assets" in z["reason"]
    assert m(body, "return_on_assets", "JPM", "2025-12-31")["status"] == "ok"


def test_a_missing_line_item_affects_only_the_ratios_that_need_it() -> None:
    facts = without_tags(load_facts("AAPL"), "us-gaap:InventoryNet")
    body = post(adapter=edgar_adapter(edgar_transport(facts_override={"AAPL": facts}))).json()

    for ratio in ("inventory_turnover", "days_inventory_outstanding", "cash_conversion_cycle"):
        result = m(body, ratio, "AAPL", AAPL_FY26)
        assert result["status"] == "missing_data", ratio
        assert result["reason"] == "Inventory is not reported by this company."
    affected = {
        k for k, v in body["metrics"].items() if k.endswith(AAPL_FY26) and v["status"] != "ok"
    }
    baseline = post().json()
    before = {k for k, v in baseline["metrics"].items() if k.endswith(AAPL_FY26) and v["status"] != "ok"}
    newly_missing = {k.split(":")[0] for k in affected - before}
    assert newly_missing == {"inventory_turnover", "days_inventory_outstanding", "cash_conversion_cycle"}


def test_the_earliest_displayed_year_averages_with_the_year_before_it() -> None:
    body = post({"companies": [{"ticker": "AAPL"}], "years": 10}).json()

    first = body["companies"][0]["periods"][0]
    assert first["label"] == "FY2017"
    # FY2017 revenue 229,234 / average of FY2016 (321,686) and FY2017 (375,319) total assets.
    assert m(body, "asset_turnover", "AAPL", first["id"])["value"] == approx(229_234 / ((321_686 + 375_319) / 2))


def test_without_a_prior_year_only_the_averaged_ratios_are_missing() -> None:
    statements = edgar_adapter().financial_statements(RequestContext(user_id=None, keys={}), "AAPL").last(1)
    year = Year(statements, 0)

    turnover = metric(lambda: RATIOS_BY_ID["asset_turnover"].compute(year))
    assert turnover.status == "missing_data"
    assert turnover.reason == (
        "Needs the prior year's Total Assets for the average balance, and FY2026 is the earliest year in the data."
    )
    assert metric(lambda: RATIOS_BY_ID["net_margin"].compute(year)).status == "ok"


def test_valuation_multiples_need_a_price() -> None:
    body = post().json()

    pe = m(body, "price_to_earnings", "AAPL", AAPL_FY26)
    assert pe["status"] == "missing_data"
    assert "price" in pe["reason"].lower()
    assert m(body, "book_value_per_share", "AAPL", AAPL_FY26)["status"] == "ok"


def test_a_user_supplied_price_values_the_latest_fiscal_year() -> None:
    body = post({"companies": [{"ticker": "AAPL", "price": 250}]}).json()

    assert m(body, "price_to_earnings", "AAPL", AAPL_FY26)["value"] == approx(250 / 8.98)
    assert m(body, "price_to_book", "AAPL", AAPL_FY26)["value"] == approx(32.411165, rel=1e-6)
    # Market cap = 250 × 14,532,259,000 shares; P/S = market cap / revenue 478,834.
    assert m(body, "price_to_sales", "AAPL", AAPL_FY26)["value"] == approx(
        250 * 14_532_259_000 / 478_834e6
    )
    earlier = m(body, "price_to_earnings", "AAPL", AAPL_FY25)
    assert earlier["status"] == "missing_data"
    assert "latest fiscal year" in earlier["reason"]


def test_input_validation() -> None:
    res = post({"companies": [{"ticker": " ", "price": -1}], "years": 0})

    assert res.status_code == 422
    fields = res.json()["error"]["fields"]
    assert fields["companies.0.ticker"] == "Enter a ticker."
    assert fields["companies.0.price"] == "Price must be greater than 0."
    assert fields["years"] == "Choose between 1 and 10 years."

    too_many = post({"companies": [{"ticker": t} for t in ["A", "B", "C", "D", "E", "F"]]})
    assert too_many.json()["error"]["fields"]["companies"] == "Compare at most 5 companies."
    dupes = post({"companies": [{"ticker": "AAPL"}, {"ticker": "aapl"}]})
    assert dupes.json()["error"]["fields"]["companies.1.ticker"] == "AAPL is already in the list."


def test_an_unknown_ticker_is_an_inline_error_on_its_row() -> None:
    res = post({"companies": [{"ticker": "AAPL"}, {"ticker": "ZZZZ"}]})

    assert res.status_code == 422
    error = res.json()["error"]
    assert error["code"] == "no_such_data"
    assert "Unknown ticker ZZZZ" in error["fields"]["companies.1.ticker"]


def test_an_edgar_outage_is_source_unavailable() -> None:
    res = post(adapter=edgar_adapter(edgar_transport(status=503)))

    assert res.status_code == 503
    assert res.json()["error"]["code"] == "source_unavailable"
