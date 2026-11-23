"""Test helpers that play the web app's part of the sign-in handshake."""

from __future__ import annotations

import time

import jwt
from fastapi.testclient import TestClient

TEST_SESSION_SECRET = "test-session-secret-not-for-production-0123456789"


def login_assertion(
    google_sub: str = "google-sub-alice",
    email: str = "alice@example.test",
    name: str | None = "Alice",
    *,
    secret: str = TEST_SESSION_SECRET,
    expires_in: int = 60,
    audience: str = "sextant-compute",
) -> str:
    """What apps/web signs after it has verified a Google ID token."""
    now = int(time.time())
    claims = {
        "iss": "sextant-web",
        "aud": audience,
        "sub": google_sub,
        "email": email,
        "name": name,
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def sign_in(client: TestClient, google_sub: str = "google-sub-alice", **kwargs) -> str:
    """Sign in and return the session token (the value of the session cookie)."""
    response = client.post(
        "/api/compute/auth/sessions",
        json={"assertion": login_assertion(google_sub, **kwargs)},
    )
    assert response.status_code == 201, response.text
    return response.json()["token"]


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
