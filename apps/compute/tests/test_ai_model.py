"""The Claude client behind AI Explain, against a recorded-shape fake transport (no network)."""

from __future__ import annotations

import json

import httpx
import pytest

from sextant_compute.ai.model import AnthropicModel, Completion, ModelUnavailable

# The shape of a Messages API response (docs.anthropic.com/en/api/messages).
REPLY = {
    "id": "msg_01",
    "type": "message",
    "role": "assistant",
    "model": "claude-test",
    "content": [{"type": "text", "text": "  The call is worth 10.45.  "}],
    "stop_reason": "end_turn",
    "usage": {"input_tokens": 812, "output_tokens": 95},
}


def fake(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_sends_the_key_from_the_environment_and_returns_text_and_token_counts(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setenv("AI_MODEL", "claude-test")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "http://claude.invalid")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=REPLY)

    model = AnthropicModel.from_env(transport=fake(handler))

    assert model.complete("system text", "user text") == Completion("The call is worth 10.45.", 812, 95)
    request = seen[0]
    assert str(request.url) == "http://claude.invalid/v1/messages"
    assert request.headers["x-api-key"] == "test-key-not-real"
    assert request.headers["anthropic-version"] == "2023-06-01"
    body = json.loads(request.content)
    assert body["model"] == "claude-test"
    assert body["system"] == "system text"
    assert body["messages"] == [{"role": "user", "content": "user text"}]


def test_retries_overload_and_then_reports_the_model_unavailable():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(529, json={"type": "error", "error": {"type": "overloaded_error"}})

    model = AnthropicModel("k", transport=fake(handler), sleep=lambda _s: None)

    with pytest.raises(ModelUnavailable):
        model.complete("s", "p")
    assert calls == 3


def test_a_rejected_key_is_reported_as_unavailable_without_retrying():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(401, json={"type": "error", "error": {"type": "authentication_error"}})

    with pytest.raises(ModelUnavailable):
        AnthropicModel("bad", transport=fake(handler), sleep=lambda _s: None).complete("s", "p")
    assert calls == 1


TOOL_REPLY = {
    "id": "msg_02",
    "type": "message",
    "role": "assistant",
    "model": "claude-test",
    "content": [
        {"type": "text", "text": "Let me price it."},
        {"type": "tool_use", "id": "toolu_01", "name": "options_price", "input": {"spot": 100}},
    ],
    "stop_reason": "tool_use",
    "usage": {"input_tokens": 1500, "output_tokens": 60},
}


def test_a_tool_use_conversation_sends_the_tools_and_returns_the_tool_calls():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=TOOL_REPLY)

    tools = [{"name": "options_price", "description": "d", "input_schema": {"type": "object", "properties": {}}}]
    messages = [{"role": "user", "content": "What is the call worth?"}]
    turn = AnthropicModel("k", transport=fake(handler)).converse("system", messages, tools, must_answer=False)

    assert turn.stop_reason == "tool_use"
    assert turn.tool_uses == [{"type": "tool_use", "id": "toolu_01", "name": "options_price", "input": {"spot": 100}}]
    assert turn.text == "Let me price it."
    assert (turn.input_tokens, turn.output_tokens) == (1500, 60)
    assert seen[0]["tools"] == tools
    assert seen[0]["messages"] == messages
    assert seen[0]["system"] == "system"
    assert "tool_choice" not in seen[0]


def test_a_turn_that_must_answer_keeps_the_tools_declared_but_forbids_calling_them():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=REPLY)

    tools = [{"name": "t", "description": "d", "input_schema": {"type": "object", "properties": {}}}]
    turn = AnthropicModel("k", transport=fake(handler)).converse(
        "s", [{"role": "user", "content": "q"}], tools, must_answer=True
    )

    assert seen[0]["tools"] == tools
    assert seen[0]["tool_choice"] == {"type": "none"}
    assert turn.tool_uses == []
    assert turn.text == "The call is worth 10.45."


# Seen live on 2026-11-23: claude-haiku-5-5 thinks by default, and on a real
# portfolio prompt the thinking used the whole output budget, so the reply held
# only a thinking block and AI Explain showed an empty explanation.
THINKING_ONLY_REPLY = {
    **REPLY,
    "content": [{"type": "thinking", "thinking": "", "signature": "sig"}],
    "stop_reason": "max_tokens",
    "usage": {"input_tokens": 2400, "output_tokens": 700},
}


def test_explain_and_analyst_requests_turn_thinking_off():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=REPLY)

    model = AnthropicModel("k", transport=fake(handler))
    model.complete("s", "p")
    model.converse("s", [{"role": "user", "content": "q"}], [], must_answer=True)

    assert [body["thinking"] for body in seen] == [{"type": "disabled"}] * 2


def test_a_reply_without_any_text_is_reported_as_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=THINKING_ONLY_REPLY)

    model = AnthropicModel("k", transport=fake(handler))

    with pytest.raises(ModelUnavailable):
        model.complete("s", "p")
    with pytest.raises(ModelUnavailable):
        model.converse("s", [{"role": "user", "content": "q"}], [], must_answer=True)


def test_an_unusable_reply_still_reports_the_tokens_it_was_billed_for():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=THINKING_ONLY_REPLY)

    model = AnthropicModel("k", transport=fake(handler))

    with pytest.raises(ModelUnavailable) as explain:
        model.complete("s", "p")
    with pytest.raises(ModelUnavailable) as analyst:
        model.converse("s", [{"role": "user", "content": "q"}], [], must_answer=True)

    for raised in (explain.value, analyst.value):
        assert (raised.input_tokens, raised.output_tokens) == (2400, 700)


def test_a_failed_request_reports_no_tokens():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"type": "error", "error": {"type": "authentication_error"}})

    with pytest.raises(ModelUnavailable) as raised:
        AnthropicModel("bad", transport=fake(handler)).complete("s", "p")

    assert (raised.value.input_tokens, raised.value.output_tokens) == (0, 0)
