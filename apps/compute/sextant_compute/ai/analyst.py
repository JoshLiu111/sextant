"""AI Analyst: ``POST /api/compute/ai/analyst`` with ``{"question": str}``. Signed-in users only.

The model picks Sextant's tools (``ai/tools.py``) and their parameters; Sextant
runs them and sends back the result envelopes; the model then writes the answer,
citing each number as ``[[number|calculation_id|metric id]]``. The response
carries the answer split into text and checked citations (``ai/citations.py``),
the tool-call trace, and the raw result of every calculation run.

One question costs one unit of the daily AI quota shared with AI Explain (usage
row tool ``"analyst"``, tokens summed over every round); a failed model call
costs nothing.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, BeforeValidator

from sextant_compute.ai import prompts, tools, usage
from sextant_compute.ai.citations import Segment, check_answer, plain_text
from sextant_compute.ai.model import AnalystModel, ModelUnavailable, Turn
from sextant_compute.auth import CurrentUser
from sextant_compute.auth.deps import get_db
from sextant_compute.data.context import RequestContext
from sextant_compute.data.service import Ctx, Data, DataService
from sextant_compute.db import Database
from sextant_compute.envelope import ResultEnvelope
from sextant_compute.errors import ApiError, check

router = APIRouter(tags=["ai"])

USAGE_TOOL = "analyst"
MAX_QUESTION_CHARS = 2000
MAX_TOOL_ROUNDS = 5
"""Rounds in which the model may call tools; after that it must answer."""
UNAVAILABLE_MESSAGE = "AI Analyst is temporarily unavailable. Please retry in a moment."

SYSTEM = """\
You are AI Analyst in Sextant, a suite of finance tools. You answer the user's question \
by calling Sextant's tools and explaining their results in plain English.

