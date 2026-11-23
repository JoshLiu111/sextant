"""Operator view of AI usage (story 95): calls, tokens and estimated cost per user per day.

Only accounts listed in ``OPERATOR_EMAILS`` may read it; everyone else gets a 404,
so the view's existence (and every user's email) stays hidden.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.auth_helpers import bearer, sign_in
from tests.test_ai_explain import OPTIONS, StubModel

USAGE = "/api/compute/operator/ai-usage"
ACCESS = "/api/compute/operator/access"
OPERATOR = "ops@example.test"


@pytest.fixture
def model(client: TestClient) -> StubModel:
    stub = StubModel(input_tokens=1000, output_tokens=200)
    client.app.state.ai_model = stub
    return stub


@pytest.fixture
def operator(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("OPERATOR_EMAILS", f"someone-else@example.test, {OPERATOR.upper()}")
    return sign_in(client, "google-sub-ops", email=OPERATOR, name="Ops")


def user_id(client: TestClient, token: str) -> str:
    return client.get("/api/compute/me", headers=bearer(token)).json()["id"]


def explain(client: TestClient, token: str) -> None:
    response = client.post("/api/compute/ai/explain/options", json=OPTIONS, headers=bearer(token))
    assert response.status_code == 200, response.text


def log_usage(db_url: str, uid: str, days_ago: int, input_tokens: int | None, output_tokens: int | None) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(
            "INSERT INTO ai_usage (user_id, tool, input_tokens, output_tokens, created_at)"
            " VALUES (%s, 'options', %s, %s, now() - make_interval(days => %s))",
            (uid, input_tokens, output_tokens, days_ago),
        )


def test_visitors_and_non_operators_get_a_404_that_reveals_nothing(client, monkeypatch, model):
    monkeypatch.setenv("OPERATOR_EMAILS", OPERATOR)
    alice = sign_in(client)
    explain(client, alice)

    for headers in ({}, bearer(alice), bearer("not-a-session")):
        for path in (USAGE, ACCESS):
            response = client.get(path, headers=headers)
            assert response.status_code == 404, (path, headers)
            assert "alice@example.test" not in response.text
            assert response.json()["error"]["code"] == "not_found"


def test_without_any_operator_configured_nobody_gets_in(client, monkeypatch):
    monkeypatch.delenv("OPERATOR_EMAILS", raising=False)
    token = sign_in(client, "google-sub-ops", email=OPERATOR)

    assert client.get(USAGE, headers=bearer(token)).status_code == 404
    assert client.get(ACCESS, headers=bearer(token)).status_code == 404


def test_an_operator_is_let_in(client, operator):
    assert client.get(ACCESS, headers=bearer(operator)).status_code == 204
    assert client.get(USAGE, headers=bearer(operator)).status_code == 200


@pytest.fixture
def prices(monkeypatch: pytest.MonkeyPatch) -> None:
    # $3 per million input tokens, $15 per million output tokens.
    monkeypatch.setenv("AI_PRICE_INPUT_USD_PER_MTOK", "3")
    monkeypatch.setenv("AI_PRICE_OUTPUT_USD_PER_MTOK", "15")


def utc_day(days_ago: int) -> str:
    return (datetime.now(UTC).date() - timedelta(days=days_ago)).isoformat()


def test_totals_per_user_and_per_day_match_the_usage_log(client, model, operator, prices, db_url):
    alice = sign_in(client)
    bob = sign_in(client, "google-sub-bob", email="bob@example.test", name="Bob")
    alice_id, bob_id = user_id(client, alice), user_id(client, bob)
    explain(client, alice)
    explain(client, alice)  # today: 2 calls x (1000 in, 200 out)
    log_usage(db_url, alice_id, 1, 5000, 1000)  # yesterday
    log_usage(db_url, bob_id, 0, None, None)  # in flight: counts as a call, no tokens yet
    log_usage(db_url, bob_id, 45, 9999, 9999)  # outside the default 30-day window

    body = client.get(USAGE, headers=bearer(operator)).json()

    assert body["pricing"] == {"input_usd_per_mtok": 3.0, "output_usd_per_mtok": 15.0}
    assert (body["since"], body["until"]) == (utc_day(29), utc_day(0))
    days = [
        (d["day"], d["email"], d["calls"], d["input_tokens"], d["output_tokens"], d["estimated_cost_usd"])
        for d in body["days"]
    ]
    # 2000 x $3/M + 400 x $15/M = $0.012; 5000 x $3/M + 1000 x $15/M = $0.03.
    assert days == [
        (utc_day(0), "alice@example.test", 2, 2000, 400, 0.012),
        (utc_day(0), "bob@example.test", 1, 0, 0, 0.0),
        (utc_day(1), "alice@example.test", 1, 5000, 1000, 0.03),
    ]
    users = [
        (u["email"], u["name"], u["calls"], u["input_tokens"], u["output_tokens"], u["estimated_cost_usd"])
        for u in body["users"]
    ]
    assert users == [
        ("alice@example.test", "Alice", 3, 7000, 1400, 0.042),
        ("bob@example.test", "Bob", 1, 0, 0, 0.0),
    ]
    assert body["totals"] == {"calls": 4, "input_tokens": 7000, "output_tokens": 1400, "estimated_cost_usd": 0.042}


def test_the_window_is_the_last_n_utc_days_including_today(client, operator, db_url):
    alice = sign_in(client)
    for days_ago in (0, 1, 2):
        log_usage(db_url, user_id(client, alice), days_ago, 100, 10)

    body = client.get(USAGE, params={"days": 2}, headers=bearer(operator)).json()

    assert (body["since"], body["until"]) == (utc_day(1), utc_day(0))
    assert [d["day"] for d in body["days"]] == [utc_day(0), utc_day(1)]
    assert body["totals"]["calls"] == 2
    assert client.get(USAGE, params={"days": 0}, headers=bearer(operator)).status_code == 422


def test_without_configured_prices_the_cost_uses_the_default_model_list_price(client, operator, db_url, monkeypatch):
    monkeypatch.delenv("AI_PRICE_INPUT_USD_PER_MTOK", raising=False)
    monkeypatch.delenv("AI_PRICE_OUTPUT_USD_PER_MTOK", raising=False)
    log_usage(db_url, user_id(client, sign_in(client)), 0, 1_000_000, 1_000_000)

    body = client.get(USAGE, headers=bearer(operator)).json()

    # Claude Haiku list price: $1 per million input tokens, $5 per million output tokens.
    assert body["pricing"] == {"input_usd_per_mtok": 1.0, "output_usd_per_mtok": 5.0}
    assert body["totals"]["estimated_cost_usd"] == 6.0


def test_an_empty_log_gives_zero_totals(client, operator):
    body = client.get(USAGE, headers=bearer(operator)).json()

    assert body["users"] == [] and body["days"] == []
    assert body["totals"] == {"calls": 0, "input_tokens": 0, "output_tokens": 0, "estimated_cost_usd": 0.0}
