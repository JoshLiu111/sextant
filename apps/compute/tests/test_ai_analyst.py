"""AI Analyst (stories 86-88, 91): questions answered through tool use.

The model is a scripted stub (``ScriptedModel``): each turn is a function of the
conversation so far, so a turn can quote the calculation a tool call returned.
No test reaches the network.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

import psycopg
import pytest
from fastapi.testclient import TestClient

from sextant_compute.ai.model import ModelUnavailable, Turn
from sextant_compute.data.synthetic import HISTORY_END, HISTORY_START
from tests.auth_helpers import bearer, sign_in

ASK = "/api/compute/ai/analyst"
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
RISK = {
    "tickers": ["DEMO-A"],
    "benchmark": "DEMO-MKT",
    "start": HISTORY_START.isoformat(),
    "end": HISTORY_END.isoformat(),
}

Script = Callable[[list[dict]], Turn]


def tool_use(name: str, arguments: dict, call_id: str = "toolu_1") -> Turn:
    return Turn([{"type": "tool_use", "id": call_id, "name": name, "input": arguments}], "tool_use", 500, 40)


def answer(text: str) -> Turn:
    return Turn([{"type": "text", "text": text}], "end_turn", 900, 120)


def tool_results(messages: list[dict]) -> list[dict]:
    """The tool_result blocks the service sent back in its latest message."""
    return [b for b in messages[-1]["content"] if b["type"] == "tool_result"]


def last_result(messages: list[dict]) -> dict:
    return json.loads(tool_results(messages)[-1]["content"])


@dataclass
class ScriptedModel:
    """Stands in for Claude: plays ``script`` turn by turn and records every request."""

    script: list[Script] = field(default_factory=list)
    fail: bool = False
    requests: list[dict] = field(default_factory=list)

    def converse(self, system: str, messages: list[dict], tools: list[dict], *, must_answer: bool) -> Turn:
        self.requests.append(
            {"system": system, "messages": json.loads(json.dumps(messages)), "tools": tools, "must_answer": must_answer}
        )
        if self.fail:
            raise ModelUnavailable("stubbed outage")
        return self.script[len(self.requests) - 1](messages)


@pytest.fixture
def model(client: TestClient) -> ScriptedModel:
    stub = ScriptedModel()
    client.app.state.ai_model = stub
    return stub


def ask(client: TestClient, token: str, question: str = "What is this call worth?"):
    return client.post(ASK, json={"question": question}, headers=bearer(token))


def quoting_call_price(written: Callable[[float], str]) -> Script:
    def turn(messages: list[dict]) -> Turn:
        result = last_result(messages)
        value = result["metrics"]["call_price"]["value"]
        return answer(f"The call is worth [[{written(value)}|{result['calculation_id']}|call_price]] per share.")

    return turn


def prices_the_option_then(final: Script) -> list[Script]:
    return [lambda _: tool_use("options_price", OPTIONS), final]


def test_anonymous_questions_are_rejected(client: TestClient, model):
    assert client.post(ASK, json={"question": "Hi"}).status_code == 401
    assert model.requests == []


def test_the_compute_endpoints_are_offered_as_tools_with_typed_parameters(client, model):
    model.script = [lambda _: answer("Nothing to compute.")]
    token = sign_in(client)

    assert ask(client, token).status_code == 200

    tools = {t["name"]: t for t in model.requests[0]["tools"]}
    assert {
        "options_price",
        "options_strategy",
        "options_american",
        "risk_metrics",
        "portfolio_metrics",
        "company_statements",
        "company_ratios",
        "valuation_dcf",
        "macro_indicators",
        "treasury_rates",
        "screen_companies",
        "sec_filings",
    } <= set(tools)
    options = tools["options_price"]
    assert options["description"]
    schema = options["input_schema"]
    assert schema["type"] == "object"
    assert schema["properties"]["volatility"]["type"] == "number"
    assert set(schema["properties"]["option_type"]["enum"]) == {"call", "put"}
    # Nested models are inlined: no $ref the model would have to resolve.
    assert "$ref" not in json.dumps([t["input_schema"] for t in tools.values()])


def test_the_model_picks_a_tool_sextant_runs_it_and_the_answer_cites_the_calculation(client, model):
    model.script = prices_the_option_then(quoting_call_price(lambda v: f"{v:.2f}"))
    token = sign_in(client)

    response = ask(client, token)

    assert response.status_code == 200, response.text
    body = response.json()
    # The trace: which tool, with which parameters, giving which calculation.
    [call] = body["calls"]
    assert call["tool"] == "options_price"
    assert call["input"] == OPTIONS
    assert call["error"] is None
    calc_id = call["calculation_id"]
    # The raw result of that calculation comes with the answer.
    raw = body["calculations"][calc_id]
    assert raw["tool"] == "options"
    assert raw["metrics"]["call_price"]["value"] == pytest.approx(10.4506, abs=1e-4)
    # The model got the result as the tool's answer.
    sent = last_result(model.requests[1]["messages"])
    assert sent["calculation_id"] == calc_id
    # The answer, split into text and checked citations.
    text, cited, rest = body["answer"]
    assert text == {"type": "text", "text": "The call is worth "}
    assert cited["type"] == "citation"
    assert cited["text"] == "10.45"
    assert cited["calculation_id"] == calc_id
    assert cited["metric"] == "call_price"
    assert cited["actual"] == pytest.approx(10.4506, abs=1e-4)
    assert cited["matches"] is True
    assert rest == {"type": "text", "text": " per share."}


@pytest.mark.parametrize("written", ["10.4", "12.00", "1,045", "$9.99"])
def test_a_misquoted_number_is_flagged(client, model, written):
    model.script = prices_the_option_then(quoting_call_price(lambda _: written))
    token = sign_in(client)

    cited = ask(client, token).json()["answer"][1]

    assert cited["text"] == written
    assert cited["matches"] is False
    assert cited["actual"] == pytest.approx(10.4506, abs=1e-4)


@pytest.mark.parametrize("written", ["10", "10.5", "10.45", "$10.451", "10.4506"])
def test_a_rounded_quote_matches_at_the_precision_it_is_written(client, model, written):
    model.script = prices_the_option_then(quoting_call_price(lambda _: written))
    token = sign_in(client)

    assert ask(client, token).json()["answer"][1]["matches"] is True


def risk_answer(metric: str, written: str) -> Script:
    def turn(messages: list[dict]) -> Turn:
        calc = last_result(messages)["calculation_id"]
        return answer(f"Volatility is [[{written}|{calc}|{metric}]].")

    return turn


def test_percentages_are_read_against_the_metric_unit(client, model):
    token = sign_in(client)
    model.script = [lambda _: tool_use("risk_metrics", RISK), lambda m: answer(json.dumps(last_result(m)))]
    raw = json.loads(ask(client, token).json()["answer"][0]["text"])
    vol = raw["metrics"]["annualized_volatility:DEMO-A"]
    assert vol["unit"] == "decimal"
    pct = f"{vol['value'] * 100:.1f}%"

    model.requests.clear()
    model.script = [lambda _: tool_use("risk_metrics", RISK), risk_answer("annualized_volatility:DEMO-A", pct)]
    right = ask(client, token).json()["answer"][1]
    model.requests.clear()
    model.script = [
        lambda _: tool_use("risk_metrics", RISK),
        risk_answer("annualized_volatility:DEMO-A", f"{vol['value'] * 100:.1f}"),  # 18.3 for 0.183
    ]
    wrong = ask(client, token).json()["answer"][1]

    assert right["matches"] is True
    assert wrong["matches"] is False


def test_citations_of_unknown_calculations_or_metrics_are_flagged(client, model):
    def turn(messages: list[dict]) -> Turn:
        calc = last_result(messages)["calculation_id"]
        return answer(f"A [[10.45|calc_madeup|call_price]] B [[10.45|{calc}|no_such_metric]].")

    model.script = prices_the_option_then(turn)
    token = sign_in(client)

    citations = [s for s in ask(client, token).json()["answer"] if s["type"] == "citation"]

    assert [(c["matches"], c["actual"]) for c in citations] == [(False, None), (False, None)]
    assert citations[0]["reason"] == "No calculation with this id was run for this answer."
    assert citations[1]["reason"] == "This calculation has no metric no_such_metric."


def test_invalid_tool_input_goes_back_to_the_model_as_an_error_and_is_traced(client, model):
    def retry(messages: list[dict]) -> Turn:
        [result] = tool_results(messages)
        assert result["is_error"] is True
        assert "Volatility must be greater than 0%" in result["content"]
        return tool_use("options_price", OPTIONS, "toolu_2")

    model.script = [lambda _: tool_use("options_price", OPTIONS | {"volatility": -1}), retry, quoting_call_price(str)]
    token = sign_in(client)

    body = ask(client, token).json()

    failed, ok = body["calls"]
    assert failed["calculation_id"] is None
    assert "volatility: Volatility must be greater than 0% and at most 500%." in failed["error"]
    assert ok["calculation_id"] in body["calculations"]
    assert len(body["calculations"]) == 1


def test_an_unknown_tool_is_reported_to_the_model(client, model):
    def recover(messages: list[dict]) -> Turn:
        [result] = tool_results(messages)
        assert result["is_error"] is True
        return answer("I could not run that.")

    model.script = [lambda _: tool_use("delete_everything", {}), recover]
    token = sign_in(client)

    body = ask(client, token).json()

    assert body["calls"][0]["tool"] == "delete_everything"
    assert body["calls"][0]["calculation_id"] is None


def test_the_model_must_answer_after_the_last_tool_round(client, model):
    model.script = [lambda _: tool_use("options_price", OPTIONS, f"toolu_{i}") for i in range(5)]
    model.script.append(lambda _: answer("Done."))
    token = sign_in(client)

    body = ask(client, token).json()

    assert [r["must_answer"] for r in model.requests] == [False] * 5 + [True]
    # The tools stay declared (the history holds tool calls); the model just may not call them.
    assert model.requests[-1]["tools"] == model.requests[0]["tools"]
    assert len(body["calls"]) == len(model.requests) - 1
    assert body["answer"] == [{"type": "text", "text": "Done."}]


def quota(client: TestClient, token: str) -> dict:
    return client.get(QUOTA, headers=bearer(token)).json()


def test_one_question_uses_one_unit_of_the_shared_daily_quota(client, model, monkeypatch):
    monkeypatch.setenv("AI_DAILY_QUOTA", "1")
    model.script = prices_the_option_then(quoting_call_price(str))
    token = sign_in(client)

    first = ask(client, token)
    refused = ask(client, token)

    assert first.json()["quota"]["remaining"] == 0
    assert refused.status_code == 429
    assert refused.json()["error"]["code"] == "quota_exceeded"
    # AI Explain draws on the same quota.
    explain = client.post("/api/compute/ai/explain/options", json=OPTIONS, headers=bearer(token))
    assert explain.status_code == 429


def test_each_question_is_logged_once_with_the_tokens_of_every_round(client, model, db_url):
    model.script = prices_the_option_then(quoting_call_price(str))
    token = sign_in(client)
    user_id = client.get("/api/compute/me", headers=bearer(token)).json()["id"]

    body = ask(client, token).json()

    assert body["usage"] == {"input_tokens": 1400, "output_tokens": 160}
    with psycopg.connect(db_url, row_factory=psycopg.rows.dict_row) as conn:
        rows = conn.execute("SELECT user_id::text, tool, input_tokens, output_tokens FROM ai_usage").fetchall()
    assert rows == [{"user_id": user_id, "tool": "analyst", "input_tokens": 1400, "output_tokens": 160}]


def test_a_model_outage_is_reported_and_costs_nothing(client, model):
    model.fail = True
    token = sign_in(client)

    response = ask(client, token)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_unavailable"
    assert quota(client, token)["used"] == 0


def fails_billing(input_tokens: int, output_tokens: int) -> Script:
    def turn(_messages: list[dict]) -> Turn:
        raise ModelUnavailable("stubbed: no text", input_tokens, output_tokens)

    return turn


def test_a_question_that_fails_after_paid_rounds_logs_their_tokens_but_costs_no_quota(client, model, db_url):
    # Round 1 calls a tool (500 in, 40 out); round 2 is billed (900 in, 3000 out) but unusable.
    model.script = prices_the_option_then(fails_billing(900, 3000))
    token = sign_in(client)

    response = ask(client, token)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "ai_unavailable"
    assert quota(client, token)["used"] == 0
    with psycopg.connect(db_url, row_factory=psycopg.rows.dict_row) as conn:
        rows = conn.execute("SELECT tool, status, input_tokens, output_tokens FROM ai_usage").fetchall()
    assert rows == [{"tool": "analyst", "status": "failed", "input_tokens": 1400, "output_tokens": 3040}]


def test_an_unexpected_error_midway_also_logs_the_tokens_spent_and_costs_no_quota(client, model, db_url):
    def crashes(_messages: list[dict]) -> Turn:
        raise RuntimeError("stubbed bug")

    model.script = prices_the_option_then(crashes)
    token = sign_in(client)

    with pytest.raises(RuntimeError):
        ask(client, token)

    assert quota(client, token)["used"] == 0
    with psycopg.connect(db_url, row_factory=psycopg.rows.dict_row) as conn:
        rows = conn.execute("SELECT status, input_tokens, output_tokens FROM ai_usage").fetchall()
    assert rows == [{"status": "failed", "input_tokens": 500, "output_tokens": 40}]


@pytest.mark.parametrize("question", ["", "   ", "x" * 2001])
def test_an_empty_or_overlong_question_is_rejected_and_costs_nothing(client, model, question):
    token = sign_in(client)

    response = ask(client, token, question)

    assert response.status_code == 422
    assert "question" in response.json()["error"]["fields"]
    assert model.requests == []
    assert quota(client, token)["used"] == 0


def test_answers_that_touch_on_buying_or_selling_carry_the_not_advice_notice(client, model):
    model.script = [lambda _: answer("You might buy it.")]
    token = sign_in(client)

    body = ask(client, token).json()

    assert body["advice_notice"].startswith("This is only a reading of the calculation")
    assert "not investment advice" in model.requests[0]["system"].lower()
