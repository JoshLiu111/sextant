"""Settings: a signed-in user's own Tiingo key (save, validate, replace, delete).

Tiingo is faked with an ``httpx.MockTransport`` that answers like the real
``GET /api/test`` endpoint (checked 2026-11-22): always HTTP 200, with a message
saying whether the token was accepted.
"""

from __future__ import annotations

import httpx
import psycopg
import pytest

from sextant_compute.data.service import Ctx
from sextant_compute.data.tiingo import TiingoAdapter
from sextant_compute.keys.api import get_tiingo
from tests.auth_helpers import bearer, sign_in

VALID_KEY = "0123456789abcdef0123456789abcdef0123abcd"
OTHER_VALID_KEY = "fedcba9876543210fedcba9876543210fedc9876"
TEST_KEY_SECRET = "test-provider-key-secret-not-for-production-0123456789"


class FakeTiingo:
    """Accepts the tokens in ``valid``; ``down`` makes it answer 503."""

    def __init__(self, valid: set[str]) -> None:
        self.valid = valid
        self.down = False
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.down:
            return httpx.Response(503, text="Service Unavailable")
        if request.url.path != "/api/test":
            return httpx.Response(404, json={"detail": "Not found."})
        auth = request.headers.get("authorization", "")
        if not auth:
            return httpx.Response(200, json={"message": "'AUTHORIZATION header' was not set"})
        token = auth.removeprefix("Token ")
        if token in self.valid:
            return httpx.Response(200, json={"message": "You successfully sent a request"})
        return httpx.Response(200, json={"message": "Auth Token was not correct"})


@pytest.fixture
def tiingo(client, monkeypatch) -> FakeTiingo:
    monkeypatch.setenv("PROVIDER_KEY_SECRET", TEST_KEY_SECRET)
    fake = FakeTiingo({VALID_KEY, OTHER_VALID_KEY})
    adapter = TiingoAdapter(base_url="https://tiingo.test", transport=httpx.MockTransport(fake.handler))
    client.app.dependency_overrides[get_tiingo] = lambda: adapter
    return fake


@pytest.fixture
def alice(client) -> dict[str, str]:
    return bearer(sign_in(client, "sub-alice", email="alice@example.test"))


def save(client, headers, key: str):
    return client.put("/api/compute/keys/tiingo", json={"key": key}, headers=headers)


def test_a_valid_key_is_saved_and_only_a_masked_hint_comes_back(client, tiingo, alice):
    saved = save(client, alice, VALID_KEY)

    assert saved.status_code == 200, saved.text
    assert saved.json()["provider"] == "tiingo"
    assert saved.json()["hint"] == "abcd"
    listed = client.get("/api/compute/keys", headers=alice)
    assert listed.status_code == 200
    assert [k["provider"] for k in listed.json()] == ["tiingo"]
    assert listed.json()[0]["hint"] == "abcd"
    for response in (saved, listed):
        assert VALID_KEY not in response.text
    assert tiingo.requests[0].headers["authorization"] == f"Token {VALID_KEY}"


def test_a_key_tiingo_rejects_shows_key_is_invalid_and_stores_nothing(client, tiingo, alice):
    response = save(client, alice, "not-a-real-tiingo-key")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_key"
    assert "key is invalid" in error["fields"]["key"]
    assert client.get("/api/compute/keys", headers=alice).json() == []


def test_a_tiingo_outage_shows_source_unavailable_and_stores_nothing(client, tiingo, alice):
    tiingo.down = True

    response = save(client, alice, VALID_KEY)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"
    assert "temporarily unavailable" in response.json()["error"]["message"]
    assert client.get("/api/compute/keys", headers=alice).json() == []


def test_a_rejected_replacement_keeps_the_key_already_saved(client, tiingo, alice):
    save(client, alice, VALID_KEY)

    assert save(client, alice, "wrong-key-0000").status_code == 422

    assert [k["hint"] for k in client.get("/api/compute/keys", headers=alice).json()] == ["abcd"]