Rules:
- Get every figure from a tool result. Never invent, estimate, recall or look up numbers \
yourself. If the tools can't answer the question, say so.
- Call the tools you need (several at once is fine), then answer. Use each tool's defaults \
unless the question says otherwise.
- Cite every number you take from a result, in this exact form: \
[[<the number as you write it>|<calculation_id>|<metric id>]], for example \
[[18.3%|calc_0123abcd|annualized_volatility:DEMO-A]] or [[$391.0B|calc_0123abcd|revenue:2024-09-28]]. \
Only metric ids from the result's "metrics" (or a screener row as <metric>:<TICKER>) can be cited. \
Write the number in the citation exactly as the reader should see it, rounded sensibly; \
show decimal metrics as percentages (0.183 as 18.3%).
- Plain text in short paragraphs: no headings, tables or Markdown.
- This is not investment advice. Never recommend buying, selling or holding anything. \
If you mention buying or selling at all, say clearly that this is only a reading of \
the calculations, not advice.
"""


def _strip_question(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


class Question(BaseModel):
    question: Annotated[
        str,
        BeforeValidator(_strip_question),
        check(lambda v: v != "", "Ask a question."),
        check(lambda v: len(v) <= MAX_QUESTION_CHARS, f"Keep the question under {MAX_QUESTION_CHARS} characters."),
    ]


class ToolCall(BaseModel):
    id: str
    tool: str
    input: Any
    calculation_id: str | None
    error: str | None


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int


class QuotaOut(BaseModel):
    limit: int
    used: int
    remaining: int
    resets_at: str


class AnalystAnswer(BaseModel):
    question: str
    answer: list[Segment]
    """The answer as text and citation segments; join their ``text`` to read it."""
    calls: list[ToolCall]
    """Every tool call, in order, with its parameters and the calculation it produced."""
    calculations: dict[str, dict[str, Any]]
    """The raw result envelope of every calculation run, by calculation id."""
    advice_notice: str | None
    usage: TokenUsage
    quota: QuotaOut


def get_model(request: Request) -> AnalystModel:
    return request.app.state.ai_model


Db = Annotated[Database, Depends(get_db)]
Model = Annotated[AnalystModel, Depends(get_model)]

_NOISY_DETAILS = {"url", "accession"}


def tool_payload(result: ResultEnvelope) -> dict:
    """A result as the model reads it: series thinned, empty fields and filing links dropped."""
    data = prompts.result_payload(result)
    for m in data["metrics"].values():
        for key in ("reason", "unit"):
            if m.get(key) is None:
                m.pop(key, None)
        if m.get("status") == "ok":
            m.pop("status")
        details = {k: v for k, v in m.pop("details", {}).items() if k not in _NOISY_DETAILS}
        if details:
            m["details"] = details
    return data


class Conversation:
    """One question's tool-use loop: runs the tools, keeps the trace and the results."""

    def __init__(self, model: AnalystModel, data: DataService, ctx: RequestContext) -> None:
        self.model, self.data, self.ctx = model, data, ctx
        self.calls: list[ToolCall] = []
        self.calculations: dict[str, ResultEnvelope] = {}
        self.input_tokens = self.output_tokens = 0

    def _turn(self, messages: list[dict], offer_tools: bool) -> Turn:
        turn = self.model.converse(SYSTEM, messages, tools.specs() if offer_tools else None)
        self.input_tokens += turn.input_tokens
        self.output_tokens += turn.output_tokens
        return turn

    def _run(self, use: dict) -> dict:
        outcome = tools.run_tool(use["name"], use.get("input"), self.data, self.ctx)
        result = outcome.result
        if result is not None:
            self.calculations[result.calculation_id] = result
        self.calls.append(
            ToolCall(
                id=use["id"],
                tool=use["name"],
                input=use.get("input"),
                calculation_id=result.calculation_id if result else None,
                error=outcome.error,
            )
        )
        block = {"type": "tool_result", "tool_use_id": use["id"]}
        if result is None:
            return block | {"content": outcome.error, "is_error": True}
        return block | {"content": json.dumps(tool_payload(result))}

    def answer(self, question: str) -> str:
        messages: list[dict] = [{"role": "user", "content": question}]
        for round_no in range(MAX_TOOL_ROUNDS + 1):
            turn = self._turn(messages, offer_tools=round_no < MAX_TOOL_ROUNDS)
            if not turn.tool_uses:
                return turn.text
            messages.append({"role": "assistant", "content": turn.content})
            messages.append({"role": "user", "content": [self._run(use) for use in turn.tool_uses]})
        raise AssertionError("unreachable: the last round offers no tools")


def _quota_exceeded(limit: int) -> ApiError:
    calls = "call" if limit == 1 else "calls"
    return ApiError(
        429,
        "quota_exceeded",
        f"You have used all {limit} AI {calls} for today. Your quota resets at 00:00 UTC.",
    )


@router.post("/analyst")
def ask(body: Question, user: CurrentUser, db: Db, model: Model, data: Data, ctx: Ctx) -> AnalystAnswer:
    limit = usage.daily_limit()
    with db.connection() as conn:
        usage_id = usage.reserve(conn, user.id, USAGE_TOOL, limit)
    if usage_id is None:
        raise _quota_exceeded(limit)
    conversation = Conversation(model, data, ctx)
    try:
        text = conversation.answer(body.question)
    except ModelUnavailable as exc:
        with db.connection() as conn:
            usage.release(conn, user.id, usage_id)
        raise ApiError(503, "ai_unavailable", UNAVAILABLE_MESSAGE) from exc
    except BaseException:
        with db.connection() as conn:
            usage.release(conn, user.id, usage_id)
        raise
    with db.connection() as conn:
        usage.record(conn, user.id, usage_id, conversation.input_tokens, conversation.output_tokens)
        remaining = usage.quota(conn, user.id, limit)
    segments = check_answer(text, conversation.calculations)
    return AnalystAnswer(
        question=body.question,
        answer=segments,
        calls=conversation.calls,
        calculations={cid: r.model_dump(mode="json") for cid, r in conversation.calculations.items()},
        advice_notice=prompts.advice_notice(plain_text(segments)),
        usage=TokenUsage(input_tokens=conversation.input_tokens, output_tokens=conversation.output_tokens),
        quota=QuotaOut(**remaining.as_json()),
    )
