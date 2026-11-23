"""AI Explain on every tool besides Options (one test per tool, stubbed model).

Each test checks the model was handed the server-side result of that tool:
its numbers, any metric the tool could not compute (with its reason), and,
for demo data, that the result is synthetic.
"""

from __future__ import annotations

import json
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from sextant_compute.data.synthetic import HISTORY_START
from tests.auth_helpers import bearer, sign_in
from tests.data_fixtures import serving
from tests.edgar_fixtures import edgar_adapter
from tests.fred_fixtures import SERIES_DOES_NOT_EXIST, RecordedFred
from tests.fred_fixtures import recorded_adapter as recorded_fred
from tests.treasury_fixtures import recorded_adapter as recorded_treasury
from tests.test_ai_explain import StubModel

# About 40 trading days: too few returns for a 99.9% VaR.
SHORT_HISTORY = {"start": HISTORY_START.isoformat(), "end": (HISTORY_START + timedelta(days=60)).isoformat()}


@pytest.fixture
def model(client: TestClient) -> StubModel:
    stub = StubModel(reply="A plain reading.")
    client.app.state.ai_model = stub
    return stub


def explain(client: TestClient, tool: str, body: dict, token: str | None = None) -> dict:
    response = client.post(
        f"/api/compute/ai/explain/{tool}", json=body, headers=bearer(token or sign_in(client))
    )
    assert response.status_code == 200, response.text
    out = response.json()
    assert out["tool"] == tool
    assert out["explanation"] == "A plain reading."
    return out


def shown(model: StubModel) -> tuple[str, dict]:
    """The prompt and the result envelope the model was shown (parsed back out of the prompt)."""
    [(_system, prompt)] = model.prompts
    result = json.loads(prompt.split("Result (JSON):\n", 1)[1].split("\n\nExplain this result.", 1)[0])
    return prompt, result


def assert_demo_framing(model: StubModel, prompt: str) -> None:
    assert "synthetic demo data" in prompt
    assert "demo data" in model.prompts[0][0].lower()


def test_risk_explains_the_demo_result_as_demo_data(client, model):
    out = explain(client, "risk", {"tickers": ["DEMO-A"], **SHORT_HISTORY, "confidence": 0.999})

    prompt, result = shown(model)
    assert result["calculation_id"] == out["calculation_id"]
    assert result["tool"] == "risk"
    assert result["source"]["is_demo"] is True
    assert result["metrics"]["annualized_volatility:DEMO-A"]["status"] == "ok"
    var = result["metrics"]["var:DEMO-A"]
    assert var["status"] == "missing_data"
    assert "needs at least 1000 daily returns" in var["reason"]
    assert_demo_framing(model, prompt)


def test_my_portfolio_explains_the_demo_portfolio(client, model):
    holdings = [{"ticker": "DEMO-A", "weight": 0.6}, {"ticker": "DEMO-B", "weight": 0.4}]

    explain(client, "portfolio", {"holdings": holdings, **SHORT_HISTORY, "confidence": 0.999})

    prompt, result = shown(model)
    assert result["tool"] == "portfolio"
    assert result["meta"]["parameters"]["holdings"] == holdings
    assert result["metrics"]["annualized_volatility:portfolio"]["status"] == "ok"
    assert result["metrics"]["var:portfolio"]["status"] == "missing_data"
    assert "needs at least 1000 daily returns" in result["metrics"]["var:portfolio"]["reason"]
    assert_demo_framing(model, prompt)


SAVED = {
    "name": "Retirement",
    "holdings": [
        {"ticker": "DEMO-A", "quantity": 10, "cost_price": 95.5, "currency": "USD"},
        {"ticker": "DEMO-B", "quantity": 2.5, "cost_price": 40, "currency": "USD"},
    ],
}


def test_my_portfolio_explains_a_saved_portfolio_of_its_owner_only(client, model):
    alice = sign_in(client, "sub-alice", email="alice@example.test")
    bob = sign_in(client, "sub-bob", email="bob@example.test")
    saved = client.post("/api/compute/portfolios", json=SAVED, headers=bearer(alice)).json()
    body = {"portfolio_id": saved["id"], **SHORT_HISTORY}

    explain(client, "portfolio-saved", body, token=alice)

    prompt, result = shown(model)
    assert result["tool"] == "portfolio"
    assert result["meta"]["parameters"]["name"] == "Retirement"
    assert result["metrics"]["market_value:portfolio"]["status"] == "ok"
    assert result["metrics"]["cost_basis:portfolio"]["value"] == pytest.approx(10 * 95.5 + 2.5 * 40)
    assert_demo_framing(model, prompt)
    # Someone else's portfolio is not found, and costs nothing.
    other = client.post("/api/compute/ai/explain/portfolio-saved", json=body, headers=bearer(bob))
    assert other.status_code == 404
    assert client.get("/api/compute/ai/quota", headers=bearer(bob)).json()["used"] == 0


@pytest.fixture
def edgar(client):
    with serving(edgar_adapter(), "sec_edgar", on=client.app):
        yield


