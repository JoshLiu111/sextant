"""The language model behind AI Explain: Claude, through the Anthropic Messages API.

Everything that talks to a model goes through ``ExplainModel.complete``, so tests
swap in a stub (``app.state.ai_model``) and never reach the network.

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
MAX_OUTPUT_TOKENS = 700


class Completion(NamedTuple):
    text: str
    input_tokens: int
    output_tokens: int


class ModelUnavailable(Exception):
    """The model can't answer right now (not configured, outage, bad response)."""


class ExplainModel(Protocol):
    def complete(self, system: str, prompt: str) -> Completion: ...


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
        if not self._api_key:
            raise ModelUnavailable("ANTHROPIC_API_KEY is not set")
        body = {
            "model": self._model,
            "max_tokens": MAX_OUTPUT_TOKENS,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {"x-api-key": self._api_key, "anthropic-version": API_VERSION}
        try:
            with httpx.Client(transport=self._transport, timeout=30.0) as http:
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
            text = "".join(block["text"] for block in data["content"] if block.get("type") == "text")
            usage = data["usage"]
            return Completion(text.strip(), int(usage["input_tokens"]), int(usage["output_tokens"]))
        except (ValueError, KeyError, TypeError) as exc:
            raise ModelUnavailable("Claude API returned an unexpected response") from exc
