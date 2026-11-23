"""Operator view of AI usage (``/api/compute/operator/...``), story 95.

Only accounts whose email is listed in ``OPERATOR_EMAILS`` (comma-separated,
case-insensitive) get in. Everyone else, signed in or not, gets a 404
``not_found``, so the view's existence and users' emails stay hidden.

- ``GET /access``: 204 for an operator (the web app checks this before rendering).
- ``GET /ai-usage?days=N``: calls, tokens and estimated cost per user and per
  user per UTC day, over the last N days (default 30, today included).
- ``GET /users?days=N``: registered users, sign-ups per UTC day over the same kind
  of window, and users who signed in within the last 7 and 30 days.
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
    """Every logged call, including one still waiting for the model (no tokens yet)."""
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


SIGNED_IN_RECENTLY_DAYS = 7
SIGNED_IN_THIS_MONTH_DAYS = 30


class DaySignUps(BaseModel):
    day: date
    """The UTC calendar day."""
    users: int


class SignedInWithin(BaseModel):
    days: int
    users: int
    """Users whose last sign-in was within ``days`` days. ``last_login_at`` only moves
    at sign-in and sessions last 30 days, so this undercounts daily use."""


class UsersReport(BaseModel):
    since: date
    until: date
    total_users: int
    sign_ups: list[DaySignUps]
    """Every UTC day in the window, newest first, including days without sign-ups."""
    signed_in_within: list[SignedInWithin]


_USER_COUNTS = """
SELECT count(*)::int AS total_users,
       count(*) FILTER (WHERE last_login_at >= now() - make_interval(days => %s))::int AS within_recently,
       count(*) FILTER (WHERE last_login_at >= now() - make_interval(days => %s))::int AS within_this_month
FROM users
"""

_SIGN_UPS_PER_DAY = """
SELECT (created_at AT TIME ZONE 'UTC')::date AS day, count(*)::int AS users
FROM users
WHERE created_at >= %s
GROUP BY 1
"""


@router.get("/users")
def users(_operator: Operator, db: Db, days: Annotated[int, Query(ge=1, le=366)] = 30) -> UsersReport:
    until = datetime.now(UTC).date()
    since = until - timedelta(days=days - 1)
    with db.connection() as conn:
        counts = conn.execute(_USER_COUNTS, (SIGNED_IN_RECENTLY_DAYS, SIGNED_IN_THIS_MONTH_DAYS)).fetchone()
        rows = conn.execute(_SIGN_UPS_PER_DAY, (datetime.combine(since, time(), tzinfo=UTC),)).fetchall()

    per_day = {r["day"]: r["users"] for r in rows}
    return UsersReport(
        since=since,
        until=until,
        total_users=counts["total_users"],
        sign_ups=[
            DaySignUps(day=day, users=per_day.get(day, 0))
            for day in (until - timedelta(days=i) for i in range(days))
        ],
        signed_in_within=[
            SignedInWithin(days=SIGNED_IN_RECENTLY_DAYS, users=counts["within_recently"]),
            SignedInWithin(days=SIGNED_IN_THIS_MONTH_DAYS, users=counts["within_this_month"]),
        ],
    )
