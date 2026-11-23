"""AI Explain endpoints (``/api/compute/ai/...``). Signed-in users only.

- ``GET /quota``: today's quota ``{limit, used, remaining, resets_at}``.
- ``POST /explain/<tool>``: the body is that tool's own request model (the
  ``meta.parameters`` of the result on screen). The service recomputes the result
  itself, so the model only ever sees numbers Sextant calculated, then asks the
  model for a plain-English reading that cites its numbers the way AI Analyst
  does; each citation is checked against that one result (``ai/citations.py``). One call costs one unit of the daily quota;
  a failed model call costs nothing.

Each tool registers itself with ``add_explainer(tool, RequestModel, compute, guide)``;
the registrations and their guides live in ``ai/explainers.py``.
"""

# No ``from __future__ import annotations``: ``add_explainer`` builds handlers
# whose parameter types are only known at runtime, and FastAPI reads them eagerly.

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from sextant_compute.ai import prompts, usage
from sextant_compute.ai.citations import Segment, check_answer, plain_text
from sextant_compute.ai.model import ExplainModel, ModelUnavailable
from sextant_compute.auth import CurrentUser, User
from sextant_compute.auth.deps import get_db
from sextant_compute.data.context import RequestContext
from sextant_compute.data.service import Ctx, Data, DataService
from sextant_compute.db import Database
from sextant_compute.envelope import ResultEnvelope
from sextant_compute.errors import ApiError

router = APIRouter(tags=["ai"])

Db = Annotated[Database, Depends(get_db)]

UNAVAILABLE_MESSAGE = "AI Explain is temporarily unavailable. Please retry in a moment."


def get_model(request: Request) -> ExplainModel:
    return request.app.state.ai_model


Model = Annotated[ExplainModel, Depends(get_model)]


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int


class QuotaOut(BaseModel):
    limit: int
    used: int
    remaining: int
    resets_at: str


class Explanation(BaseModel):
    tool: str
    calculation_id: str
    """The calculation the explanation reads (recomputed server-side)."""
    explanation: str
    """The answer as plain text (the citations' numbers as written, without their markup)."""
    answer: list[Segment]
    """The answer as text, citation and uncited-number segments, each citation checked against the calculation."""
    advice_notice: str | None
    """Set when the answer touches on buying or selling: it is only a reading, not advice."""
    usage: TokenUsage
    quota: QuotaOut


@router.get("/quota")
def get_quota(user: CurrentUser, db: Db) -> QuotaOut:
    with db.connection() as conn:
        return QuotaOut(**usage.quota(conn, user.id, usage.daily_limit()).as_json())


def explain(tool: str, guide: str, result: ResultEnvelope, user_id, db: Database, model: ExplainModel) -> Explanation:
    limit = usage.daily_limit()
    with db.connection() as conn:
        usage_id = usage.reserve(conn, user_id, tool, limit)
    if usage_id is None:
        raise usage.quota_exceeded(limit, "AI Explain")
    try:
        completion = model.complete(prompts.SYSTEM, prompts.user_prompt(guide, result))
    except ModelUnavailable as exc:
        with db.connection() as conn:
            usage.release(conn, user_id, usage_id)
        raise ApiError(503, "ai_unavailable", UNAVAILABLE_MESSAGE) from exc
    except BaseException:
        with db.connection() as conn:
            usage.release(conn, user_id, usage_id)
        raise
    with db.connection() as conn:
        usage.record(conn, user_id, usage_id, completion.input_tokens, completion.output_tokens)
        remaining = usage.quota(conn, user_id, limit)
    segments = check_answer(completion.text, {result.calculation_id: result})
    text = plain_text(segments)
    return Explanation(
        tool=tool,
        calculation_id=result.calculation_id,
        explanation=text,
        answer=segments,
        advice_notice=prompts.advice_notice(text),
        usage=TokenUsage(input_tokens=completion.input_tokens, output_tokens=completion.output_tokens),
        quota=QuotaOut(**remaining.as_json()),
    )


@dataclass(frozen=True)
class ToolInputs:
    """What a tool's endpoint may need besides its request: the signed-in user,
    the database, and the DataService with this request's ``ctx``."""

    user: User
    db: Database
    data: DataService
    ctx: RequestContext


def add_explainer(
    tool: str,
    request_model: type[BaseModel],
    compute: Callable[[BaseModel, ToolInputs], ResultEnvelope],
    guide: str,
) -> None:
    """Expose ``POST /explain/<tool>``: validate like the tool, recompute, explain.

    ``compute(req, inputs)`` returns the tool's envelope, usually by calling the
    tool's own endpoint function. It runs before the quota is touched, so the
    tool's own errors (422 field errors, unknown tickers, source outages) cost nothing.
    """

    def handler(  # type: ignore[valid-type]
        req: request_model, user: CurrentUser, db: Db, model: Model, data: Data, ctx: Ctx
    ) -> Explanation:
        result = compute(req, ToolInputs(user=user, db=db, data=data, ctx=ctx))
        return explain(tool, guide, result, user.id, db, model)

    handler.__name__ = f"explain_{tool}"
    router.add_api_route(f"/explain/{tool}", handler, methods=["POST"], response_model=Explanation)


# Registers every tool's explainer (imports this module, so it comes last).
from sextant_compute.ai import explainers  # noqa: E402, F401
