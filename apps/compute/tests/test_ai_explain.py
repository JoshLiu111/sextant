"""AI Explain (story 85, 89-91): a plain-English reading of a tool's result.

The model is always a stub here (``StubModel``); no test reaches the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import psycopg
import pytest
from fastapi.testclient import TestClient

from sextant_compute.ai.model import AnthropicModel, Completion, ModelUnavailable
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
    billed_on_failure: tuple[int, int] = (0, 0)
    """Tokens a failed call was still billed for (e.g. a reply with no text)."""
    prompts: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, system: str, prompt: str) -> Completion:
        self.prompts.append((system, prompt))
        if self.fail:
            raise ModelUnavailable("stubbed outage", *self.billed_on_failure)
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


def quota(client: TestClient, token: str) -> dict:
    response = client.get(QUOTA, headers=bearer(token))
    assert response.status_code == 200, response.text
    return response.json()


def test_each_call_uses_one_unit_of_the_daily_quota(client, model, monkeypatch):
    monkeypatch.setenv("AI_DAILY_QUOTA", "3")
    token = sign_in(client)
    assert quota(client, token) | {"resets_at": None} == {"limit": 3, "used": 0, "remaining": 3, "resets_at": None}

    first = explain(client, token).json()
    second = explain(client, token).json()

    assert first["quota"]["remaining"] == 2
    assert second["quota"]["remaining"] == 1
    assert quota(client, token)["remaining"] == 1
    assert quota(client, token)["resets_at"].endswith("T00:00:00Z")


def test_calls_over_the_daily_quota_are_refused_with_a_clear_message(client, model, monkeypatch):
    monkeypatch.setenv("AI_DAILY_QUOTA", "2")
    token = sign_in(client)
    explain(client, token)
    explain(client, token)

    refused = explain(client, token)

    assert refused.status_code == 429
    error = refused.json()["error"]
    assert error["code"] == "quota_exceeded"
    assert error["message"] == (
        "You have used all 2 AI Explain calls for today. Your quota resets at 00:00 UTC."
    )
    assert len(model.prompts) == 2  # the model is never asked once the quota is used up
    assert quota(client, token)["remaining"] == 0


def test_the_quota_is_per_user(client, model, monkeypatch):
    monkeypatch.setenv("AI_DAILY_QUOTA", "1")
    alice = sign_in(client, "sub-alice", email="alice@example.test")
    bob = sign_in(client, "sub-bob", email="bob@example.test")
    explain(client, alice)

    assert explain(client, alice).status_code == 429
    assert quota(client, bob)["remaining"] == 1
    assert explain(client, bob).status_code == 200


def test_calls_from_earlier_days_do_not_count_against_today(client, model, db_url, monkeypatch):
    monkeypatch.setenv("AI_DAILY_QUOTA", "1")
    token = sign_in(client)
    user_id = client.get("/api/compute/me", headers=bearer(token)).json()["id"]
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO ai_usage (user_id, tool, input_tokens, output_tokens, created_at)"
            " VALUES (%s, 'options', 10, 10, now() - interval '1 day')",
            (user_id,),
        )

    assert quota(client, token)["remaining"] == 1
    assert explain(client, token).status_code == 200


def test_invalid_inputs_get_the_tools_own_field_errors_and_cost_nothing(client, model):
    token = sign_in(client)

    response = explain(client, token, OPTIONS | {"volatility": -0.1})

    assert response.status_code == 422
    assert response.json()["error"]["fields"] == {
        "volatility": "Volatility must be greater than 0% and at most 500%."
    }
    assert model.prompts == []
    assert quota(client, token)["used"] == 0


def test_a_model_outage_is_reported_and_costs_nothing(client, model):
    model.fail = True
    token = sign_in(client)

    response = explain(client, token)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_unavailable"
    assert quota(client, token)["used"] == 0


def usage_log(db_url: str) -> list[dict]:
    with psycopg.connect(db_url, row_factory=psycopg.rows.dict_row) as conn:
        return conn.execute("SELECT tool, status, input_tokens, output_tokens FROM ai_usage").fetchall()


def test_a_failed_call_is_logged_with_the_tokens_it_cost_but_not_charged(client, model, db_url, monkeypatch):
    monkeypatch.setenv("AI_DAILY_QUOTA", "1")
    model.fail, model.billed_on_failure = True, (2400, 700)
    token = sign_in(client)

    assert explain(client, token).status_code == 503

    assert usage_log(db_url) == [{"tool": "options", "status": "failed", "input_tokens": 2400, "output_tokens": 700}]
    assert quota(client, token)["used"] == 0
    model.fail = False
    assert explain(client, token).status_code == 200


def test_every_call_is_logged_with_its_user_tool_tokens_and_time(client, model, db_url):
    token = sign_in(client)
    user_id = client.get("/api/compute/me", headers=bearer(token)).json()["id"]

    body = explain(client, token).json()

    assert body["usage"] == {"input_tokens": 1200, "output_tokens": 180}
    with psycopg.connect(db_url, row_factory=psycopg.rows.dict_row) as conn:
        rows = conn.execute(
            "SELECT user_id::text, tool, status, input_tokens, output_tokens,"
            " now() - created_at < interval '1 minute' AS recent FROM ai_usage"
        ).fetchall()
    assert rows == [
        {
            "user_id": user_id,
            "tool": "options",
            "status": "ok",
            "input_tokens": 1200,
            "output_tokens": 180,
            "recent": True,
        }
    ]


def test_answers_that_touch_on_buying_or_selling_carry_the_not_advice_notice(client, model):
    token = sign_in(client)
    model.reply = "A trader might buy this call if they expect the stock to rise."

    trading = explain(client, token).json()
    model.reply = "Delta of 0.64 means the call gains about 64 cents per $1 rise in the stock."
    neutral = explain(client, token).json()

    assert trading["advice_notice"] == (
        "This is only a reading of the calculation, not investment advice "
        "or a recommendation to buy or sell anything."
    )
    assert neutral["advice_notice"] is None


def test_without_an_api_key_ai_explain_is_unavailable(client, monkeypatch):
    # The real Claude client, as configured from an environment with no key.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    client.app.state.ai_model = AnthropicModel.from_env()
    token = sign_in(client)

    response = explain(client, token)

    assert response.status_code == 503
    assert response.json()["error"]["message"] == "AI Explain is temporarily unavailable. Please retry in a moment."
