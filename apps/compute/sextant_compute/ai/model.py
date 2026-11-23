"""The language model behind AI Explain and AI Analyst: Claude, through the Anthropic Messages API.

Everything that talks to a model goes through ``ExplainModel.complete`` (one
prompt, one answer) or ``AnalystModel.converse`` (a tool-use conversation), so
tests swap in a stub (``app.state.ai_model``) and never reach the network.

Configuration (environment, compute service only):

- ``ANTHROPIC_API_KEY``: required. Without it every call raises ``ModelUnavailable``.
- ``AI_MODEL``: model id; defaults to ``DEFAULT_MODEL``.
- ``ANTHROPIC_BASE_URL``: tests only (e2e points it at ``e2e/fake-anthropic.mjs``).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from typing import NamedTuple, Protocol

import httpx

from sextant_compute.data.retry import get_with_retries

DEFAULT_MODEL = "claude-haiku-5-5"
DEFAULT_BASE_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"
# A real portfolio explanation runs to about 650 output tokens. Calls are few (the
# daily quota is small), so each gets plenty of room.
MAX_OUTPUT_TOKENS = 2000
ANALYST_MAX_OUTPUT_TOKENS = 3000
# claude-haiku-5-5 thinks by default, and thinking counts against max_tokens: on a
# real portfolio prompt it used the whole budget and left no answer (seen live
# 2026-11-23). Neither feature needs it, and the Analyst would otherwise have to
# send thinking blocks back with every tool result.
THINKING_OFF = {"type": "disabled"}


class Completion(NamedTuple):
    text: str
    input_tokens: int
    output_tokens: int


class Turn(NamedTuple):
    """One model reply in a tool-use conversation.

    ``content`` holds Messages API content blocks as JSON: ``{"type": "text", "text"}``
    and ``{"type": "tool_use", "id", "name", "input"}``. ``stop_reason`` is
    ``"tool_use"`` when the model wants the tools run, else e.g. ``"end_turn"``.
    """

    content: list[dict]
    stop_reason: str
    input_tokens: int
    output_tokens: int

    @property
    def text(self) -> str:
        return "".join(b["text"] for b in self.content if b.get("type") == "text").strip()

    @property
    def tool_uses(self) -> list[dict]:
        return [b for b in self.content if b.get("type") == "tool_use"]


class ModelUnavailable(Exception):
    """The model can't answer right now (not configured, outage, bad response)."""


class ExplainModel(Protocol):
    def complete(self, system: str, prompt: str) -> Completion: ...


class AnalystModel(Protocol):
    def converse(self, system: str, messages: list[dict], tools: list[dict], *, must_answer: bool) -> Turn:
        """The next assistant turn. With ``must_answer`` the model may not call a tool
        (the tools stay declared: the API requires them once the history holds tool calls)."""
        ...


class AnthropicModel:
    """Claude via ``POST /v1/messages``. Retries 429/5xx a couple of times."""

    def __init__(
        self,
        api_key: str | None,
        model: str = DEFAULT_MODEL,
        base_url: str = DEFAULT_BASE_URL,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._sleep = sleep

    @classmethod
    def from_env(cls, *, transport: httpx.BaseTransport | None = None) -> AnthropicModel:
        return cls(
            api_key=os.environ.get("ANTHROPIC_API_KEY") or None,
            model=os.environ.get("AI_MODEL") or DEFAULT_MODEL,
            base_url=os.environ.get("ANTHROPIC_BASE_URL") or DEFAULT_BASE_URL,
            transport=transport,
        )

    def complete(self, system: str, prompt: str) -> Completion:
        data = self._post(
            {
                "max_tokens": MAX_OUTPUT_TOKENS,
                "system": system,
                "messages": [{"role": "user", "content": prompt}],
            }
        )
        try:
            text = "".join(block["text"] for block in data["content"] if block.get("type") == "text")
            usage = data["usage"]
            completion = Completion(text.strip(), int(usage["input_tokens"]), int(usage["output_tokens"]))
        except (KeyError, TypeError) as exc:
            raise ModelUnavailable("Claude API returned an unexpected response") from exc
        if not completion.text:
            raise ModelUnavailable(f"Claude API returned no text (stop_reason {data.get('stop_reason')})")
        return completion

    def converse(self, system: str, messages: list[dict], tools: list[dict], *, must_answer: bool) -> Turn:
        body: dict = {"max_tokens": ANALYST_MAX_OUTPUT_TOKENS, "system": system, "messages": messages, "tools": tools}
        if must_answer:
            body["tool_choice"] = {"type": "none"}
        data = self._post(body)
        try:
            content = [
                {"type": "text", "text": b["text"]}
                if b["type"] == "text"
                else {"type": "tool_use", "id": b["id"], "name": b["name"], "input": b["input"]}
                for b in data["content"]
                if b.get("type") in ("text", "tool_use")
            ]
            usage = data["usage"]
            turn = Turn(content, str(data["stop_reason"]), int(usage["input_tokens"]), int(usage["output_tokens"]))
        except (KeyError, TypeError) as exc:
            raise ModelUnavailable("Claude API returned an unexpected response") from exc
        if not turn.text.strip() and not turn.tool_uses:
            raise ModelUnavailable(f"Claude API returned no text (stop_reason {turn.stop_reason})")
        return turn

    def _post(self, body: dict) -> dict:
        if not self._api_key:
            raise ModelUnavailable("ANTHROPIC_API_KEY is not set")
        body = {"model": self._model, "thinking": THINKING_OFF, **body}
        headers = {"x-api-key": self._api_key, "anthropic-version": API_VERSION}
        try:
            with httpx.Client(transport=self._transport, timeout=60.0) as http:
                response = get_with_retries(
                    lambda: http.post(f"{self._base_url}/v1/messages", json=body, headers=headers),
                    attempts=3,
                    backoff=1.0,
                    sleep=self._sleep,
                    retry_transport_errors=True,
                )
        except httpx.HTTPError as exc:
            raise ModelUnavailable(f"Claude API unreachable: {exc}") from exc
        if response.status_code != 200:
            raise ModelUnavailable(f"Claude API answered {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise ModelUnavailable("Claude API returned an unexpected response") from exc
        if not isinstance(data, dict):
            raise ModelUnavailable("Claude API returned an unexpected response")
        return data
