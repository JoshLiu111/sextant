"""Session storage and the web-to-compute login assertion.

Sign-in handshake: apps/web runs Google OIDC and verifies the ID token, then
signs a short-lived HS256 *login assertion* with ``SESSION_SECRET``
(iss=sextant-web, aud=sextant-compute, sub=Google subject, email, name, and a
random jti) that lives at most 60 seconds. Compute verifies it, records the jti
so the assertion cannot be replayed, upserts the user and issues an opaque
session token.
Only holders of SESSION_SECRET can mint assertions, so the endpoint is safe
to expose publicly under /api/compute.
"""

from __future__ import annotations

import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta

import jwt
import psycopg

SESSION_LIFETIME = timedelta(days=30)
ASSERTION_MAX_AGE = timedelta(seconds=60)  # ADR 0001
MIN_SECRET_LENGTH = 32


class InvalidAssertion(ValueError):
    pass


class SecretNotConfigured(RuntimeError):
    pass


def session_secret() -> str:
    secret = os.environ.get("SESSION_SECRET", "")
    if len(secret) < MIN_SECRET_LENGTH:
        raise SecretNotConfigured(f"SESSION_SECRET must be at least {MIN_SECRET_LENGTH} characters")
    return secret


def verify_login_assertion(assertion: str) -> dict:
    try:
        claims = jwt.decode(
            assertion,
            session_secret(),
            algorithms=["HS256"],
            audience="sextant-compute",
            issuer="sextant-web",
            options={"require": ["exp", "iat", "sub", "email", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise InvalidAssertion(str(exc)) from exc
    if claims["exp"] - claims["iat"] > ASSERTION_MAX_AGE.total_seconds():
        raise InvalidAssertion("assertion lifetime too long")
    return claims


def _hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def _consume_assertion(conn: psycopg.Connection, claims: dict) -> None:
    """Record the assertion's jti; raise InvalidAssertion if it was already used."""
    conn.execute("DELETE FROM used_login_assertions WHERE expires_at < now()")
    fresh = conn.execute(
        """
        INSERT INTO used_login_assertions (jti, expires_at)
        VALUES (%s, to_timestamp(%s))
        ON CONFLICT (jti) DO NOTHING
        RETURNING jti
        """,
        (str(claims["jti"]), claims["exp"]),
    ).fetchone()
    if fresh is None:
        raise InvalidAssertion("assertion already used")


def create_session(conn: psycopg.Connection, claims: dict) -> tuple[str, datetime, dict]:
    """Open a session for verified ``claims``. Raises InvalidAssertion on a replayed jti."""
    _consume_assertion(conn, claims)
    user = conn.execute(
        """
        INSERT INTO users (google_sub, email, name)
        VALUES (%(sub)s, %(email)s, %(name)s)
        ON CONFLICT (google_sub) DO UPDATE
           SET email = EXCLUDED.email, name = EXCLUDED.name, last_login_at = now()
        RETURNING id, email, name
        """,
        {"sub": claims["sub"], "email": claims["email"], "name": claims.get("name")},
    ).fetchone()
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(UTC) + SESSION_LIFETIME
    conn.execute(
        "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (_hash(token), user["id"], expires_at),
    )
    return token, expires_at, user


def user_for_token(conn: psycopg.Connection, token: str) -> dict | None:
    return conn.execute(
        """
        SELECT u.id, u.email, u.name
          FROM sessions s JOIN users u ON u.id = s.user_id
         WHERE s.token_hash = %s AND s.expires_at > now()
        """,
        (_hash(token),),
    ).fetchone()


def delete_session(conn: psycopg.Connection, token: str) -> None:
    conn.execute("DELETE FROM sessions WHERE token_hash = %s", (_hash(token),))


def delete_user(conn: psycopg.Connection, user_id) -> None:
    """Delete the account. ON DELETE CASCADE removes every user-owned row."""
    conn.execute("DELETE FROM users WHERE id = %s", (user_id,))