@pytest.fixture
def ctx_keys(client):
    """GET it to see the ``ctx.keys`` a data endpoint would get on this request."""
    path = "/api/compute/test-only/ctx-keys"

    @client.app.get(path)
    def probe(ctx: Ctx) -> dict[str, str]:
        return dict(ctx.keys)

    return lambda headers=None: client.get(path, headers=headers).json()


def test_replacing_and_deleting_a_key_take_effect_on_the_next_request(client, tiingo, alice, ctx_keys):
    assert ctx_keys(alice) == {}

    save(client, alice, VALID_KEY)
    assert ctx_keys(alice) == {"tiingo": VALID_KEY}

    replaced = save(client, alice, OTHER_VALID_KEY)
    assert replaced.json()["hint"] == "9876"
    assert ctx_keys(alice) == {"tiingo": OTHER_VALID_KEY}
    assert [k["hint"] for k in client.get("/api/compute/keys", headers=alice).json()] == ["9876"]

    assert client.delete("/api/compute/keys/tiingo", headers=alice).status_code == 204
    assert ctx_keys(alice) == {}
    assert client.get("/api/compute/keys", headers=alice).json() == []


def test_anonymous_visitors_have_no_keys_and_cannot_save_one(client, tiingo, ctx_keys):
    assert ctx_keys() == {}
    assert client.get("/api/compute/keys").status_code == 401
    assert save(client, {}, VALID_KEY).status_code == 401
    assert client.delete("/api/compute/keys/tiingo").status_code == 401
    assert tiingo.requests == []


def test_one_users_key_is_never_seen_or_removed_by_another_user(client, tiingo, alice, ctx_keys):
    bob = bearer(sign_in(client, "sub-bob", email="bob@example.test"))
    save(client, alice, VALID_KEY)

    assert client.get("/api/compute/keys", headers=bob).json() == []
    assert ctx_keys(bob) == {}
    assert client.delete("/api/compute/keys/tiingo", headers=bob).status_code == 204
    assert ctx_keys(alice) == {"tiingo": VALID_KEY}


def test_the_key_is_encrypted_at_rest(client, tiingo, alice, db_url):
    save(client, alice, VALID_KEY)

    with psycopg.connect(db_url) as conn:
        rows = conn.execute("SELECT * FROM provider_keys").fetchall()
    assert len(rows) == 1
    assert VALID_KEY.encode() not in b"".join(
        bytes(v) if isinstance(v, (bytes, memoryview)) else str(v).encode() for v in rows[0]
    )


def test_a_key_saved_under_another_secret_reads_as_absent(client, tiingo, alice, ctx_keys, monkeypatch):
    save(client, alice, VALID_KEY)

    monkeypatch.setenv("PROVIDER_KEY_SECRET", "a-rotated-secret-that-is-also-long-enough-0123")

    assert ctx_keys(alice) == {}


def test_without_the_encryption_secret_nothing_is_saved(client, tiingo, alice, monkeypatch):
    monkeypatch.delenv("PROVIDER_KEY_SECRET")

    response = save(client, alice, VALID_KEY)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "keys_not_configured"
    assert client.get("/api/compute/keys", headers=alice).json() == []


def test_deleting_the_account_deletes_the_key(client, tiingo, alice, db_url):
    save(client, alice, VALID_KEY)

    assert client.delete("/api/compute/me", headers=alice).status_code == 204

    with psycopg.connect(db_url) as conn:
        assert conn.execute("SELECT count(*) FROM provider_keys").fetchone() == (0,)


@pytest.mark.parametrize("key", ["", "   ", "has a space", "x" * 201])
def test_a_malformed_key_is_rejected_inline_without_asking_tiingo(client, tiingo, alice, key):
    response = save(client, alice, key)

    assert response.status_code == 422
    assert "key" in response.json()["error"]["fields"]
    assert tiingo.requests == []
