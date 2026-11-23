"""AI Explain (story 85, 89-91): a plain-English reading of a tool's result.

The model is always a stub here (``StubModel``); no test reaches the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from fastapi.testclient import TestClient

from sextant_compute.ai.model import Completion, ModelUnavailable
from tests.auth_helpers import bearer, sign_in

EXPLAIN = "/api/compute/ai/explain/options"
QUOTA = "/api/compute/ai/quota"
OPTIONS = {
    "spot": 100,
    "strike": 100,
    "time_to_expiry": 1,
    "volatility": 0.2,
    "risk_free_rate": 0.05,
    "dividend_yield": 0,
    "option_type": "call",
}


@dataclass
class StubModel:
    """Stands in for Claude: records each prompt and answers ``reply``."""

    reply: str = "The call is worth about 10.45 under these inputs."
    input_tokens: int = 1200
    output_tokens: int = 180
    fail: bool = False
    prompts: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, system: str, prompt: str) -> Completion:
        self.prompts.append((system, prompt))
        if self.fail:
            raise ModelUnavailable("stubbed outage")
        return Completion(self.reply, self.input_tokens, self.output_tokens)


@pytest.fixture
def model(client: TestClient) -> StubModel:
    stub = StubModel()
    client.app.state.ai_model = stub
    return stub


def explain(client: TestClient, token: str, body: dict | None = None):
    return client.post(EXPLAIN, json=body or OPTIONS, headers=bearer(token))


def test_anonymous_requests_are_rejected(client: TestClient):
    assert client.post(EXPLAIN, json=OPTIONS).status_code == 401
    assert client.get(QUOTA).status_code == 401


def test_a_signed_in_user_gets_an_explanation_of_the_calculated_result(client, model):
    token = sign_in(client)

    response = explain(client, token)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["explanation"] == model.reply
    assert body["tool"] == "options"
    assert body["calculation_id"].startswith("calc_")
    # The model saw the server-side result envelope: the BS call price for these
    # inputs is 10.4506 (Hull, Example 15.6 style textbook value).
    system, prompt = model.prompts[0]
    assert "10.45" in prompt
    assert "call_price" in prompt
    assert "not investment advice" in system.lower()
