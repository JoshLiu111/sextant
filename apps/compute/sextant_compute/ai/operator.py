"""Operator view of AI usage (``/api/compute/operator/...``), story 95.

Only accounts whose email is listed in ``OPERATOR_EMAILS`` (comma-separated,
case-insensitive) get in. Everyone else, signed in or not, gets a 404
``not_found``, so the view's existence and users' emails stay hidden.

- ``GET /access``: 204 for an operator (the web app checks this before rendering).
- ``GET /ai-usage?days=N``: calls, tokens and estimated cost per user and per
  user per UTC day, over the last N days (default 30, today included). Failed
  calls are included (they spent tokens) and also counted on their own.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from sextant_compute.auth import OptionalUser, User
from sextant_compute.auth.deps import get_db
from sextant_compute.db import Database
from sextant_compute.errors import ApiError

router = APIRouter(tags=["operator"])

Db = Annotated[Database, Depends(get_db)]

# List price of the default model (USD per million tokens). The usage log does not
# record the model per call, so the cost is an estimate at the configured price.
DEFAULT_INPUT_USD_PER_MTOK = 1.0
DEFAULT_OUTPUT_USD_PER_MTOK = 5.0


def operator_emails() -> frozenset[str]:
    raw = os.environ.get("OPERATOR_EMAILS", "")
    return frozenset(e.strip().lower() for e in raw.split(",") if e.strip())


def _require_operator(user: OptionalUser) -> User:
    if user is None or user.email.strip().lower() not in operator_emails():
        raise ApiError(404, "not_found", "Not found.")
    return user


Operator = Annotated[User, Depends(_require_operator)]


@router.get("/access", status_code=204)
def access(_operator: Operator) -> Response:
    return Response(status_code=204)


def _price(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


class Pricing(BaseModel):
    input_usd_per_mtok: float
    output_usd_per_mtok: float

    @classmethod
    def from_env(cls) -> Pricing:
        return cls(
            input_usd_per_mtok=_price("AI_PRICE_INPUT_USD_PER_MTOK", DEFAULT_INPUT_USD_PER_MTOK),
            output_usd_per_mtok=_price("AI_PRICE_OUTPUT_USD_PER_MTOK", DEFAULT_OUTPUT_USD_PER_MTOK),
        )

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        usd = input_tokens * self.input_usd_per_mtok + output_tokens * self.output_usd_per_mtok
        return round(usd / 1_000_000, 6)


class UsageTotals(BaseModel):
    calls: int
    """Every logged call: failed ones, and one still waiting for the model (no tokens yet)."""
    failed_calls: int
    """Calls the model failed on. They don't count against the user's quota, but
    their tokens (e.g. AI Analyst rounds before the failure) are in the totals."""
    input_tokens: int
    output_tokens: int
    estimated_cost_usd: float


class UserUsage(UsageTotals):
    user_id: UUID
    email: str
    name: str | None


class DayUsage(UserUsage):
    day: date
    """The UTC calendar day, the same day the quota counts."""


class AiUsageReport(BaseModel):
    since: date
    until: date
    pricing: Pricing
    totals: UsageTotals
    users: list[UserUsage]
    """Highest estimated cost first."""
    days: list[DayUsage]
    """Newest day first; within a day, highest estimated cost first."""


_PER_USER_PER_DAY = """
SELECT (a.created_at AT TIME ZONE 'UTC')::date AS day,
       a.user_id, u.email, u.name,
       count(*)::int AS calls,
       count(*) FILTER (WHERE a.status = 'failed')::int AS failed_calls,
       coalesce(sum(a.input_tokens), 0)::bigint AS input_tokens,
       coalesce(sum(a.output_tokens), 0)::bigint AS output_tokens
FROM ai_usage a JOIN users u ON u.id = a.user_id
WHERE a.created_at >= %s
GROUP BY 1, 2, 3, 4
"""


def _totals(rows: Iterable[dict], pricing: Pricing) -> dict:
    rows = list(rows)
    input_tokens = sum(r["input_tokens"] for r in rows)
    output_tokens = sum(r["output_tokens"] for r in rows)
    return {
        "calls": sum(r["calls"] for r in rows),
        "failed_calls": sum(r["failed_calls"] for r in rows),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost_usd": pricing.cost(input_tokens, output_tokens),
    }


def _by_cost(item: UserUsage) -> tuple:
    return (-item.estimated_cost_usd, -item.calls, item.email)


@router.get("/ai-usage")
def ai_usage(_operator: Operator, db: Db, days: Annotated[int, Query(ge=1, le=366)] = 30) -> AiUsageReport:
    pricing = Pricing.from_env()
    until = datetime.now(UTC).date()
    since = until - timedelta(days=days - 1)
    with db.connection() as conn:
        rows = conn.execute(_PER_USER_PER_DAY, (datetime.combine(since, time(), tzinfo=UTC),)).fetchall()

    per_day = sorted(
        (
            DayUsage(day=r["day"], user_id=r["user_id"], email=r["email"], name=r["name"], **_totals([r], pricing))
            for r in rows
        ),
        key=_by_cost,
    )
    per_day.sort(key=lambda d: d.day, reverse=True)

    rows_by_user: dict[UUID, list[dict]] = {}
    for r in rows:
        rows_by_user.setdefault(r["user_id"], []).append(r)
    per_user = sorted(
        (
            UserUsage(user_id=uid, email=rs[0]["email"], name=rs[0]["name"], **_totals(rs, pricing))
            for uid, rs in rows_by_user.items()
        ),
        key=_by_cost,
    )

    return AiUsageReport(
        since=since,
        until=until,
        pricing=pricing,
        totals=UsageTotals(**_totals(rows, pricing)),
        users=per_user,
        days=per_day,
    )
