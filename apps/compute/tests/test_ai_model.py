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
    turn = AnthropicModel("k", transport=fake(handler)).converse("system", messages, tools)

    assert turn.stop_reason == "tool_use"
    assert turn.tool_uses == [{"type": "tool_use", "id": "toolu_01", "name": "options_price", "input": {"spot": 100}}]
    assert turn.text == "Let me price it."
    assert (turn.input_tokens, turn.output_tokens) == (1500, 60)
    assert seen[0]["tools"] == tools
    assert seen[0]["messages"] == messages
    assert seen[0]["system"] == "system"


def test_a_conversation_without_tools_sends_no_tools_field():
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json=REPLY)

    turn = AnthropicModel("k", transport=fake(handler)).converse("s", [{"role": "user", "content": "q"}], None)

    assert "tools" not in seen[0]
    assert turn.tool_uses == []
    assert turn.text == "The call is worth 10.45."
