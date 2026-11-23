"""AI Analyst: ``POST /api/compute/ai/analyst`` with ``{"question": str}``. Signed-in users only.

The model picks Sextant's tools (``ai/tools.py``) and their parameters; Sextant
runs them and sends back the result envelopes; the model then writes the answer,
citing each number as ``[[number|calculation_id|metric id]]``. The response
carries the answer split into text, checked citations and uncited numbers (``ai/citations.py``),
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
from sextant_compute.ai.citations import CITING_RULE, Segment, check_answer, plain_text
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

SYSTEM = f"""\
You are AI Analyst in Sextant, a suite of finance tools. You answer the user's question \
by calling Sextant's tools and explaining their results in plain English.

Rules:
- Get every figure from a tool result. Never invent, estimate, recall or look up numbers \
yourself. If the tools can't answer the question, say so.
- Call the tools you need (several at once is fine), then answer. Use each tool's defaults \
unless the question says otherwise.
{CITING_RULE}- Plain text in short paragraphs: no headings, tables or Markdown.
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
    """The answer as text, citation and uncited-number segments; join their ``text`` to read it."""
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

class Conversation:
    """One question's tool-use loop: runs the tools, keeps the trace and the results."""

    def __init__(
        self, model: AnalystModel, data: DataService, ctx: RequestContext, db: Database | None = None
    ) -> None:
        self.model, self.data, self.ctx, self.db = model, data, ctx, db
        self.calls: list[ToolCall] = []
        self.calculations: dict[str, ResultEnvelope] = {}
        self.input_tokens = self.output_tokens = 0

    def _turn(self, messages: list[dict], must_answer: bool) -> Turn:
        turn = self.model.converse(SYSTEM, messages, tools.specs(), must_answer=must_answer)
        self.input_tokens += turn.input_tokens
        self.output_tokens += turn.output_tokens
        return turn

    def _run(self, use: dict) -> dict:
        outcome = tools.run_tool(use["name"], use.get("input"), self.data, self.ctx, self.db)
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
        return block | {"content": json.dumps(prompts.result_payload(result, drop_ok_status=True))}

    def answer(self, question: str) -> str:
        messages: list[dict] = [{"role": "user", "content": question}]
        for round_no in range(MAX_TOOL_ROUNDS + 1):
            turn = self._turn(messages, must_answer=round_no == MAX_TOOL_ROUNDS)
            if not turn.tool_uses or round_no == MAX_TOOL_ROUNDS:
                return turn.text
            messages.append({"role": "assistant", "content": turn.content})
            messages.append({"role": "user", "content": [self._run(use) for use in turn.tool_uses]})
        raise AssertionError("unreachable: the last round always answers")


@router.post("/analyst")
def ask(body: Question, user: CurrentUser, db: Db, model: Model, data: Data, ctx: Ctx) -> AnalystAnswer:
    limit = usage.daily_limit()
    with db.connection() as conn:
        usage_id = usage.reserve(conn, user.id, USAGE_TOOL, limit)
    if usage_id is None:
        raise usage.quota_exceeded(limit, "AI")
    conversation = Conversation(model, data, ctx, db)
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
