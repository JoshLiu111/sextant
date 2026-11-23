import pytest
from fastapi.testclient import TestClient

from sextant_compute.app import create_app
from tests.auth_helpers import bearer, login_assertion, sign_in


def test_signed_in_user_can_read_their_identity(client):
    token = sign_in(client, "google-sub-alice", email="alice@example.test", name="Alice")

    response = client.get("/api/compute/me", headers=bearer(token))

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "alice@example.test"
    assert body["name"] == "Alice"
    assert body["id"]


def test_session_cookie_identifies_the_user_like_a_bearer_token(client):
    token = sign_in(client)

    client.cookies.set("sextant_session", token)
    response = client.get("/api/compute/me")

    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.test"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer not-a-real-session"}])
def test_anonymous_or_unknown_session_is_401(client, headers):
    assert client.get("/api/compute/me", headers=headers).status_code == 401


def test_sign_out_ends_the_session(client):
    token = sign_in(client)

    assert client.delete("/api/compute/auth/session", headers=bearer(token)).status_code == 204

    assert client.get("/api/compute/me", headers=bearer(token)).status_code == 401


def test_sign_out_only_ends_that_session(client):
    laptop = sign_in(client)
    phone = sign_in(client)

    client.delete("/api/compute/auth/session", headers=bearer(laptop))

    assert client.get("/api/compute/me", headers=bearer(phone)).status_code == 200


def test_signing_in_again_keeps_the_same_account_and_refreshes_the_profile(client):
    first = client.get("/api/compute/me", headers=bearer(sign_in(client, name="Alice"))).json()
    second = client.get("/api/compute/me", headers=bearer(sign_in(client, name="Alice B."))).json()

    assert second["id"] == first["id"]
    assert second["name"] == "Alice B."


def test_different_google_accounts_are_different_users(client):
    alice = client.get("/api/compute/me", headers=bearer(sign_in(client, "sub-a"))).json()
    bob = client.get(
        "/api/compute/me", headers=bearer(sign_in(client, "sub-b", email="bob@example.test"))
    ).json()

    assert alice["id"] != bob["id"]


@pytest.mark.parametrize(
    "assertion",
    [
        login_assertion(secret="a-different-secret-that-is-long-enough-123"),
        login_assertion(expires_in=-10),
        login_assertion(audience="someone-else"),
        login_assertion(expires_in=24 * 3600),
        "not-a-jwt",
    ],
    ids=["wrong-secret", "expired", "wrong-audience", "too-long-lived", "garbage"],
)
def test_sign_in_rejects_assertions_not_freshly_signed_by_the_web_app(client, assertion):
    response = client.post("/api/compute/auth/sessions", json={"assertion": assertion})

    assert response.status_code == 401


def test_deleting_the_account_signs_out_every_session(client):
    laptop = sign_in(client)
    phone = sign_in(client)

    assert client.delete("/api/compute/me", headers=bearer(laptop)).status_code == 204

    assert client.get("/api/compute/me", headers=bearer(laptop)).status_code == 401
    assert client.get("/api/compute/me", headers=bearer(phone)).status_code == 401


def test_signing_in_after_deletion_starts_a_new_empty_account(client):
    token = sign_in(client)
    old_id = client.get("/api/compute/me", headers=bearer(token)).json()["id"]
    client.delete("/api/compute/me", headers=bearer(token))

    new_id = client.get("/api/compute/me", headers=bearer(sign_in(client))).json()["id"]

    assert new_id != old_id


def test_deleting_requires_a_signed_in_user(client):
    assert client.delete("/api/compute/me").status_code == 401


def test_without_a_database_tools_still_work_and_accounts_are_unavailable(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SESSION_SECRET", "x" * 40)
    with TestClient(create_app()) as anon:
        assert anon.get("/api/compute/health").status_code == 200
        assert anon.get("/api/compute/me", headers=bearer("whatever")).status_code == 401
        response = anon.post(
            "/api/compute/auth/sessions",
            json={"assertion": login_assertion(secret="x" * 40)},
        )
        assert response.status_code == 503
