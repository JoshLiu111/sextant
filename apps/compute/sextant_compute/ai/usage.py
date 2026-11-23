"""SQL for the AI usage log and the daily quota. Every function is scoped by ``user_id``.

The quota day is the UTC calendar day. A call first *reserves* a row (under a
per-user advisory lock, so concurrent calls can't overshoot the quota), then
either records its token counts or releases the row when the model fails.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, time, timedelta
from typing import NamedTuple
from uuid import UUID

import psycopg

DEFAULT_DAILY_QUOTA = 20

_TODAY = "created_at >= date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"


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


def _used_today(conn: psycopg.Connection, user_id: UUID) -> int:
    row = conn.execute(f"SELECT count(*) AS n FROM ai_usage WHERE user_id = %s AND {_TODAY}", (user_id,)).fetchone()
    assert row is not None
    return int(row["n"])


def quota(conn: psycopg.Connection, user_id: UUID, limit: int) -> Quota:
    return Quota(limit, _used_today(conn, user_id), next_reset())


def reserve(conn: psycopg.Connection, user_id: UUID, tool: str, limit: int) -> UUID | None:
    """Take one call from today's quota; None when it is used up. Commit before calling the model."""
    conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"ai_usage:{user_id}",))
    if _used_today(conn, user_id) >= limit:
        return None
    row = conn.execute(
        "INSERT INTO ai_usage (user_id, tool) VALUES (%s, %s) RETURNING id", (user_id, tool)
    ).fetchone()
    assert row is not None
    return row["id"]


def record(conn: psycopg.Connection, user_id: UUID, usage_id: UUID, input_tokens: int, output_tokens: int) -> None:
    conn.execute(
        "UPDATE ai_usage SET input_tokens = %s, output_tokens = %s WHERE id = %s AND user_id = %s",
        (input_tokens, output_tokens, usage_id, user_id),
    )


def release(conn: psycopg.Connection, user_id: UUID, usage_id: UUID) -> None:
    conn.execute("DELETE FROM ai_usage WHERE id = %s AND user_id = %s", (usage_id, user_id))
