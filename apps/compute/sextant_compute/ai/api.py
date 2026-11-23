"""AI Explain endpoints (``/api/compute/ai/...``). Signed-in users only.

- ``GET /quota``: today's quota ``{limit, used, remaining, resets_at}``.
- ``POST /explain/<tool>``: the body is that tool's own request model (the
  ``meta.parameters`` of the result on screen). The service recomputes the result
  itself, so the model only ever sees numbers Sextant calculated, then asks the
  model for a plain-English reading. One call costs one unit of the daily quota;
  a failed model call costs nothing.

Add a tool with ``add_explainer(tool, RequestModel, compute, guide)``.
"""

# No ``from __future__ import annotations``: ``add_explainer`` builds handlers
# whose parameter types are only known at runtime, and FastAPI reads them eagerly.

from collections.abc import Callable
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from sextant_compute.ai import prompts, usage
from sextant_compute.ai.model import ExplainModel, ModelUnavailable
from sextant_compute.auth import CurrentUser
from sextant_compute.auth.deps import get_db
from sextant_compute.db import Database
from sextant_compute.envelope import ResultEnvelope
from sextant_compute.errors import ApiError
from sextant_compute.options.api import OptionsRequest
from sextant_compute.options.api import price as options_price

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
    advice_notice: str | None
    """Set when the answer touches on buying or selling: it is only a reading, not advice."""
    usage: TokenUsage
    quota: QuotaOut


@router.get("/quota")
def get_quota(user: CurrentUser, db: Db) -> QuotaOut:
    with db.connection() as conn:
        return QuotaOut(**usage.quota(conn, user.id, usage.daily_limit()).as_json())


def _quota_exceeded(limit: int) -> ApiError:
    calls = "call" if limit == 1 else "calls"
    return ApiError(
        429,
        "quota_exceeded",
        f"You have used all {limit} AI Explain {calls} for today. Your quota resets at 00:00 UTC.",
    )


def explain(tool: str, guide: str, result: ResultEnvelope, user_id, db: Database, model: ExplainModel) -> Explanation:
    limit = usage.daily_limit()
    with db.connection() as conn:
        usage_id = usage.reserve(conn, user_id, tool, limit)
    if usage_id is None:
        raise _quota_exceeded(limit)
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
    return Explanation(
        tool=tool,
        calculation_id=result.calculation_id,
        explanation=completion.text,
        advice_notice=prompts.advice_notice(completion.text),
        usage=TokenUsage(input_tokens=completion.input_tokens, output_tokens=completion.output_tokens),
        quota=QuotaOut(**remaining.as_json()),
    )


def add_explainer(
    tool: str,
    request_model: type[BaseModel],
    compute: Callable[..., ResultEnvelope],
    guide: str,
) -> None:
    """Expose ``POST /explain/<tool>``: validate like the tool, recompute, explain."""

    def handler(req: request_model, user: CurrentUser, db: Db, model: Model) -> Explanation:  # type: ignore[valid-type]
        return explain(tool, guide, compute(req), user.id, db, model)

    handler.__name__ = f"explain_{tool}"
    router.add_api_route(f"/explain/{tool}", handler, methods=["POST"], response_model=Explanation)


OPTIONS_GUIDE = """
Options Calculator: European Black-Scholes prices and Greeks for one option.
Inputs (meta.parameters) are decimals: volatility 0.2 means 20%, rates and dividend
yield likewise; time_to_expiry is in years. option_type selects the chart and the
implied volatility; prices and Greeks are given for both the call and the put.
Units: currency = price per share; per_dollar = change per $1 move in the spot
(Delta, Gamma); per_vol_point = price change per 1 percentage point of volatility
(Vega); per_day = price change per calendar day (Theta, usually negative);
per_rate_point = price change per 1 percentage point of the risk-free rate (Rho);
decimal = a fraction (implied volatility 0.25 means 25%). implied_volatility is
missing_data unless a market price was entered. Series: payoff_at_expiry and
theoretical_value across spot prices (x = spot, y = option value).
"""

add_explainer("options", OptionsRequest, options_price, OPTIONS_GUIDE)
