from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Request

from sextant_compute.auth import sessions
from sextant_compute.db import Database, DatabaseNotConfigured
from sextant_compute.errors import ApiError

SESSION_COOKIE = "sextant_session"


@dataclass(frozen=True)
class User:
    id: UUID
    email: str
    name: str | None


def get_db(request: Request) -> Database:
    return request.app.state.db


def session_token(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    scheme, _, value = header.partition(" ")
    if scheme.lower() == "bearer" and value.strip():
        return value.strip()
    return request.cookies.get(SESSION_COOKIE) or None


def _optional_user(request: Request, db: Annotated[Database, Depends(get_db)]) -> User | None:
    token = session_token(request)
    if token is None:
        return None
    try:
        with db.connection() as conn:
            row = sessions.user_for_token(conn, token)
    except DatabaseNotConfigured:
        return None
    return User(id=row["id"], email=row["email"], name=row["name"]) if row else None


def _required_user(user: Annotated[User | None, Depends(_optional_user)]) -> User:
    if user is None:
        raise ApiError(401, "unauthorized", "Sign in required.")
    return user


OptionalUser = Annotated[User | None, Depends(_optional_user)]
CurrentUser = Annotated[User, Depends(_required_user)]