def assert_real_data(model: StubModel, prompt: str, result: dict) -> None:
    assert result["source"]["is_demo"] is False
    assert "synthetic demo data" not in prompt


def test_company_health_check_explains_the_statements(client, model, edgar):
    explain(client, "company", {"ticker": "JPM"})

    prompt, result = shown(model)
    assert result["tool"] == "company"
    assert result["company"]["ticker"] == "JPM"
    assert result["metrics"]["net_income:2025-12-31"]["status"] == "ok"
    cogs = result["metrics"]["cost_of_revenue:2025-12-31"]
    assert cogs["status"] == "missing_data"
    assert cogs["reason"] == "Cost of Revenue is not reported by this company."
    assert_real_data(model, prompt, result)
    # The filing links behind each cell are left out: the model only needs the numbers.
    assert "sec.gov/Archives" not in prompt
    assert len(prompt) < 40_000


def test_company_health_check_explains_the_ratios(client, model, edgar):
    explain(client, "company-ratios", {"companies": [{"ticker": "AAPL"}, {"ticker": "MSFT"}]})

    prompt, result = shown(model)
    assert result["tool"] == "company"
    assert [c["ticker"] for c in result["companies"]] == ["AAPL", "MSFT"]
    assert result["metrics"]["current_ratio:AAPL:2026-09-26"]["status"] == "ok"
    pe = result["metrics"]["price_to_earnings:AAPL:2026-09-26"]
    assert pe["status"] == "missing_data"
    assert "price" in pe["reason"].lower()
    assert_real_data(model, prompt, result)


def test_valuation_explains_the_dcf(client, model, edgar):
    explain(client, "valuation", {"ticker": "AAPL"})

    prompt, result = shown(model)
    assert result["tool"] == "valuation"
    assert result["company"]["ticker"] == "AAPL"
    assert result["metrics"]["free_cash_flow"]["status"] == "ok"
    cost_of_debt = result["metrics"]["cost_of_debt"]
    assert cost_of_debt["status"] == "missing_data"
    assert cost_of_debt["reason"] == "Interest Expense is not reported by this company for FY2026."
    assert "growth_rates" in result["sensitivity"]
    assert_real_data(model, prompt, result)


def test_macro_dashboard_explains_the_headline_indicators(client, model):
    # FRED has no unemployment series today: that indicator is missing_data, the rest still show.
    fred = RecordedFred(
        override=lambda path, sid: httpx.Response(400, json=SERIES_DOES_NOT_EXIST) if sid == "UNRATE" else None
    )
    with serving(recorded_fred(fred), "fred", on=client.app):
        explain(client, "macro", {})

    prompt, result = shown(model)
    assert result["tool"] == "macro"
    assert result["metrics"]["latest:gdp_growth"]["value"] == 2.3
    assert result["metrics"]["latest:gdp_growth"]["details"]["date"] == "2026-07-01"
    unemployment = result["metrics"]["latest:unemployment_rate"]
    assert unemployment["status"] == "missing_data"
    assert unemployment["reason"]
    assert len(result["series"]["history:cpi_inflation"]["points"]) == 11  # thinned for the prompt
    assert_real_data(model, prompt, result)


def test_macro_dashboard_explains_the_treasury_rates(client, model):
    with serving(recorded_treasury(), "treasury", on=client.app):
        explain(client, "macro-rates", {"end": "2026-11-22"})

    prompt, result = shown(model)
    assert result["tool"] == "macro"
    assert result["metrics"]["latest:yield_10y"]["value"] == 4.92
    assert result["metrics"]["latest:yield_2y"]["value"] == 4.63
    assert result["metrics"]["latest:spread_10y_2y"]["value"] == pytest.approx(0.29)
    assert result["series"]["yield_curve:latest"]["details"]["date"] == "2026-11-20"
    assert result["series"]["history:spread_10y_2y"]["bands"], "the inversion periods reach the model"
    assert_real_data(model, prompt, result)


def test_screener_explains_the_screen_and_its_exclusions(client, model, edgar):
    explain(client, "screener", {"year": 2025})

    prompt, result = shown(model)
    assert result["tool"] == "screener"
    assert [c["metric"] for c in result["criteria"]] == ["revenue_growth", "gross_margin", "roe"]
    assert "NVDA" in [r["ticker"] for r in result["rows"]]
    assert result["matched"] == len(result["rows"])
    assert result["excluded"]["total"] > 0
    assert result["excluded"]["by_criterion"][0]["reasons"]
    assert_real_data(model, prompt, result)


def test_a_long_screen_shows_the_model_the_top_rows_and_the_full_count(client, model, edgar):
    explain(client, "screener", {"year": 2025, "criteria": [{"metric": "revenue", "op": "min", "value": 0}]})

    _prompt, result = shown(model)
    assert len(result["rows"]) == 25
    assert result["matched"] > 25


def test_screener_explains_the_latest_filings(client, model, edgar):
    explain(client, "screener-filings", {"ticker": "AAPL"})

    prompt, result = shown(model)
    assert result["tool"] == "screener"
    assert result["scope"] == "company"
    assert result["filings"] and all(f["company"] for f in result["filings"])
    assert_real_data(model, prompt, result)
