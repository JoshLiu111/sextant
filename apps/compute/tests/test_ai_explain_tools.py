"""AI Explain on every tool besides Options (one test per tool, stubbed model).

Each test checks the model was handed the server-side result of that tool:
its numbers, any metric the tool could not compute (with its reason), and,
for demo data, that the result is synthetic.
"""

from __future__ import annotations

import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from sextant_compute.data.synthetic import HISTORY_START
from tests.auth_helpers import bearer, sign_in
from tests.data_fixtures import serving
from tests.edgar_fixtures import edgar_adapter
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
