"""Settings: a signed-in user's own FMP key, next to (and independent of) a Tiingo key.

FMP is ``FakeFmp`` (tests/fmp_fixtures.py): a bad key answers 401 the way the
real stable API does. The shared rules (input validation, encryption at rest,
rotated secret, account deletion) are covered for Tiingo in
test_provider_keys.py; they don't depend on the provider.
"""

from __future__ import annotations

import pytest

from fmp_fixtures import FakeFmp
from sextant_compute.data.service import Ctx
from sextant_compute.keys.api import get_fmp, get_tiingo
from tests.auth_helpers import bearer, sign_in
from tiingo_fixtures import FakeTiingo

FMP_KEY = "fmpkey0123456789abcdef0123456789wxyz"
OTHER_FMP_KEY = "fmpkey9876543210fedcba9876543210qrst"
TIINGO_KEY = "0123456789abcdef0123456789abcdef0123abcd"
TEST_KEY_SECRET = "test-provider-key-secret-not-for-production-0123456789"


@pytest.fixture
def fmp(client, monkeypatch) -> FakeFmp:
    monkeypatch.setenv("PROVIDER_KEY_SECRET", TEST_KEY_SECRET)
    fake = FakeFmp({FMP_KEY, OTHER_FMP_KEY})
    adapter = fake.adapter()
    client.app.dependency_overrides[get_fmp] = lambda: adapter
    return fake


@pytest.fixture
def tiingo(client) -> FakeTiingo:
    fake = FakeTiingo({TIINGO_KEY})
    adapter = fake.adapter()
    client.app.dependency_overrides[get_tiingo] = lambda: adapter
    return fake


@pytest.fixture
def alice(client) -> dict[str, str]:
    return bearer(sign_in(client, "sub-alice", email="alice@example.test"))


@pytest.fixture
def ctx_keys(client):
    path = "/api/compute/test-only/ctx-keys"

    @client.app.get(path)
    def probe(ctx: Ctx) -> dict[str, str]:
        return dict(ctx.keys)

    return lambda headers=None: client.get(path, headers=headers).json()


def save(client, headers, provider: str, key: str):
    return client.put(f"/api/compute/keys/{provider}", json={"key": key}, headers=headers)


def listed(client, headers) -> dict[str, str]:
    return {k["provider"]: k["hint"] for k in client.get("/api/compute/keys", headers=headers).json()}


def test_an_fmp_key_is_checked_with_fmp_saved_replaced_and_deleted(client, fmp, tiingo, alice, ctx_keys):
    saved = save(client, alice, "fmp", FMP_KEY)

    assert saved.status_code == 200, saved.text
    assert saved.json()["provider"] == "fmp"
    assert saved.json()["hint"] == "wxyz"
    assert FMP_KEY not in saved.text
    assert fmp.requests[0].headers["apikey"] == FMP_KEY
    assert tiingo.requests == []  # the FMP key was checked with FMP only
    assert listed(client, alice) == {"fmp": "wxyz"}
    assert ctx_keys(alice) == {"fmp": FMP_KEY}

    assert save(client, alice, "fmp", OTHER_FMP_KEY).json()["hint"] == "qrst"
    assert ctx_keys(alice) == {"fmp": OTHER_FMP_KEY}

    assert client.delete("/api/compute/keys/fmp", headers=alice).status_code == 204
    assert ctx_keys(alice) == {}
    assert listed(client, alice) == {}


def test_a_key_fmp_rejects_shows_key_is_invalid_and_keeps_the_earlier_key(client, fmp, alice):
    save(client, alice, "fmp", FMP_KEY)

    response = save(client, alice, "fmp", "not-a-real-fmp-key")

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_key"
    assert "key is invalid: FMP rejected it" in error["fields"]["key"]
    assert listed(client, alice) == {"fmp": "wxyz"}


def test_an_fmp_outage_shows_source_unavailable_and_stores_nothing(client, fmp, alice):
    fmp.status = 503

    response = save(client, alice, "fmp", FMP_KEY)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "source_unavailable"
    assert listed(client, alice) == {}


def test_tiingo_and_fmp_keys_live_side_by_side(client, fmp, tiingo, alice, ctx_keys):
    assert save(client, alice, "tiingo", TIINGO_KEY).status_code == 200
    assert save(client, alice, "fmp", FMP_KEY).status_code == 200

    assert listed(client, alice) == {"tiingo": "abcd", "fmp": "wxyz"}
    assert ctx_keys(alice) == {"tiingo": TIINGO_KEY, "fmp": FMP_KEY}

    assert client.delete("/api/compute/keys/fmp", headers=alice).status_code == 204
    assert ctx_keys(alice) == {"tiingo": TIINGO_KEY}


def test_one_users_fmp_key_is_never_seen_or_removed_by_another_user(client, fmp, alice, ctx_keys):
    bob = bearer(sign_in(client, "sub-bob", email="bob@example.test"))
    save(client, alice, "fmp", FMP_KEY)

    assert listed(client, bob) == {}
    assert ctx_keys(bob) == {}
    assert client.delete("/api/compute/keys/fmp", headers=bob).status_code == 204
    assert ctx_keys(alice) == {"fmp": FMP_KEY}


def test_anonymous_visitors_cannot_save_an_fmp_key(client, fmp):
    assert save(client, {}, "fmp", FMP_KEY).status_code == 401
    assert fmp.requests == []
