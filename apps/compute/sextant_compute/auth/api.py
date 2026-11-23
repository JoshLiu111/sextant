from __future__ import annotations

import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from sextant_compute.auth import sessions
from sextant_compute.auth.deps import CurrentUser, get_db, session_token
from sextant_compute.db import Database, DatabaseNotConfigured
from sextant_compute.errors import ApiError

router = APIRouter(tags=["auth"])

Db = Annotated[Database, Depends(get_db)]

log = logging.getLogger(__name__)


class UserOut(BaseModel):
    id: UUID
    email: str
    name: str | None


class SessionIn(BaseModel):
    assertion: str


class SessionOut(BaseModel):
    token: str
    expires_at: datetime
    user: UserOut


def _unavailable(reason: str) -> ApiError:
    """503 for a server misconfiguration. The reason goes to the logs, never to the visitor."""
    log.error("Accounts unavailable: %s", reason)
    return ApiError(503, "accounts_unavailable", "Sign-in is temporarily unavailable. Please try again later.")


def _invalid_assertion() -> ApiError:
    return ApiError(401, "unauthorized", "Sign-in failed. Please try again.")


@router.post("/auth/sessions", status_code=status.HTTP_201_CREATED, response_model=SessionOut)
def create_session(body: SessionIn, db: Db) -> SessionOut:
    """Exchange a login assertion signed by apps/web for a session token."""
    try:
        claims = sessions.verify_login_assertion(body.assertion)
    except sessions.SecretNotConfigured as exc:
        raise _unavailable(str(exc)) from exc
    except sessions.InvalidAssertion as exc:
        raise _invalid_assertion() from exc
    try:
        with db.connection() as conn:
            token, expires_at, user = sessions.create_session(conn, claims)
    except DatabaseNotConfigured as exc:
        raise _unavailable(str(exc)) from exc
    except sessions.InvalidAssertion as exc:
        raise _invalid_assertion() from exc
    return SessionOut(token=token, expires_at=expires_at, user=UserOut(**user))


@router.delete("/auth/session", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(request: Request, db: Db) -> Response:
    """End the current session. Idempotent: signed-out callers get 204 too."""
    token = session_token(request)
    if token is not None and db.configured:
        with db.connection() as conn:
            sessions.delete_session(conn, token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserOut)
def me(user: CurrentUser) -> UserOut:
    return UserOut(id=user.id, email=user.email, name=user.name)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_account(user: CurrentUser, db: Db) -> Response:
    """Permanently delete the account and, by cascade, all user-owned rows."""
    with db.connection() as conn:
        sessions.delete_user(conn, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
