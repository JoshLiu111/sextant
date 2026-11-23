"""SQL for users' uploaded factor files (``user_factor_files``, migration 0008).

Every function takes the owner's ``user_id`` and filters by it: a user's factors
are never read for anyone else, and never go to a cache.
"""

from __future__ import annotations

import math
from typing import Any
from uuid import UUID

import pandas as pd
import psycopg
from psycopg.types.json import Jsonb

from sextant_compute.risk.factor_files import FactorFile, Frequency, Kind

_SUMMARY = "kind, filename, frequency, factors->'dates'->>0 AS first, factors->'dates'->>-1 AS last," \
    " jsonb_array_length(factors->'dates') AS periods, factors->'order' AS columns, uploaded_at"


def _encode(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "dates": [d.date().isoformat() for d in frame.index],
        "order": list(frame.columns),
        "columns": {c: [None if math.isnan(v) else float(v) for v in frame[c]] for c in frame.columns},
    }


def _decode(value: dict[str, Any]) -> pd.DataFrame:
    index = pd.DatetimeIndex(pd.to_datetime(value["dates"]), name="date")
    data = {c: [math.nan if v is None else v for v in value["columns"][c]] for c in value["order"]}
    return pd.DataFrame(data, index=index, columns=value["order"], dtype=float)


def upsert(conn: psycopg.Connection, user_id: UUID, filename: str, file: FactorFile) -> dict[str, Any]:
    """Save the user's file of ``file.kind``, replacing any earlier one of that kind."""
    row = conn.execute(
        "INSERT INTO user_factor_files (user_id, kind, filename, frequency, factors) VALUES (%s, %s, %s, %s, %s)"
        " ON CONFLICT (user_id, kind) DO UPDATE SET filename = EXCLUDED.filename,"
        " frequency = EXCLUDED.frequency, factors = EXCLUDED.factors, uploaded_at = now()"
        f" RETURNING {_SUMMARY}",
        (user_id, file.kind, filename, file.frequency, Jsonb(_encode(file.frame))),
    ).fetchone()
    assert row is not None
    return row


def list_for(conn: psycopg.Connection, user_id: UUID) -> list[dict[str, Any]]:
    """The user's files, without the factor values. ``three_factor`` sorts first."""
    return conn.execute(
        f"SELECT {_SUMMARY} FROM user_factor_files WHERE user_id = %s ORDER BY kind DESC", (user_id,)
    ).fetchall()


def frames_for(conn: psycopg.Connection, user_id: UUID) -> dict[Kind, tuple[Frequency, pd.DataFrame]]:
    """kind -> (frequency, decimal factor frame) for each file the user uploaded."""
    rows = conn.execute(
        "SELECT kind, frequency, factors FROM user_factor_files WHERE user_id = %s", (user_id,)
    ).fetchall()
    return {r["kind"]: (r["frequency"], _decode(r["factors"])) for r in rows}


def delete(conn: psycopg.Connection, user_id: UUID, kind: Kind) -> bool:
    """False if the user had no file of ``kind``."""
    cur = conn.execute("DELETE FROM user_factor_files WHERE user_id = %s AND kind = %s", (user_id, kind))
    return cur.rowcount == 1
