"""Valuation Calculator (P2) API: FCF DCF, WACC breakdown and sensitivity table.

Hand-computed cases run on a tiny company (round numbers in one fiscal year),
served in place of MSFT's companyfacts; the rest run on the recorded fixtures.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from main import app
from tests.data_fixtures import serving
from tests.edgar_fixtures import CIKS, edgar_adapter, edgar_transport, load_facts, without_tags

client = TestClient(app)
PATH = "/api/compute/valuation/dcf"
M = 1_000_000

# One fiscal year, FY2025 (2024-07-01 .. 2025-06-30), in USD millions.
TINY = {
    "NetCashProvidedByUsedInOperatingActivities": 120,
    "PaymentsToAcquirePropertyPlantAndEquipment": 20,  # FCF = 100
    "CashAndCashEquivalentsAtCarryingValue": 50,
    "DebtCurrent": 10,
    "LongTermDebtNoncurrent": 40,  # total debt = 50
    "CommonStockSharesOutstanding": 10,  # millions of shares
    "InterestExpense": 4,  # cost of debt = 4 / 50 = 8%
    "IncomeTaxExpenseBenefit": 21,
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": 100,  # tax 21%
    "StockholdersEquity": 150,  # book equity
}
INSTANTS = {
    "CashAndCashEquivalentsAtCarryingValue",
    "DebtCurrent",
    "LongTermDebtNoncurrent",
    "CommonStockSharesOutstanding",
    "StockholdersEquity",
}


def tiny_facts(values: dict[str, float] = TINY) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    for tag, val in values.items():
        row: dict[str, Any] = {
            "end": "2025-06-30",
            "val": val * M,
            "accn": "0000789019-25-000001",
            "fy": 2025,
            "fp": "FY",
            "form": "10-K",
            "filed": "2025-07-30",
        }
        if tag not in INSTANTS:
            row["start"] = "2024-07-01"
        unit = "shares" if tag == "CommonStockSharesOutstanding" else "USD"
        facts[tag] = {"label": tag, "units": {unit: [row]}}
    return {"cik": CIKS["MSFT"], "entityName": "TINY CO", "facts": {"us-gaap": facts}}


def post_tiny(body: dict[str, Any], facts: dict[str, Any] | None = None):
    adapter = edgar_adapter(edgar_transport(facts_override={"MSFT": facts or tiny_facts()}))
    with serving(adapter, "sec_edgar"):
        return client.post(PATH, json={"ticker": "MSFT", **body})


def values(body: dict[str, Any], *ids: str) -> list[float | None]:
    return [body["metrics"][i]["value"] for i in ids]


def test_dcf_matches_a_hand_computed_example() -> None:
    # FCF0 = 100. g = 10%, r = 10%, g_inf = 0, N = 2:
    # CF1 = 110 -> PV 100; CF2 = 121 -> PV 100; TV = 121 / 0.10 = 1210 -> PV 1000.
    # EV = 1200; equity = 1200 + cash 50 - debt 50 = 1200; per share = 1200 / 10 = 120.
    res = post_tiny({"growth_rate": 0.10, "terminal_growth": 0.0, "discount_rate": 0.10, "forecast_years": 2})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["tool"] == "valuation"
    assert body["source"]["id"] == "sec_edgar"
    assert values(body, "free_cash_flow", "cash", "total_debt", "shares_outstanding") == [
        100 * M,
        50 * M,
        50 * M,
        10 * M,
    ]
    assert body["metrics"]["pv_forecast_fcf"]["value"] == pytest.approx(200 * M, rel=1e-12)
    assert body["metrics"]["pv_terminal_value"]["value"] == pytest.approx(1000 * M, rel=1e-12)
    assert body["metrics"]["enterprise_value"]["value"] == pytest.approx(1200 * M, rel=1e-12)
    assert body["metrics"]["equity_value"]["value"] == pytest.approx(1200 * M, rel=1e-12)
    assert body["metrics"]["intrinsic_value_per_share"]["value"] == pytest.approx(120, rel=1e-12)
    assert body["metrics"]["intrinsic_value_per_share"]["unit"] == "per_share"
    projected = [(p["x"], p["y"]) for p in body["series"]["projected_fcf"]["points"]]
    assert projected == [(1, pytest.approx(110 * M)), (2, pytest.approx(121 * M))]


def test_wacc_breakdown_is_derived_from_the_statements_and_capm() -> None:
    # Re = 4% + 1.2 x 5% = 10%. Rd = 4 / 50 = 8%. t = 21 / 100 = 21%.
    # D/V = 50 / (150 book equity + 50) = 25%. WACC = 0.75 x 10% + 0.25 x 8% x 0.79 = 9.08%.
    res = post_tiny({"risk_free_rate": 0.04, "beta": 1.2, "equity_risk_premium": 0.05})

    assert res.status_code == 200, res.text
    m = res.json()["metrics"]
    assert m["cost_of_equity"]["value"] == pytest.approx(0.10)
    assert m["cost_of_debt"]["value"] == pytest.approx(0.08)
    assert m["tax_rate"]["value"] == pytest.approx(0.21)
    assert m["after_tax_cost_of_debt"]["value"] == pytest.approx(0.0632)
    assert m["debt_weight"]["value"] == pytest.approx(0.25)
    assert m["equity_weight"]["value"] == pytest.approx(0.75)
    assert m["wacc"]["value"] == pytest.approx(0.0908)
    assert m["discount_rate"]["value"] == pytest.approx(0.0908)
    assert m["wacc"]["unit"] == "decimal"
    assert m["cost_of_debt"]["details"]["basis"] == "derived"


def test_any_wacc_component_can_be_overridden() -> None:
    # Re 12%, Rd 6%, t 25%, D/V 40%: WACC = 0.6 x 12% + 0.4 x 6% x 0.75 = 9%.
    res = post_tiny({"cost_of_equity": 0.12, "cost_of_debt": 0.06, "tax_rate": 0.25, "debt_weight": 0.4})

    m = res.json()["metrics"]
    assert m["wacc"]["value"] == pytest.approx(0.09)
    assert m["cost_of_equity"]["details"]["basis"] == "override"
    assert m["equity_weight"]["value"] == pytest.approx(0.6)


def test_a_share_price_sets_the_market_value_of_equity_for_the_weights() -> None:
    # E = $30 x 10M shares = 300; D/V = 50 / 350.
    res = post_tiny({"share_price": 30})

    assert res.json()["metrics"]["debt_weight"]["value"] == pytest.approx(50 / 350)


def test_the_sensitivity_center_cell_equals_the_base_case() -> None:
    res = post_tiny({"growth_rate": 0.10, "terminal_growth": 0.0, "discount_rate": 0.10, "forecast_years": 2})

    body = res.json()
    grid = body["sensitivity"]
    assert grid["growth_rates"] == pytest.approx([0.08, 0.09, 0.10, 0.11, 0.12])
    assert grid["discount_rates"] == pytest.approx([0.09, 0.095, 0.10, 0.105, 0.11])
    center = body["metrics"]["sensitivity:2:2"]
    assert center["value"] == body["metrics"]["intrinsic_value_per_share"]["value"]
    assert center["value"] == pytest.approx(120)
    # Higher growth is worth more; a higher discount rate is worth less.
    assert body["metrics"]["sensitivity:3:2"]["value"] > center["value"] > body["metrics"]["sensitivity:2:3"]["value"]


def test_sensitivity_cells_at_or_below_terminal_growth_are_errors() -> None:
    res = post_tiny({"discount_rate": 0.04, "terminal_growth": 0.035})

    m = res.json()["metrics"]
    assert m["sensitivity:2:0"]["status"] == "error"  # 3% discount rate
    assert "must be below the discount rate" in m["sensitivity:2:0"]["reason"]
    assert m["sensitivity:2:2"]["status"] == "ok"


def test_terminal_growth_at_or_above_an_entered_discount_rate_is_a_field_error() -> None:
    res = post_tiny({"discount_rate": 0.03, "terminal_growth": 0.03})

    assert res.status_code == 422
    assert res.json()["error"]["fields"] == {"terminal_growth": "Terminal growth must be below the discount rate."}


def test_terminal_growth_at_or_above_the_wacc_is_an_error_on_the_results() -> None:
    # Re = 1% (override), WACC = 0.75 x 1% + 0.25 x 8% x 0.79 = 2.33% < 2.5% terminal growth.
    res = post_tiny({"cost_of_equity": 0.01, "terminal_growth": 0.025})

    assert res.status_code == 200, res.text
    m = res.json()["metrics"]
    assert m["wacc"]["status"] == "ok"
    for key in ("enterprise_value", "intrinsic_value_per_share"):
        assert m[key]["status"] == "error"
        assert m[key]["reason"] == "Terminal growth (2.50%) must be below the discount rate (2.33%)."


def test_out_of_range_inputs_are_reported_per_field() -> None:
    res = post_tiny({"forecast_years": 0, "growth_rate": 3, "debt_weight": 1, "beta": None})

    assert res.status_code == 422
    fields = res.json()["error"]["fields"]
    assert fields["forecast_years"] == "Choose between 1 and 20 years."
    assert fields["growth_rate"] == "Enter a growth rate between -50% and 100%."
    assert fields["debt_weight"] == "Enter a debt weight from 0% up to (not including) 100%."
    assert "beta" in fields


def test_missing_fcf_inputs_show_missing_data_naming_the_item() -> None:
    facts = without_tags(load_facts("MSFT"), "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment")
    res = post_tiny({}, facts)

    m = res.json()["metrics"]
    assert m["free_cash_flow"]["status"] == "missing_data"
    assert m["free_cash_flow"]["reason"].startswith("Capital Expenditure is not reported by this company")
    assert m["intrinsic_value_per_share"]["status"] == "missing_data"
    assert m["intrinsic_value_per_share"]["reason"] == m["free_cash_flow"]["reason"]
    assert m["sensitivity:2:2"]["status"] == "missing_data"
    assert m["wacc"]["status"] == "ok"  # the rest still renders


def test_a_company_without_interest_expense_needs_a_cost_of_debt_override() -> None:
    with serving(edgar_adapter(), "sec_edgar"):
        derived = client.post(PATH, json={"ticker": "AAPL"}).json()["metrics"]
        overridden = client.post(PATH, json={"ticker": "AAPL", "cost_of_debt": 0.04}).json()["metrics"]

    assert derived["cost_of_debt"]["status"] == "missing_data"
    assert derived["cost_of_debt"]["reason"] == "Interest Expense is not reported by this company for FY2026."
    assert derived["wacc"]["status"] == "missing_data"
    assert overridden["intrinsic_value_per_share"]["status"] == "ok"


def test_the_default_ticker_values_msft_from_its_latest_10k() -> None:
    with serving(edgar_adapter(), "sec_edgar"):
        res = client.post(PATH, json={})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["company"]["ticker"] == "MSFT"
    assert body["base_period"]["label"] == "FY2026"
    assert body["meta"]["data_cutoff"] == body["base_period"]["filed"]
    m = body["metrics"]
    # FCF = OCF 182,935M - capex 115,948M (MSFT 10-K FY2026).
    assert m["free_cash_flow"]["value"] == 66_987_000_000
    assert m["free_cash_flow"]["details"]["url"].startswith("https://www.sec.gov/Archives/edgar/data/789019/")
    assert m["total_debt"]["value"] == 9_227_000_000 + 31_067_000_000
    for key in ("wacc", "enterprise_value", "intrinsic_value_per_share", "sensitivity:2:2"):
        assert m[key]["status"] == "ok", m[key]
    assert m["sensitivity:2:2"]["value"] == m["intrinsic_value_per_share"]["value"]
    assert [p["x"] for p in body["series"]["historical_fcf"]["points"]][-1] == "2026-06-30"
    assert len(body["series"]["historical_fcf"]["points"]) == 5


def test_an_unknown_ticker_is_a_field_error() -> None:
    with serving(edgar_adapter(), "sec_edgar"):
        res = client.post(PATH, json={"ticker": "ZZZZ"})

    assert res.status_code == 422
    assert "ZZZZ" in res.json()["error"]["fields"]["ticker"]


def test_an_edgar_outage_is_a_503() -> None:
    with serving(edgar_adapter(edgar_transport(status=503)), "sec_edgar"):
        res = client.post(PATH, json={})

    assert res.status_code == 503
    assert res.json()["error"]["code"] == "source_unavailable"
