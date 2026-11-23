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
