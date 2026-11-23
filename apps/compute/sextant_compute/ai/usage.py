"""The AI usage log and the daily quota. Every query is scoped by ``user_id``.

Every AI call goes through ``metered``: it *reserves* a row (under a per-user
advisory lock, so concurrent calls can't overshoot the quota), runs the call,
then records the tokens it spent. A call that fails keeps its row with status
``failed`` and whatever tokens it spent before failing: the operator view counts
them, the quota does not. The quota day is the UTC calendar day.
"""

from __future__ import annotations

import math
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from typing import NamedTuple
from uuid import UUID

import psycopg

from sextant_compute.ai.model import ModelUnavailable
from sextant_compute.db import Database
from sextant_compute.errors import ApiError

DEFAULT_DAILY_QUOTA = 20

_TODAY = "created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"
_CHARGED = "status <> 'failed'"


class Quota(NamedTuple):
    limit: int
    used: int
    resets_at: datetime

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)

    def as_json(self) -> dict:
        return {
            "limit": self.limit,
            "used": self.used,
            "remaining": self.remaining,
            "resets_at": self.resets_at.isoformat().replace("+00:00", "Z"),
        }


def daily_limit() -> int:
    """``AI_DAILY_QUOTA`` (calls per user per UTC day), default ``DEFAULT_DAILY_QUOTA``."""
    raw = os.environ.get("AI_DAILY_QUOTA", "").strip()
    return int(raw) if raw else DEFAULT_DAILY_QUOTA


def next_reset(now: datetime | None = None) -> datetime:
    now = now or datetime.now(UTC)
    return datetime.combine(now.date() + timedelta(days=1), time(), tzinfo=UTC)


def time_until_reset(now: datetime | None = None) -> str:
    """How long until the quota resets, e.g. "about 5 hours" or "25 minutes": the same in
    every time zone, so a message can say it before the page knows the visitor's."""
    now = now or datetime.now(UTC)
    minutes = math.ceil((next_reset(now) - now).total_seconds() / 60)
    if minutes < 60:
        return f"{minutes} minute{'' if minutes == 1 else 's'}"
    hours = round(minutes / 60)
    return f"about {hours} hour{'' if hours == 1 else 's'}"


def quota_exceeded(limit: int, calls_of: str) -> ApiError:
    """The 429 for a used-up quota. ``calls_of`` names the calls, e.g. "AI Explain" ("AI Explain calls")."""
    calls = "call" if limit == 1 else "calls"
    return ApiError(
        429,
        "quota_exceeded",
        f"You have used all {limit} {calls_of} {calls} for today. Your quota resets in {time_until_reset()}.",
    )


def _used_today(conn: psycopg.Connection, user_id: UUID) -> int:
    row = conn.execute(f"SELECT count(*) AS n FROM ai_usage WHERE user_id = %s AND {_CHARGED} AND {_TODAY}", (user_id,)).fetchone()
    assert row is not None
    return int(row["n"])


def quota(conn: psycopg.Connection, user_id: UUID, limit: int) -> Quota:
    return Quota(limit, _used_today(conn, user_id), next_reset())


def _reserve(conn: psycopg.Connection, user_id: UUID, tool: str, limit: int) -> UUID | None:
    """Take one call from today's quota; None when it is used up. Commit before calling the model."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"ai_usage:{user_id}",))
    if _used_today(conn, user_id) >= limit:
        return None
    row = conn.execute(
        "INSERT INTO ai_usage (user_id, tool) VALUES (%s, %s) RETURNING id", (user_id, tool)
    ).fetchone()
    assert row is not None
    return row["id"]


def _finish(conn: psycopg.Connection, user_id: UUID, usage_id: UUID, meter: Meter, status: str) -> None:
    conn.execute(
        "UPDATE ai_usage SET status = %s, input_tokens = %s, output_tokens = %s WHERE id = %s AND user_id = %s",
        (status, meter.input_tokens, meter.output_tokens, usage_id, user_id),
    )


class QuotaExceeded(Exception):
    def __init__(self, limit: int) -> None:
        super().__init__(f"daily AI quota of {limit} used up")
        self.limit = limit


@dataclass
class Meter:
    """The tokens one metered call has spent so far; the caller adds each model reply.

    After the ``metered`` block ends normally, ``quota`` is the user's quota
    including this call.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    quota: Quota | None = None

    def add(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens


@contextmanager
def metered(db: Database, user_id: UUID, tool: str) -> Iterator[Meter]:
    """Run one AI call against the user's daily quota and log what it spent.

    Raises ``QuotaExceeded`` (before the block runs) when today's quota is used up.
    If the block raises, the call is logged as ``failed`` with the tokens added so
    far, plus those a ``ModelUnavailable`` says it was billed for, and does not
    count against the quota; the exception propagates.
    """
    limit = daily_limit()
    with db.connection() as conn:
        usage_id = _reserve(conn, user_id, tool, limit)
    if usage_id is None:
        raise QuotaExceeded(limit)
    meter = Meter()
    try:
        yield meter
    except BaseException as exc:
        if isinstance(exc, ModelUnavailable):
            meter.add(exc.input_tokens, exc.output_tokens)
        with db.connection() as conn:
            _finish(conn, user_id, usage_id, meter, "failed")
        raise
    with db.connection() as conn:
        _finish(conn, user_id, usage_id, meter, "ok")
        meter.quota = quota(conn, user_id, limit)
