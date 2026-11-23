"""Risk & Performance on My data: the signed-in user's own factor files (ADR 0003).

Endpoints (all ``CurrentUser``: 401 when signed out), under ``/api/compute/risk/factor-files``:

- ``GET ""``: the user's files, ``[FactorFileOut]`` (3-factor file first).
- ``POST ""`` with ``{filename, csv}``: parses a Kenneth R. French Data Library
  CSV (``risk.factor_files``) and saves it as the user's ``three_factor`` or
  ``momentum`` file, by its columns, replacing the earlier file of that kind.
  An unreadable file answers 422 ``unreadable_factor_file`` (field ``file``)
  and stores nothing; so does a file whose frequency differs from the user's
  other file (both must be monthly or both daily).
- ``DELETE /{kind}``: removes that file (204, also when there was none).

``POST /risk/metrics`` with a My data ``source`` regresses on these files
(``load_user_factors``); nothing here goes to a cache.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

import pandas as pd
from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, Field

from sextant_compute.auth import CurrentUser
from sextant_compute.auth.deps import get_db
from sextant_compute.db import Database
from sextant_compute.envelope import MissingData
from sextant_compute.errors import ApiError
from sextant_compute.risk import factor_store
from sextant_compute.risk.factor_files import (
    MOMENTUM,
    FactorFileUnreadable,
    Frequency,
    Kind,
    parse_factor_file,
)

router = APIRouter(tags=["risk factor files"])

Db = Annotated[Database, Depends(get_db)]
MAX_CSV_CHARS = 5_000_000
"""The daily 3-factor file since 1926 is about 1 MB."""
KIND_NAMES: dict[Kind, str] = {"three_factor": "3-factor", "momentum": "momentum"}
FACTOR_SOURCE = "user_upload"
"""The ``factor_source`` id regressions on an uploaded file carry."""


class FactorFileIn(BaseModel):
    filename: Annotated[str, Field(max_length=255)] = ""
    csv: Annotated[str, Field(max_length=MAX_CSV_CHARS)]
    """The file's text."""


class FactorFileOut(BaseModel):
    kind: Kind
    filename: str
    frequency: Frequency
    first: str
    """First period: ``YYYY-MM`` for monthly files, ``YYYY-MM-DD`` for daily."""
    last: str
    periods: int
    columns: list[str]
    uploaded_at: datetime


def _out(row: dict) -> FactorFileOut:
    def period(iso: str) -> str:
        return iso[:7] if row["frequency"] == "monthly" else iso

    return FactorFileOut.model_validate({**row, "first": period(row["first"]), "last": period(row["last"])})


def _unreadable(message: str) -> ApiError:
    return ApiError(422, "unreadable_factor_file", message, fields={"file": message})


@router.get("")
def list_factor_files(user: CurrentUser, db: Db) -> list[FactorFileOut]:
    with db.connection() as conn:
        return [_out(row) for row in factor_store.list_for(conn, user.id)]


@router.post("")
def upload_factor_file(body: FactorFileIn, user: CurrentUser, db: Db) -> FactorFileOut:
    try:
        parsed = parse_factor_file(body.csv)
    except FactorFileUnreadable as exc:
        raise _unreadable(exc.message) from exc
    with db.connection() as conn:
        for other in factor_store.list_for(conn, user.id):
            if other["kind"] != parsed.kind and other["frequency"] != parsed.frequency:
                raise _unreadable(
                    f"This {KIND_NAMES[parsed.kind]} file is {parsed.frequency} but your "
                    f"{KIND_NAMES[other['kind']]} file is {other['frequency']}. Both must have the same "
                    f"frequency: remove the {KIND_NAMES[other['kind']]} file or upload a {other['frequency']} one."
                )
        row = factor_store.upsert(conn, user.id, body.filename.strip() or "factors.csv", parsed)
    return _out(row)


@router.delete("/{kind}", status_code=status.HTTP_204_NO_CONTENT)
def delete_factor_file(kind: Kind, user: CurrentUser, db: Db) -> Response:
    with db.connection() as conn:
        factor_store.delete(conn, user.id, kind)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


NO_UPLOAD = (
    "My data has no factors until you upload a factor file (e.g. F-F_Research_Data_Factors.CSV "
    "from the Kenneth R. French Data Library). Sextant ships no real factor data."
)


def load_user_factors(
    db: Database, user_id: UUID | None, start: date, end: date
) -> tuple[pd.DataFrame | MissingData, Frequency]:
    """The user's uploaded factors as one decimal frame (3-factor columns plus MOM if
    uploaded), with its frequency; or why there are none for ``start``..``end``."""
    if user_id is None:
        return MissingData(NO_UPLOAD), "daily"
    with db.connection() as conn:
        files = factor_store.frames_for(conn, user_id)
    if "three_factor" not in files:
        if "momentum" in files:
            return MissingData(
                "Your momentum file needs a 3-factor file (Mkt-RF, SMB, HML, RF) to go with it. "
                "Upload F-F_Research_Data_Factors.CSV at the same frequency."
            ), files["momentum"][0]
        return MissingData(NO_UPLOAD), "daily"
    frequency, frame = files["three_factor"]
    if "momentum" in files:
        frame = frame.drop(columns=[MOMENTUM], errors="ignore").join(files["momentum"][1][[MOMENTUM]], how="left")
    window = frame.loc[pd.Timestamp(start) : pd.Timestamp(end) + pd.offsets.MonthEnd(0)]
    if window.empty:
        def period(ts: pd.Timestamp) -> str:
            return ts.strftime("%Y-%m") if frequency == "monthly" else ts.date().isoformat()

        return MissingData(
            f"Your factor file covers {period(frame.index[0])} to {period(frame.index[-1])}, which does not "
            f"overlap the price range {start.isoformat()} to {end.isoformat()}."
        ), frequency
    return frame, frequency
