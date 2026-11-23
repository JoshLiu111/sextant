"""Saved valuation assumptions (P2, story 70): a signed-in user's named DCF/WACC inputs per ticker.

Every query is scoped by the current user's id: someone else's set answers 404,
the same as an id that does not exist. Saving under a name the user already has
for that ticker replaces that set (same id), so "save" never piles up duplicates.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from psycopg.types.json import Jsonb
from pydantic import BaseModel, BeforeValidator

from sextant_compute.auth import CurrentUser
from sextant_compute.auth.deps import get_db
from sextant_compute.db import Database
from sextant_compute.errors import ApiError, check
from sextant_compute.valuation.api import Ticker, ValuationAssumptions

router = APIRouter(tags=["valuation"])

Db = Annotated[Database, Depends(get_db)]
MAX_NAME = 100
MAX_TICKER = 20


def _strip(value: object) -> object:
    return value.strip() if isinstance(value, str) else value


class AssumptionSetIn(BaseModel):
    ticker: Annotated[Ticker, check(lambda v: len(v) <= MAX_TICKER, f"Use at most {MAX_TICKER} characters.")]
    name: Annotated[
        str,
        BeforeValidator(_strip),
        check(lambda v: v != "", "Enter a name."),
        check(lambda v: len(v) <= MAX_NAME, f"Use at most {MAX_NAME} characters."),
    ]
    assumptions: ValuationAssumptions


class AssumptionSetOut(AssumptionSetIn):
    id: UUID
    created_at: datetime
    updated_at: datetime


_COLUMNS = "id, ticker, name, assumptions, created_at, updated_at"


def _out(row: dict[str, Any]) -> AssumptionSetOut:
    return AssumptionSetOut.model_validate(row)


@router.get("/assumptions")
def list_assumption_sets(user: CurrentUser, db: Db, ticker: Ticker | None = None) -> list[AssumptionSetOut]:
    """The user's saved sets, oldest first; only ``ticker``'s when given."""
    with db.connection() as conn:
        rows = conn.execute(
            f"SELECT {_COLUMNS} FROM valuation_assumptions"
            " WHERE user_id = %s AND (%s::text IS NULL OR ticker = %s) ORDER BY created_at, id",
            (user.id, ticker, ticker),
        ).fetchall()
    return [_out(row) for row in rows]


@router.post("/assumptions", status_code=status.HTTP_201_CREATED)
def save_assumption_set(body: AssumptionSetIn, user: CurrentUser, db: Db) -> AssumptionSetOut:
    with db.connection() as conn:
        row = conn.execute(
            "INSERT INTO valuation_assumptions (user_id, ticker, name, assumptions) VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (user_id, ticker, name)"
            " DO UPDATE SET assumptions = EXCLUDED.assumptions, updated_at = now()"
            f" RETURNING {_COLUMNS}",
            (user.id, body.ticker, body.name, Jsonb(body.assumptions.model_dump())),
        ).fetchone()
    assert row is not None
    return _out(row)


@router.delete("/assumptions/{set_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assumption_set(set_id: UUID, user: CurrentUser, db: Db) -> Response:
    with db.connection() as conn:
        deleted = conn.execute(
            "DELETE FROM valuation_assumptions WHERE id = %s AND user_id = %s", (set_id, user.id)
        ).rowcount
    if not deleted:
        raise ApiError(404, "not_found", "No such saved assumptions.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
